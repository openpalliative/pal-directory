import json
import re
import urllib.parse

import pytest

from pipeline import net, pravo_acts, territories
from pipeline.common import load_regions
from pipeline.tests.conftest import ROOT, read_rows

FIX = ROOT / "pipeline" / "tests" / "fixtures" / "pravo"
EMPTY = {"items": [], "itemsTotalCount": 0, "itemsPerPage": 100, "currentPage": 1, "pagesTotalCount": 0}


class FakeApi:
    def __init__(self):
        self.calls = []

    def __call__(self, path, params):
        url = f"http://{net.PRAVO_HOST}{path}?" + urllib.parse.urlencode(params)
        net.check_pravo_api(url)
        self.calls.append((path, dict(params)))
        if path == "/api/PublicBlocks":
            return (FIX / "public-blocks-subjects.json").read_bytes(), {}
        p = dict(params)
        f = FIX / f"{p['Block']}-{p['Name']}-{p['Index']}.json"
        body = f.read_bytes() if f.is_file() else json.dumps(EMPTY).encode()
        return body, {}


def norm(name: str) -> str:
    return re.sub(r"[\s\-]", "", name.lower().replace("ё", "е").replace("-чувашия", "").replace(" - чувашия", ""))


def test_pravo_block_column_matches_portal_names():
    blocks = {b["code"]: b["name"] for b in json.loads((FIX / "public-blocks-subjects.json").read_text(encoding="utf-8"))}
    regions = load_regions(ROOT)
    assert len({r["pravo_block"] for r in regions}) == 83
    for r in regions:
        assert r["pravo_block"] in blocks, r["id"]
        assert norm(blocks[r["pravo_block"]]) == norm(r["name"]), (r["id"], blocks[r["pravo_block"]])


def test_fixture_has_no_denied_blocks():
    codes = {b["code"] for b in json.loads((FIX / "public-blocks-subjects.json").read_text(encoding="utf-8"))}
    assert not codes & territories.PRAVO_BLOCKS
    for f in FIX.glob("*.json"):
        assert not territories.PATTERN.search(f.read_text(encoding="utf-8")), f.name


def test_collect_offline_never_asks_denied_blocks():
    api = FakeApi()
    res = pravo_acts.collect(api, load_regions(ROOT), retrieved="2026-10-12")
    blocks = {c[1]["Block"] for c in api.calls if c[0] == "/api/Documents"}
    assert len(blocks) == 83 and not blocks & territories.PRAVO_BLOCKS
    assert {c[1]["Name"] for c in api.calls if c[0] == "/api/Documents"} == set(pravo_acts.WORDS)
    assert res["queries"] == 83 * len(pravo_acts.WORDS)
    by_id = {a["id"]: a for a in res["acts"]}
    kgd = by_id["3901202609100002"]
    assert kgd["region_id"] == "RU-KGD" and kgd["number"] == "678" and kgd["doc_date"] == "2026-09-09"
    assert kgd["act_type"] == "Приказ" and kgd["authority"] == "Министерства здравоохранения Калининградской области"
    assert kgd["url"] == "http://publication.pravo.gov.ru/document/3901202609100002" and kgd["pages"] == 20
    assert by_id["3900202503060002"]["kind"] == "reimbursement"
    assert by_id["4401202605290002"]["region_id"] == "RU-KOS"
    assert all(a["id"][:2] == {"RU-KGD": "39", "RU-KOS": "44"}[a["region_id"]] for a in res["acts"])


def test_search_refuses_denied_block():
    api = FakeApi()
    with pytest.raises(net.HostNotAllowed):
        pravo_acts.search(api, "region91", "паллиативной")
    assert api.calls == []


def test_mismatched_eo_is_dropped(monkeypatch):
    def api(path, params):
        if path == "/api/PublicBlocks":
            return (FIX / "public-blocks-subjects.json").read_bytes(), {}
        doc = json.loads((FIX / "region39-паллиативной-1.json").read_text(encoding="utf-8"))["items"][0]
        bad = dict(doc, eoNumber="9100202601010001")
        return json.dumps({"items": [doc, bad], "pagesTotalCount": 1}).encode(), {}

    res = pravo_acts.collect(api, [r for r in load_regions(ROOT) if r["id"] == "RU-KGD"])
    assert [a["id"] for a in res["acts"]] == ["3901202609100002"]
    assert res["mismatched"] and res["mismatched"][0]["eoNumber"] == "9100202601010001"


