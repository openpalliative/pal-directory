import json
import os
from pathlib import Path

from opsite.data import BuildError, coerce, make_envelope, read_csv, read_yaml

from pipeline import demo, merge, routes_review
from pipeline.common import SNAPSHOT, load_regions, read_json, split_list

REPO = "pal-directory"
NAMES = ["regions", "region-lines", "addressees", "federal-lines", "routers", "routes", "entrypoints", "region-acts"]
RZN_TERMS = "rzn-source-terms"
LICENSES = {"regions": RZN_TERMS, "region-lines": RZN_TERMS, "addressees": RZN_TERMS, "federal-lines": RZN_TERMS,
            "routers": "CC0-1.0", "routes": "public-domain-official-act", "entrypoints": "CC0-1.0",
            "region-acts": "public-domain-official-act"}
SCHEMA_VERSIONS = {"regions": "1.1.0", "addressees": "1.1.0", "routes": "1.1.0", "federal-lines": "1.1.0"}
STALE = {"routes": 365, "region-acts": 120}
RZN_TERMS_TEXT = "на условиях источника, с указанием источника: Росздравнадзор"
ACT_LICENSE = "public domain (ст. 1259 п. 6 ГК РФ, официальные документы)"
PAGE_URL = "https://roszdravnadzor.gov.ru/pages/main/call/to/tel"
LTA_SNAPSHOT = Path("data/snapshots/rzn-lta.json")
ACTS_SNAPSHOT = Path("data/snapshots/pravo-acts.json")
MODES = ("real", "links", "demo")
SYNTHETIC = {"id": "synthetic", "title": "Пример на выдуманных данных"}
ACT_KINDS = {"program", "organization", "routing", "reimbursement", "nutrition", "devices", "subsidy", "other"}


def mode() -> str:
    value = os.environ.get("PD_DATA_MODE", "real")
    if value not in MODES:
        raise BuildError(f"PD_DATA_MODE может быть real, links или demo, а здесь «{value}»")
    return value


def fixtures(root: Path) -> list[dict]:
    return [json.loads((root / "tests" / "fixtures" / f"{n}.json").read_text(encoding="utf-8")) for n in NAMES]


def datasets(root) -> list[dict]:
    root = Path(root)
    if os.environ.get("OP_FIXTURES") == "1" or not (root / "data" / "regions.csv").is_file():
        return fixtures(root)
    return build_all(root, mode())


def schema(root: Path, name: str) -> dict:
    return json.loads((root / "data" / "schema" / f"{name}.schema.json").read_text(encoding="utf-8"))


def item_schema(root: Path, name: str) -> dict:
    return schema(root, name)["properties"]["items"]["items"]


def snapshot(root) -> dict:
    snap = read_json(Path(root) / SNAPSHOT, {}) or {}
    return {k: snap.get(k) for k in ("url", "page_url", "sha256", "etag", "last_modified", "assured_date", "checked_at",
                                     "unchanged_since", "regions_total", "regions_published", "lines", "unreachable_weeks")}


def rzn_source(snap: dict) -> dict:
    out = {"id": "rzn-hotlines", "title": "Росздравнадзор. Номера телефонов «Горячих линий» в субъектах Российской Федерации",
           "url": snap.get("url") or PAGE_URL, "license": RZN_TERMS_TEXT}
    if snap.get("checked_at"):
        out["retrieved_at"] = snap["checked_at"]
    if snap.get("sha256"):
        out["sha256"] = snap["sha256"]
    return out


def lta_source(snap: dict) -> dict | None:
    if not snap.get("url"):
        return None
    return {"id": "rzn-lta", "title": f"Росздравнадзор, открытые данные «Перечень территориальных органов Росздравнадзора» "
                                      f"(набор 7710537160-lta, версия {snap['modified']})",
            "url": snap["url"], "retrieved_at": snap.get("checked_at", ""), "sha256": snap.get("sha256", ""),
            "license": RZN_TERMS_TEXT}


def ru_date(iso: str) -> str:
    return f"{iso[8:10]}.{iso[5:7]}.{iso[:4]}" if len(iso) >= 10 else iso


def rzn_missing_reason(hot: dict, lta: dict) -> str:
    when = ru_date(hot.get("assured_date") or "")
    version = lta.get("modified") or ""
    return (f"В таблице Росздравнадзора от {when} и в открытых данных Росздравнадзора (версия {version}) "
            f"строки территориального органа Росздравнадзора по этому региону нет")


