import time
import urllib.error
import urllib.parse
import urllib.request

ALLOWED_HOSTS = ("roszdravnadzor.gov.ru",)
PRAVO_HOST = "publication.pravo.gov.ru"
PRAVO_API_PATHS = ("/api/Documents", "/api/Document", "/api/PublicBlocks")
PRAVO_PDF_PATH = "/file/pdf"
USER_AGENT = "openpalliative-watch (+https://github.com/openpalliative)"
TIMEOUT = 30
PAUSES = (5, 15)
PRAVO_PAUSE = 2.0
MAX_BYTES = 20 * 1024 * 1024
MAX_PDF_BYTES = 60 * 1024 * 1024

_last_pravo = [0.0]


class SourceDown(Exception):
    pass


class TooLarge(SourceDown):
    pass


class HostNotAllowed(ValueError):
    pass


def check_host(url: str) -> None:
    parts = urllib.parse.urlsplit(url)
    if parts.scheme != "https" or (parts.hostname or "") not in ALLOWED_HOSTS:
        raise HostNotAllowed(f"адрес {url} вне разрешённых: только https://{', '.join(ALLOWED_HOSTS)}")


def check_pravo_api(url: str) -> None:
    parts = urllib.parse.urlsplit(url)
    if parts.scheme != "http" or parts.hostname != PRAVO_HOST or parts.path not in PRAVO_API_PATHS or parts.port:
        raise HostNotAllowed(f"адрес {url} вне разрешённых: только http://{PRAVO_HOST}{{{','.join(PRAVO_API_PATHS)}}}")


def check_pravo_pdf(url: str) -> None:
    parts = urllib.parse.urlsplit(url)
    query = urllib.parse.parse_qs(parts.query)
    eo = query.get("eoNumber", [""])
    if (parts.scheme != "http" or parts.hostname != PRAVO_HOST or parts.path != PRAVO_PDF_PATH or parts.port
            or set(query) != {"eoNumber"} or len(eo) != 1 or not (eo[0].isdigit() and len(eo[0]) == 16)):
        raise HostNotAllowed(f"адрес {url} вне разрешённых: только http://{PRAVO_HOST}{PRAVO_PDF_PATH}?eoNumber=<16 цифр>")


def quote_url(url: str) -> str:
    parts = urllib.parse.urlsplit(url)
    path = urllib.parse.quote(urllib.parse.unquote(parts.path), safe="/")
    return urllib.parse.urlunsplit((parts.scheme, parts.netloc, path, parts.query, ""))


def read_limited(r, max_bytes: int, url: str) -> bytes:
    length = r.headers.get("Content-Length")
    if length and length.isdigit() and int(length) > max_bytes:
        raise TooLarge(f"{url}: файл {length} байт, больше предела {max_bytes}")
    body = r.read(max_bytes + 1)
    if len(body) > max_bytes:
        raise TooLarge(f"{url}: файл больше предела {max_bytes} байт")
    return body


def get(url: str, *, timeout: int = TIMEOUT, pauses=PAUSES, sleep=time.sleep, check=check_host,
        max_bytes: int = MAX_BYTES) -> tuple[bytes, dict]:
    url = quote_url(url)
    check(url)
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    last = None
    for attempt in range(len(pauses) + 1):
        try:
            with urllib.request.urlopen(req, timeout=timeout) as r:
                check(r.geturl())
                body = read_limited(r, max_bytes, url)
                headers = {k.lower(): v for k, v in r.headers.items()}
            if not body:
                raise SourceDown(f"пустой ответ: {url}")
            return body, headers
        except TooLarge:
            raise
        except (SourceDown, urllib.error.URLError, TimeoutError, ConnectionError) as e:
            last = e
        if attempt < len(pauses):
            sleep(pauses[attempt])
    raise SourceDown(f"{url}: {last}")


def pravo_wait(sleep=time.sleep, clock=time.monotonic) -> None:
    left = PRAVO_PAUSE - (clock() - _last_pravo[0])
    if left > 0:
        sleep(left)
    _last_pravo[0] = clock()


def pravo_api(path: str, params: list[tuple[str, str]], *, sleep=time.sleep, pauses=PAUSES) -> tuple[bytes, dict]:
    url = f"http://{PRAVO_HOST}{path}?" + urllib.parse.urlencode(params)
    check_pravo_api(url)
    pravo_wait(sleep)
    return get(url, pauses=pauses, sleep=sleep, check=check_pravo_api)


def pravo_pdf(eo: str, *, sleep=time.sleep, pauses=PAUSES) -> tuple[bytes, dict]:
    url = f"http://{PRAVO_HOST}{PRAVO_PDF_PATH}?eoNumber={eo}"
    check_pravo_pdf(url)
    pravo_wait(sleep)
    return get(url, pauses=pauses, sleep=sleep, check=check_pravo_pdf, max_bytes=MAX_PDF_BYTES)
