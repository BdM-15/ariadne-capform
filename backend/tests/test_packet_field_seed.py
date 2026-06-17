from thread.domain.packet_field_seed import PACKET_FIELD_SEEDS


def test_packet_seeds_reference_briefing_dictionary_keys():
    keys = {s.key for s in PACKET_FIELD_SEEDS}
    assert "customer_name" in keys
    assert "rfp_release_date" in keys
    assert "proposal_risks" in keys
    assert len(keys) >= 15