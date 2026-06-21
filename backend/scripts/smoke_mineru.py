"""End-to-end MinerU smoke — health + /file_parse on a tiny PDF."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend" / "src"))

from thread.bootstrap.mineru_paths import mineru_installed, mineru_install_hint
from thread.config import get_settings
from thread.services.mineru_client import call_mineru_file_parse, probe_mineru_health

_MINIMAL_PDF = b"""%PDF-1.4
1 0 obj<</Type/Catalog/Pages 2 0 R>>endobj
2 0 obj<</Type/Pages/Kids[3 0 R]/Count 1>>endobj
3 0 obj<</Type/Page/MediaBox[0 0 612 792]/Parent 2 0 R/Contents 4 0 R>>endobj
4 0 obj<</Length 44>>stream
BT /F1 24 Tf 100 700 Td (Smoke) Tj ET
endstream
endobj
xref
0 5
trailer<</Size 5/Root 1 0 R>>
startxref
0
%%EOF"""


def main() -> int:
    settings = get_settings()
    if not settings.mineru_enabled:
        print("FAIL: MINERU_ENABLED=false")
        return 1
    if not mineru_installed(settings):
        print(f"FAIL: MinerU not installed. {mineru_install_hint(settings)}")
        return 1
    if not probe_mineru_health(settings):
        print(f"FAIL: MinerU API unreachable at {settings.mineru_local_endpoint}")
        print("Start app with python app.py or wait for autostart to finish.")
        return 1

    tmp = ROOT / ".tmp" / "mineru_smoke.pdf"
    tmp.parent.mkdir(parents=True, exist_ok=True)
    tmp.write_bytes(_MINIMAL_PDF)
    try:
        md = call_mineru_file_parse(settings, tmp, filename="mineru_smoke.pdf")
    except Exception as exc:
        print(f"FAIL: parse error: {exc}")
        return 1
    finally:
        tmp.unlink(missing_ok=True)

    if not md.strip():
        print("FAIL: empty markdown returned")
        return 1
    print(f"OK: MinerU parse returned {len(md)} chars")
    print(md[:240].replace("\n", " "))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())