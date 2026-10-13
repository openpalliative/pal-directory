import json

import pytest
import yaml

from opsite.build import check_envelope
from pipeline import export, fixtures
from pipeline.common import AGENCY_ORDER
from pipeline.tests.conftest import ROOT

MAX_BYTES = 1024 * 1024


def envelopes(monkeypatch, mode):
    monkeypatch.setenv("PD_DATA_MODE", mode)
    monkeypatch.delenv("OP_FIXTURES", raising=False)
    return {e["dataset"]: e for e in export.datasets(ROOT)}


@pytest.mark.parametrize("mode", ["real", "links", "demo"])
def test_envelopes_pass_schemas(monkeypatch, mode):
    envs = envelopes(monkeypatch, mode)
    assert sorted(envs) == sorted(export.NAMES)
    for name, env in envs.items():
        check_envelope(env, ROOT / "data" / "schema" / f"{name}.schema.json", name)
        assert len(json.dumps(env, ensure_ascii=False, indent=1).encode()) < MAX_BYTES, name


def test_fixtures_pass_schemas_and_are_fresh(monkeypatch):
    monkeypatch.setenv("OP_FIXTURES", "1")
    built = fixtures.build()
    for env in export.datasets(ROOT):
        check_envelope(env, ROOT / "data" / "schema" / f"{env['dataset']}.schema.json", env["dataset"])
        assert env == built[env["dataset"]], f"tests/fixtures/{env['dataset']}.json устарел: uv run python -m pipeline.fixtures"


def test_bad_mode(monkeypatch):
    monkeypatch.setenv("PD_DATA_MODE", "prod")
    with pytest.raises(Exception, match="PD_DATA_MODE"):
        export.datasets(ROOT)


def test_regions_and_lines(monkeypatch):
    envs = envelopes(monkeypatch, "real")
    regions = envs["regions"]["items"]
    assert len(regions) == 83 and envs["regions"]["counts"]["excluded"] == 6
    assert all(r["verified"] for r in regions)
    lines = envs["region-lines"]["items"]
    assert all(ln["verified"] is False and ln["origin"] == "rzn" for ln in lines)
    keys = [(ln["region_id"], AGENCY_ORDER[ln["agency"]], ln["source_row"]) for ln in lines]
    assert keys == sorted(keys)
    assert len({ln["id"] for ln in lines}) == len(lines)
    ids = {r["id"] for r in regions}
    assert {ln["region_id"] for ln in lines} == ids
    for r in regions:
        own = [ln for ln in lines if ln["region_id"] == r["id"] and not ln["hidden"]]
        assert r["lines"] == len(own)
        assert r["has_pain_pmp"] == any({"pain", "pmp"} & set(ln["topics"]) for ln in own)
    for ln in lines:
        assert ln["roles"][0] == ln["agency"]
        assert ln["foreign_number"] == bool(ln["shared_with"])
        assert set(ln["shared_with"]) <= ids
    gold = yaml.safe_load((ROOT / "tests" / "golden" / "rzn-counts.yaml").read_text(encoding="utf-8"))
    assert sum(r["has_pain_pmp"] for r in regions) == gold["regions_with_pain_pmp"]
    assert sum(ln["topics_checked"] for ln in lines) == gold["topics_checked"]


def test_demo_is_synthetic(monkeypatch):
    envs = envelopes(monkeypatch, "demo")
    lines = envs["region-lines"]["items"]
    assert all(ln["origin"] == "synthetic" and ln["tel"].startswith("+7000") for ln in lines)
    assert envs["region-lines"]["source"][0]["title"] == "Пример на выдуманных данных"
    assert len({ln["region_id"] for ln in lines}) == 83
    names = {a["name"] for a in envs["addressees"]["items"]}
    assert "Министерство здравоохранения Калининградской области (Медицинский информационный аналитический центр (Контакт-центр 122)" in names
    line_ids = {ln["id"] for ln in lines}
    assert all(set(a["line_ids"]) <= line_ids for a in envs["addressees"]["items"])


def test_addressees(monkeypatch):
    envs = envelopes(monkeypatch, "real")
    items = envs["addressees"]["items"]
    assert len(items) == 247 and len({a["id"] for a in items}) == 247
    assert all(a["postal_address"] is None and a["email"] is None for a in items if a["agency"] != "rzn")
    assert sum(1 for a in items if a["agency"] == "rzn" and a["postal_address"]) == 81
    line_ids = {ln["id"] for ln in envs["region-lines"]["items"]}
    assert all(set(a["line_ids"]) <= line_ids for a in items)
    assert next(a for a in items if a["id"] == "ru-ce-minzdrav")["line_ids"] == []


def test_federal_not_in_now_yaml(monkeypatch):
    now = yaml.safe_load((ROOT / "opsite" / "now.yaml").read_text(encoding="utf-8"))
    now_digits = {"".join(c for c in str(x["number"]) if c.isdigit())[-10:] for x in now["lines"]}
    fed = envelopes(monkeypatch, "real")["federal-lines"]["items"]
    assert fed and all(x["tel"][-10:] not in now_digits for x in fed)
    assert all(x["number"].replace(" ", "") in x["quote_verbatim"].replace(" ", "") for x in fed)
    assert not any(x["tel"] == "122" for x in fed)


def test_entrypoints_match_ux_map(monkeypatch):
    items = envelopes(monkeypatch, "real")["entrypoints"]["items"]
    assert [(e["id"], e["path"]) for e in items] == [("regions", ""), ("federal", "federal/"), ("routes", "routes/")]
    assert [e["maturity"] for e in items] == ["beta", "beta", "draft"]


def test_snapshot_helper():
    snap = export.snapshot(ROOT)
    assert snap["assured_date"] == "2026-03-03"
    assert snap["checked_at"] and snap["sha256"]


def test_federal_search_recorded(monkeypatch):
    from opsite.data import read_yaml as ry
    fed = ry(ROOT / "data" / "federal.yaml")
    assert fed["search"]["searched_at"] and fed["search"]["result"]
    for line in fed["lines"]:
        if line["source_ref"] != "rzn-page":
            assert line.get("eoNumber") and line.get("point") and line["quote_verbatim"] and line["verified"] == "false"
    env = envelopes(monkeypatch, "real")["federal-lines"]
    assert any(s["id"] == "pravo-federal-search" for s in env["source"])
