import re

import pytest

from opsite.data import BuildError, read_csv, read_yaml
from pipeline import export, routes_review
from pipeline.tests.conftest import ROOT, personal

FILES = sorted((ROOT / "data" / "routes").glob("*.yaml"))
ROUTES = {p.name: read_yaml(p) for p in FILES}
KGD = ROUTES["kgd-678.yaml"]
STOP = ["балл", "положительных ответ", "месяц", "прогноз", "Анкета", "анкет", "критери", "альбумин", "масс", "%",
        "индекс Карновского", "шкал", "ECOG", "PPS"]
OCR_GARBAGE = ("ПМИ", "ИМИ", "ИМП", "больнина", "]", "|")


def texts(route: dict) -> list[str]:
    out = [q["text_verbatim"] for q in route["quotes"]] + [u["org"] + " " + u["unit"] for u in route["units"]]
    out += [d["name"] for d in route.get("districts") or []]
    return out


@pytest.fixture(scope="module")
def published():
    env = next(e for e in export.datasets(ROOT) if e["dataset"] == "routes")
    return {r["id"]: r for r in env["items"]}


def test_kgd_act():
    act = KGD["act"]
    assert act["eoNumber"] == "3901202609100002"
    assert act["url"] == "http://publication.pravo.gov.ru/document/3901202609100002"
    assert act["number"] == "678" and act["date"] == "2026-09-09"
    assert {a["eoNumber"] for a in KGD["related_acts"]} == {"3901202605080009", "3901202601300007"}


def test_kgd_tables():
    amb = [u for u in KGD["units"] if u["table"] == "ambulatory"]
    inp = [u for u in KGD["units"] if u["table"] == "inpatient"]
    assert [int(u["n"]) for u in amb] == list(range(1, 19))
    assert [int(u["n"]) for u in inp] == list(range(1, 12))
    svetly = next(u for u in inp if "Светловская" in u["org"])
    assert svetly["n"] == "11" and svetly["sic"] == "true"


def test_kgd_no_districts():
    assert KGD["districts"] in ([], "[]") and all("district" not in u for u in KGD["units"])


@pytest.mark.parametrize("name", sorted(ROUTES))
@pytest.mark.parametrize("word", STOP)
def test_no_questionnaire_or_criteria(name, word):
    assert not any(word in t for t in texts(ROUTES[name])), name


@pytest.mark.parametrize("name", sorted(ROUTES))
def test_route_hygiene(name):
    r = ROUTES[name]
    assert re.fullmatch(r"\d{16}", r["act"]["eoNumber"])
    assert r["act"]["url"].endswith(r["act"]["eoNumber"])
    assert r["audience"] in ("adults", "children")
    for t in texts(r):
        assert not personal(t), (name, t)
    for u in r["units"]:
        assert u["org"] and u["unit"] and int(u["page"]) >= 1, (name, u)
        for bad in OCR_GARBAGE:
            assert bad not in u["org"] + u["unit"], (name, u["n"], bad)
        assert "verified" not in u and "scan_checked_at" not in u, "verified и scan_checked_at ставит routes_review"
    assert r["verified"] == "false", "маршрут целиком verified считается из подписей, в yaml всегда false"


def test_regions_point_to_routes():
    regions = {r["id"]: r for r in read_csv(ROOT / "data" / "regions.csv")}
    ids = {r["id"] for r in ROUTES.values()}
    for r in ROUTES.values():
        if r["id"] == r["region_id"].lower():
            assert regions[r["region_id"]]["route"] == r["id"]
    assert {r["route"] for r in regions.values() if r["route"]} <= ids


def test_published_unverified_without_second_check(published):
    for r in published.values():
        assert r["verified"] is False
        assert all(u["verified"] is False for u in r["units"])
    kgd = published["ru-kgd"]
    assert kgd["scan_checked_pages"] == [3, 19, 20]
    assert all(u["scan_checked_at"] for u in kgd["units"])


def test_verified_only_with_second_reviewer(tmp_path):
    root = tmp_path
    (root / "data" / "review").mkdir(parents=True)
    route = {"act": {"eoNumber": "3901202609100002"}, "units": [{"table": "ambulatory", "n": 1, "page": 19}],
             "quotes": [{"point": "п. 1", "page": 3}]}
    base = ("pages:\n  - eo: \"3901202609100002\"\n    page: {page}\n    units: {units}\n    quotes: {quotes}\n"
            "    checked_by: first\n    checked_at: 2026-10-12\n    method: m\n    second_check: {second}\n")
    one = base.format(page=19, units='["ambulatory 1"]', quotes="[]", second="null")
    two = base.format(page=3, units="[]", quotes='["п. 1"]', second="null")
    (root / routes_review.SCAN_PAGES).write_text(one + two.split("pages:\n")[1], encoding="utf-8")
    out = routes_review.apply(route, routes_review.load(root))
    assert out["units"][0]["scan_checked_at"] == "2026-10-12" and out["units"][0]["verified"] is False
    assert out["verified"] is False
    second = "{checked_by: second, checked_at: 2026-10-13, method: m}"
    (root / routes_review.SCAN_PAGES).write_text(
        base.format(page=19, units='["ambulatory 1"]', quotes="[]", second=second)
        + base.format(page=3, units="[]", quotes='["п. 1"]', second=second).split("pages:\n")[1], encoding="utf-8")
    out = routes_review.apply(route, routes_review.load(root))
    assert out["verified"] is True and out["verified_at"] == "2026-10-13"
    (root / routes_review.SCAN_PAGES).write_text(
        base.format(page=19, units='["ambulatory 1"]', quotes="[]", second="{checked_by: first, checked_at: 2026-10-13, method: m}"),
        encoding="utf-8")
    with pytest.raises(BuildError, match="другим человеком"):
        routes_review.load(root)


def test_planned_route_acts_are_parsed_or_skipped_with_reason():
    skipped = read_yaml(ROOT / "data" / "review" / "routes-skipped.yaml")["skipped"]
    done = {r["act"]["eoNumber"] for r in ROUTES.values()}
    reasons = {s["eoNumber"]: s["reason"] for s in skipped}
    for eo in ("4401202605290002", "4401202602200003", "6601202602050002", "6601202604240003", "6001202603300015",
               "7801202503070012", "3901202605080009", "2001202505300001"):
        assert eo in done or len(reasons.get(eo, "")) > 40, eo
    assert not done & set(reasons)
    spb = next(s for s in skipped if s["eoNumber"] == "7801202503070012")
    assert "345н/372н" in spb["superseded_refs"][0]["text_verbatim"]


def test_districts_point_to_units():
    for name, r in ROUTES.items():
        keys = {routes_review.unit_key(u) for u in r["units"]}
        for d in list(r.get("districts") or []) + list(r.get("referrals") or []):
            assert set(d["units"]) <= keys, (name, d)


def test_route_sources_have_sha256():
    import csv
    import hashlib
    with open(ROOT / "raw" / "SOURCES.tsv", encoding="utf-8", newline="") as f:
        rows = {r["id"]: r for r in csv.DictReader(f, delimiter="\t")}
    for name, r in ROUTES.items():
        src = rows.get(r["source_ref"])
        assert src and r["act"]["eoNumber"] in src["url"] and len(src["sha256"]) == 64, name
        pdf = ROOT / "raw" / "cache" / "pdf" / f"{r['act']['eoNumber']}.pdf"
        if pdf.is_file():
            assert hashlib.sha256(pdf.read_bytes()).hexdigest() == src["sha256"], name
