from thread.services.vault_ofm import (
    clean_packet_field_related_links,
    insert_related_links,
    normalize_related_section,
    parse_list_property,
    render_frontmatter_ofm,
)


def test_insert_related_before_added_updated():
    text = """# Note

## Related
- [[existing]]

## Added/Updated 2026-06-08
- Seeded from script.
"""
    updated, n = insert_related_links(text, ["new-concept"])
    assert n == 1
    assert "- [[new-concept]]" in updated.split("## Added/Updated")[0]
    assert "## Added/Updated" in updated
    assert updated.index("new-concept") < updated.index("## Added/Updated")


def test_normalize_moves_eof_bullets_into_related():
    text = """## Related
- [[hub]]

## Added/Updated 2026-06-08
- Seeded.
- [[match-lens]]
- [[suitability]]
"""
    updated, n = normalize_related_section(text)
    assert n >= 2
    related = updated.split("## Related", 1)[1].split("## Added/Updated", 1)[0]
    assert "[[match-lens]]" in related
    tail = updated.split("## Added/Updated", 1)[1]
    assert "- [[match-lens]]" not in tail


def test_normalize_inline_related_to_bullets():
    text = """## Related
[[thread-wiki-schema]] [[capture-llm-wiki]]
"""
    updated, n = normalize_related_section(text)
    assert n == 2
    assert "- [[thread-wiki-schema]]" in updated
    assert "- [[capture-llm-wiki]]" in updated


def test_clean_packet_field_related_keeps_doctrine():
    text = """## Related
- [[thread-wiki-schema]]
- [[award_date]]
- [[competitor-posture]]
- [[contract_end_date]]
"""
    updated, n, removed = clean_packet_field_related_links(
        text,
        "competitive_landscape_summary",
        frozenset({"award_date", "contract_end_date", "competitive_landscape_summary"}),
    )
    assert n == 2
    assert "award_date" in removed
    assert "[[competitor-posture]]" in updated
    assert "[[award_date]]" not in updated


def test_render_tags_as_yaml_list():
    meta = {
        "name": "Test",
        "type": "concept",
        "id": "concept-test",
        "tags": '["packet-field", "data-element"]',
    }
    fm = render_frontmatter_ofm(meta)
    assert "tags:" in fm
    assert "  - packet-field" in fm
    assert 'tags: "["' not in fm
    assert parse_list_property(meta["tags"]) == ["packet-field", "data-element"]