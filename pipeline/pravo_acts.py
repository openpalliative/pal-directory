import argparse
import datetime as dt
import json
import re
import sys
from pathlib import Path

from pipeline import net, territories
from pipeline.common import load_regions, read_json, today, write_csv, write_json

WORDS = ("паллиативной", "паллиативную", "паллиативная", "паллиативных", "хоспис")
PAGE_SIZE = 100
ACTS = Path("data/pravo/region-acts.csv")
SNAPSHOT = Path("data/snapshots/pravo-acts.json")
CACHE = Path("raw/cache/pravo")
DOC_URL = "http://publication.pravo.gov.ru/document/{eo}"
FIELDS = ["id", "region_id", "act_type", "authority", "number", "doc_date", "publish_date", "title", "pages", "url",
          "kind", "words", "retrieved_at"]
ACT_TYPES = ("Постановление", "Распоряжение", "Приказ", "Указ", "Закон", "Решение", "Совместный приказ")
KINDS = [
    ("reimbursement", r"возмещени\w*\s+(?:[\w-]+\s+){0,4}субъекту\s+российской|межрегиональн\w*\s+(соглашени|расч)"
                      r"|возмещени\w*\s+затрат,\s+связанных\s+с\s+оказанием\s+медицинской\s+помощи\s+при\s+заболевани"),
    ("routing", r"маршрутизац|маршрут\w*\s+оказания"),
    ("program", r"программ"),
    ("subsidy", r"субсиди|гранта?\b|грантов"),
    ("nutrition", r"питани"),
    ("devices", r"медицинск\w*\s+издели|изделий\s+медицинского|кислородн"),
    ("organization", r"об\s+оказании|об\s+организации|организации\s+оказания|порядк|совершенствовани|правил"
                     r"|перечн|положени|хоспис|отделени|кабинет|выездн|создани|регламент|взаимодейств"),
]


class PravoFormatError(Exception):
    pass


def kind_of(title: str) -> str:
    low = title.lower().replace("ё", "е")
    for kind, rx in KINDS:
        if re.search(rx, low):
            return kind
    return "other"


def heading_of(complex_name: str) -> tuple[str, str]:
    first = re.split(r"\s+от\s+\d{2}\.\d{2}\.\d{4}", complex_name.split("\n")[0], maxsplit=1)[0].strip()
    for t in sorted(ACT_TYPES, key=len, reverse=True):
        if first.startswith(t + " "):
            return t, first[len(t) + 1:].strip()
    return "", first


