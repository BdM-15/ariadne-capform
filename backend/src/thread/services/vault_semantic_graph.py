"""Semantic cross-linking — connect capabilities, concepts, milestones, packet fields."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from thread.config import Settings
from thread.domain.enums import PacketSection
from thread.domain.packet_field_seed import PACKET_ANSWERABLE_SEEDS
from thread.services.vault_link_index import build_link_index
from thread.services.vault_ofm import insert_related_links
from thread.services.vault_write import (
    _parse_frontmatter,
    _slug,
    _vault_root,
    append_log,
)

_WIKILINK_RE = re.compile(r"\[\[([^\]|#]+)")
_TOKEN_RE = re.compile(r"[a-z][a-z0-9]{3,}")

_STOPWORDS = frozenset(
    {
        "capability",
        "capabilities",
        "concept",
        "global",
        "capture",
        "company",
        "federal",
        "government",
        "contract",
        "contracts",
        "services",
        "service",
        "management",
        "system",
        "systems",
        "based",
        "with",
        "from",
        "that",
        "this",
        "your",
        "into",
        "over",
        "under",
        "about",
        "through",
        "across",
        "proof",
        "point",
        "discriminator",
        "portfolio",
        "platform",
        "module",
        "suite",
        "status",
        "scale",
        "high",
        "readiness",
        "digital",
        "technology",
        "enterprise",
        "analysis",
        "strategy",
        "development",
        "requirements",
        "framework",
        "evaluation",
        "proposal",
        "past",
        "performance",
    }
)

# Keyword triggers → high-confidence concept/capability stems
_KEYWORD_TARGETS: tuple[tuple[frozenset[str], tuple[str, ...]], ...] = (
    (frozenset({"cyber", "cybersecurity", "cmmc", "nist", "dfars", "cdi"}), (
        "cybersecurity-capability",
        "kbr-cyber-range",
        "dfars-cybersecurity-requirements",
        "cmmc-certification-framework",
        "cmmc-certification-status",
    )),
    (frozenset({"cleared", "clearance", "sci", "workforce", "personnel"}), (
        "cleared-workforce",
        "cleared-workforce-at-scale-discriminator",
        "agency-specific-evaluation-tendencies",
    )),
    (frozenset({"fedramp", "il5", "vaault", "cloud", "authorization"}), (
        "fedramp-high-authorization-vaault",
        "fedramp-high-plus-il5-discriminator",
        "dod-srg-impact-level-5-authorization-vaault",
        "kbr-vaault",
    )),
    (frozenset({"teaming", "subcontract", "partner", "prime", "mentor"}), (
        "gap-fill-teaming",
        "teaming-fit",
        "teaming-strategy-development",
        "small-business-participation-evaluation-factor",
    )),
    (frozenset({"pricing", "ffp", "fixed", "price", "ptw", "cost"}), (
        "price-to-win-analysis",
        "firm-fixed-pricing",
        "ffp-shaping-radar",
        "non-fixed-pricing",
        "pricing-buckets",
    )),
    (frozenset({"recompete", "incumbent", "expiring", "pop"}), (
        "recompete-radar",
        "hot-agency-recompete",
        "recompete-strategy-distinctions",
        "competitor-posture",
    )),
    (frozenset({"money", "flow", "spend", "obligation", "recipient", "agency"}), (
        "follow-the-money",
        "capture-intensity",
        "market-concentration",
        "entities",
    )),
    (frozenset({"swot", "strength", "weakness", "threat", "opportunity"}), (
        "strategy-lens",
        "discriminator-development",
        "competitor-posture",
        "gap-fill-teaming",
    )),
    (frozenset({"milestone", "qualification", "pursuit", "bid", "gate", "ms1", "ms2", "ms3", "ms4"}), (
        "milestones-overview",
        "milestone_1",
        "milestone_2",
        "milestone_3",
        "milestone_4",
        "gate-review-process",
        "bid-no-bid-decision-framework",
        "ms1-qualification",
        "ms2-pursuit",
        "ms3-bid-no-bid",
        "ms4-pricing-approval",
    )),
    (frozenset({"shipley", "capture", "win", "theme", "discriminator"}), (
        "capture-plan-development",
        "discriminator-development",
        "win-strategy-development",
        "capture-planning-phase",
    )),
    (frozenset({"sustainment", "logcap", "readiness", "maintenance"}), (
        "kbr-readiness-and-sustainment",
        "logcap-v-contract",
        "proven-sustainment-scale-discriminator",
    )),
    (frozenset({"autonomous", "uas", "unmanned", "space", "ssa"}), (
        "autonomous-systems-capability",
        "artemis-uas",
        "iron-stallion",
        "u-s-space-force-ssa-performance-iron-stallion",
    )),
    (frozenset({"data", "analytics", "twin", "engineering"}), (
        "data-analytics-capability",
        "digital-engineering-capability",
        "encompass-digital-twin-platform",
        "athena-data-management-suite",
    )),
    (frozenset({"past", "performance", "pp", "relevance"}), (
        "past-performance-relevance-reality",
        "outstanding-rating-reality",
        "competitor-posture",
    )),
    (frozenset({"proposal", "compliance", "matrix", "rfp"}), (
        "common-proposal-disqualification-causes",
        "ambiguous-requirement-red-flags",
        "hidden-requirement-patterns",
        "professional-services-proposal-patterns",
    )),
    (frozenset({"lessons", "debrief", "gao", "protest"}), (
        "lessons-learned-index",
        "debrief-exploitation-strategy",
        "gao-protest-risk-patterns",
    )),
)

_SECTION_CONCEPTS: dict[str, tuple[str, ...]] = {
    PacketSection.COMPETITIVE_POSITION.value: (
        "competitor-posture",
        "teaming-fit",
        "follow-the-money",
        "capture-intensity",
        "recompete-radar",
        "strategy-lens",
    ),
    PacketSection.SOLUTION_STRATEGY.value: (
        "discriminator-development",
        "gap-fill-teaming",
        "strategy-lens",
        "win-strategy-development",
    ),
    PacketSection.CUSTOMER_CONTEXT.value: (
        "customer-position",
        "relationship-heatmap",
        "hot-agency",
        "agency-specific-evaluation-tendencies",
    ),
    PacketSection.PRICE_TO_WIN.value: (
        "price-to-win-analysis",
        "firm-fixed-pricing",
        "ffp-shaping-radar",
        "pricing-buckets",
    ),
    PacketSection.RISKS_AND_GAPS.value: (
        "gao-protest-risk-patterns",
        "ambiguous-requirement-red-flags",
        "hidden-requirement-patterns",
    ),
    PacketSection.REQUIREMENTS_AND_SCOPE.value: (
        "teaming-strategy-development",
        "cleared-workforce",
        "gap-fill-teaming",
    ),
    PacketSection.OPPORTUNITY_OVERVIEW.value: (
        "capture-plan-development",
        "bid-no-bid-decision-framework",
        "milestone_1",
    ),
    PacketSection.RECOMMENDATION_AND_NEXT_ACTIONS.value: (
        "capture-plan-development",
        "bid-no-bid-decision-framework",
        "milestone_1",
    ),
}

# Zone pairs allowed for automatic semantic linking
_ZONE_RULES: dict[str, frozenset[str]] = {
    "capability": frozenset({"concept", "capability", "milestone", "data-element", "hub"}),
    "concept": frozenset({"concept", "capability", "milestone", "hub", "data-element"}),
    "milestone": frozenset({"concept", "milestone", "capability", "hub"}),
    "agency": frozenset({"concept", "hub", "capability"}),
    "competitor": frozenset({"concept", "hub", "capability"}),
    "data-element": frozenset({"concept", "capability", "hub"}),
    "hub": frozenset({"concept", "capability", "milestone", "hub", "data-element"}),
    "synthesis": frozenset({"concept", "capability", "milestone", "hub"}),
}


@dataclass
class VaultPage:
    rel: str
    stem: str
    zone: str
    name: str
    tokens: frozenset[str]
    existing_links: frozenset[str]


@dataclass
class SemanticLinkReport:
    dry_run: bool
    pages_scanned: int = 0
    links_added: int = 0
    pages_updated: int = 0
    pairs: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "dry_run": self.dry_run,
            "pages_scanned": self.pages_scanned,
            "links_added": self.links_added,
            "pages_updated": self.pages_updated,
            "pairs": self.pairs[:200],
        }


def _rel(vault: Path, path: Path) -> str:
    return str(path.relative_to(vault)).replace("\\", "/")


def _zone(rel: str, page_type: str) -> str:
    if rel.startswith("global/domain_intel/capabilities/") and "catalog" not in rel:
        return "capability"
    if "/capture/concepts/" in rel:
        return "concept"
    if rel.startswith("milestones/") or "/milestones/" in rel:
        return "milestone"
    if rel.startswith("entities/agencies/"):
        return "agency"
    if rel.startswith("entities/competitors/"):
        return "competitor"
    if rel.startswith("data-elements/"):
        return "data-element"
    if page_type == "meta" or "catalog" in rel or rel.endswith("entities.md"):
        return "hub"
    if "domain_intel" in rel or "global_wiki" in rel:
        return "concept"
    return "synthesis"


def _tokenize(*parts: str) -> frozenset[str]:
    tokens: set[str] = set()
    for part in parts:
        for match in _TOKEN_RE.finditer(part.lower()):
            tok = match.group(0)
            if tok not in _STOPWORDS and len(tok) >= 4:
                tokens.add(tok)
    return frozenset(tokens)


def _existing_links(text: str) -> frozenset[str]:
    return frozenset(m.group(1).strip().lower() for m in _WIKILINK_RE.finditer(text))


def _catalog_pages(vault: Path) -> list[VaultPage]:
    pages: list[VaultPage] = []
    for path in sorted(vault.rglob("*.md")):
        rel = _rel(vault, path)
        if rel in ("index.md", "log.md"):
            continue
        if rel.startswith((".obsidian/", "foundation/", "generated-projections/")):
            continue
        text = path.read_text(encoding="utf-8", errors="replace")
        meta, body = _parse_frontmatter(text)
        name = meta.get("name") or path.stem.replace("-", " ")
        stem = path.stem
        zone = _zone(rel, meta.get("type", ""))
        tokens = _tokenize(name, stem, meta.get("summary", ""), body[:1200])
        pages.append(
            VaultPage(
                rel=rel,
                stem=stem,
                zone=zone,
                name=name,
                tokens=tokens,
                existing_links=_existing_links(text),
            )
        )
    return pages


def _jaccard(a: frozenset[str], b: frozenset[str]) -> float:
    if not a or not b:
        return 0.0
    inter = len(a & b)
    if inter == 0:
        return 0.0
    return inter / len(a | b)


def _score_pair(source: VaultPage, target: VaultPage) -> float:
    if source.stem == target.stem:
        return 0.0
    allowed = _ZONE_RULES.get(source.zone, frozenset())
    if target.zone not in allowed:
        return 0.0

    score = _jaccard(source.tokens, target.tokens)

    # Stem/name overlap boost
    src_slug = _slug(source.name)
    tgt_slug = _slug(target.name)
    if src_slug and tgt_slug and (src_slug in tgt_slug or tgt_slug in src_slug):
        score += 0.25
    if target.stem.replace("-", " ") in source.name.lower():
        score += 0.2
    if source.stem.replace("-", " ") in target.name.lower():
        score += 0.15

    return score


def _keyword_suggestions(page: VaultPage, stems: dict[str, VaultPage]) -> list[tuple[str, float]]:
    out: list[tuple[str, float]] = []
    for keys, targets in _KEYWORD_TARGETS:
        if not page.tokens & keys:
            continue
        for stem in targets:
            if stem in stems and stem != page.stem:
                out.append((stem, 0.45))
    return out


def _section_suggestions(page: VaultPage, stems: dict[str, VaultPage]) -> list[tuple[str, float]]:
    if page.zone != "data-element":
        return []
    key = page.stem
    section = None
    for seed in PACKET_ANSWERABLE_SEEDS:
        if seed.key == key:
            section = seed.section.value
            break
    if not section:
        return []
    out: list[tuple[str, float]] = []
    for stem in _SECTION_CONCEPTS.get(section, ()):
        if stem in stems:
            out.append((stem, 0.4))
    return out


def _semantic_suggestions(
    page: VaultPage,
    catalog: list[VaultPage],
    stems: dict[str, VaultPage],
    *,
    max_links: int = 6,
    min_score: float = 0.1,
) -> list[tuple[str, float]]:
    scored: dict[str, float] = {}
    link_cap = 4 if page.zone == "data-element" else max_links

    # Packet field stubs link to doctrine — not to each other via token overlap.
    if page.zone != "data-element":
        for target in catalog:
            if target.stem == page.stem:
                continue
            s = _score_pair(page, target)
            if s >= min_score:
                scored[target.stem] = max(scored.get(target.stem, 0.0), s)

    for stem, s in _keyword_suggestions(page, stems):
        scored[stem] = max(scored.get(stem, 0.0), s)

    section_boost = 0.15 if page.zone == "data-element" else 0.0
    for stem, s in _section_suggestions(page, stems):
        scored[stem] = max(scored.get(stem, 0.0), s + section_boost)

    # Capabilities cross-link shared product tokens (crystalvista, etc.)
    if page.zone == "capability":
        for target in catalog:
            if target.zone != "capability" or target.stem == page.stem:
                continue
            shared = page.tokens & target.tokens
            if len(shared) >= 2:
                scored[target.stem] = max(scored.get(target.stem, 0.0), 0.18 + 0.05 * len(shared))

    ranked = sorted(scored.items(), key=lambda x: -x[1])
    return ranked[:link_cap]


def apply_semantic_crosslinks(
    settings: Settings,
    *,
    dry_run: bool = True,
    min_score: float = 0.1,
    max_per_page: int = 6,
    bidirectional_threshold: float = 0.22,
) -> SemanticLinkReport:
    vault = _vault_root(settings)
    report = SemanticLinkReport(dry_run=dry_run)
    catalog = _catalog_pages(vault)
    stems = {p.stem: p for p in catalog}
    index = build_link_index(vault)

    # Precompute suggestions per page
    suggestions: dict[str, list[tuple[str, float]]] = {}
    for page in catalog:
        suggestions[page.stem] = _semantic_suggestions(
            page, catalog, stems, max_links=max_per_page, min_score=min_score
        )

    # Bidirectional: if A→B strong, ensure B→A
    for page in catalog:
        for target_stem, score in list(suggestions[page.stem]):
            if score < bidirectional_threshold:
                continue
            reverse = suggestions.get(target_stem, [])
            if not any(s == page.stem for s, _ in reverse):
                reverse = list(reverse)
                reverse.append((page.stem, score * 0.9))
                reverse.sort(key=lambda x: -x[1])
                suggestions[target_stem] = reverse[:max_per_page]

    for page in catalog:
        report.pages_scanned += 1
        sug = suggestions.get(page.stem, [])
        new_stems: list[str] = []
        for target_stem, score in sug:
            if index.resolve(target_stem) is None and target_stem not in stems:
                continue
            if target_stem.lower() in page.existing_links:
                continue
            new_stems.append(target_stem)
            report.pairs.append(f"{page.stem} → {target_stem} ({score:.2f})")

        if not new_stems:
            continue

        path = vault / Path(page.rel)
        text = path.read_text(encoding="utf-8")
        updated, n = insert_related_links(text, new_stems)
        if n == 0:
            continue
        report.links_added += n
        report.pages_updated += 1
        if not dry_run:
            path.write_text(updated, encoding="utf-8")

    if not dry_run:
        append_log(
            settings,
            "semantic",
            "vault cross-link",
            f"links={report.links_added} pages={report.pages_updated}",
        )

    return report


def compound_semantic_graph(settings: Settings) -> SemanticLinkReport:
    """Full semantic pass — run after repair or trusted ingest."""
    return apply_semantic_crosslinks(settings, dry_run=False)