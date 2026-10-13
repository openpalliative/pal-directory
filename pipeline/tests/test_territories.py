import json
import os
import re
import subprocess
from pathlib import Path

import pytest

from pipeline import export, parse_rzn, territories
from pipeline.common import load_regions
from pipeline.tests.conftest import ROOT, read_rows, synth_cells, write_xlsx

NAMES = ["Донецкая Народная Республика", "Запорожская область", "Луганская Народная Республика",
         "Республика Крым", "Севастополь", "Херсонская область"]
AGENCY_NAMES = ["Территориальный орган Росздравнадзора по Республике Крым и городу федерального значения Севастополю",
                "Территориальный орган Росздравнадзора по Запорожской области и Херсонской области"]
GREP = r"Крым|Севастоп|Донецк|Луганск|Запорож|Херсон|ДНР|ЛНР"
ALLOWED_FILES = {"opsite/lint/territories.yaml", "pipeline/tests/test_territories.py"}
SKIP_DIRS = {"node_modules", ".venv", ".git", "__pycache__", ".pytest_cache", "_site", "_reports"}


@pytest.mark.parametrize("name", NAMES + AGENCY_NAMES)
def test_filter_matches_every_territory(name):
    assert territories.is_excluded(name)


@pytest.mark.parametrize("name", ["Республика Карелия", "Краснодарский край", "Ростовская область", "Белгородская область",
                                  "Республика Адыгея", "Москва", "Санкт-Петербург", "Крымская улица"])
def test_filter_keeps_other_regions(name):
    assert not territories.is_excluded(name)


def test_regions_csv_has_no_territories():
    rows = read_rows(ROOT / "data" / "regions.csv")
    assert len(rows) == 83
    assert "excluded" not in rows[0]
    assert not any(territories.is_excluded(*r.values()) for r in rows)


def test_parser_drops_territory_rows(tmp_path):
    regions = load_regions(ROOT)
    cells = synth_cells() + [(n, "Министерство здравоохранения", "8 (000) 000-00-00") for n in NAMES]
    res = parse_rzn.parse(write_xlsx(tmp_path / "t.xlsx", cells), regions, "2026-03-03")
    assert res["counts"]["excluded_rows"] == 6 and res["counts"]["excluded_regions"] == 6
    assert {ln["region_id"] for ln in res["lines"]} == {r["id"] for r in regions}
    text = json.dumps(res["lines"] + res["agencies"] + res["gaps"], ensure_ascii=False)
    assert not territories.PATTERN.search(text)


def test_pravo_denylist():
    assert territories.PRAVO_BLOCKS == {"region80", "region81", "region84", "region85", "region91", "region92"}
    assert not territories.block_allowed("region91") and territories.block_allowed("region39")
    assert not territories.eo_allowed("9100202601010001") and territories.eo_allowed("3901202609100002")


@pytest.mark.parametrize("mode", ["real", "links", "demo"])
def test_no_territories_published(monkeypatch, mode):
    monkeypatch.setenv("PD_DATA_MODE", mode)
    monkeypatch.delenv("OP_FIXTURES", raising=False)
    for env in export.datasets(ROOT):
        m = territories.PATTERN.search(json.dumps(env, ensure_ascii=False))
        assert m is None, (env["dataset"], m)


def test_grep_finds_only_filter_and_this_test():
    rx = re.compile(GREP, re.I)
    found = set()
    for dirpath, dirnames, filenames in os.walk(ROOT):
        dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS and not (Path(dirpath) == ROOT / "raw" and d == "cache")]
        for name in filenames:
            p = Path(dirpath) / name
            if p.suffix in (".png", ".pdf", ".xlsx", ".pyc", ".zip"):
                continue
            try:
                text = p.read_text(encoding="utf-8")
            except (UnicodeDecodeError, OSError):
                continue
            if rx.search(text):
                found.add(p.relative_to(ROOT).as_posix())
    assert found <= ALLOWED_FILES, sorted(found - ALLOWED_FILES)


def test_raw_cache_ignored():
    assert "raw/cache/" in (ROOT / ".gitignore").read_text(encoding="utf-8").split()
    if (ROOT / ".git").is_dir():
        tracked = subprocess.run(["git", "ls-files", "raw/cache"], cwd=ROOT, capture_output=True, text=True).stdout
        assert not tracked.strip()

