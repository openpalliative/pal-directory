import datetime as dt
import hashlib
import json
import types

import pytest

from opsite.data import read_yaml
from pipeline import net, watch
from pipeline.common import LINES, SNAPSHOT
from pipeline.tests.conftest import ROOT, read_rows, synth_cells, write_xlsx

XLSX_PATH = "/i/upload/files/Главная страница/горячая линия/горячая линия-03.06.2027.xlsx"
TODAY = dt.date(2026, 10, 19)


def page(number="+7 800 550 99 03", href=XLSX_PATH) -> bytes:
    return (f'<html><a href="{href}">Скачать</a><h3>Контакты</h3><div>&laquo;Горячая линия&raquo; Росздравнадзора '
            f'по соблюдению прав граждан в сфере охраны здоровья - <a href="tel:+78005509903">{number}</a></div>'
            "</html>").encode()


def fake_get(body: bytes, page_bytes: bytes | None = None, down=False):
    calls = []

    def get(url, **_):
        net.check_host(net.quote_url(url))
        calls.append(url)
        if down:
            raise net.SourceDown("нет ответа")
        if url.endswith("/tel"):
            return page_bytes or page(), {}
        return body, {"etag": '"x"', "last-modified": "Wed, 03 Jun 2027 07:00:00 GMT"}
    get.calls = calls
    return get


def test_unchanged_file_moves_data_date(tmp_root, monkeypatch):
    snap = json.loads((tmp_root / SNAPSHOT).read_text(encoding="utf-8"))
    body = b"same-bytes"
    snap["sha256"] = hashlib.sha256(body).hexdigest()
    (tmp_root / SNAPSHOT).write_text(json.dumps(snap), encoding="utf-8")
    before = (tmp_root / LINES).read_text(encoding="utf-8")
    rep = watch.run(tmp_root, today=TODAY, get=fake_get(body), cache=tmp_root / "cache")
    assert rep["mode"] == "facts" and rep["review"] == [] and rep["pr"] is None
    assert read_yaml(tmp_root / "data" / "meta.yaml")["data_date"] == "2026-10-19"
    new = json.loads((tmp_root / SNAPSHOT).read_text(encoding="utf-8"))
    assert new["checked_at"] == "2026-10-19" and new["unreachable_weeks"] == 0
    assert (tmp_root / LINES).read_text(encoding="utf-8") == before


def test_hotline_change_goes_to_review(tmp_root):
    snap = json.loads((tmp_root / SNAPSHOT).read_text(encoding="utf-8"))
    snap["sha256"] = hashlib.sha256(b"x").hexdigest()
    (tmp_root / SNAPSHOT).write_text(json.dumps(snap), encoding="utf-8")
    rep = watch.run(tmp_root, today=TODAY, get=fake_get(b"x", page("+7 800 000 00 00")), cache=tmp_root / "cache")
    assert [r["kind"] for r in rep["review"]] == ["phone_changed"]


def test_new_valid_file_makes_pr(tmp_root, tmp_path):
    cells = synth_cells()
    i = next(k for k, c in enumerate(cells) if "53-52-02" in c[2])
    cells[i] = (cells[i][0], cells[i][1], cells[i][2].replace("53-52-02", "53-52-09"))
    body = write_xlsx(tmp_path / "new.xlsx", cells).read_bytes()
    (tmp_root / "data" / "review" / "overrides.csv").write_text(
        "id,topics,audience,topics_checked,hide,note,checked_by,checked_at\nru-kgd-rzn-84012535202,complaints,,true,,,,\n",
        encoding="utf-8")
    meta_before = (tmp_root / "data" / "meta.yaml").read_text(encoding="utf-8")
    rep = watch.run(tmp_root, today=TODAY, get=fake_get(body), cache=tmp_root / "cache")
    assert rep["mode"] == "pr"
    assert rep["pr"]["branch"] == "watch/2026-10-19" and rep["pr"]["labels"] == ["review:data"]
    assert "| RU-KGD |" in rep["pr"]["body"] and "8 (4012) 53-52-09" in rep["pr"]["body"]
    assert "ru-kgd-rzn-84012535202" in rep["pr"]["body"]
    ids = {r["id"] for r in read_rows(tmp_root / LINES)}
    assert "ru-kgd-rzn-84012535209" in ids and "ru-kgd-rzn-84012535202" not in ids
    snap = json.loads((tmp_root / SNAPSHOT).read_text(encoding="utf-8"))
    assert snap["sha256"] == hashlib.sha256(body).hexdigest() and snap["assured_date"] == "2027-06-03"
    assert snap["last_modified"] == "2027-06-03T07:00:00Z" and snap["unchanged_since"] == "2026-10-19"
    assert (tmp_root / "data" / "meta.yaml").read_text(encoding="utf-8") == meta_before


