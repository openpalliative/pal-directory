import argparse
import hashlib
import re
import sys
from pathlib import Path

from pipeline import net, territories

CACHE = Path("raw/cache/pdf")


def fetch(root: Path, eo: str, *, get=net.pravo_pdf) -> dict:
    if not re.fullmatch(r"\d{16}", eo) or not territories.eo_allowed(eo):
        raise net.HostNotAllowed(f"eoNumber {eo} не подходит")
    target = root / CACHE / f"{eo}.pdf"
    if target.is_file():
        body = target.read_bytes()
    else:
        body, _ = get(eo)
        if not body.startswith(b"%PDF"):
            raise net.SourceDown(f"{eo}: ответ не PDF")
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(body)
    return {"eo": eo, "path": str(target.relative_to(root)), "bytes": len(body),
            "sha256": hashlib.sha256(body).hexdigest()}


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="python -m pipeline.route_pdfs")
    ap.add_argument("eo", nargs="+")
    a = ap.parse_args(argv)
    for eo in a.eo:
        try:
            got = fetch(Path.cwd(), eo)
        except (net.SourceDown, net.HostNotAllowed) as e:
            print(f"{eo}: ошибка {e}", file=sys.stderr)
            return 1
        print(f"{got['eo']}\t{got['bytes']}\t{got['sha256']}\t{got['path']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
