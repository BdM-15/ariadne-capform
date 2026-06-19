from pathlib import Path


def test_candidate_editor_template_has_stem_picker_and_tooltips():
    text = Path("src/thread/ui/templates/partials/knowledge_candidate_editor.html").read_text(
        encoding="utf-8"
    )
    assert "vault-stem-select" in text
    assert 'name="related_stems"' in text
    assert 'name="related_custom"' in text
    assert "settings-label-tip" in text
    assert "Related wikilinks" in text
    assert "vault-editor-body-input" in text