def test_broken_format_goes_to_review(tmp_root, tmp_path):
    body = write_xlsx(tmp_path / "bad.xlsx", synth_cells(), sheet="Лист1").read_bytes()
    before = (tmp_root / LINES).read_text(encoding="utf-8")
    rep = watch.run(tmp_root, today=TODAY, get=fake_get(body), cache=tmp_root / "cache")
    assert rep["mode"] == "facts"
    assert [r["kind"] for r in rep["review"]] == ["format_changed"]
    assert rep["review"][0]["label"] == "watch:format"
    assert (tmp_root / LINES).read_text(encoding="utf-8") == before
    assert json.loads((tmp_root / SNAPSHOT).read_text(encoding="utf-8"))["pending_sha256"]


def test_unreachable_three_weeks(tmp_root):
    kinds = []
    for week in range(3):
        rep = watch.run(tmp_root, today=TODAY + dt.timedelta(days=7 * week), get=fake_get(b"", down=True),
                        cache=tmp_root / "cache")
        kinds.append([r["kind"] for r in rep["review"]])
        assert rep["mode"] == "facts"
    assert kinds == [[], [], ["source_unreachable"]]
    assert json.loads((tmp_root / SNAPSHOT).read_text(encoding="utf-8"))["unreachable_weeks"] == 3


def test_missing_link_counts_as_unreachable(tmp_root):
    rep = watch.run(tmp_root, today=TODAY, get=fake_get(b"x", page(href="/files/other.pdf")), cache=tmp_root / "cache")
    assert rep["facts"] and "источник недоступен" in rep["facts"][0]["what"]


def test_old_source_and_freeze(tmp_root):
    meta = tmp_root / "data" / "meta.yaml"
    meta.write_text(meta.read_text(encoding="utf-8").replace('maintainer_ru_checked_at: ""',
                                                             "maintainer_ru_checked_at: 2026-10-01"), encoding="utf-8")
    rep = watch.run(tmp_root, today=dt.date(2027, 4, 5), get=fake_get(b"", down=True), cache=tmp_root / "cache")
    assert {r["kind"] for r in rep["review"]} == {"old_source", "freeze"}


def test_review_keys_are_stable():
    a = watch.review("old_source", "t", "b", "s")
    b = watch.review("old_source", "t2", "b2", "s")
    assert a["key"] == b["key"] and len(a["key"]) == 12


def test_open_issues_dedupes(tmp_path):
    report = {"review": [watch.review("old_source", "Таблице больше года", "текст", "u1"),
                         watch.review("freeze", "Заморозить", "текст", "u2")]}
    path = tmp_path / "watch.json"
    path.write_text(json.dumps(report, ensure_ascii=False), encoding="utf-8")
    calls = []

    def runner(cmd, **_):
        calls.append(cmd)
        existing = "[]" if report["review"][1]["key"] in " ".join(cmd) else '[{"number": 7}]'
        return types.SimpleNamespace(stdout=existing)
    assert watch.open_issues(path, runner=runner) == 1
    created = [c for c in calls if c[:3] == ["gh", "issue", "create"]]
    assert len(created) == 1 and created[0][-1] == "watch:freeze"
    assert report["review"][1]["key"] in created[0][4]


def test_open_issues_dry_run(tmp_path, capsys):
    path = tmp_path / "watch.json"
    path.write_text(json.dumps({"review": [watch.review("freeze", "Заморозить", "т", "u")]}), encoding="utf-8")
    assert watch.open_issues(path, dry_run=True) == 1
    assert "gh issue create" in capsys.readouterr().out


def acts_root(tmp_root):
    import shutil
    from pipeline import pravo_acts
    shutil.copytree(ROOT / "data" / "routes", tmp_root / "data" / "routes", dirs_exist_ok=True)
    rows = [r for r in read_rows(ROOT / pravo_acts.ACTS) if r["id"] != "3901202609100002"]
    from pipeline.common import write_csv
    write_csv(tmp_root / pravo_acts.ACTS, pravo_acts.FIELDS, rows)
    return rows


