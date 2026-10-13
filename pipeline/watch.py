import argparse
import datetime as dt
import email.utils
import hashlib
import json
import re
import subprocess
import sys
import urllib.parse
from pathlib import Path

from opsite.data import read_csv, read_yaml

from pipeline import fetch_lta, fetch_rzn, net, parse_rzn, pravo_acts
from pipeline.common import LINES, SNAPSHOT, load_regions, read_json, write_csv, write_json

UNREACHABLE_WEEKS = 3
OLD_SOURCE_DAYS = 365
FREEZE_DAYS = 180
ACTS_EVERY_DAYS = 28
LABELS = {"source_unreachable": "watch:unreachable", "format_changed": "watch:format",
          "old_source": "watch:old-source", "freeze": "watch:freeze", "phone_changed": "review:data",
          "route_act": "watch:route", "acts_unreachable": "watch:unreachable", "lta_changed": "review:data"}


def iso_http_date(value: str) -> str:
    if not value:
        return ""
    try:
        d = email.utils.parsedate_to_datetime(value)
    except (TypeError, ValueError):
        return value
    return d.astimezone(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def review(kind: str, title: str, body: str, source: str) -> dict:
    key = hashlib.sha256(f"{kind}{source}".encode()).hexdigest()[:12]
    return {"kind": kind, "title": title, "body": body, "source": source, "key": key, "label": LABELS[kind]}


def set_data_date(root: Path, day: str) -> None:
    path = root / "data" / "meta.yaml"
    text = path.read_text(encoding="utf-8")
    path.write_text(re.sub(r"(?m)^data_date: .*$", f"data_date: {day}", text), encoding="utf-8")


def lines_by_region(rows: list[dict]) -> dict[str, dict[str, str]]:
    out: dict[str, dict[str, str]] = {}
    for r in rows:
        out.setdefault(r["region_id"], {})[r["tel"]] = r.get("number_display", r["tel"])
    return out


def diff_table(old: list[dict], new: list[dict]) -> tuple[str, int]:
    a, b = lines_by_region(old), lines_by_region(new)
    rows, changed = [], 0
    for reg in sorted(set(a) | set(b)):
        was, now = a.get(reg, {}), b.get(reg, {})
        gone = [was[t] for t in sorted(set(was) - set(now))]
        added = [now[t] for t in sorted(set(now) - set(was))]
        if gone or added:
            changed += 1
            rows.append(f"| {reg} | {len(was)} | {len(now)} | {', '.join(gone) or '-'} | {', '.join(added) or '-'} |")
    head = "| Регион | Было номеров | Стало | Пропал | Новый номер |\n|---|---|---|---|---|"
    return (head + "\n" + "\n".join(rows)) if rows else "Номера не изменились, поменялись только подписи или часы", changed


def orphans(root: Path, new_ids: set[str]) -> list[str]:
    path = root / "data" / "review" / "overrides.csv"
    return [r["id"] for r in (read_csv(path) if path.is_file() else []) if r["id"] not in new_ids]


def check_age(snap: dict, meta: dict, today: dt.date, out: list[dict]) -> None:
    lm = snap.get("last_modified", "")
    if lm and (today - dt.date.fromisoformat(lm[:10])).days > OLD_SOURCE_DAYS:
        out.append(review("old_source", "Таблице Росздравнадзора больше года",
                          f"Файл на сайте не менялся с {lm[:10]}. Номера могли устареть, нужна сверка мейнтейнером в РФ",
                          snap.get("url", "")))
    mc = meta.get("maintainer_ru_checked_at", "")
    if mc and (today - dt.date.fromisoformat(mc[:10])).days > FREEZE_DAYS:
        out.append(review("freeze", "Нет мейнтейнера в РФ 6 месяцев: заморозить данные",
                          f"Последняя отметка мейнтейнера в РФ {mc}. Решение о заморозке за мейнтейнерами",
                          "data/meta.yaml"))


def unreachable(root: Path, snap: dict, report: dict, err: Exception, day: str) -> dict:
    snap["unreachable_weeks"] = int(snap.get("unreachable_weeks", 0)) + 1
    snap["last_attempt_at"] = day
    write_json(root / SNAPSHOT, snap)
    report["facts"].append({"path": str(SNAPSHOT), "what": f"источник недоступен: {err}", "source": fetch_rzn.PAGE_URL})
    if snap["unreachable_weeks"] >= UNREACHABLE_WEEKS:
        report["review"].append(review("source_unreachable", "Источник недоступен, нужен раннер в РФ",
                                       f"Страница Росздравнадзора не отвечает {snap['unreachable_weeks']} недели подряд. "
                                       "Задайте переменную WATCH_RUNNER с раннером мейнтейнера в РФ",
                                       fetch_rzn.PAGE_URL))
    report["mode"] = "facts"
    return report


def check_hotline(root: Path, got: dict, report: dict) -> None:
    fed = read_yaml(root / "data" / "federal.yaml")["lines"]
    want = next((x["number"] for x in fed if x["id"] == "rzn-hotline"), "")
    if got["hotline"] is None or re.sub(r"\D", "", got["hotline"]) != re.sub(r"\D", "", want):
        report["review"].append(review("phone_changed", "Номер горячей линии Росздравнадзора на странице изменился",
                                       f"В data/federal.yaml: {want}. На странице: {got['hotline'] or 'не найден'}",
                                       fetch_rzn.PAGE_URL))


def new_file(root: Path, snap: dict, got: dict, report: dict, day: str, cache: Path) -> None:
    name = Path(urllib.parse.unquote(urllib.parse.urlsplit(got["url"]).path)).name
    target = cache / name
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(got["body"])
    regions = load_regions(root)
    try:
        res = parse_rzn.parse(target, regions, parse_rzn.assured_from(target, day))
    except parse_rzn.FormatError as e:
        snap.update({"last_attempt_at": day, "pending_sha256": got["sha256"]})
        write_json(root / SNAPSHOT, snap)
        report["review"].append(review("format_changed", "Формат таблицы Росздравнадзора изменился",
                                       f"{e}. Новый файл: {got['url']}, sha256 {got['sha256']}. Данные на сайте не менялись",
                                       got["url"] + got["sha256"]))
        report["mode"] = "facts"
        return
    old = read_csv(root / LINES) if (root / LINES).is_file() else []
    table, changed = diff_table(old, res["lines"])
    lost = orphans(root, {ln["id"] for ln in res["lines"]})
    source = {"url": got["url"], "etag": got["etag"], "last_modified": iso_http_date(got["last_modified"]),
              "page_url": got["page_url"], "checked_at": day, "unchanged_since": day, "unreachable_weeks": 0,
              "pending_sha256": None}
    parse_rzn.run(root, target, source=source)
    body = [f"Новый файл Росздравнадзора: {got['url']}", f"sha256 `{got['sha256']}`", "",
            f"Регионов с изменениями: {changed}", "", table, ""]
    if lost:
        body += ["Правки в data/review/overrides.csv для номеров, которых больше нет (перенесите разметку):", ""]
        body += [f"- {x}" for x in lost]
    report["pr"] = {"branch": f"watch/{day}", "title": f"data: новая таблица Росздравнадзора {day}",
                    "body": "\n".join(body), "labels": ["review:data"]}
    report["mode"] = "pr"


def run(root: Path, *, today: dt.date | None = None, get=net.get, cache: Path | None = None) -> dict:
    today = today or dt.date.today()
    day = today.isoformat()
    cache = cache or root / "raw" / "cache"
    snap = read_json(root / SNAPSHOT, {}) or {}
    meta = read_yaml(root / "data" / "meta.yaml")
    report = {"checked_at": day, "mode": "none", "facts": [], "review": [], "pr": None}
    try:
        got = fetch_rzn.fetch(get)
    except (net.SourceDown, fetch_rzn.LinkNotFound) as e:
        unreachable(root, snap, report, e, day)
        check_age(snap, meta, today, report["review"])
        return report
    check_hotline(root, got, report)
    snap["page_checked_at"] = day
    if got["sha256"] == snap.get("sha256"):
        snap.update({"checked_at": day, "unchanged_since": snap.get("unchanged_since") or day, "unreachable_weeks": 0,
                     "last_attempt_at": day, "pending_sha256": None, "page_url": got["page_url"]})
        if got["etag"]:
            snap["etag"] = got["etag"]
        write_json(root / SNAPSHOT, snap)
        set_data_date(root, day)
        report["facts"].append({"path": str(SNAPSHOT), "what": f"файл не изменился, sha256 {got['sha256']}",
                                "source": got["url"]})
        report["mode"] = "facts"
    else:
        new_file(root, snap, got, report, day, cache)
    check_age(read_json(root / SNAPSHOT, {}), meta, today, report["review"])
    return report


def route_acts(root: Path) -> list[dict]:
    out = []
    for p in sorted((root / "data" / "routes").glob("*.yaml")):
        r = read_yaml(p)
        acts = [r["act"]] + list(r.get("amended_by") or [])
        out.append({"id": r["id"], "region_id": r["region_id"], "numbers": {a["number"] for a in acts},
                    "eos": {a["eoNumber"] for a in acts}})
    return out


def touches_route(act: dict, routes: list[dict]) -> dict | None:
    for r in routes:
        if r["region_id"] != act["region_id"]:
            continue
        for number in r["numbers"]:
            if re.search(rf"О\s+внесении\s+изменени\w*\s+в\s+приказ.*№\s*{re.escape(number)}(?![\w-])", act["title"]):
                return r
    return None


def acts_due(snap: dict, today: dt.date) -> bool:
    last = snap.get("retrieved_at") or ""
    return not last or (today - dt.date.fromisoformat(last)).days >= ACTS_EVERY_DAYS


def run_acts(root: Path, *, today: dt.date | None = None, get=None, force: bool = False) -> dict:
    today = today or dt.date.today()
    day = today.isoformat()
    report = {"checked_at": day, "mode": "none", "facts": [], "review": [], "pr": None}
    snap = read_json(root / pravo_acts.SNAPSHOT, {}) or {}
    if not force and not acts_due(snap, today):
        return report
    path = root / pravo_acts.ACTS
    old = {r["id"]: r for r in read_csv(path)} if path.is_file() else {}
    try:
        res = pravo_acts.collect(get or pravo_acts.live_get, load_regions(root), retrieved=day)
    except (net.SourceDown, pravo_acts.PravoFormatError) as e:
        report["review"].append(review("acts_unreachable", "Портал официального опубликования недоступен или сменил формат",
                                       f"{e}. Индекс актов не обновлён", "http://publication.pravo.gov.ru/api/Documents"))
        report["mode"] = "facts"
        return report
    fresh = res["acts"]
    for a in fresh:
        if a["id"] in old:
            a["retrieved_at"] = old[a["id"]]["retrieved_at"]
    new = [a for a in fresh if a["id"] not in old]
    gone = sorted(set(old) - {a["id"] for a in fresh})
    snap.update({"retrieved_at": day, "queries": res["queries"], "acts": len(fresh),
                 "regions_with_acts": len({a["region_id"] for a in fresh}), "mismatched_eo": len(res["mismatched"])})
    if not new and not gone:
        write_json(root / pravo_acts.SNAPSHOT, snap)
        report["facts"].append({"path": str(pravo_acts.SNAPSHOT), "what": "новых актов нет",
                                "source": "http://publication.pravo.gov.ru/api/Documents"})
        report["mode"] = "facts"
        return report
    rows = sorted(fresh + [{**old[i], "pages": int(old[i]["pages"] or 0), "words": old[i]["words"].split(";")}
                           for i in gone], key=lambda a: (a["region_id"], a["doc_date"], a["id"]))
    write_csv(path, pravo_acts.FIELDS, pravo_acts.to_csv(rows))
    write_json(root / pravo_acts.SNAPSHOT, snap)
    routes = route_acts(root)
    for a in new:
        route = touches_route(a, routes)
        if route or a["kind"] in ("organization", "routing"):
            what = (f"изменения в приказ маршрута {route['id']}" if route else "новый акт об организации или маршрутизации")
            report["review"].append(review(
                "route_act", f"Новый акт о паллиативной помощи: {a['region_id']}, № {a['number']} от {a['doc_date']}",
                f"{what}. {a['title']}\n\nПубликация: {a['url']}\nPDF: http://publication.pravo.gov.ru/file/pdf?eoNumber={a['id']}"
                "\n\nДанные маршрута не менялись. Сверьте акт и решите, нужен ли новый перечень", a["id"]))
    body = [f"Новых актов на портале официального опубликования: {len(new)}", "",
            "| Регион | eoNumber | № | Дата | Тип | Название |", "|---|---|---|---|---|---|"]
    body += [f"| {a['region_id']} | {a['id']} | {a['number']} | {a['doc_date']} | {a['kind']} | {a['title'][:160]} |"
             for a in new]
    if gone:
        body += ["", "Пропали из выдачи поиска (оставлены в индексе, проверьте вручную): " + ", ".join(gone)]
    report["pr"] = {"branch": f"watch-acts/{day}", "title": f"data: новые региональные акты {day}",
                    "body": "\n".join(body), "labels": ["review:data"]}
    report["mode"] = "pr"
    return report


def run_lta(root: Path, *, today: dt.date | None = None, get=net.get) -> dict:
    today = today or dt.date.today()
    day = today.isoformat()
    report = {"checked_at": day, "mode": "none", "facts": [], "review": [], "pr": None}
    snap = read_json(root / fetch_lta.SNAPSHOT, {}) or {}
    try:
        got = fetch_lta.fetch(get)
    except (net.SourceDown, fetch_lta.LtaFormatError) as e:
        report["facts"].append({"path": str(fetch_lta.SNAPSHOT), "what": f"открытые данные недоступны: {e}",
                                "source": fetch_lta.META_URL})
        report["mode"] = "facts"
        return report
    if got["sha256"] == snap.get("sha256"):
        snap["checked_at"] = day
        write_json(root / fetch_lta.SNAPSHOT, snap)
        report["facts"].append({"path": str(fetch_lta.SNAPSHOT), "what": "набор территориальных органов не изменился",
                                "source": got["url"]})
        report["mode"] = "facts"
        return report
    old = {r["region_ids"]: r for r in read_csv(root / fetch_lta.LTA)} if (root / fetch_lta.LTA).is_file() else {}
    try:
        new_snap = fetch_lta.run(root, got)
    except fetch_lta.LtaFormatError as e:
        report["review"].append(review("format_changed", "Формат открытых данных о территориальных органах изменился",
                                       f"{e}. Файл: {got['url']}", got["url"] + got["sha256"]))
        report["mode"] = "facts"
        return report
    rows = {r["region_ids"]: r for r in read_csv(root / fetch_lta.LTA)}
    changed = [k for k in sorted(set(old) | set(rows))
               if {f: (old.get(k) or {}).get(f) for f in fetch_lta.LTA_FIELDS[2:]}
               != {f: (rows.get(k) or {}).get(f) for f in fetch_lta.LTA_FIELDS[2:]}]
    body = [f"Новая версия открытых данных Росздравнадзора о территориальных органах: {new_snap['modified']}",
            f"Файл: {got['url']}, sha256 `{got['sha256']}`", "",
            f"Изменились строки по регионам: {', '.join(changed) or 'нет, только служебные поля'}"]
    report["pr"] = {"branch": f"watch-lta/{day}", "title": f"data: территориальные органы Росздравнадзора {new_snap['modified']}",
                    "body": "\n".join(body), "labels": ["review:data"]}
    report["mode"] = "pr"
    return report


def merge_reports(day: str, reports: list[dict]) -> dict:
    out = {"checked_at": day, "mode": "none", "facts": [], "review": [], "pr": None}
    prs = [r["pr"] for r in reports if r.get("pr")]
    for r in reports:
        out["facts"] += r["facts"]
        out["review"] += r["review"]
    if prs:
        out["pr"] = {"branch": f"watch/{day}", "title": prs[0]["title"] if len(prs) == 1 else f"data: изменения в источниках {day}",
                     "body": "\n\n---\n\n".join(p["body"] for p in prs), "labels": ["review:data"]}
        out["mode"] = "pr"
    elif out["facts"]:
        out["mode"] = "facts"
    return out


def run_all(root: Path, *, today: dt.date | None = None, sources=("rzn", "lta", "acts"), force_acts=False) -> dict:
    today = today or dt.date.today()
    reports = []
    if "rzn" in sources:
        reports.append(run(root, today=today))
    if "lta" in sources:
        reports.append(run_lta(root, today=today))
    if "acts" in sources:
        reports.append(run_acts(root, today=today, force=force_acts))
    return merge_reports(today.isoformat(), reports)


def write_report(root: Path, report: dict) -> None:
    out = root / "_reports"
    out.mkdir(exist_ok=True)
    (out / "watch.json").write_text(json.dumps(report, ensure_ascii=False, indent=1), encoding="utf-8")
    lines = [f"mode={report['mode']}", f"date={report['checked_at']}"]
    if report.get("pr"):
        (out / "watch-pr.md").write_text(report["pr"]["body"] + "\n", encoding="utf-8")
        lines += [f"branch={report['pr']['branch']}", f"title={report['pr']['title']}"]
    (out / "watch.env").write_text("\n".join(lines) + "\n", encoding="utf-8")


def open_issues(report_path: Path, *, runner=subprocess.run, dry_run: bool = False) -> int:
    report = json.loads(report_path.read_text(encoding="utf-8"))
    opened = 0
    for item in report.get("review", []):
        title = f"{item['title']} [{item['key']}]"
        found = runner(["gh", "issue", "list", "--state", "all", "--search", f"{item['key']} in:title", "--json", "number"],
                       capture_output=True, text=True, check=True) if not dry_run else None
        if found is not None and json.loads(found.stdout or "[]"):
            continue
        cmd = ["gh", "issue", "create", "--title", title, "--body", f"{item['body']}\n\nИсточник: {item['source']}",
               "--label", item["label"]]
        if dry_run:
            print(" ".join(cmd))
        else:
            runner(["gh", "label", "create", item["label"], "--force", "--color", "C2410C"], check=True)
            runner(cmd, check=True)
        opened += 1
    return opened


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="python -m pipeline.watch")
    ap.add_argument("--open-issues", type=Path)
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--sources", default="rzn,lta,acts", help="что проверять: rzn, lta, acts через запятую")
    ap.add_argument("--force-acts", action="store_true", help="искать акты, даже если 4 недели ещё не прошли")
    a = ap.parse_args(argv)
    root = Path.cwd()
    if a.open_issues:
        n = open_issues(a.open_issues, dry_run=a.dry_run)
        print(f"Новых issue: {n}")
        return 0
    sources = tuple(x.strip() for x in a.sources.split(",") if x.strip())
    unknown = set(sources) - {"rzn", "lta", "acts"}
    if unknown:
        print(f"Неизвестные источники: {', '.join(sorted(unknown))}", file=sys.stderr)
        return 2
    report = run_all(root, sources=sources, force_acts=a.force_acts)
    write_report(root, report)
    print(f"Проверка {report['checked_at']}: режим {report['mode']}, фактов {len(report['facts'])}, "
          f"на ревью {len(report['review'])}")
    if report["mode"] == "pr":
        print(f"Нужен PR {report['pr']['branch']}: {report['pr']['title']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