def regions_items(regions: list[dict], lines: list[dict], gaps: list[dict], rzn_regions: set[str],
                  acts: list[dict], reason: str) -> list[dict]:
    out = []
    for r in regions:
        own = [ln for ln in lines if ln["region_id"] == r["id"] and not ln["hidden"]]
        missing = r["id"] not in rzn_regions
        out.append({
            "id": r["id"], "slug": r["slug"], "name": r["name"], "name_source": r["name_source"],
            "name_genitive": r["name_genitive"], "name_dative": r["name_dative"], "aliases": split_list(r["aliases"]),
            "capital": r["capital"], "oktmo": r["oktmo"] or None, "route": r["route"] or None,
            "router": r["router"] or None, "pravo_block": r["pravo_block"] or None,
            "acts": sum(1 for a in acts if a["region_id"] == r["id"]),
            "has_pain_pmp": any({"pain", "pmp"} & set(ln["topics"]) for ln in own), "lines": len(own),
            "source_gaps": [{k: g[k] for k in ("agency", "kind", "text_verbatim", "source_row")}
                            for g in gaps if g["region_id"] == r["id"]],
            "rzn_missing": missing, "rzn_missing_reason": reason if missing else None,
            "source_ref": "rzn-hotlines", "verified": r["verified"] == "true", "verified_at": r["verified_at"] or None,
        })
    return out


def federal(root: Path) -> tuple[list[dict], dict | None]:
    raw = read_yaml(root / "data" / "federal.yaml")
    items = [coerce(x, item_schema(root, "federal-lines")) for x in raw["lines"]]
    search = raw.get("search")
    source = None
    if search:
        source = {"id": "pravo-federal-search", "title": f"Поиск на портале официального опубликования "
                                                          f"{ru_date(search['searched_at'])}: {search['result']}",
                  "url": search["where"], "retrieved_at": search["searched_at"]}
    return items, source


def routers(root: Path) -> tuple[list[dict], list[dict]]:
    items = [coerce(x, item_schema(root, "routers")) for x in read_yaml(root / "data" / "routers.yaml")["routers"]]
    sources = [{"id": x["source_ref"], "title": x["source_title"], "url": x["source_url"],
                "retrieved_at": x["retrieved_at"]} for x in items]
    return items, sources


def routes(root: Path) -> tuple[list[dict], list[dict]]:
    items, sources = [], []
    signatures = routes_review.load(root)
    for p in sorted((root / "data" / "routes").glob("*.yaml")):
        it = coerce(read_yaml(p), item_schema(root, "routes"))
        it = routes_review.apply(it, signatures)
        items.append(it)
        sources.append({"id": it["source_ref"], "title": it["act"]["title"], "url": it["act"]["url"],
                        "eoNumber": it["act"]["eoNumber"], "license": ACT_LICENSE})
    return items, sources


def region_acts(root: Path, published: set[str]) -> tuple[list[dict], dict]:
    path = root / "data" / "pravo" / "region-acts.csv"
    snap = read_json(root / ACTS_SNAPSHOT, {}) or {}
    if not path.is_file():
        return [], snap
    review_path = root / "data" / "review" / "acts.csv"
    review = {}
    for r in read_csv(review_path) if review_path.is_file() else []:
        where = f"data/review/acts.csv, строка {r['_line']}"
        if r["kind"] and r["kind"] not in ACT_KINDS:
            raise BuildError(f"{where}, поле kind: допустимо {', '.join(sorted(ACT_KINDS))}")
        review[r["id"]] = r
    items = []
    for r in read_csv(path):
        if r["region_id"] not in published:
            raise BuildError(f"data/pravo/region-acts.csv, строка {r['_line']}: регион {r['region_id']} не публикуется")
        rv = review.pop(r["id"], None) or {}
        items.append({
            "id": r["id"], "region_id": r["region_id"], "act_type": r["act_type"], "authority": r["authority"],
            "number": r["number"], "doc_date": r["doc_date"], "publish_date": r["publish_date"], "title": r["title"],
            "pages": int(r["pages"] or 0), "url": r["url"], "kind": rv.get("kind") or r["kind"],
            "kind_checked": rv.get("kind_checked") == "true", "words": split_list(r["words"]),
            "source_ref": "pravo-api", "retrieved_at": r["retrieved_at"], "verified": True,
            "verified_at": r["retrieved_at"],
        })
    if review:
        raise BuildError(f"data/review/acts.csv: правки для актов, которых нет в индексе: {', '.join(sorted(review))}")
    return items, snap


