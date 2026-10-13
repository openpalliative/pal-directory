import pytest

from pipeline import parse_rzn
from pipeline.common import load_regions
from pipeline.parse_rzn import FormatError, Stats
from pipeline.tests.conftest import ROOT, synth_cells, write_xlsx


@pytest.fixture(scope="module")
def regions():
    return load_regions(ROOT)


def parse(path, regions):
    return parse_rzn.parse(path, regions, "2026-03-03")


def test_synthetic_full_table(tmp_path, regions):
    res = parse(write_xlsx(tmp_path / "t.xlsx", synth_cells()), regions)
    assert res["regions_total"] == 83
    assert len(res["lines"]) >= 380
    assert {ln["region_id"] for ln in res["lines"]} == {r["id"] for r in regions}
    assert res["counts"]["excluded_rows"] == 0


@pytest.mark.parametrize("kwargs, needle", [
    ({"sheet": "Лист1"}, "нет листа"),
    ({"extra_col": True}, "лишние столбцы"),
    ({"drop_first_region": True}, "не указан регион"),
])
def test_format_breaks(tmp_path, regions, kwargs, needle):
    path = write_xlsx(tmp_path / "t.xlsx", synth_cells(), **kwargs)
    with pytest.raises(FormatError, match=needle):
        parse(path, regions)


def test_too_few_numbers(tmp_path, regions):
    cells = [(n, a, "8 (000) 000-00-00" if i % 3 == 0 else "нет") for i, (n, a, c) in enumerate(synth_cells())]
    with pytest.raises(FormatError, match="ожидалось не меньше"):
        parse(write_xlsx(tmp_path / "t.xlsx", cells), regions)


def test_unknown_region(tmp_path, regions):
    cells = synth_cells()
    cells[0] = ("Новая область", cells[0][1], cells[0][2])
    with pytest.raises(FormatError, match="не найден в data/regions.csv"):
        parse(write_xlsx(tmp_path / "t.xlsx", cells), regions)


def test_not_xlsx(tmp_path, regions):
    p = tmp_path / "t.xlsx"
    p.write_text("<html>ошибка</html>", encoding="utf-8")
    with pytest.raises(FormatError, match="не читается"):
        parse(p, regions)


@pytest.mark.parametrize("text, tels", [
    ("8 (4012) 53-52-02 \n8 (4012) 53-52-01", ["+74012535202", "+74012535201"]),
    ("8 (498) 602\u201303\u201303", ["+74986020303"]),
    ("(4722) 73-20-03 (добавочный-31-00-1) - по вопросам", ["+74722732003"]),
    (" +7 919 362 17 45 \u2014 обращения", ["+79193621745"]),
    ("8-800-100-43-03", ["+78001004303"]),
    ("8 351 240 22 22 (доб. 101)", ["+73512402222"]),
    ("122, доб. 3 ", ["122"]),
    ("пн - чт: 8:30 - 17:30, пт 8:30 - 16:30", []),
    ("на период с 31.12.2022 по 08.01.2023, с 9:00 до 18:00", []),
])
def test_find_numbers(text, tels):
    got = [s["tel"] for ln in parse_rzn.split_lines(text) for s in parse_rzn.find_numbers(ln)]
    assert got == tels


def test_malformed_number_is_reported():
    stats = Stats()
    items, _ = parse_rzn.group_cell("8(871) 22-38-13\n8 (800) 100-00-00", stats, {"region_id": "RU-XX"})
    assert [i.tel for i in items] == ["+78001000000"]
    assert stats.malformed == [{"region_id": "RU-XX", "raw": "8(871) 22-38-13"}]


@pytest.mark.parametrize("text, want", [
    ("(круглосуточно)", True),
    ("- круглосуточно", True),
    ("(круглосуточный)", True),
    ("(работает круглосуточно, в том числе в выходные и праздничные дни)", True),
    ("с 17-00 до 08-00, круглосуточно в выходные и праздничные дни", False),
    ("в выходные дни, 24 часа", False),
])
def test_round_clock(text, want):
    assert parse_rzn.is_24x7(text) is want


