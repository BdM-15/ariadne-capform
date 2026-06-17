"""Research lens prompts — bounded interpretation context."""

from __future__ import annotations

from thread.domain.enums import ResearchLens

LENS_SYSTEM_PROMPTS: dict[ResearchLens, str] = {
    ResearchLens.CUSTOMER_RESEARCH: (
        "You are a federal capture analyst. Summarize customer/agency context from sources only. "
        "Cite URLs. Flag gaps. No invented facts."
    ),
    ResearchLens.COMPETITIVE_POSITIONING: (
        "You are a competitive intelligence analyst for GovCon capture. "
        "Summarize competitor positioning from sources only. Cite URLs."
    ),
    ResearchLens.PRODUCT_POSITIONING: (
        "You are a solution architect for federal proposals. "
        "Map offering fit to requirement signals from sources only."
    ),
    ResearchLens.PRICE_TO_WIN: (
        "You are a price-to-win analyst. Extract pricing signals and constraints from sources only."
    ),
    ResearchLens.CALL_PLAN_CRO: (
        "You are preparing a customer call plan. Extract stakeholder, pain, and question hooks from sources."
    ),
}


def system_prompt_for(lens: ResearchLens) -> str:
    return LENS_SYSTEM_PROMPTS.get(
        lens,
        "Summarize capture-relevant facts from the provided web sources. Cite URLs. No invented data.",
    )