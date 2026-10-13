import re
from pathlib import Path

from opsite.data import BuildError, read_yaml

SCAN_PAGES = Path("data/review/scan_pages.yaml")
DATE = re.compile(r"\d{4}-\d{2}-\d{2}")


def _check(entry: dict, i: int) -> dict:
    where = f"{SCAN_PAGES}, запись {i + 1}"
    if not re.fullmatch(r"\d{16}", str(entry.get("eo", ""))):
        raise BuildError(f"{where}, поле eo: eoNumber из 16 цифр")
    if not str(entry.get("page", "")).isdigit():
        raise BuildError(f"{where}, поле page: номер страницы PDF")
    if not DATE.fullmatch(str(entry.get("checked_at", ""))) or not entry.get("method") or not entry.get("checked_by"):
        raise BuildError(f"{where}: нужны checked_by, checked_at (ГГГГ-ММ-ДД) и method")
    second = entry.get("second_check")
    if second in (None, "", "null", "~"):
        second = None
    if second is not None:
        if not isinstance(second, dict):
            raise BuildError(f"{where}, second_check: null или запись с checked_by, checked_at, method")
        if not DATE.fullmatch(str(second.get("checked_at", ""))) or not second.get("checked_by") \
                or not second.get("method"):
            raise BuildError(f"{where}, second_check: нужны checked_by, checked_at и method")
        if second["checked_by"] == entry["checked_by"]:
            raise BuildError(f"{where}, second_check: второй проверяющий должен быть другим человеком")
    return {"eo": str(entry["eo"]), "page": int(entry["page"]), "units": [str(u) for u in entry.get("units") or []],
            "quotes": [str(q) for q in entry.get("quotes") or []], "checked_at": str(entry["checked_at"]),
            "second_at": str(second["checked_at"]) if second else None}


def load(root: Path) -> list[dict]:
    path = root / SCAN_PAGES
    if not path.is_file():
        return []
    raw = read_yaml(path) or {}
    return [_check(e, i) for i, e in enumerate(raw.get("pages") or [])]


def unit_key(unit: dict) -> str:
    part = unit.get("part")
    return f"{unit['table']} {unit['n']}" + (f".{part}" if part not in (None, "") else "")


def apply(route: dict, signatures: list[dict]) -> dict:
    eo = route["act"]["eoNumber"]
    own = [s for s in signatures if s["eo"] == eo]
    out = dict(route)

    def sign(page: int, key: str, field: str):
        for s in own:
            if s["page"] == page and key in s[field]:
                return s
        return None

    units, quotes = [], []
    for u in route["units"]:
        s = sign(u["page"], unit_key(u), "units")
        units.append({**u, "scan_checked_at": s["checked_at"] if s else None, "verified": bool(s and s["second_at"])})
    for q in route["quotes"]:
        s = sign(q["page"], q["point"], "quotes")
        quotes.append({**q, "scan_checked_at": s["checked_at"] if s else None, "verified": bool(s and s["second_at"])})
    out["units"], out["quotes"] = units, quotes
    out["scan_checked_pages"] = sorted({s["page"] for s in own})
    out["verified"] = bool(units) and all(u["verified"] for u in units) and all(q["verified"] for q in quotes)
    if out["verified"]:
        out["verified_at"] = max(s["second_at"] for s in own if s["second_at"])
    else:
        out["verified_at"] = None
    return out
