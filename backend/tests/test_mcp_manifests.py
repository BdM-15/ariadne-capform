from pathlib import Path

from thread.config import Settings
from thread.mcp.manifest import discover_manifests


def test_discover_eight_mcp_manifests():
    settings = Settings()
    root = settings.resolve(Path("tools/mcps"))
    manifests = discover_manifests(root)
    assert len(manifests) >= 8
    assert "usaspending" in manifests
    assert "sam_gov" in manifests
    assert manifests["usaspending"].command