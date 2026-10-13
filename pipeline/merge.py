from pathlib import Path

from opsite.data import BuildError, read_csv

from pipeline.common import AGENCIES, AGENCY_ORDER, LINES, split_list

TOPICS = {"pain", "pmp", "drugs", "complaints", "general", "other", "staff"}
AUDIENCES = {"adults", "children", "all"}
OFF_CARD = {"other", "staff"}
ROLE_TOPICS = ("pmp", "pain", "general")


def _bool(value: str, where: str) -> bool | None:
    if value == "":
        return None
    if value not in ("true", "false"):
        raise BuildError(f"{where}: ожидается true или false, а здесь «{value}»")
    return value == "true"


def load_lines(root: Path) -> list[dict]:
    out = []
    for r in read_csv(root / LINES):
        row = {k: v for k, v in r.items() if k != "_line"}
        row["is_24x7"] = r["is_24x7"] == "true"
        row["topics"] = split_list(r["topics"])
        row["shared_with"] = split_list(r["shared_with"])
        row["source_row"] = int(r["source_row"])
        out.append(row)
    return out


def load_agencies(root: Path) -> list[dict]:
    return [{k: v for k, v in r.items() if k != "_line"} for r in read_csv(root / AGENCIES)]


def load_overrides(root: Path, line_ids: set[str]) -> dict[str, dict]:
    path = root / "data" / "review" / "overrides.csv"
    out = {}
    for r in read_csv(path) if path.is_file() else []:
        where = f"data/review/overrides.csv, строка {r['_line']}"
        if r["id"] not in line_ids:
            raise BuildError(f"{where}: правка для пропавшего номера {r['id']}: номер сменился, перенесите разметку")
        topics = split_list(r["topics"])
        if set(topics) - TOPICS:
            raise BuildError(f"{where}, поле topics: допустимые темы {', '.join(sorted(TOPICS))}")
        if r["audience"] and r["audience"] not in AUDIENCES:
            raise BuildError(f"{where}, поле audience: допустимо adults, children или all")
        out[r["id"]] = {"topics": topics, "audience": r["audience"],
                        "topics_checked": _bool(r["topics_checked"], f"{where}, поле topics_checked"),
                        "hide": _bool(r["hide"], f"{where}, поле hide")}
    return out


def enrich(line: dict, override: dict | None, *, origin: str, source_ref: str) -> dict:
    o = override or {}
    topics = o.get("topics") or line["topics"]
    item = dict(line)
    item.update({
        "topics": topics,
        "audience": o.get("audience") or line["audience"],
        "topics_checked": bool(o.get("topics_checked")),
        "roles": [line["agency"]] + [t for t in ROLE_TOPICS if t in topics],
        "foreign_number": bool(line["shared_with"]),
        "hidden": o["hide"] if o.get("hide") is not None else set(topics) <= OFF_CARD,
        "origin": origin,
        "source_ref": source_ref,
        "verified": False,
        "verified_at": None,
    })
    return item


def region_lines(root: Path) -> list[dict]:
    lines = load_lines(root)
    overrides = load_overrides(root, {ln["id"] for ln in lines})
    return [enrich(ln, overrides.get(ln["id"]), origin="rzn", source_ref="rzn-hotlines") for ln in lines]


def load_lta(root: Path) -> list[dict]:
    path = root / "data" / "rzn" / "lta.csv"
    return [{k: v for k, v in r.items() if k != "_line"} for r in read_csv(path)] if path.is_file() else []


def load_gaps(root: Path) -> list[dict]:
    path = root / "data" / "rzn" / "gaps.csv"
    out = []
    for r in read_csv(path) if path.is_file() else []:
        out.append({"region_id": r["region_id"], "agency": r["agency"], "kind": r["kind"],
                    "text_verbatim": r["text_verbatim"], "source_row": int(r["source_row"])})
    return out


def lta_by_region(lta: list[dict]) -> dict[str, dict]:
    out = {}
    for row in lta:
        for rid in split_list(row["region_ids"]):
            if rid in out:
                raise BuildError(f"data/rzn/lta.csv: регион {rid} указан у двух территориальных органов")
            out[rid] = row
    return out


def addressees(agencies: list[dict], lines: list[dict], slug: dict[str, str], source_ref: str,
               verified_at: str, lta: list[dict] | None = None, lta_version: str | None = None,
               lta_checked: str | None = None) -> list[dict]:
    by_region = lta_by_region(lta or [])
    rows = list(agencies)
    have = {(a["region_id"], a["agency"]) for a in agencies}
    for rid in sorted(by_region):
        if rid in slug and (rid, "rzn") not in have:
            rows.append({"region_id": rid, "agency": "rzn", "agency_name": ""})
    rows.sort(key=lambda a: (a["region_id"], AGENCY_ORDER[a["agency"]]))
    out = []
    for a in rows:
        item = {
            "id": f"{slug[a['region_id']]}-{a['agency']}",
            "region_id": a["region_id"],
            "agency": a["agency"],
            "name": a["agency_name"],
            "name_hotlines": None,
            "line_ids": [ln["id"] for ln in lines if ln["region_id"] == a["region_id"] and ln["agency"] == a["agency"]],
            "postal_address": None,
            "email": None,
            "hours_text": None,
            "source_ref": source_ref,
            "source_version": None,
            "verified": True,
            "verified_at": verified_at,
        }
        to = by_region.get(a["region_id"]) if a["agency"] == "rzn" else None
        if to:
            if a["agency_name"] and a["agency_name"] != to["name"]:
                item["name_hotlines"] = a["agency_name"]
            item.update({"name": to["name"], "postal_address": to["postal_address"] or None,
                         "email": to["email"] or None, "hours_text": to["hours_text"] or None,
                         "source_ref": "rzn-lta", "source_version": lta_version,
                         "verified_at": lta_checked or verified_at})
        out.append(item)
    return out
