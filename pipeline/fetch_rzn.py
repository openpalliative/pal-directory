import hashlib
import html
import re
import urllib.parse

from pipeline import net

PAGE_URL = "https://roszdravnadzor.gov.ru/pages/main/call/to/tel"
HOTLINE = re.compile(r"«Горячая линия»\s*Росздравнадзора по соблюдению прав граждан в сфере охраны здоровья\s*-\s*"
                     r"(\+7[\d\s()-]{10,16}\d)")


class LinkNotFound(Exception):
    pass


def page_text(raw: bytes) -> str:
    text = re.sub(r"<[^>]+>", " ", raw.decode("utf-8", errors="replace"))
    return re.sub(r"\s+", " ", html.unescape(text)).replace("\xa0", " ")


def find_xlsx(raw: bytes, page_url: str = PAGE_URL) -> str:
    links = re.findall(r'href="([^"]+\.xlsx)"', raw.decode("utf-8", errors="replace"), re.I)
    found = sorted({l for l in links if "горяч" in urllib.parse.unquote(l).lower()})
    if len(found) != 1:
        raise LinkNotFound(f"на странице {page_url} ссылок на xlsx горячих линий: {len(found)}, ожидалась одна")
    return net.quote_url(urllib.parse.urljoin(page_url, html.unescape(found[0])))


def hotline_number(raw: bytes) -> str | None:
    m = HOTLINE.search(page_text(raw))
    return re.sub(r"\s+", " ", m.group(1)).strip() if m else None


def fetch(get=net.get) -> dict:
    page, _ = get(PAGE_URL)
    url = find_xlsx(page)
    body, headers = get(url)
    return {"page_url": PAGE_URL, "page_sha256": hashlib.sha256(page).hexdigest(), "hotline": hotline_number(page),
            "url": url, "body": body, "sha256": hashlib.sha256(body).hexdigest(), "bytes": len(body),
            "etag": headers.get("etag", ""), "last_modified": headers.get("last-modified", "")}
