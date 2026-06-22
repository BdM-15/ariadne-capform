"""Clew analytics — thin wrapper over shared thread.intel.charts SQL layer."""

from __future__ import annotations

from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from thread.intel.charts import ANALYSIS_MODES, run_facet_analysis
from thread.intel.facet_query import InsightFacetQuery, build_facet_sql, query_from_dict

__all__ = ["ANALYSIS_MODES", "facet_from_payload", "run_facet_analysis", "build_facet_sql"]


def facet_from_payload(body: dict[str, Any]) -> InsightFacetQuery | None:
    facet = body.get("facet")
    if isinstance(facet, dict):
        return query_from_dict({**facet, "id": facet.get("id") or "analyze", "name": facet.get("name") or "Analysis"})
    return query_from_dict(
        {
            "id": "analyze",
            "name": "Analysis",
            "agency": body.get("agency"),
            "sub_agency": body.get("sub_agency"),
            "recipient": body.get("recipient"),
            "naics_codes": body.get("naics_codes") or body.get("naics"),
            "psc_codes": body.get("psc_codes"),
        }
    )