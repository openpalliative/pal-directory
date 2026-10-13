import csv
import datetime as dt
import io
import json
import os
import re
from pathlib import Path
from urllib.parse import quote, urlsplit

from markupsafe import Markup

from opsite.data import OPSITE

ISSUE_BASE = "https://github.com/openpalliative/pal-directory/issues/new"
PAGES_ROOT = "https://openpalliative.github.io/pal-directory/"
SAFE = "-_.!~*'()"
SHOWN_TOPICS = {"pain", "pmp", "drugs", "complaints", "general"}
SECTIONS = ("pain", "medical", "complaints")
AGENCIES = ("minzdrav", "rzn", "tfoms")
SOURCE_STALE_DAYS = 365
PRINT_CHECK_DAYS = 90
SPRITE = ("phone", "circle-help", "circle-check", "clock", "external-link", "file-warning")
ACT_ORDER = ("routing", "organization", "program", "reimbursement", "devices", "nutrition", "subsidy", "other")
CSV_SETS = ("region-lines", "addressees")
CARD_ACTS = 5
PAGE_ACTS = 25
MODES = ("real", "links", "demo")


def data_mode() -> str:
    value = os.environ.get("PD_DATA_MODE", "real")
    return value if value in MODES else "real"


def sprite() -> Markup:
    parts = []
    for name in SPRITE:
        svg = (OPSITE / "ui" / "icons" / f"{name}.svg").read_text(encoding="utf-8")
        inner = re.search(r"<svg[^>]*>(.*)</svg>", svg, re.S).group(1).strip()
        parts.append(f'<symbol id="pd-i-{name}" viewBox="0 0 24 24">{inner}</symbol>')
    return Markup('<svg class="pd-sprite" aria-hidden="true" focusable="false">' + "".join(parts) + "</svg>")


def issue_url(region: str, region_name: str, line: str = "", number: str = "", data_version: str = "") -> str:
    title = f"Номер: {region_name}, {number}" if number else f"Номер: {region_name}"
    params = [("template", "wrong-number.yml"), ("title", title), ("region", region), ("line", line),
              ("data_version", data_version)]
    return ISSUE_BASE + "?" + "&".join(f"{k}={quote(v, safe=SAFE)}" for k, v in params if v)


def sort_name(name: str) -> str:
    base = name[len("Республика "):] if name.startswith("Республика ") else name
    return base.lower().replace("ё", "е")


def section_of(line: dict) -> str | None:
    topics = set(line["topics"])
    if line["hidden"] or not topics & SHOWN_TOPICS:
        return None
    if topics & {"pain", "pmp"}:
        return "pain"
    return "medical" if line["agency"] == "minzdrav" else "complaints"


def group_by_agency(lines: list[dict]) -> list[dict]:
    groups: list[dict] = []
    for line in lines:
        if groups and groups[-1]["agency"] == line["agency"] and groups[-1]["name"] == line["agency_name"]:
            groups[-1]["lines"].append(line)
        else:
            groups.append({"agency": line["agency"], "name": line["agency_name"], "lines": [line]})
    return groups


def domain(url: str) -> str:
    host = urlsplit(url).hostname or ""
    return host[4:] if host.startswith("www.") else host


def read_snapshot(root: Path) -> dict:
    path = root / "data" / "snapshots" / "rzn-hotlines.json"
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def source_info(ctx, lines: list[dict]) -> dict:
    snap = read_snapshot(ctx.root)
    env = ctx.data.get("regions") or {}
    src = next((s for s in env.get("source", []) if s.get("id") == "rzn-hotlines"), {})
    real = [ln for ln in lines if ln["origin"] != "synthetic"]
    assured = (real[0]["assured_date"] if real else "") or snap.get("assured_date") or \
        (snap.get("last_modified") or "")[:10]
    checked = snap.get("checked_at") or snap.get("unchanged_since") or ""
    stale = False
    if assured:
        stale = (dt.date.today() - dt.date.fromisoformat(assured)).days > SOURCE_STALE_DAYS
    return {
        "assured_date": assured,
        "checked_at": checked,
        "page_url": snap.get("page_url") or "https://roszdravnadzor.gov.ru/pages/main/call/to/tel",
        "file_url": snap.get("url") or src.get("url") or "",
        "sha256": snap.get("sha256") or src.get("sha256") or "",
        "rows": snap.get("rows"),
        "stale": stale,
    }


def items(ctx, name: str) -> list[dict]:
    env = ctx.data.get(name)
    return env["items"] if env else []


def first(d: dict, *keys: str):
    for k in keys:
        v = d.get(k)
        if v not in (None, "", []):
            return v
    return None


