"""Shared SQL fragments — ported from capture-insights queries.py for PostgreSQL."""

PRIME_TABLE = "intel_usaspending_prime_awards"

AGENCY_EXPR = """COALESCE(
    NULLIF(parent_award_agency_name, ''),
    NULLIF(awarding_sub_agency_name, ''),
    NULLIF(funding_agency_name, ''),
    '(Unspecified Agency)'
)"""

STATE_EXPR = "COALESCE(NULLIF(primary_place_of_performance_state_code, ''), '??')"

PRICING_BUCKET_EXPR = """CASE
    WHEN UPPER(COALESCE(type_of_contract_pricing, '')) LIKE '%FIRM FIXED%'
      OR UPPER(COALESCE(type_of_contract_pricing, '')) LIKE '%FIXED PRICE%'
         AND UPPER(COALESCE(type_of_contract_pricing, '')) NOT LIKE '%INCENTIVE%'
      OR UPPER(COALESCE(type_of_contract_pricing, '')) LIKE '%FIXED PRICE REDETERMINATION%'
    THEN 'firm_fixed'
    WHEN UPPER(COALESCE(type_of_contract_pricing, '')) LIKE '%COST%'
      OR UPPER(COALESCE(type_of_contract_pricing, '')) LIKE '%TIME AND MATERIAL%'
      OR UPPER(COALESCE(type_of_contract_pricing, '')) LIKE '%LABOR HOUR%'
    THEN 'cost_reimbursable'
    WHEN UPPER(COALESCE(type_of_contract_pricing, '')) LIKE '%INCENTIVE%'
    THEN 'incentive'
    ELSE 'other'
END"""

MONTHS_TO_END_EXPR = """(
    EXTRACT(YEAR FROM age(period_of_performance_current_end_date, CURRENT_DATE)) * 12
    + EXTRACT(MONTH FROM age(period_of_performance_current_end_date, CURRENT_DATE))
)::int"""


def round_numeric(expr: str, places: int = 2) -> str:
    """PostgreSQL round() needs numeric — float/double round(n, int) does not exist."""
    return f"ROUND(({expr})::numeric, {places})"


def naics_filter(naics_codes: list[str] | None, *, prefix: str = "AND") -> tuple[str, dict]:
    if not naics_codes:
        return "", {}
    placeholders = ", ".join(f":naics_{i}" for i in range(len(naics_codes)))
    params = {f"naics_{i}": code for i, code in enumerate(naics_codes)}
    return f" {prefix} naics_code IN ({placeholders})", params