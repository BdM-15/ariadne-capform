"""Knowledge page guide content."""

from thread.ui.knowledge_guides import guide_for_knowledge, guide_for_vault_ops


def test_knowledge_guides_have_required_fields():
    for guide in (guide_for_knowledge(), guide_for_vault_ops()):
        assert guide["title"]
        assert guide["purpose"]
        assert guide["when"]
        assert guide["how_to_use"]
        assert guide["tips"]