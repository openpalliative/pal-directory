import pytest

from opsite.data import BuildError
from pipeline import merge
from pipeline.tests.conftest import ROOT

HEAD = "id,topics,audience,topics_checked,hide,note,checked_by,checked_at\n"


def write(root, body):
    (root / "data" / "review" / "overrides.csv").write_text(HEAD + body, encoding="utf-8")


def test_committed_overrides_have_no_orphans():
    merge.region_lines(ROOT)


def test_orphan_override_fails(tmp_root):
    write(tmp_root, "ru-kgd-rzn-80000000000,pain,,true,,,,\n")
    with pytest.raises(BuildError, match="правка для пропавшего номера ru-kgd-rzn-80000000000"):
        merge.region_lines(tmp_root)


def test_bad_topic_fails(tmp_root):
    write(tmp_root, "ru-kgd-rzn-84012535202,urgent,,,,,,\n")
    with pytest.raises(BuildError, match="topics"):
        merge.region_lines(tmp_root)


def test_override_applies(tmp_root):
    write(tmp_root, "ru-kgd-rzn-84012535202,complaints,adults,true,,сверено по подписи,curator,2026-10-11\n"
                    "ru-kgd-tfoms-84012313555,,,,false,,,\n"
                    "ru-kgd-tfoms-88002509122,,,,true,,,\n")
    by_id = {x["id"]: x for x in merge.region_lines(tmp_root)}
    a = by_id["ru-kgd-rzn-84012535202"]
    assert a["topics"] == ["complaints"] and a["audience"] == "adults" and a["topics_checked"] is True
    assert a["roles"] == ["rzn"] and a["verified"] is False
    assert by_id["ru-kgd-tfoms-84012313555"]["hidden"] is False
    assert by_id["ru-kgd-tfoms-88002509122"]["hidden"] is True


def test_staff_and_other_hidden_by_default():
    lines = merge.region_lines(ROOT)
    for ln in lines:
        assert ln["hidden"] == (set(ln["topics"]) <= {"other", "staff"})


def test_keyword_lines_are_reviewed():
    import re
    from pipeline.tests.conftest import read_rows
    keywords = re.compile(r"обезбол|паллиат|лекарств|жалоб|ВМП|ковид|коронав|вакцин|оплат", re.I)
    reviewed = {r["id"]: r for r in read_rows(ROOT / "data" / "review" / "overrides.csv")}
    for ln in read_rows(ROOT / "data" / "rzn" / "lines.csv"):
        if keywords.search(ln["topic_text"]):
            assert ln["id"] in reviewed, f"{ln['id']}: тема не проверена человеком"
    for r in reviewed.values():
        if r["topics_checked"] == "true":
            assert r["checked_by"] and re.fullmatch(r"\d{4}-\d{2}-\d{2}", r["checked_at"]) and r["topics"], r["id"]