def decorate_line(line: dict, names: dict) -> dict:
    out = dict(line)
    out["shared_names"] = [names[r] for r in line.get("shared_with", []) if r in names]
    out["synthetic"] = line["origin"] == "synthetic"
    hours = (line.get("hours_text") or "").strip()
    out["hours_shown"] = "" if line["is_24x7"] and hours.lower().strip(" .()") == "круглосуточно" else hours
    return out


def addressee(a: dict) -> dict:
    email = first(a, "email") or ""
    return {
        "agency": a["agency"],
        "name": a["name"],
        "name_old": first(a, "name_old", "name_previous", "name_hotlines", "name_table") or "",
        "postal_address": first(a, "postal_address") or "",
        "email": email if email.endswith("roszdravnadzor.gov.ru") else "",
        "hours": first(a, "hours_text", "work_mode", "hours") or "",
        "source_ref": a.get("source_ref", ""),
    }


def gaps_of(region: dict, malformed: list[dict]) -> list[dict]:
    raw = region.get("source_gaps") or [{"agency": m.get("agency") or "", "kind": "malformed", "text": m.get("raw") or ""}
                                        for m in malformed if m.get("region_id") == region["id"]]
    if isinstance(raw, (str, dict)):
        raw = [raw]
    out = []
    for g in raw:
        if isinstance(g, str):
            out.append({"agency": "", "kind": "", "text": g, "note": ""})
        elif isinstance(g, dict):
            text = first(g, "text_verbatim", "text", "quote", "source_text") or ""
            if text:
                out.append({"agency": g.get("agency") or "", "kind": g.get("kind") or "", "text": text,
                            "note": first(g, "note", "reason", "what") or ""})
    grouped: list[dict] = []
    for g in out:
        if grouped and (grouped[-1]["agency"], grouped[-1]["kind"], grouped[-1]["note"]) == (g["agency"], g["kind"], g["note"]):
            grouped[-1]["texts"].append(g["text"])
        else:
            grouped.append({"agency": g["agency"], "kind": g["kind"], "note": g["note"], "texts": [g["text"]]})
    return grouped


def act_key(act: dict):
    kind = act.get("kind") or "other"
    order = ACT_ORDER.index(kind) if kind in ACT_ORDER else len(ACT_ORDER)
    date = act.get("doc_date") or act.get("date") or ""
    return (order, "".join(chr(0x10FFFF - ord(c)) for c in date))


def decorate_act(act: dict) -> dict:
    eo = act.get("eoNumber") or act.get("id") or ""
    return {**act, "eo": eo, "kind": act.get("kind") or "other",
            "date": act.get("doc_date") or act.get("date") or "",
            "href": act.get("url") or (f"http://publication.pravo.gov.ru/document/{eo}" if eo else "")}


def acts_info(ctx) -> dict | None:
    env = ctx.data.get("region-acts")
    if not env:
        return None
    by_region: dict[str, list] = {}
    for act in env["items"]:
        by_region.setdefault(act.get("region_id"), []).append(decorate_act(act))
    for lst in by_region.values():
        lst.sort(key=act_key)
    retrieved = max((a.get("retrieved_at") or "" for a in env["items"]), default="") or env.get("data_date", "")
    return {"by_region": by_region, "total": len(env["items"]), "regions": len(by_region),
            "retrieved_at": retrieved, "data_date": env.get("data_date", "")}


ROUTE_SPLIT = 60
ROUTE_PART = 45
TABLES = ("ambulatory", "home", "inpatient", "children_ambulatory", "children_home", "children_inpatient", "other")


def unit_ref(u: dict) -> str:
    return f"{u['table']} {u['n']}" + (f".{u['part']}" if u.get("part") else "")


def ref_units(refs: list[str], by_ref: dict) -> list[dict]:
    out = []
    for ref in refs:
        found = by_ref.get(ref) or [u for key, u in by_ref.items() if key.startswith(ref + ".")]
        for u in found if isinstance(found, list) else [found]:
            if u not in out:
                out.append(u)
    return out


def group_refs(rows: list[tuple[list[str], str]], by_ref: dict) -> list[dict]:
    groups: dict[tuple, dict] = {}
    for refs, name in rows:
        key = tuple(refs)
        if key not in groups:
            groups[key] = {"units": ref_units(refs, by_ref), "names": []}
        groups[key]["names"].append(name)
    return list(groups.values())


