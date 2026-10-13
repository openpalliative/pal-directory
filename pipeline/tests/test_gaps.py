import pytest

from pipeline import export
from pipeline.tests.conftest import ROOT, read_rows, real_xlsx

GAP_REGIONS = {"RU-CE", "RU-LIP", "RU-YEV"}
MISSING = {"RU-MOW", "RU-MOS"}


@pytest.fixture(scope="module")
def envs():
    return {e["dataset"]: e for e in export.datasets(ROOT)}


def test_every_region_has_rzn_or_flag(envs):
    rzn = {a["region_id"] for a in envs["addressees"]["items"] if a["agency"] == "rzn"}
    for r in envs["regions"]["items"]:
        if r["id"] in rzn:
            assert r["rzn_missing"] is False and r["rzn_missing_reason"] is None, r["id"]
        else:
            assert r["rzn_missing"] is True and r["rzn_missing_reason"], f"{r['id']}: нет ТО Росздравнадзора и нет флага"


def test_missing_regions(envs):
    flagged = {r["id"] for r in envs["regions"]["items"] if r["rzn_missing"]}
    assert flagged == MISSING
    reason = next(r for r in envs["regions"]["items"] if r["id"] == "RU-MOW")["rzn_missing_reason"]
    assert "03.03.2026" in reason and "20261001" in reason


def test_gaps_verbatim(envs):
    with_gaps = {r["id"]: r["source_gaps"] for r in envs["regions"]["items"] if r["source_gaps"]}
    assert set(with_gaps) == GAP_REGIONS
    assert [g["kind"] for g in with_gaps["RU-YEV"]] == ["no_number"]
    assert {g["kind"] for g in with_gaps["RU-CE"]} == {"malformed"} and len(with_gaps["RU-CE"]) == 2
    assert with_gaps["RU-LIP"][0]["text_verbatim"] == "8 (962) 90-05-53"
    for gaps in with_gaps.values():
        for g in gaps:
            assert "tel:" not in g["text_verbatim"] and "+7" not in g["text_verbatim"]


@pytest.mark.skipif(real_xlsx() is None, reason="нет raw/cache с таблицей РЗН")
def test_gaps_are_substrings_of_source():
    import openpyxl
    ws = openpyxl.load_workbook(real_xlsx())["ПЕРЕЧЕНЬ"]
    for g in read_rows(ROOT / "data" / "rzn" / "gaps.csv"):
        cell = " ".join(str(ws.cell(int(g["source_row"]), 4).value or "").replace("\xa0", " ").split())
        assert g["text_verbatim"] in cell, g