def entrypoints(root: Path) -> list[dict]:
    return [coerce(x, item_schema(root, "entrypoints")) for x in read_yaml(root / "data" / "entrypoints.yaml")["items"]]


def envelope(name: str, items: list, source: list, meta: dict, excluded: int = 0) -> dict:
    return make_envelope(dataset=name, repo=REPO, items=items, source=source, meta=meta,
                         schema_version=SCHEMA_VERSIONS.get(name, "1.0.0"), stale_after_days=STALE.get(name, 90),
                         license=LICENSES[name], excluded=excluded)


def build_all(root: Path, data_mode: str) -> list[dict]:
    meta = read_yaml(root / "data" / "meta.yaml")
    regions = load_regions(root)
    snap = read_json(root / SNAPSHOT, {}) or {}
    lta_snap = read_json(root / LTA_SNAPSHOT, {}) or {}
    rzn = rzn_source(snap)
    lta_src = lta_source(lta_snap)
    dropped = snap.get("dropped") or {}
    excluded_regions = dropped.get("excluded_regions", 0)
    excluded_rows = dropped.get("excluded_rows", 0)
    slug = {r["id"]: r["slug"] for r in regions}
    agencies = merge.load_agencies(root)
    lta = merge.load_lta(root)
    if data_mode == "demo":
        raw = demo.synthetic_lines(regions, snap.get("assured_date") or meta["data_date"])
        lines = [merge.enrich(ln, None, origin="synthetic", source_ref="synthetic") for ln in raw]
        lines_source, lines_excluded = [SYNTHETIC], 0
    else:
        lines = merge.region_lines(root)
        lines_source, lines_excluded = [rzn], excluded_rows
    published = [] if data_mode == "links" else lines
    addr = merge.addressees(agencies, published, slug, "rzn-hotlines", meta["data_date"], lta,
                            lta_snap.get("modified"), lta_snap.get("checked_at"))
    rzn_regions = {a["region_id"] for a in addr if a["agency"] == "rzn"}
    acts, acts_snap = region_acts(root, set(slug))
    reason = rzn_missing_reason(snap, lta_snap)
    gaps = merge.load_gaps(root)
    fed_items, fed_search = federal(root)
    router_items, router_sources = routers(root)
    route_items, route_sources = routes(root)
    iso = {"id": "iso-3166-2-ru", "title": "ISO 3166-2:RU, коды субъектов", "url": "https://www.iso.org/obp/ui/#iso:code:3166:RU"}
    page = {"id": "rzn-page", "title": "Росздравнадзор, страница «Горячие линии», блок «Контакты»", "url": PAGE_URL,
            "retrieved_at": snap.get("page_checked_at") or "2026-10-11", "license": RZN_TERMS_TEXT}
    pravo = {"id": "pravo-api", "title": "Официальный интернет-портал правовой информации, API публикаций по субъектам",
             "url": "http://publication.pravo.gov.ru/api/Documents", "retrieved_at": acts_snap.get("retrieved_at", ""),
             "license": ACT_LICENSE}
    addr_sources = [rzn] + ([lta_src] if lta_src else [])
    lta_excluded = lta_snap.get("excluded_rows", 0)
    return [
        envelope("regions", regions_items(regions, lines, gaps, rzn_regions, acts, reason), [rzn, iso, pravo], meta,
                 excluded_regions),
        envelope("region-lines", published, lines_source, meta, lines_excluded),
        envelope("addressees", addr, addr_sources, meta, excluded_rows + lta_excluded),
        envelope("federal-lines", fed_items, [page] + ([fed_search] if fed_search else []), meta),
        envelope("routers", router_items, router_sources, meta),
        envelope("routes", route_items, route_sources, meta),
        envelope("entrypoints", entrypoints(root), [{"id": "pal-directory", "title": "Куда звонить"}], meta),
        envelope("region-acts", acts, [pravo], meta),
    ]
