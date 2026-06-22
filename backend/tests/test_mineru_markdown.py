"""MinerU markdown normalization for vault readability."""

from thread.services.mineru_markdown import (
    format_mineru_vault_document,
    html_tables_to_markdown,
    normalize_mineru_body,
    summarize_mineru_body,
)

_HILTON_SAMPLE = """# Guest Folio

Confirmation Number - 3449622516

# Primary Guest

Guest Name

MARTIN, BENJAMIN

# Stay Details

Check In Date

Check Out Date

Mar 31, 2026

Apr 02, 2026

![](images/logo.jpg)

<table><tr><td>Date</td><td>Type</td><td>Amount</td></tr><tr><td>Mar 31, 2026</td><td>Charge</td><td>$276.32</td></tr></table>

<table><tr><td>Type</td><td>Amount</td></tr><tr><td>Folio Balance</td><td>$0.00</td></tr></table>
"""


def test_html_tables_to_markdown():
    raw = "<table><tr><td>Date</td><td>Amount</td></tr><tr><td>Mar 31</td><td>$10.00</td></tr></table>"
    out = html_tables_to_markdown(raw)
    assert "| Date | Amount |" in out
    assert "| --- | --- |" in out
    assert "| Mar 31 | $10.00 |" in out
    assert "<table>" not in out


def test_normalize_demotes_heading_spam_and_strips_images():
    out = normalize_mineru_body(_HILTON_SAMPLE)
    assert out.count("# Guest Folio") == 1
    assert "### Primary Guest" in out
    assert "![](images/" not in out
    assert "| Date | Type | Amount |" in out


def test_summarize_hotel_folio():
    normalized = normalize_mineru_body(_HILTON_SAMPLE)
    summary = summarize_mineru_body(normalized, filename="StayFolio_Hilton.pdf")
    assert "Guest Folio" in summary
    assert "MARTIN, BENJAMIN" in summary
    assert "3449622516" in summary
    assert "Mar 31, 2026" in summary


def test_format_mineru_vault_document_uses_abstract_callout():
    doc = format_mineru_vault_document(
        filename="StayFolio_Hilton.pdf",
        ingest_id="dc1a11067e93",
        ingest_rel="ingest/inbox/dc1a/file.pdf",
        parsed_rel="ingest/parsed/dc1a/output.md",
        raw_body=_HILTON_SAMPLE,
    )
    assert "> [!abstract] Extracted" in doc
    assert "Parsed via MinerU" not in doc
    assert "mineru_parsed" not in doc
    assert "MARTIN, BENJAMIN" in doc
    assert "| Folio Balance | $0.00 |" in doc
    assert "_Source:_" in doc