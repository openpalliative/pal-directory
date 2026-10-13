import re

import pytest

from pipeline import fetch_rzn, net
from pipeline.tests.conftest import ROOT

NETWORK_CALLS = re.compile(r"urlopen|http\.client|socket\.|requests\.|httpx|urllib3")


def test_allowlist_is_rzn_only():
    assert net.ALLOWED_HOSTS == ("roszdravnadzor.gov.ru",)


@pytest.mark.parametrize("url", [
    "https://publication.pravo.gov.ru/document/1",
    "http://roszdravnadzor.gov.ru/pages/main/call/to/tel",
    "https://roszdravnadzor.gov.ru.evil.example/x",
    "https://palliative.mosreg.ru/",
    "https://advita.ru/",
])
def test_other_hosts_refused(url):
    with pytest.raises(net.HostNotAllowed):
        net.check_host(url)


def test_rzn_host_allowed():
    net.check_host(fetch_rzn.PAGE_URL)
    net.check_host(net.quote_url("https://roszdravnadzor.gov.ru/i/upload/files/Главная страница/x.xlsx"))


def test_only_net_module_opens_connections():
    for p in sorted((ROOT / "pipeline").glob("*.py")):
        if p.name == "net.py":
            continue
        assert not NETWORK_CALLS.search(p.read_text(encoding="utf-8")), p.name


def test_pipeline_names_only_allowed_hosts():
    allowed = {"roszdravnadzor.gov.ru", "publication.pravo.gov.ru", "github.com"}
    for name in ("net.py", "fetch_rzn.py", "fetch_lta.py", "pravo_acts.py", "route_pdfs.py", "watch.py"):
        p = ROOT / "pipeline" / name
        hosts = set(re.findall(r"https?://([a-z0-9.-]+)", p.read_text(encoding="utf-8")))
        assert hosts <= allowed, (p.name, hosts)
    assert net.PRAVO_HOST == "publication.pravo.gov.ru"
    assert net.PRAVO_API_PATHS == ("/api/Documents", "/api/Document", "/api/PublicBlocks")


def test_get_uses_allowlist_before_network(monkeypatch):
    called = []
    monkeypatch.setattr(net.urllib.request, "urlopen", lambda *a, **k: called.append(a))
    with pytest.raises(net.HostNotAllowed):
        net.get("https://example.org/", pauses=())
    assert called == []


class FakeResponse:
    def __init__(self, size, length=None):
        self.size = size
        self.headers = {"Content-Length": str(length)} if length is not None else {}

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def geturl(self):
        return fetch_rzn.PAGE_URL

    def read(self, n=-1):
        return b"x" * (self.size if n < 0 else min(n, self.size))


@pytest.mark.parametrize("length", [None, 21 * 1024 * 1024])
def test_get_refuses_more_than_20_mb(monkeypatch, length):
    monkeypatch.setattr(net.urllib.request, "urlopen", lambda *a, **k: FakeResponse(21 * 1024 * 1024, length))
    with pytest.raises(net.SourceDown, match="предел"):
        net.get(fetch_rzn.PAGE_URL, pauses=(1,), sleep=lambda s: None)


def test_get_reads_small_file(monkeypatch):
    monkeypatch.setattr(net.urllib.request, "urlopen", lambda *a, **k: FakeResponse(1000))
    body, _ = net.get(fetch_rzn.PAGE_URL, pauses=())
    assert len(body) == 1000


def test_zip_bomb_refused(tmp_path):
    import zipfile
    from pipeline import parse_rzn
    path = tmp_path / "bomb.xlsx"
    with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED) as z:
        with z.open("xl/worksheets/sheet1.xml", "w", force_zip64=True) as f:
            chunk = b"\0" * (1024 * 1024)
            for _ in range(200):
                f.write(chunk)
    assert path.stat().st_size < 2 * 1024 * 1024
    with pytest.raises(parse_rzn.FormatError, match="после распаковки"):
        parse_rzn.load_sheet(path)


def test_openpyxl_uses_defusedxml():
    from openpyxl import xml
    assert xml.DEFUSEDXML is True