def test_acts_watch_new_act_makes_pr_and_route_issue(tmp_root):
    from pipeline import pravo_acts
    from pipeline.tests.test_pravo_acts import FakeApi
    acts_root(tmp_root)
    route_before = (tmp_root / "data" / "routes" / "kgd-678.yaml").read_text(encoding="utf-8")
    api = FakeApi()
    rep = watch.run_acts(tmp_root, today=TODAY, get=api, force=True)
    blocks = {c[1]["Block"] for c in api.calls if c[0] == "/api/Documents"}
    assert not blocks & {"region80", "region81", "region84", "region85", "region91", "region92"}
    assert rep["mode"] == "pr" and rep["pr"]["labels"] == ["review:data"]
    assert "3901202609100002" in rep["pr"]["body"]
    issues = [r for r in rep["review"] if r["kind"] == "route_act"]
    assert len(issues) == 1 and issues[0]["label"] == "watch:route"
    assert "file/pdf?eoNumber=3901202609100002" in issues[0]["body"]
    ids = {r["id"] for r in read_rows(tmp_root / pravo_acts.ACTS)}
    assert "3901202609100002" in ids
    assert (tmp_root / "data" / "routes" / "kgd-678.yaml").read_text(encoding="utf-8") == route_before


def test_acts_watch_amendment_of_route_order():
    routes = watch.route_acts(ROOT)
    act = {"region_id": "RU-KGD", "title": "О внесении изменений в приказ Министерства здравоохранения Калининградской "
                                           "области от 9 сентября 2026 года № 678", "kind": "other"}
    assert watch.touches_route(act, routes)["id"] == "ru-kgd"
    assert watch.touches_route({**act, "title": act["title"].replace("678", "6789")}, routes) is None
    assert watch.touches_route({**act, "region_id": "RU-IRK"}, routes) is None


def test_acts_watch_runs_every_four_weeks(tmp_root):
    from pipeline import pravo_acts
    (tmp_root / pravo_acts.SNAPSHOT).write_text(json.dumps({"retrieved_at": "2026-10-12"}), encoding="utf-8")

    def boom(*a, **k):
        raise AssertionError("сеть не нужна")

    rep = watch.run_acts(tmp_root, today=dt.date(2026, 10, 30), get=boom)
    assert rep["mode"] == "none"
    assert watch.acts_due({"retrieved_at": "2026-10-12"}, dt.date(2026, 11, 9))


def test_acts_watch_no_changes_is_fact(tmp_root):
    from pipeline import pravo_acts
    from pipeline.tests.test_pravo_acts import FakeApi
    res = pravo_acts.collect(FakeApi(), load_regions_for(tmp_root), retrieved="2026-10-12")
    from pipeline.common import write_csv
    write_csv(tmp_root / pravo_acts.ACTS, pravo_acts.FIELDS, pravo_acts.to_csv(res["acts"]))
    rep = watch.run_acts(tmp_root, today=TODAY, get=FakeApi(), force=True)
    assert rep["mode"] == "facts" and rep["pr"] is None and rep["review"] == []


def load_regions_for(root):
    from pipeline.common import load_regions
    return load_regions(root)


def test_merge_reports_one_pr():
    a = {"facts": [1], "review": [], "pr": {"title": "a", "body": "A"}}
    b = {"facts": [], "review": [2], "pr": {"title": "b", "body": "B"}}
    rep = watch.merge_reports("2026-10-19", [a, b])
    assert rep["mode"] == "pr" and rep["pr"]["branch"] == "watch/2026-10-19" and "A" in rep["pr"]["body"]
    assert rep["review"] == [2]


def test_lta_watch(tmp_root):
    from pipeline import fetch_lta
    from pipeline.tests.test_lta import synthetic_rows, to_cp1251
    meta = ("property,value\ndata-20261101-structure-20180925,"
            "https://roszdravnadzor.gov.ru/opendata/7710537160-lta/data-20261101-structure-20180925.csv\n").encode("cp1251")
    rows = synthetic_rows()
    body = to_cp1251(rows)

    def get(url):
        net.check_host(url)
        return (meta, {}) if url.endswith("meta.csv") else (body, {})

    rep = watch.run_lta(tmp_root, today=TODAY, get=get)
    assert rep["mode"] == "pr" and "20261101" in rep["pr"]["title"]
    snap = json.loads((tmp_root / fetch_lta.SNAPSHOT).read_text(encoding="utf-8"))
    assert snap["modified"] == "20261101" and snap["sha256"] == hashlib.sha256(body).hexdigest()
    rep = watch.run_lta(tmp_root, today=TODAY, get=get)
    assert rep["mode"] == "facts" and rep["pr"] is None