def test_heading_applies_to_group():
    cell = ("Горячая линия по лекарственному обеспечению: \n8 (8442)95-15-13; \n8 (8442) 95-15-20  \n"
            "с 08-00 до 17-00, круглосуточно в выходные и праздничные дни\n\n"
            "Горячая линия по вопросам обезболивания: \n8 (8442) 59-85-75 (круглосуточно)")
    stats = Stats()
    items, lines = parse_rzn.group_cell(cell, stats, {})
    ctx = {"region_id": "RU-VGG", "agency": "minzdrav", "agency_name": "x", "row": 1, "assured_date": "2026-03-03"}
    rows = [parse_rzn.finalize(i, lines, ctx) for i in items]
    assert [r["topic_text"] for r in rows] == ["Горячая линия по лекарственному обеспечению"] * 2 + [
        "Горячая линия по вопросам обезболивания"]
    assert [r["is_24x7"] for r in rows] == [False, False, True]
    assert rows[0]["hours_text"].startswith("с 08-00 до 17-00")
    assert rows[2]["topics"] == ["pain"]


def test_privacy_scrub():
    stats = Stats()
    lines = parse_rzn.scrub(["8 (800) 100-50-90", "irotfoms@irkoms.ru Есть телефоны филиалов",
                             "ответственные сотрудники: Иванова Мария Петровна 8 (863) 000-00-00",
                             "8 (800) 000-00-01"], stats)
    assert lines == ["8 (800) 100-50-90", "Есть телефоны филиалов"]
    assert stats.email == 1 and stats.personal == 2


@pytest.mark.parametrize("raw, tel, want", [
    ("8 (4842) 719-002", "+74842719002", "8 (4842) 71-90-02"),
    ("8 3852 50 71 14", "+73852507114", "8 (3852) 50-71-14"),
    ("8 (812) 63-555-64", "+78126355564", "8 (812) 635-55-64"),
    ("8(4942) 399000", "+74942399000", "8 (4942) 39-90-00"),
    ("8 (800) 2222-905", "+78002222905", "8 (800) 222-29-05"),
    ("122", "122", "122"),
])
def test_display(raw, tel, want):
    assert parse_rzn.display(raw, tel) == want


@pytest.mark.parametrize("name, want", [
    ("Территориальный орган Росздравнадзора по Алтайскому краю", "rzn"),
    ("Территориальный фонд ОМС Пермского края", "tfoms"),
    ("Обязательное медицинское страхование по Чеченской Республике", "tfoms"),
    ("ТЕРРИТОРИАЛЬНЫЙ ФОНД ОБЯЗАТЕЛЬНОГО МЕДИЦИНСКОГО СТРАХОВАНИЯ РОСТОВСКОЙ ОБЛАСТИ", "tfoms"),
    ("Комитет здравоохранения Волгоградской области", "minzdrav"),
])
def test_agency(name, want):
    assert parse_rzn.agency_of(name) == want


def test_expired_period_is_other():
    assert parse_rzn.topics_of("", "на период с 31.12.2022 по 08.01.2023", "2026-03-03") == ["other"]
    assert parse_rzn.topics_of("директор", "", "2026-03-03") == ["staff"]
    assert parse_rzn.topics_of("", "", "2026-03-03") == ["general"]


@pytest.mark.parametrize("raw, kind", [
    ("8 (804) 700-91-03", "tollfree"),
    ("8 (800) 550-99-03", "tollfree"),
    ("8 (812) 703-73-73", "landline"),
    ("8 (921) 123-45-67", "mobile"),
    ("122", "short"),
])
def test_tollfree_codes(raw, kind):
    spans = parse_rzn.find_numbers(raw)
    assert len(spans) == 1
    assert parse_rzn.kind_of(spans[0]["tel"]) == kind