@pytest.mark.parametrize("title, kind", [
    ("Об утверждении региональной программы «Развитие системы оказания паллиативной медицинской помощи»", "program"),
    ("О маршрутизации пациентов, нуждающихся в оказании паллиативной медицинской помощи", "routing"),
    ("Об утверждении Маршрута оказания паллиативной медицинской помощи детям", "routing"),
    ("О порядке возмещения областью иному субъекту Российской Федерации ... паллиативной медицинской помощи",
     "reimbursement"),
    ("О предоставлении субсидий на оказание паллиативной медицинской помощи", "subsidy"),
    ("О порядке возмещения Пензенской областью субъекту Российской Федерации, на территории которого гражданину, зарегистрированному по месту жительства на территории Пензенской области, фактически оказана медицинская помощь, затрат, связанных с оказанием медицинской помощи при заболеваниях, не включенных в базовую программу обязательного медицинского страхования, и паллиативной медицинской помощи", "reimbursement"),
    ("Об обеспечении лечебным питанием детей, нуждающихся в паллиативной помощи", "nutrition"),
    ("Об организации передачи пациенту медицинских изделий", "devices"),
    ("Об организации оказания паллиативной медицинской помощи взрослому населению", "organization"),
    ("О денежных выплатах отдельным медицинским работникам", "other"),
])
def test_kind_dictionary(title, kind):
    assert pravo_acts.kind_of(title) == kind


def test_committed_index():
    rows = read_rows(ROOT / "data" / "pravo" / "region-acts.csv")
    assert len(rows) >= 250 and len({r["region_id"] for r in rows}) >= 60
    assert len({r["id"] for r in rows}) == len(rows)
    blocks = {r["id"]: r["pravo_block"][-2:] for r in load_regions(ROOT)}
    for r in rows:
        assert r["id"][:2] == blocks[r["region_id"]], r["id"]
        assert territories.eo_allowed(r["id"])
        assert r["url"] == f"http://publication.pravo.gov.ru/document/{r['id']}"
        assert r["kind"] == pravo_acts.kind_of(r["title"]), r["id"]
    for eo in ("3901202609100002", "4401202605290002", "6601202602050002", "7801202503070012"):
        assert eo in {r["id"] for r in rows}


def test_api_allowlist():
    net.check_pravo_api("http://publication.pravo.gov.ru/api/Documents?Block=region39")
    net.check_pravo_api("http://publication.pravo.gov.ru/api/PublicBlocks?parent=subjects")
    for bad in ("https://publication.pravo.gov.ru/api/Documents", "http://publication.pravo.gov.ru/api/Other",
                "http://publication.pravo.gov.ru/file/pdf?eoNumber=3901202609100002",
                "http://publication.pravo.gov.ru.evil.example/api/Documents", "http://pravo.gov.ru/api/Documents"):
        with pytest.raises(net.HostNotAllowed):
            net.check_pravo_api(bad)
    net.check_pravo_pdf("http://publication.pravo.gov.ru/file/pdf?eoNumber=3901202609100002")
    for bad in ("http://publication.pravo.gov.ru/file/pdf?eoNumber=1", "http://publication.pravo.gov.ru/file/pdf",
                "http://publication.pravo.gov.ru/file/pdf?eoNumber=3901202609100002&x=1"):
        with pytest.raises(net.HostNotAllowed):
            net.check_pravo_pdf(bad)


def test_pause_between_requests():
    slept, clock = [], iter([0.0, 0.0, 0.5, 2.0]).__next__
    net._last_pravo[0] = -10.0
    net.pravo_wait(slept.append, clock)
    net.pravo_wait(slept.append, clock)
    assert slept == [pytest.approx(1.5)]
