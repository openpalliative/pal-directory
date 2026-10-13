import re
from pathlib import Path

import yaml

RULES = Path(__file__).resolve().parents[1] / "opsite" / "lint" / "territories.yaml"
PRAVO_BLOCKS = frozenset({"region80", "region81", "region84", "region85", "region91", "region92"})
EO_PREFIXES = frozenset(code[-2:] for code in PRAVO_BLOCKS)


def _pattern() -> re.Pattern:
    rules = yaml.load(RULES.read_text(encoding="utf-8"), Loader=yaml.BaseLoader)
    patterns = rules.get("patterns") or []
    if len(patterns) < 8:
        raise RuntimeError(f"{RULES}: список исключённых территорий пуст или неполон, разбор остановлен")
    return re.compile("|".join(f"(?:{p})" for p in patterns))


PATTERN = _pattern()


def is_excluded(*texts) -> bool:
    return any(PATTERN.search(str(t)) for t in texts if t)


def block_allowed(code: str) -> bool:
    return code not in PRAVO_BLOCKS


def eo_allowed(eo: str) -> bool:
    return str(eo)[:2] not in EO_PREFIXES
