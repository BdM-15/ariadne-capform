from pathlib import Path

from thread.config import Settings
from thread.skills.registry import discover_skills


def test_discover_platform_skills():
    settings = Settings()
    skills = discover_skills(settings.resolve(settings.skills_root))
    assert "clew_intel" in skills
    assert "mcp_federal_tools" in skills
    assert "skill-creator" in skills
    assert "vault_maintainer" in skills
    assert "idea_capturer" in skills
    assert "obsidian-markdown" in skills