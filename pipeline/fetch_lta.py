import argparse
import csv
import hashlib
import io
import re
import sys
from pathlib import Path

from pipeline import net, territories
from pipeline.common import load_regions, read_json, today, write_csv, write_json

DATASET = "7710537160-lta"
META_URL = f"https://roszdravnadzor.gov.ru/opendata/{DATASET}/meta.csv"
LTA = Path("data/rzn/lta.csv")
SNAPSHOT = Path("data/snapshots/rzn-lta.json")
CACHE = Path("raw/cache/lta")
LTA_FIELDS = ["source_row", "region_ids", "name", "full_name", "postal_address", "email", "hours_text"]
DROPPED = ("head", "deputy_head", "functions")
REQUIRED = ("full_name", "name", "address", "mail", "work_mode") + DROPPED
EMAIL_OK = re.compile(r"[\w.+-]+@(?:[\w-]+\.)*roszdravnadzor\.gov\.ru")
MIN_ROWS = 60


class LtaFormatError(Exception):
    pass


def latest_data_url(meta: bytes) -> tuple[str, str]:
    text = meta.decode("cp1251")
    rows = list(csv.reader(io.StringIO(text)))
    links = sorted((r[0], r[1]) for r in rows if len(r) >= 2 and re.fullmatch(r"data-\d{8}-structure-\d{8}", r[0]))
    if not links:
        raise LtaFormatError("В meta.csv набора нет ссылок на data-ГГГГММДД-structure-ГГГГММДД")
    name, url = links[-1]
    if not url.startswith(f"https://roszdravnadzor.gov.ru/opendata/{DATASET}/"):
        raise LtaFormatError(f"Ссылка на данные ведёт не в набор {DATASET}: {url}")
    return name, url


def clean(value: str) -> str:
    return re.sub(r"\s+", " ", (value or "").replace("\xa0", " ")).strip()


def parts_of(name: str) -> list[str]:
    tail = name.split(" по ", 1)[1] if " по " in name else ""
    return [re.sub(r"^г\.\s*", "", p.strip()) for p in re.split(r",\s*|\s+и\s+", tail) if p.strip()]


def match_regions(name: str, regions: list[dict]) -> list[str]:
    parts = parts_of(name)
    dative = {re.sub(r"^г\.\s*", "", r["name_dative"]): r["id"] for r in regions if r["name_dative"]}
    return sorted(dative[p] for p in parts if p in dative)


def parse(body: bytes, regions: list[dict]) -> dict:
    try:
        text = body.decode("cp1251")
    except UnicodeDecodeError as e:
        raise LtaFormatError(f"Файл набора {DATASET} не в cp1251: {e}") from e
    reader = csv.DictReader(io.StringIO(text), delimiter=";")
    missing = [f for f in REQUIRED if f not in (reader.fieldnames or [])]
    if missing:
        raise LtaFormatError(f"В наборе {DATASET} нет столбцов: {', '.join(missing)}")
    rows, excluded, unmatched, bad_email = [], 0, [], 0
    for n, raw in enumerate(reader, start=2):
        for f in DROPPED:
            raw.pop(f, None)
        if territories.is_excluded(*raw.values()):
            excluded += 1
            continue
        name = clean(raw["name"])
        ids = match_regions(name, regions)
        if not ids:
            unmatched.append(name)
            continue
        mail = clean(raw["mail"])
        email = mail if EMAIL_OK.fullmatch(mail) else ""
        bad_email += bool(mail and not email)
        rows.append({"source_row": n, "region_ids": ";".join(ids), "name": name, "full_name": clean(raw["full_name"]),
                     "postal_address": clean(raw["address"]), "email": email, "hours_text": clean(raw["work_mode"])})
    if len(rows) < MIN_ROWS:
        raise LtaFormatError(f"В наборе {DATASET} разобрано {len(rows)} строк, ожидалось не меньше {MIN_ROWS}")
    if unmatched:
        raise LtaFormatError(f"Не сопоставлены с регионами (поле name_dative в data/regions.csv): {'; '.join(unmatched)}")
    covered = {i for r in rows for i in r["region_ids"].split(";")}
    return {"rows": rows, "excluded": excluded, "bad_email": bad_email, "covered": sorted(covered),
            "total": len(rows) + excluded}


def fetch(get=net.get) -> dict:
    meta, _ = get(META_URL)
    name, url = latest_data_url(meta)
    body, headers = get(url)
    modified = re.search(r"data-(\d{8})", name).group(1)
    return {"name": name, "url": url, "body": body, "sha256": hashlib.sha256(body).hexdigest(), "bytes": len(body),
            "modified": modified, "meta_url": META_URL, "last_modified": headers.get("last-modified", "")}


def run(root: Path, got: dict) -> dict:
    regions = load_regions(root)
    res = parse(got["body"], regions)
    cache = root / CACHE
    cache.mkdir(parents=True, exist_ok=True)
    (cache / f"{got['name']}.csv").write_bytes(got["body"])
    write_csv(root / LTA, LTA_FIELDS, res["rows"])
    snap = read_json(root / SNAPSHOT, {}) or {}
    snap.update({"dataset": DATASET, "meta_url": got["meta_url"], "url": got["url"], "modified": got["modified"],
                 "sha256": got["sha256"], "bytes": got["bytes"], "checked_at": today(), "rows_total": res["total"],
                 "rows": len(res["rows"]), "excluded_rows": res["excluded"], "dropped_fields": list(DROPPED),
                 "emails_dropped": res["bad_email"], "regions_covered": len(res["covered"]),
                 "regions_missing": sorted({r["id"] for r in regions} - set(res["covered"]))})
    write_json(root / SNAPSHOT, snap)
    return snap


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="python -m pipeline.fetch_lta")
    ap.add_argument("--file", type=Path)
    ap.add_argument("--url")
    a = ap.parse_args(argv)
    try:
        if a.file:
            body = a.file.read_bytes()
            name = a.file.stem
            m = re.search(r"data-(\d{8})", name)
            got = {"name": name, "url": a.url or "", "body": body, "sha256": hashlib.sha256(body).hexdigest(),
                   "bytes": len(body), "modified": m.group(1) if m else "", "meta_url": META_URL, "last_modified": ""}
        else:
            got = fetch()
        snap = run(Path.cwd(), got)
    except (net.SourceDown, LtaFormatError) as e:
        print(f"Ошибка: {e}", file=sys.stderr)
        return 1
    print(f"Набор {DATASET} от {snap['modified']}: строк {snap['rows']}, исключено {snap['excluded_rows']}, "
          f"регионов покрыто {snap['regions_covered']}, без ТО: {', '.join(snap['regions_missing']) or 'нет'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
