"""USASpending bulk CSV column definitions — shared with capture-insights download."""

from __future__ import annotations

PRIME_TABLE = "intel_usaspending_prime_awards"
SUB_TABLE = "intel_usaspending_subawards"
PRIME_STAGING_TABLE = "intel_prime_staging"
PRIME_KEY_COL = "contract_transaction_unique_key"

# Slim prime columns requested by download_usaspending_bulk.py / ingest_historical.py
PRIME_TARGET_FIELDS: tuple[str, ...] = (
    "contract_transaction_unique_key",
    "contract_award_unique_key",
    "action_date_fiscal_year",
    "action_date",
    "parent_award_id_piid",
    "award_id_piid",
    "modification_number",
    "federal_action_obligation",
    "total_dollars_obligated",
    "potential_total_value_of_award",
    "total_outlayed_amount_for_overall_award",
    "period_of_performance_start_date",
    "period_of_performance_current_end_date",
    "period_of_performance_potential_end_date",
    "ordering_period_end_date",
    "primary_place_of_performance_city_name",
    "primary_place_of_performance_state_code",
    "prime_award_base_transaction_description",
    "transaction_description",
    "naics_code",
    "naics_description",
    "product_or_service_code",
    "product_or_service_code_description",
    "dod_acquisition_program_description",
    "parent_award_agency_name",
    "awarding_sub_agency_name",
    "awarding_office_name",
    "funding_agency_name",
    "funding_sub_agency_name",
    "funding_office_name",
    "recipient_name",
    "recipient_uei",
    "recipient_parent_name",
    "recipient_parent_uei",
    "solicitation_date",
    "solicitation_identifier",
    "solicitation_procedures",
    "extent_competed",
    "type_of_set_aside",
    "fair_opportunity_limited_sources",
    "other_than_full_and_open_competition",
    "number_of_offers_received",
    "subcontracting_plan",
    "government_furnished_property",
    "type_of_contract_pricing",
    "action_type",
    "award_type",
    "type_of_idc",
    "idv_type",
    "undefinitized_action",
    "program_acronym",
    "multi_year_contract",
    "multiple_or_single_award_idv",
    "usaspending_permalink",
)

PRIME_MONEY_FIELDS: frozenset[str] = frozenset(
    {
        "federal_action_obligation",
        "total_dollars_obligated",
        "potential_total_value_of_award",
        "total_outlayed_amount_for_overall_award",
    }
)

PRIME_DATE_FIELDS: frozenset[str] = frozenset(
    {
        "action_date",
        "period_of_performance_start_date",
        "period_of_performance_current_end_date",
        "period_of_performance_potential_end_date",
        "ordering_period_end_date",
        "solicitation_date",
    }
)

PRIME_INT_FIELDS: frozenset[str] = frozenset({"action_date_fiscal_year"})

DERIVED_PRIME_FIELDS: tuple[str, ...] = ("fy", "quarter", "fetch_date")


def _nullif_text(column: str) -> str:
    return f"NULLIF(NULLIF({column}, ''), 'NULL')"


def prime_staging_ddl() -> str:
    cols = ",\n    ".join(f"{name} TEXT" for name in PRIME_TARGET_FIELDS)
    return f"""
        CREATE UNLOGGED TABLE IF NOT EXISTS {PRIME_STAGING_TABLE} (
            {cols}
        )
    """


def prime_table_ddl() -> str:
    cols: list[str] = []
    for name in PRIME_TARGET_FIELDS:
        if name in PRIME_MONEY_FIELDS:
            cols.append(f"{name} DOUBLE PRECISION")
        elif name in PRIME_DATE_FIELDS:
            cols.append(f"{name} DATE")
        elif name in PRIME_INT_FIELDS:
            cols.append(f"{name} INTEGER")
        else:
            cols.append(f"{name} VARCHAR")
    cols.append("fy INTEGER")
    cols.append("quarter INTEGER")
    cols.append("fetch_date DATE")
    body = ",\n    ".join(cols)
    return f"CREATE TABLE IF NOT EXISTS {PRIME_TABLE} (\n    {body}\n)"


def prime_insert_from_staging_sql() -> str:
    """INSERT prime rows from TEXT staging with casts + derived fy/quarter."""
    selects: list[str] = []
    for name in PRIME_TARGET_FIELDS:
        base = _nullif_text(name)
        if name in PRIME_MONEY_FIELDS:
            selects.append(f"{base}::DOUBLE PRECISION AS {name}")
        elif name in PRIME_DATE_FIELDS:
            selects.append(f"{base}::DATE AS {name}")
        elif name in PRIME_INT_FIELDS:
            selects.append(f"{base}::INTEGER AS {name}")
        else:
            selects.append(f"{base}::VARCHAR AS {name}")

    action_dt = f"{_nullif_text('action_date')}::DATE"
    selects.append(
        f"EXTRACT(YEAR FROM ({action_dt} + INTERVAL '3 months'))::INTEGER AS fy"
    )
    selects.append(
        "((EXTRACT(MONTH FROM ("
        f"{action_dt} + INTERVAL '3 months')) - 1) / 3 + 1)::INTEGER AS quarter"
    )
    selects.append("CURRENT_DATE AS fetch_date")

    target_cols = ", ".join([*PRIME_TARGET_FIELDS, *DERIVED_PRIME_FIELDS])
    select_sql = ",\n            ".join(selects)
    return f"""
        INSERT INTO {PRIME_TABLE} ({target_cols})
        SELECT
            {select_sql}
        FROM {PRIME_STAGING_TABLE}
    """


def sanitize_sub_column(name: str) -> str:
    """Normalize CSV header to safe PostgreSQL identifier (lowercase)."""
    cleaned = name.strip().lower().replace(" ", "_").replace("-", "_")
    cleaned = "".join(ch if ch.isalnum() or ch == "_" else "_" for ch in cleaned)
    while "__" in cleaned:
        cleaned = cleaned.replace("__", "_")
    return cleaned.strip("_") or "column"