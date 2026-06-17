# Data Dictionary - Plain English + "How the AI Uses It" (Karpathy Style)

This document explains the important fields in your contract data the way a smart non-expert (or an AI) should understand them.

Goal: When you or a future fine-tuned model looks at a row, you immediately know:
- What the number or code actually means in the real world of capture.
- Why it matters for winning work.
- Common pitfalls.
- Example questions / SQL you can ask.

We will keep expanding this as we add more columns and derived fields. Think of it as the "LLM wiki" for your specific domain (starting with 561210 but useful for other NAICS too).

---

## Core Money Fields

**federal_action_obligation**
- Plain English: The actual dollars the government has paid or is on the hook for in this specific transaction (modification, new award, etc.).
- Why it matters: This is the real "size of the prize" number you care about for pipeline and win rate math.
- Pitfalls: Can be negative on de-obligations. Sometimes the big number is "base + all options" instead.
- How an AI / you should use it: Sum this for total market size, average award size, your historical share, etc.
- Example question: "What was the total obligated in 561210 by Army in FY2024?"

**base_and_all_options_value** / **potential_total_value_of_award**
- Plain English: The maximum the contract could be worth if every option is exercised.
- Why it matters: For "big picture" market sizing and for pricing strategy (what did the winner think the total value was?).
- Use when: You're doing long-term market forecasts or comparing "what they bid vs what actually got spent".

---

## Time Fields (Critical for Recompete Radar)

**action_date**
- Plain English: The date this specific action (new award, modification, etc.) was signed or became effective.

**period_of_performance_current_end_date**
- Plain English: When the current period of performance ends on this contract/action.
- Why it matters enormously: This (plus any extensions) tells you when the work is likely to be recompeted.
- How we use it: Calculate "months until end", flag anything expiring in next 6/12/24 months.

**fy** and **quarter** (we derive these)
- Plain English: Fiscal Year and quarter (government FY starts Oct 1).
- Why derived: Makes "year over year growth" and "quarterly trends" trivial to query.

---

## Who Got the Money / Who is Paying

**recipient_name** + **recipient_uei**
- Plain English: The company (or JV, or team) that received the money on this transaction.
- UEI is the modern unique identifier (replaced DUNS).
- Why it matters: This is how you find "who is winning what" and build competitor lists or your own historical performance.

**awarding_agency_name** / **funding_agency_name**
- Plain English: The agency that is "buying" the service.
- Often the same, but not always (one agency can fund, another can award/manage).

**recipient_state_code** / **place_of_performance_state_code**
- Useful for geographic concentration analysis.

---

## What Was Bought (NAICS / PSC)

**naics_code** + **naics_description**
- This is your primary filter right now (561210 = Facilities Support Services).
- The script and future UI will let you easily switch or combine multiple NAICS.
- Future fine-tuned models will learn the language patterns that appear under 561210 vs 541512 etc.

**product_or_service_code** (PSC)
- More granular than NAICS. Often very useful for "exactly what kind of work".

---

## Competition & Set-Aside (Hugely Important for Strategy)

**extent_competed**
- Examples: "Full and Open Competition", "Not Competed", "Competed under SAP", etc.
- Tells you how hard it was to win (or whether it was sole-sourced).

**type_set_aside**
- "NO SET ASIDE USED", "SMALL BUSINESS SET ASIDE", "8(A) COMPETED", "SDVOSB SET-ASIDE", "WOSB", etc.
- Gold for small business strategy and for understanding why certain incumbents win.

**type_of_contract_pricing**
- "FIRM FIXED PRICE", "TIME AND MATERIALS", "COST PLUS", "FIXED PRICE INCENTIVE", etc.
- Huge implications for risk and how you should price.

---

## Derived / Useful for Analysis (we will add more)

- **fy**, **quarter** (see above)
- Later we will add things like:
  - "is_expiring_soon" flag
  - "competition_intensity" (number of offers or bidders when available)
  - "your_company_match_score" (once we have your stance loaded)

---

## How This Becomes Training Data for Fine-Tuning

Every time the system (or you) produces a good "win theme", "executive summary", or "teaming recommendation", we will save:

```json
{
  "task": "generate_win_themes",
  "naics": "561210",
  "input_context": { "market_size": 123000000, "top_incumbent": "...", "your_stance": "..." },
  "good_output": "1. We have 4 consecutive years of on-time delivery... (with citations)",
  "source_award_keys": ["ABC123", "DEF456"],
  "model_used": "local-qwen2.5:7b or xai-grok"
}
```

These files (in `data/training/`) become the high-quality supervised fine-tuning dataset for a specialized "GovCon Capture Writer for 561210 and similar" model.

This is one of the highest-leverage things we can do over time.

---

## Next Steps for This Document

- Add real examples from actual loaded data.
- Add "bad data" warnings (e.g. duplicate transactions, negative obligations).
- Add the exact SQL (in DuckDB syntax) that the dashboard and agents will use for each important calculation.
- Turn sections into short "nano-lessons" the way Karpathy does in his videos.

This file should be something you can hand to a new analyst or feed to an LLM so it "understands your data language" immediately.

---

*Maintained as living documentation. Update whenever we add important fields or learn new gotchas from real data.*
