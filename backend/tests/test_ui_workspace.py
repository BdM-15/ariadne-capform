from uuid import UUID

from thread.ui.workspace import normalize_tab, research_lenses, valid_tabs


def test_valid_workspace_tabs():
    assert valid_tabs() == ("packet", "actions", "review", "research")
    assert normalize_tab("research") == "research"
    assert normalize_tab("bogus") == "packet"


def test_research_lenses_cover_all_enums():
    values = {v for v, _ in research_lenses()}
    assert "customer_research" in values
    assert len(values) == 5