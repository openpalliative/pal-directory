import json
import re

import pytest

from pipeline import export
from pipeline.parse_rzn import EMAIL, FIO
from pipeline.tests.conftest import RZN_EMAIL, ROOT, personal, strings

FILES = ["data/rzn/lines.csv", "data/rzn/agencies.csv", "data/rzn/gaps.csv", "data/snapshots/rzn-hotlines.json",
         "data/pravo/region-acts.csv"]


def published(monkeypatch, mode):
    monkeypatch.setenv("PD_DATA_MODE", mode)
    monkeypatch.delenv("OP_FIXTURES", raising=False)
    return export.datasets(ROOT)


@pytest.mark.parametrize("rel", FILES)
def test_no_personal_data_in_data(rel):
    path = ROOT / rel
    if not path.is_file():
        pytest.skip(f"нет {rel}")
    for line in path.read_text(encoding="utf-8").splitlines():
        assert not EMAIL.search(line), line
        assert not FIO.search(line), line
        assert not re.search(r"ответственн\w*\s+сотрудник", line, re.I)


def test_lta_only_official_mail_and_no_people():
    for line in (ROOT / "data" / "rzn" / "lta.csv").read_text(encoding="utf-8").splitlines():
        assert not EMAIL.search(RZN_EMAIL.sub("", line)), line
        assert not personal(line), line


@pytest.mark.parametrize("mode", ["real", "links", "demo"])
def test_no_personal_data_published(monkeypatch, mode):
    for env in published(monkeypatch, mode):
        for s in strings(env["items"]):
            assert "@" not in RZN_EMAIL.sub("", s), (env["dataset"], s)
            assert not personal(s), (env["dataset"], s)
            assert "сотрудник" not in s, (env["dataset"], s)
        assert "сотрудник" not in json.dumps(env["source"], ensure_ascii=False)


def test_raw_xlsx_not_tracked():
    ignore = (ROOT / ".gitignore").read_text(encoding="utf-8")
    assert "raw/cache/" in ignore.split()
    assert not list((ROOT / "data").rglob("*.xlsx"))
    assert not [p for p in (ROOT / "raw").rglob("*.xlsx") if "cache" not in p.parts]
    assert not [p for p in (ROOT / "raw").rglob("*.pdf") if "cache" not in p.parts]
