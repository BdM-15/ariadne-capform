from thread.domain.packet_field_seed import PACKET_ANSWERABLE_SEEDS, PACKET_FIELD_SEEDS


def test_packet_seeds_reference_briefing_dictionary_keys():
    keys = {s.key for s in PACKET_ANSWERABLE_SEEDS}
    assert "customer_name" in keys
    assert "rfp_release_date" in keys
    assert "proposal_risks" in keys
    assert "ms1_oci_sweep_initiated" in keys
    assert "ms4_execution_risks_continue_acceptable" in keys
    assert len(keys) >= 120


def test_answerable_subset_excludes_template_only():
    all_keys = {s.key for s in PACKET_FIELD_SEEDS}
    answerable = {s.key for s in PACKET_ANSWERABLE_SEEDS}
    assert "questions_slide_enabled" in all_keys
    assert "questions_slide_enabled" not in answerable