def api_json(get, path: str, params: list[tuple[str, str]], record: Path | None, name: str):
    body, _ = get(path, params)
    try:
        data = json.loads(body.decode("utf-8"))
    except (UnicodeDecodeError, ValueError) as e:
        raise PravoFormatError(f"{path}: ответ не JSON: {e}") from e
    if record is not None:
        record.mkdir(parents=True, exist_ok=True)
        (record / name).write_text(json.dumps(data, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    return data


def blocks(get, record: Path | None = None) -> list[dict]:
    data = api_json(get, "/api/PublicBlocks", [("parent", "subjects")], record, "public-blocks-subjects.json")
    if not isinstance(data, list) or not all("code" in b and "name" in b for b in data):
        raise PravoFormatError("/api/PublicBlocks?parent=subjects: ожидался список блоков с code и name")
    out = [{"code": b["code"], "name": b["name"]} for b in data if territories.block_allowed(b["code"])]
    if record is not None:
        (record / "public-blocks-subjects.json").write_text(json.dumps(out, ensure_ascii=False, indent=1) + "\n",
                                                            encoding="utf-8")
    return out


def search(get, block: str, word: str, record: Path | None = None) -> list[dict]:
    if not territories.block_allowed(block):
        raise net.HostNotAllowed(f"блок {block} в списке исключённых, запросы к нему не делаются")
    items, index, pages = [], 1, 1
    while index <= pages:
        params = [("Block", block), ("Name", word), ("PageSize", str(PAGE_SIZE)), ("Index", str(index))]
        data = api_json(get, "/api/Documents", params, record, f"{block}-{word}-{index}.json")
        if not isinstance(data, dict) or "items" not in data:
            raise PravoFormatError(f"/api/Documents {block} «{word}»: в ответе нет items")
        items += data["items"] or []
        pages = int(data.get("pagesTotalCount") or 1)
        index += 1
    return items


def record_of(doc: dict, region_id: str, retrieved: str) -> dict:
    eo = doc["eoNumber"]
    act_type, authority = heading_of(doc.get("complexName") or doc.get("title") or "")
    title = re.sub(r"\s+", " ", doc.get("name") or "").strip()
    return {
        "id": eo, "region_id": region_id, "act_type": act_type, "authority": authority,
        "number": (doc.get("number") or "").strip(), "doc_date": (doc.get("documentDate") or "")[:10],
        "publish_date": (doc.get("publishDateShort") or "")[:10], "title": title,
        "pages": int(doc.get("pagesCount") or 0), "url": DOC_URL.format(eo=eo), "kind": kind_of(title),
        "words": [], "retrieved_at": retrieved,
    }


def collect(get, regions: list[dict], *, only: set[str] | None = None, record: Path | None = None,
            retrieved: str | None = None, progress=None) -> dict:
    retrieved = retrieved or today()
    by_block = {r["pravo_block"]: r for r in regions if r.get("pravo_block")}
    found_blocks = blocks(get, record)
    names = {b["code"]: b["name"] for b in found_blocks}
    missing = sorted(set(by_block) - set(names))
    if missing:
        raise PravoFormatError(f"На портале нет блоков {', '.join(missing)} из data/regions.csv (поле pravo_block)")
    acts: dict[str, dict] = {}
    mismatched, queries, per_block = [], 0, {}
    for code in sorted(by_block):
        if only and code not in only:
            continue
        region = by_block[code]
        per_block[code] = 0
        for word in WORDS:
            queries += 1
            for doc in search(get, code, word, record):
                eo = str(doc.get("eoNumber") or "")
                if not re.fullmatch(r"\d{16}", eo) or eo[:2] != code[-2:] or not territories.eo_allowed(eo):
                    mismatched.append({"block": code, "eoNumber": eo})
                    continue
                if eo not in acts:
                    acts[eo] = record_of(doc, region["id"], retrieved)
                    per_block[code] += 1
                if word not in acts[eo]["words"]:
                    acts[eo]["words"].append(word)
            if progress:
                progress(code, word, len(acts))
    rows = sorted(acts.values(), key=lambda a: (a["region_id"], a["doc_date"], a["id"]), reverse=False)
    return {"acts": rows, "mismatched": mismatched, "queries": queries, "per_block": per_block,
            "block_names": names, "retrieved_at": retrieved}


def to_csv(rows: list[dict]) -> list[dict]:
    return [{**r, "words": ";".join(sorted(r["words"], key=WORDS.index))} for r in rows]


def run(root: Path, get, *, only: set[str] | None = None, record: Path | None = None, progress=None) -> dict:
    regions = load_regions(root)
    res = collect(get, regions, only=only, record=record, progress=progress)
    path = root / ACTS
    rows = res["acts"]
    if only and path.is_file():
        from opsite.data import read_csv
        keep = [{k: v for k, v in r.items() if k != "_line"} for r in read_csv(path)]
        done = {r["region_id"] for r in regions if r["pravo_block"] in only}
        old = [{**r, "pages": int(r["pages"] or 0), "words": r["words"].split(";") if r["words"] else []}
               for r in keep if r["region_id"] not in done]
        rows = sorted(old + rows, key=lambda a: (a["region_id"], a["doc_date"], a["id"]))
    write_csv(path, FIELDS, to_csv(rows))
    snap = read_json(root / SNAPSHOT, {}) or {}
    snap.update({"api": "http://publication.pravo.gov.ru/api/Documents", "words": list(WORDS),
                 "blocks_allowed": len(res["block_names"]), "blocks_denied": sorted(territories.PRAVO_BLOCKS),
                 "retrieved_at": res["retrieved_at"], "queries": res["queries"],
                 "acts": len(rows), "regions_with_acts": len({r["region_id"] for r in rows}),
                 "mismatched_eo": len(res["mismatched"])})
    write_json(root / SNAPSHOT, snap)
    return {**snap, "new": res}


def reclassify(root: Path) -> int:
    from opsite.data import read_csv
    path = root / ACTS
    rows = [{k: v for k, v in r.items() if k != "_line"} for r in read_csv(path)]
    changed = 0
    for r in rows:
        kind = kind_of(r["title"])
        changed += kind != r["kind"]
        r["kind"] = kind
    write_csv(path, FIELDS, rows)
    return changed


def live_get(path: str, params):
    return net.pravo_api(path, params)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="python -m pipeline.pravo_acts")
    ap.add_argument("--blocks", help="только эти блоки через запятую, например region39,region44")
    ap.add_argument("--record", type=Path, help="сохранить ответы API в папку")
    ap.add_argument("--quiet", action="store_true")
    ap.add_argument("--reclassify", action="store_true", help="пересчитать kind по словарю без сети")
    a = ap.parse_args(argv)
    if a.reclassify:
        print(f"Тип изменён у {reclassify(Path.cwd())} актов")
        return 0
    only = set(a.blocks.split(",")) if a.blocks else None
    record = a.record if a.record else Path.cwd() / CACHE
    start = dt.datetime.now()

    def progress(code, word, n):
        if not a.quiet:
            print(f"{code} «{word}»: актов всего {n}", flush=True)

    try:
        snap = run(Path.cwd(), live_get, only=only, record=record, progress=progress)
    except (net.SourceDown, PravoFormatError) as e:
        print(f"Ошибка: {e}", file=sys.stderr)
        return 1
    took = (dt.datetime.now() - start).seconds
    print(f"Актов {snap['acts']} в {snap['regions_with_acts']} регионах, запросов {snap['new']['queries']}, "
          f"не сошлось с блоком {snap['mismatched_eo']}, {took} с")
    return 0


if __name__ == "__main__":
    sys.exit(main())
