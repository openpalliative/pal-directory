import json
import sys
from pathlib import Path

from opsite.data import make_envelope

from pipeline import merge

META = {"version": "2026.10.11", "data_date": "2026-10-11"}
GENERATED = "2026-10-11T12:00:00Z"
SYNTHETIC = [{"id": "synthetic", "title": "Пример на выдуманных данных"}]


def line(id_, region, agency, agency_name, display, tel, kind, topic, hours, round_clock, topics, audience,
         ext="", raw=None, shared=()):
    return {
        "id": id_, "region_id": region, "agency": agency, "agency_name": agency_name, "number_raw": raw or display,
        "number_display": display, "tel": tel, "ext_text": ext, "kind": kind, "topic_text": topic,
        "hours_text": hours, "is_24x7": round_clock, "topics": topics, "audience": audience,
        "shared_with": list(shared), "source_row": 0,
        "source_text": " ".join(x for x in (raw or display, f"- {topic}" if topic else "", hours,
                                            "(круглосуточно)" if round_clock else "") if x),
        "assured_date": "2026-03-03",
    }


def lines() -> list[dict]:
    raw = [
        line("ru-kgd-minzdrav-80000000001", "RU-KGD", "minzdrav", "Министерство здравоохранения (пример)",
             "8 (000) 000-00-01", "+70000000001", "landline", "по вопросам обезболивания и паллиативной помощи (пример)",
             "", True, ["pain", "pmp"], "adults"),
        line("ru-kgd-rzn-80000000002", "RU-KGD", "rzn", "Территориальный орган Росздравнадзора (пример)",
             "8 (000) 000-00-02", "+70000000002", "landline", "", "с 9:00 до 18:00", False, ["general"], "all"),
        line("ru-kgd-tfoms-80000000003", "RU-KGD", "tfoms", "Территориальный фонд ОМС (пример)", "8 (000) 000-00-03",
             "+70000000003", "tollfree", "горячая линия", "", False, ["general"], "all", shared=["RU-IRK"]),
        line("ru-kgd-tfoms-80000000004", "RU-KGD", "tfoms", "Территориальный фонд ОМС (пример)", "8 (000) 000-00-04",
             "+70000000004", "landline", "директор (пример)", "", False, ["staff"], "all"),
        line("ru-irk-minzdrav-122", "RU-IRK", "minzdrav", "Министерство здравоохранения (пример)", "122", "122",
             "short", "", "", False, ["general"], "all", ext="цифра 5", raw="122 (цифра 5)"),
        line("ru-irk-tfoms-80000000003", "RU-IRK", "tfoms", "Территориальный фонд ОМС (пример)", "8 (000) 000-00-03",
             "+70000000003", "tollfree", "горячая линия", "", False, ["general"], "all", shared=["RU-KGD"]),
    ]
    return [merge.enrich(x, None, origin="synthetic", source_ref="synthetic") for x in raw]


def regions(items: list[dict]) -> list[dict]:
    base = [("RU-KGD", "Калининградская область", "Калининград", [], "ru-kgd", None, "region39", 1),
            ("RU-IRK", "Иркутская область", "Иркутск", ["Приангарье"], None, None, "region38", 0),
            ("RU-MOW", "Москва", "Москва", ["Мск"], None, "ru-mow", "region77", 0),
            ("RU-CHU", "Чукотский автономный округ", "Анадырь", ["Чукотка"], None, None, "region87", 0)]
    gaps = {"RU-CHU": [{"agency": "minzdrav", "kind": "malformed", "text_verbatim": "8 (000) 00-00-00", "source_row": 1}]}
    out = []
    for iso, name, cap, aliases, route, router, block, acts in base:
        own = [x for x in items if x["region_id"] == iso and not x["hidden"]]
        missing = iso == "RU-MOW"
        out.append({"id": iso, "slug": iso.lower(), "name": name, "name_source": name, "name_genitive": "",
                    "name_dative": "", "aliases": aliases, "capital": cap, "oktmo": None, "route": route,
                    "router": router, "pravo_block": block, "acts": acts,
                    "has_pain_pmp": any({"pain", "pmp"} & set(x["topics"]) for x in own), "lines": len(own),
                    "source_gaps": gaps.get(iso, []), "rzn_missing": missing,
                    "rzn_missing_reason": "Строки территориального органа в источнике нет (пример)" if missing else None,
                    "source_ref": "synthetic", "verified": True, "verified_at": "2026-10-11"})
    return out


def addressees(items: list[dict]) -> list[dict]:
    agencies = [{"region_id": r, "agency": a, "agency_name": n} for r, a, n in [
        ("RU-KGD", "minzdrav", "Министерство здравоохранения (пример)"),
        ("RU-KGD", "rzn", "Территориальный орган Росздравнадзора (пример)"),
        ("RU-KGD", "tfoms", "Территориальный фонд ОМС (пример)"),
        ("RU-IRK", "minzdrav", "Министерство здравоохранения (пример)")]]
    lta = [{"region_ids": "RU-KGD", "name": "Территориальный орган Росздравнадзора по области (пример)",
            "postal_address": "000000, Россия, город, улица, дом 1 (пример)", "email": "info@reg00.roszdravnadzor.gov.ru",
            "hours_text": "пн-чт 9:00-18:00, пт 9:00-16:45 (пример)"}]
    return merge.addressees(agencies, items, {"RU-KGD": "ru-kgd", "RU-IRK": "ru-irk"}, "synthetic", "2026-10-11",
                            lta, "20261001", "2026-10-11")


