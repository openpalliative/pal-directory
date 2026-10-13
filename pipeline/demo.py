SAMPLE = [
    ("minzdrav", "Министерство здравоохранения (пример)", "по вопросам обезболивания и паллиативной помощи (пример)",
     "", True, ["pain", "pmp"], "adults", "landline"),
    ("minzdrav", "Министерство здравоохранения (пример)", "по вопросам лекарственного обеспечения (пример)",
     "с 9:00 до 18:00 по будням", False, ["drugs"], "all", "landline"),
    ("rzn", "Территориальный орган Росздравнадзора (пример)", "", "с 9:00 до 18:00", False, ["general"], "all", "landline"),
    ("tfoms", "Территориальный фонд ОМС (пример)", "горячая линия (пример)", "", True, ["general"], "all", "tollfree"),
]


def synthetic_lines(regions: list[dict], assured_date: str) -> list[dict]:
    out, n = [], 0
    for r in regions:
        for agency, agency_name, topic, hours, round_clock, topics, audience, kind in SAMPLE:
            n += 1
            digits = f"{n:07d}"
            display = f"8 (000) {digits[:3]}-{digits[3:5]}-{digits[5:]}"
            source = " ".join(x for x in (display, f"- {topic}" if topic else "", hours,
                                          "(круглосуточно)" if round_clock else "") if x)
            out.append({
                "id": f"{r['slug']}-{agency}-8000{digits}",
                "region_id": r["id"], "agency": agency, "agency_name": agency_name,
                "number_raw": display, "number_display": display, "tel": f"+7000{digits}", "ext_text": "",
                "kind": kind, "topic_text": topic, "hours_text": hours, "is_24x7": round_clock, "topics": topics,
                "audience": audience, "shared_with": [], "source_row": 0, "source_text": source,
                "assured_date": assured_date,
            })
    return out
