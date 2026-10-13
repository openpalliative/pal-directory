import csv
import datetime as dt
import io
import json
import re
from pathlib import Path

from opsite.data import BuildError, read_csv, read_yaml

from pipeline import territories

AGENCY_ORDER = {"minzdrav": 0, "rzn": 1, "tfoms": 2}
LINE_FIELDS = ["id", "region_id", "agency", "agency_name", "number_raw", "number_display", "tel", "ext_text", "kind",
               "topic_text", "hours_text", "is_24x7", "topics", "audience", "shared_with", "source_row", "source_text",
               "assured_date"]
OVERRIDE_FIELDS = ["id", "topics", "audience", "topics_checked", "hide", "note", "checked_by", "checked_at"]
AGENCY_FIELDS = ["region_id", "agency", "agency_name", "source_row"]
GAP_FIELDS = ["region_id", "agency", "source_row", "kind", "text_verbatim"]
SNAPSHOT = Path("data/snapshots/rzn-hotlines.json")
AGENCIES = Path("data/rzn/agencies.csv")
GAPS = Path("data/rzn/gaps.csv")
LINES = Path("data/rzn/lines.csv")


def today() -> str:
    return dt.date.today().isoformat()


def write_csv(path: Path, fields: list[str], rows: list[dict]) -> None:
    buf = io.StringIO()
    w = csv.DictWriter(buf, fieldnames=fields, lineterminator="\n", extrasaction="ignore")
    w.writeheader()
    for r in rows:
        w.writerow(r)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(buf.getvalue(), encoding="utf-8")


def read_json(path: Path, default=None):
    return json.loads(path.read_text(encoding="utf-8")) if path.is_file() else default


def write_json(path: Path, obj) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, ensure_ascii=False, indent=1, sort_keys=False) + "\n", encoding="utf-8")


def split_list(value: str) -> list[str]:
    return [v.strip() for v in (value or "").split(";") if v.strip()]


def load_regions(root: Path) -> list[dict]:
    rows = read_csv(root / "data" / "regions.csv")
    seen = set()
    for r in rows:
        where = f"data/regions.csv, строка {r['_line']}"
        if not re.fullmatch(r"RU-[A-Z]{2,3}", r["id"]) or r["slug"] != r["id"].lower():
            raise BuildError(f"{where}, поле id: код в виде RU-KGD, slug в нижнем регистре")
        if r["id"] in seen:
            raise BuildError(f"{where}: регион {r['id']} указан дважды")
        if territories.is_excluded(r["name"], r["name_source"]):
            raise BuildError(f"{where}: эта территория не публикуется, уберите строку")
        seen.add(r["id"])
    return rows


def published_regions(regions: list[dict]) -> list[dict]:
    return list(regions)