def federal() -> list[dict]:
    return [{"id": "rzn-hotline", "number": "8 (000) 000-00-09", "tel": "+70000000009",
             "label": "Горячая линия (пример)", "is_24x7": False, "hours_text": "",
             "quote_verbatim": "Горячая линия (пример) - 8 (000) 000-00-09", "source_url": "https://example.org/",
             "retrieved_at": "2026-10-11", "source_ref": "synthetic", "verified": False, "verified_at": None}]


def routers() -> list[dict]:
    return [{"id": "ru-mow", "region_ids": ["RU-MOW"], "title": "Центр паллиативной помощи (пример)", "operator": "gov",
             "url": "https://example.org/", "number": "8 (000) 000-00-10", "tel": "+70000000010",
             "number_label": "диспетчерская (пример)", "not_affiliated": True,
             "source_title": "Пример на выдуманных данных", "source_url": "https://example.org/",
             "retrieved_at": "2026-10-11", "source_ref": "synthetic", "verified": False, "verified_at": None}]


def routes() -> list[dict]:
    return [{
        "id": "ru-kgd", "region_id": "RU-KGD", "title": "Калининградская область: кто оказывает паллиативную помощь взрослым",
        "audience": "adults", "districts": [], "amended_by": [],
        "related_acts": [{"eoNumber": "0000000000000001", "number": "1", "date": "2026-01-26", "title": "Приказ (пример)",
                          "url": "http://publication.pravo.gov.ru/document/0000000000000001", "note": "для детей (пример)"}],
        "scan_checked_pages": [1],
        "act": {"title": "Приказ (пример)", "number": "0", "date": "2026-09-09", "eoNumber": "0000000000000000",
                "url": "http://publication.pravo.gov.ru/document/0000000000000000"},
        "quotes": [{"point": "прил. 1, п. 1", "text_verbatim": "Текст пункта (пример).", "page": 1, "verified": False,
                    "scan_checked_at": "2026-10-12"}],
        "units": [{"n": 1, "table": "ambulatory", "org": "Больница № 1 (пример)", "unit": "1 кабинет ПМП", "page": 1,
                   "ocr_fixed": False, "scan_checked_at": "2026-10-12", "verified": False},
                  {"n": 1, "table": "inpatient", "org": "Больница № 2 (пример)", "unit": "1 отделение ПМП", "page": 1,
                   "ocr_fixed": True, "scan_checked_at": None, "verified": False}],
        "omitted": "Приложения к правилам здесь не приводятся (пример)",
        "source_ref": "synthetic", "verified": False, "verified_at": None}]


def entrypoints() -> list[dict]:
    base = {"audience": ["family", "org"], "offline": False, "maturity": "demo", "verified": False, "verified_at": None}
    return [{**base, "id": "regions", "title": "Куда звонить в регионе", "summary": "Пример", "path": "",
             "situations": ["who-to-call"], "printable": True},
            {**base, "id": "federal", "title": "Номера по всей стране", "summary": "Пример", "path": "federal/",
             "situations": ["who-to-call"], "printable": True},
            {**base, "id": "routes", "title": "Маршрут (пример)", "summary": "Пример", "path": "routes/ru-kgd/",
             "situations": ["who-to-call"], "printable": False}]


def region_acts() -> list[dict]:
    base = {"region_id": "RU-KGD", "act_type": "Приказ", "authority": "Министерства здравоохранения (пример)",
            "pages": 1, "kind_checked": False, "words": ["паллиативной"], "source_ref": "pravo-api",
            "retrieved_at": "2026-10-11", "verified": True, "verified_at": "2026-10-11"}
    return [{**base, "id": "0000000000000002", "number": "2", "doc_date": "2026-09-09", "publish_date": "2026-09-10",
             "title": "Об оказании паллиативной медицинской помощи (пример)",
             "url": "http://publication.pravo.gov.ru/document/0000000000000002", "kind": "organization"},
            {**base, "id": "0000000000000003", "number": "3", "doc_date": "2025-03-04", "publish_date": "2025-03-06",
             "title": "О порядке возмещения иному субъекту (пример)", "act_type": "Закон",
             "url": "http://publication.pravo.gov.ru/document/0000000000000003", "kind": "reimbursement"}]


def build() -> dict[str, dict]:
    from pipeline.export import SCHEMA_VERSIONS, STALE
    items = lines()
    data = {"regions": regions(items), "region-lines": items, "addressees": addressees(items), "federal-lines": federal(),
            "routers": routers(), "routes": routes(), "entrypoints": entrypoints(), "region-acts": region_acts()}
    out = {}
    for name, its in data.items():
        env = make_envelope(dataset=name, repo="pal-directory", items=its, source=SYNTHETIC, meta=META,
                            schema_version=SCHEMA_VERSIONS.get(name, "1.0.0"), license="CC0-1.0",
                            stale_after_days=STALE.get(name, 90))
        env["generated_at"] = GENERATED
        out[name] = env
    return out


def main() -> int:
    target = Path("tests/fixtures")
    target.mkdir(parents=True, exist_ok=True)
    for name, env in build().items():
        (target / f"{name}.json").write_text(json.dumps(env, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print(f"Фикстуры записаны в {target}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