def decorate_route(route: dict) -> dict:
    units = [{**u, "label": f"{u['n']}.{u['part']}" if u.get("part") else str(u["n"])} for u in route["units"]]
    by_ref = {unit_ref(u): u for u in units}
    order = [t for t in TABLES if any(u["table"] == t for u in units)]
    order += sorted({u["table"] for u in units} - set(order))
    tables = [{"key": t, "units": [u for u in units if u["table"] == t]} for t in order]
    districts = group_refs([(d.get("units") or [], d["name"]) for d in route.get("districts") or []], by_ref)
    referrals = group_refs([(r.get("units") or [], r["org"]) for r in route.get("referrals") or []], by_ref)
    rows = len(units) + len(districts) + len(referrals)
    parts = []
    if rows > ROUTE_SPLIT:
        for t in tables:
            for i in range(0, len(t["units"]), ROUTE_PART):
                n = i // ROUTE_PART
                parts.append({"slug": t["key"] + (f"-{n + 1}" if n else ""), "key": t["key"], "kind": "table",
                              "rows": t["units"][i:i + ROUTE_PART], "chunk": n + 1,
                              "chunks": -(-len(t["units"]) // ROUTE_PART)})
        for key, groups in (("districts", districts), ("referrals", referrals)):
            for i in range(0, len(groups), ROUTE_PART):
                n = i // ROUTE_PART
                parts.append({"slug": key + (f"-{n + 1}" if n else ""), "key": key, "kind": "map",
                              "rows": groups[i:i + ROUTE_PART], "chunk": n + 1, "chunks": -(-len(groups) // ROUTE_PART)})
    where = {id(u): part["slug"] for part in parts if part["kind"] == "table" for u in part["rows"]}
    for u in units:
        u["part"] = where.get(id(u), "")
    return {**route, "units": units, "tables": tables, "district_groups": districts, "referral_groups": referrals,
            "parts": parts, "ocr_rows": [u for u in units if u.get("ocr_fixed") and not u.get("scan_checked_at")]}


def entry_maturity(ctx, entry_id: str) -> str:
    return next((e.get("maturity", "") for e in items(ctx, "entrypoints") if e.get("id") == entry_id), "")


def build_regions(ctx) -> tuple[list[dict], dict]:
    regions = sorted(items(ctx, "regions"), key=lambda r: sort_name(r["name"]))
    names = {r["id"]: r["name"] for r in regions}
    lines = [decorate_line(ln, names) for ln in items(ctx, "region-lines")]
    routers = [{**ro, "domain": domain(ro["url"])} for ro in items(ctx, "routers")]
    route_maturity = entry_maturity(ctx, "routes")
    routes: dict[str, list] = {}
    for r in items(ctx, "routes"):
        routes.setdefault(r["region_id"], []).append({**decorate_route(r), "maturity": r.get("maturity") or route_maturity})
    addr: dict[str, dict] = {}
    for a in items(ctx, "addressees"):
        addr.setdefault(a["region_id"], {})[a["agency"]] = addressee(a)
    acts = acts_info(ctx)
    malformed = read_snapshot(ctx.root).get("malformed") or []
    version = (ctx.data.get("region-lines") or ctx.data.get("regions") or {}).get("version", "")
    out = []
    for r in regions:
        own = [ln for ln in lines if ln["region_id"] == r["id"]]
        sections = {key: [] for key in SECTIONS}
        for ln in own:
            key = section_of(ln)
            if key:
                sections[key].append(ln)
        letter = sort_name(r["name"])[0].upper()
        shown = [ln for key in SECTIONS for ln in sections[key]]
        region_addr = addr.get(r["id"], {})
        out.append({
            **r,
            "letter": letter,
            "sections": {k: group_by_agency(v) for k, v in sections.items()},
            "counts": {k: len(v) for k, v in sections.items()},
            "shown": shown,
            "has_pain": bool(sections["pain"]),
            "has_pain_source": bool(r.get("has_pain_pmp")),
            "addr": region_addr,
            "addressees": [region_addr[a] for a in AGENCIES if a in region_addr],
            "rzn_missing": bool(r.get("rzn_missing")) or (bool(region_addr) and "rzn" not in region_addr),
            "rzn_missing_reason": first(r, "rzn_missing_reason", "rzn_missing_note") or "",
            "gaps": [] if data_mode() == "links" else
                    [{**g, "agency_name": region_addr.get(g["agency"], {}).get("name", "")} for g in gaps_of(r, malformed)],
            "routers": [ro for ro in routers if r["id"] in ro["region_ids"]],
            "routes": routes.get(r["id"], []),
            "acts": acts["by_region"].get(r["id"], []) if acts else None,
            "acts_card": (acts["by_region"].get(r["id"], []) if acts else [])[:CARD_ACTS],
            "acts_more": bool(acts) and len(acts["by_region"].get(r["id"], [])) > CARD_ACTS,
            "issue_url": issue_url(r["id"], r["name"], data_version=version),
            "page_url": f"{PAGES_ROOT}regions/{r['slug']}/",
        })
    return out, {"lines": lines, "version": version, "acts": acts}


def letters(regions: list[dict]) -> list[dict]:
    groups: list[dict] = []
    for r in regions:
        if not groups or groups[-1]["letter"] != r["letter"]:
            groups.append({"letter": r["letter"], "anchor": f"pd-l-{len(groups) + 1}", "regions": []})
        groups[-1]["regions"].append(r)
    return groups


def topics_checked(lines: list[dict]) -> dict:
    real = [ln for ln in lines if ln["origin"] != "synthetic"]
    return {"total": len(real), "checked": sum(1 for ln in real if ln.get("topics_checked"))}


def context(ctx) -> dict:
    regions, meta = build_regions(ctx)
    lines = meta["lines"]
    mode = data_mode()
    demo = any(ln["synthetic"] for ln in lines) or mode == "demo"
    links = mode == "links" and not demo
    src = source_info(ctx, lines)
    today = dt.date.today()
    rl_env = ctx.data.get("region-lines") or {}
    ours = {sid for e in items(ctx, "entrypoints") for sid in e.get("situations", [])}
    situations = {s["id"]: s["title"] for s in ctx.situations if s.get("id") in ours}
    all_routes = [rt for r in regions for rt in r["routes"]]
    return {
        "pd": {
            "regions": regions,
            "letters": letters(regions),
            "mode": mode,
            "demo": demo,
            "links": links,
            "source": src,
            "version": meta["version"],
            "federal": items(ctx, "federal-lines"),
            "routes": all_routes,
            "route_regions": {r["id"]: r for r in regions if r["routes"]},
            "routers": items(ctx, "routers"),
            "entrypoints": items(ctx, "entrypoints"),
            "acts": meta["acts"],
            "excluded": (rl_env.get("counts") or {}).get("excluded", 0),
            "with_pain": sum(1 for r in regions if r["has_pain"] or (links and r["has_pain_source"])),
            "lines_total": len(lines),
            "lines_shown": sum(len(r["shown"]) for r in regions),
            "topics": topics_checked(lines),
            "rzn_addresses": sum(1 for r in regions if r["addr"].get("rzn", {}).get("postal_address")),
            "print_until": (today + dt.timedelta(days=PRINT_CHECK_DAYS)).isoformat(),
            "situations_json": json.dumps(situations, ensure_ascii=False),
            "datasets": sorted(ctx.data.values(), key=lambda e: e["dataset"]),
            "csv": [n for n in CSV_SETS if n in ctx.data],
            "issue_base": ISSUE_BASE,
            "sprite": sprite(),
        }
    }


def csv_value(value) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, list):
        return ";".join(str(v) for v in value)
    if value is None:
        return ""
    return str(value)


def write_csv(ctx) -> None:
    out = ctx.out / "data" / "v1"
    out.mkdir(parents=True, exist_ok=True)
    for name in CSV_SETS:
        env = ctx.data.get(name)
        if not env:
            continue
        schema = json.loads((ctx.root / "data" / "schema" / f"{name}.schema.json").read_text(encoding="utf-8"))
        fields = list(schema["properties"]["items"]["items"]["properties"])
        buf = io.StringIO()
        w = csv.writer(buf, lineterminator="\r\n")
        w.writerow(fields)
        for it in env["items"]:
            w.writerow([csv_value(it.get(f)) for f in fields])
        (out / f"{name}.csv").write_text("﻿" + buf.getvalue(), encoding="utf-8")


def pages(ctx):
    pd = ctx.site["pd"]
    write_csv(ctx)
    for r in pd["regions"]:
        yield f"regions/{r['slug']}/", "region.html.j2", {"region": r}
        if r["acts_more"]:
            chunks = [r["acts"][i:i + PAGE_ACTS] for i in range(0, len(r["acts"]), PAGE_ACTS)]
            paths = [f"regions/{r['slug']}/documents/" + (f"{n + 1}/" if n else "") for n in range(len(chunks))]
            for n, chunk in enumerate(chunks):
                yield paths[n], "documents.html.j2", {
                    "region": r, "acts": chunk, "first_n": n * PAGE_ACTS + 1, "pages_total": len(chunks),
                    "page_n": n + 1, "prev_path": paths[n - 1] if n else "",
                    "next_path": paths[n + 1] if n + 1 < len(chunks) else ""}
    yield "regions/", "regions.html.j2", {}
    yield "routes/", "routes.html.j2", {}
    regions = {r["id"]: r for r in pd["regions"]}
    for route in pd["routes"]:
        base = {"route": route, "region": regions.get(route["region_id"]), "draft": "legal"}
        yield f"routes/{route['id']}/", "route.html.j2", {**base, "part": None,
                                                          "page_url": f"{PAGES_ROOT}routes/{route['id']}/"}
        for i, part in enumerate(route["parts"]):
            yield f"routes/{route['id']}/{part['slug']}/", "route.html.j2", {
                **base, "part": part, "page_url": f"{PAGES_ROOT}routes/{route['id']}/{part['slug']}/",
                "prev_part": route["parts"][i - 1] if i else None,
                "next_part": route["parts"][i + 1] if i + 1 < len(route["parts"]) else None}
