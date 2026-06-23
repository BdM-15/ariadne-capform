"""Shared SQL fragments — ported from capture-insights queries.py for PostgreSQL."""

PRIME_TABLE = "intel_usaspending_prime_awards"
SUB_TABLE = "intel_usaspending_subawards"
ANALYTICS_SCHEMA = "intel_analytics"
PRIME_AWARDS_VIEW = f"{ANALYTICS_SCHEMA}.intel_prime_awards_v"
SUBAWARDS_VIEW = f"{ANALYTICS_SCHEMA}.intel_subawards_v"
DEDUP_MATVIEW = f"{ANALYTICS_SCHEMA}.mv_prime_awards_dedup"

AGENCY_EXPR = """COALESCE(
    NULLIF(parent_award_agency_name, ''),
    NULLIF(awarding_sub_agency_name, ''),
    NULLIF(funding_agency_name, ''),
    '(Unspecified Agency)'
)"""

AGENCY_NORMALIZED_EXPR = f"""CASE
    WHEN UPPER(TRIM(({AGENCY_EXPR}))) = '' THEN '(Unspecified Agency)'
    WHEN UPPER(TRIM(({AGENCY_EXPR}))) ~ '^DEPT OF '
        THEN REGEXP_REPLACE(UPPER(TRIM(({AGENCY_EXPR}))), '^DEPT OF ', 'DEPARTMENT OF ')
    ELSE UPPER(TRIM(({AGENCY_EXPR})))
END"""

def agency_normalized_expr(column: str) -> str:
    """Normalize a single agency column (DEPT OF → DEPARTMENT OF, UPPER)."""
    trimmed = f"UPPER(TRIM(COALESCE({column}, '')))"
    return f"""CASE
        WHEN {trimmed} = '' THEN ''
        WHEN {trimmed} ~ '^DEPT OF '
            THEN REGEXP_REPLACE({trimmed}, '^DEPT OF ', 'DEPARTMENT OF ')
        ELSE {trimmed}
    END"""

OBLIGATION_KIND_EXPR = """CASE
    WHEN federal_action_obligation IS NULL THEN 'unknown'
    WHEN federal_action_obligation < 0 THEN 'deobligation'
    WHEN federal_action_obligation = 0 THEN 'zero'
    ELSE 'obligation'
END"""

EXTENT_COMPETED_NORMALIZED_EXPR = "UPPER(TRIM(COALESCE(extent_competed, '')))"

# Data_Insights cleansing — keeps set-aside / competition chart buckets consistent.
SET_ASIDE_NORMALIZED_EXPR = """CASE
    WHEN type_of_set_aside ILIKE 'NO SET ASIDE USED.' THEN 'NO SET ASIDE USED'
    WHEN UPPER(TRIM(COALESCE(extent_competed, ''))) = 'FULL AND OPEN COMPETITION' THEN 'NO SET ASIDE USED'
    WHEN UPPER(TRIM(COALESCE(extent_competed, ''))) = 'FULL AND OPEN COMPETITION AFTER EXCLUSION OF SOURCES'
         AND (
             UPPER(TRIM(COALESCE(type_of_set_aside, ''))) = 'NO SET ASIDE USED'
             OR UPPER(TRIM(COALESCE(type_of_set_aside, ''))) = 'NO SET ASIDE USED.'
         ) THEN NULL
    WHEN NULLIF(TRIM(COALESCE(type_of_set_aside, '')), '') IS NULL THEN NULL
    ELSE UPPER(TRIM(type_of_set_aside))
END"""

SET_ASIDE_CHART_EXPR = f"COALESCE(({SET_ASIDE_NORMALIZED_EXPR}), '(Not Applicable)')"

STATE_EXPR = "COALESCE(NULLIF(primary_place_of_performance_state_code, ''), '??')"

PRICING_BUCKET_EXPR = """CASE
    WHEN UPPER(COALESCE(type_of_contract_pricing, '')) LIKE '%FIRM FIXED%'
      OR UPPER(COALESCE(type_of_contract_pricing, '')) LIKE '%FIXED PRICE%'
         AND UPPER(COALESCE(type_of_contract_pricing, '')) NOT LIKE '%INCENTIVE%'
      OR UPPER(COALESCE(type_of_contract_pricing, '')) LIKE '%FIXED PRICE REDETERMINATION%'
    THEN 'firm_fixed'
    WHEN UPPER(COALESCE(type_of_contract_pricing, '')) LIKE '%INCENTIVE%'
      OR UPPER(COALESCE(type_of_contract_pricing, '')) LIKE '%AWARD FEE%'
    THEN 'performance_based'
    WHEN UPPER(COALESCE(type_of_contract_pricing, '')) LIKE '%TIME AND MATERIAL%'
      OR UPPER(COALESCE(type_of_contract_pricing, '')) LIKE '%LABOR HOUR%'
    THEN 'time_materials'
    WHEN UPPER(COALESCE(type_of_contract_pricing, '')) LIKE '%COST PLUS%'
      OR UPPER(COALESCE(type_of_contract_pricing, '')) LIKE '%COST SHARING%'
      OR UPPER(TRIM(COALESCE(type_of_contract_pricing, ''))) = 'COST'
    THEN 'cost_reimbursement'
    ELSE 'other'
END"""

VEHICLE_EXPR = """COALESCE(
    NULLIF(TRIM(idv_type), ''),
    NULLIF(TRIM(type_of_idc), ''),
    'Standalone / Definitive'
)"""

IDV_FLAG_EXPR = """CASE
    WHEN NULLIF(TRIM(idv_type), '') IS NOT NULL THEN 'IDV / Task Order'
    WHEN NULLIF(TRIM(type_of_idc), '') IS NOT NULL THEN 'IDV / Task Order'
    WHEN UPPER(COALESCE(award_type, '')) LIKE '%DELIVERY ORDER%' THEN 'IDV / Task Order'
    WHEN UPPER(COALESCE(award_type, '')) LIKE '%BPA%' THEN 'IDV / Task Order'
    ELSE 'Standalone / Definitive'
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