import csv
import io
import json

import pytest
import yaml

from pipeline import export, fetch_lta, net
from pipeline.common import load_regions
from pipeline.parse_rzn import EMAIL
from pipeline.tests.conftest import ROOT, personal, read_rows
from pipeline.tests.test_territories import AGENCY_NAMES

GOLD = yaml.safe_load((ROOT / "tests" / "golden" / "lta-renames.yaml").read_text(encoding="utf-8"))
HEAD = ["full_name", "name", "head", "deputy_head", "functions", "address", "kladr", "okpo", "ogrn", "inn", "mail", "fax",
        "telephone", "longitude", "latitude", "fias_code", "work_mode", "telephone_others", "url"]
def row(name, address="000000, Россия, город, ул. Мира, 1", mail="info@reg00.roszdravnadzor.gov.ru", **kw):
    base = {h: "" for h in HEAD}
    base.update({"full_name": name.replace("Росздравнадзора", "Федеральной службы по надзору в сфере здравоохранения"),
                 "name": name, "head": "Сидоров Семён Семёнович, Руководитель", "deputy_head": "Кузьмина Анна Олеговна",
                 "functions": "1. Контроль", "address": address, "mail": mail, "work_mode": "пн-пт 9:00-18:00"})
    base.update(kw)
    return base


def to_cp1251(rows) -> bytes:
    buf = io.StringIO()
    w = csv.DictWriter(buf, fieldnames=HEAD, delimiter=";", quoting=csv.QUOTE_ALL, lineterminator="\r\n")
    w.writeheader()
    for r in rows:
        w.writerow(r)
    return buf.getvalue().encode("cp1251")


def synthetic_rows():
    regions = load_regions(ROOT)
    out = [row(f"Территориальный орган Росздравнадзора по {r['name_dative']}") for r in regions
           if r["id"] not in ("RU-MOW", "RU-MOS")]
    out.append(row(AGENCY_NAMES[0]))
    return out


def test_parse_drops_people_territories_and_bad_mail():
    rows = synthetic_rows()
    rows[5]["mail"] = "reg18.roszdravnadzor.gov.ru"
    rows[6]["mail"] = "someone@example.org"
    res = fetch_lta.parse(to_cp1251(rows), load_regions(ROOT))
    assert res["excluded"] == 1
    assert res["bad_email"] == 2
    assert len(res["covered"]) == 81
    text = json.dumps(res["rows"], ensure_ascii=False)
    assert "Сидоров" not in text and "Кузьмина" not in text and "Контроль" not in text
    assert all(r["email"] == "" or r["email"].endswith("roszdravnadzor.gov.ru") for r in res["rows"])


def test_parse_refuses_unknown_name():
    rows = synthetic_rows() + [row("Территориальный орган Росздравнадзора по Новой области")]
    with pytest.raises(fetch_lta.LtaFormatError, match="Не сопоставлены"):
        fetch_lta.parse(to_cp1251(rows), load_regions(ROOT))


def test_parse_refuses_missing_column():
    body = "\"name\";\"address\"\r\n\"x\";\"y\"\r\n".encode("cp1251")
    with pytest.raises(fetch_lta.LtaFormatError, match="нет столбцов"):
        fetch_lta.parse(body, load_regions(ROOT))


def test_fetch_uses_meta_and_allowlist(tmp_root):
    meta = ("property,value\nidentifier,7710537160-lta\n"
            "data-20261001-structure-20180925,https://roszdravnadzor.gov.ru/opendata/7710537160-lta/data-20261001-structure-20180925.csv\n"
            "data-20260901-structure-20180925,https://roszdravnadzor.gov.ru/opendata/7710537160-lta/data-20260901-structure-20180925.csv\n"
            ).encode("cp1251")
    body = to_cp1251(synthetic_rows())
    calls = []

    def get(url):
        net.check_host(url)
        calls.append(url)
        return (meta, {}) if url.endswith("meta.csv") else (body, {})

    got = fetch_lta.fetch(get)
    assert calls[1].endswith("data-20261001-structure-20180925.csv") and got["modified"] == "20261001"
    snap = fetch_lta.run(tmp_root, got)
    assert snap["rows"] == 81 and snap["excluded_rows"] == 1
    assert snap["regions_missing"] == ["RU-MOS", "RU-MOW"]
    assert [p.name for p in (tmp_root / "raw" / "cache" / "lta").glob("*.csv")] == ["data-20261001-structure-20180925.csv"]


def test_committed_lta_matches_golden():
    rows = read_rows(ROOT / "data" / "rzn" / "lta.csv")
    snap = json.loads((ROOT / "data" / "snapshots" / "rzn-lta.json").read_text(encoding="utf-8"))
    assert snap["sha256"] == GOLD["sha256"] and snap["url"].endswith(GOLD["source"])
    assert snap["rows_total"] == GOLD["rows_total"] and len(rows) == GOLD["rows"]
    assert snap["regions_covered"] == GOLD["regions_covered"] and snap["regions_missing"] == GOLD["regions_missing"]
    assert set(rows[0]) == set(fetch_lta.LTA_FIELDS)
    for r in rows:
        for value in r.values():
            assert not personal(value), (r["source_row"], personal(value))
        assert not r["email"] or r["email"].endswith(".roszdravnadzor.gov.ru")
        assert EMAIL.fullmatch(r["email"]) or r["email"] == ""


@pytest.fixture(scope="module")
def addressees():
    return {a["id"]: a for a in next(e for e in export.datasets(ROOT) if e["dataset"] == "addressees")["items"]}


def test_rzn_addresses(addressees):
    rzn = [a for a in addressees.values() if a["agency"] == "rzn"]
    assert len(rzn) == 81 and all(a["postal_address"] and a["source_ref"] == "rzn-lta" for a in rzn)
    assert all(a["source_version"] == "20261001" for a in rzn)
    assert all(a["postal_address"] is None and a["email"] is None for a in addressees.values() if a["agency"] != "rzn")
    assert all(not personal(json.dumps(a, ensure_ascii=False)) for a in addressees.values())


@pytest.mark.parametrize("region", sorted(GOLD["renamed"]))
def test_renamed(addressees, region):
    a = addressees[f"{region.lower()}-rzn"]
    assert a["name"] == GOLD["renamed"][region]["name"]
    assert a["name_hotlines"] == GOLD["renamed"][region]["name_hotlines"]


def test_lta_sources_row():
    sources = (ROOT / "raw" / "SOURCES.tsv").read_text(encoding="utf-8")
    assert GOLD["sha256"] in sources and GOLD["source"] in sources
