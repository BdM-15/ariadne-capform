"""DR-style relationship tracing — multi-hop BFS across org/teaming/vehicle/co-occurrence edges.

**Relations** in Thread means any traceable association — not only people:
- **org_money:** agency → prime obligations
- **teaming:** prime → sub; sub → other primes (2-hop network)
- **vehicle:** parent PIID → sister primes
- **co_occurrence:** shared-agency adjacent competitors
- **people:** SAM principals / vault officers (MCP overlay — stub until wired)

DR surface mapping:
- **expose:** `build_relations_graph` — seed → multi-hop BFS (default 3 hops)
- **browse:** `expand_node_neighbors` (+3 edges) + `build_browse_funnel` Sankey layers
- **relations:** same graph; people edges merge when MCP returns them
"""

from __future__ import annotations

import json
import re
from collections import deque
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from thread.intel.facet_query import InsightFacetQuery, build_facet_sql
from thread.intel.pg_queries import table_exists
from thread.intel.sql_expressions import AGENCY_EXPR, PRIME_TABLE, SUB_TABLE, round_numeric

MAX_GRAPH_NODES = 48
MAX_GRAPH_EDGES = 96
MIN_EXPOSE_NODES = 5
DEFAULT_MAX_HOPS = 3
EXPAND_BATCH = 3
BFS_DEGREE_CAP = 10


class RelationFamily(StrEnum):
    """Trace families — people is one lane among several."""
    ORG_MONEY = "org_money"
    TEAMING = "teaming"
    VEHICLE = "vehicle"
    CO_OCCURRENCE = "co_occurrence"
    PEOPLE = "people"


class NodeKind(StrEnum):
    AGENCY = "agency"
    PRIME = "prime"
    SUB = "sub"
    VEHICLE = "vehicle"
    PERSON = "person"


class EdgeKind(StrEnum):
    OBLIGATION = "obligation"
    TEAMING = "teaming"
    TEAMING_NETWORK = "teaming_network"
    VEHICLE_MEMBER = "vehicle_member"
    CO_OCCURRENCE = "co_occurrence"
    PERSON_AFFILIATION = "person_affiliation"


EDGE_FAMILY: dict[EdgeKind, RelationFamily] = {
    EdgeKind.OBLIGATION: RelationFamily.ORG_MONEY,
    EdgeKind.TEAMING: RelationFamily.TEAMING,
    EdgeKind.TEAMING_NETWORK: RelationFamily.TEAMING,
    EdgeKind.VEHICLE_MEMBER: RelationFamily.VEHICLE,
    EdgeKind.CO_OCCURRENCE: RelationFamily.CO_OCCURRENCE,
    EdgeKind.PERSON_AFFILIATION: RelationFamily.PEOPLE,
}

RELATION_FAMILY_LABELS: dict[str, str] = {
    RelationFamily.ORG_MONEY.value: "org money",
    RelationFamily.TEAMING.value: "teaming network",
    RelationFamily.VEHICLE.value: "vehicle peers",
    RelationFamily.CO_OCCURRENCE.value: "shared-agency competitors",
    RelationFamily.PEOPLE.value: "people (SAM POCs)",
}

_MAX_PEOPLE_EDGES = 6


@dataclass
class GraphEdge:
    source: str
    target: str
    kind: EdgeKind
    millions: float
    actions: int = 0
    hop: int = 0
    meta: dict[str, Any] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        return {
            "source": self.source,
            "target": self.target,
            "kind": self.kind.value,
            "family": EDGE_FAMILY.get(self.kind, RelationFamily.ORG_MONEY).value,
            "millions": self.millions,
            "actions": self.actions,
            "hop": self.hop,
            **self.meta,
        }


@dataclass
class GraphNode:
    id: str
    label: str
    kind: NodeKind
    hop: int = 0
    millions_in: float = 0.0
    millions_out: float = 0.0
    actions: int = 0
    meta: dict[str, Any] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        total = self.millions_in + self.millions_out
        tier = "high" if total >= 10 else "medium" if total >= 1 else "low"
        return {
            "id": self.id,
            "label": self.label,
            "kind": self.kind.value,
            "hop": self.hop,
            "millions_in": round(self.millions_in, 2),
            "millions_out": round(self.millions_out, 2),
            "millions_total": round(total, 2),
            "actions": self.actions,
            "magnitude_tier": tier,
            **self.meta,
        }


def _node_id(kind: NodeKind, label: str) -> str:
    return f"{kind.value}::{label}"


def _parse_node_id(node_id: str) -> tuple[NodeKind, str]:
    if "::" in node_id:
        prefix, label = node_id.split("::", 1)
        try:
            return NodeKind(prefix), label
        except ValueError:
            pass
    return NodeKind.PRIME, node_id


def _dedupe_edges(edges: list[GraphEdge]) -> list[GraphEdge]:
    seen: set[tuple[str, str, str]] = set()
    out: list[GraphEdge] = []
    for e in edges:
        key = (e.source, e.target, e.kind.value)
        if key in seen:
            continue
        seen.add(key)
        out.append(e)
    return out[:MAX_GRAPH_EDGES]


def _nodes_from_edges(edges: list[GraphEdge], hop_map: dict[str, int] | None = None) -> list[GraphNode]:
    hop_map = hop_map or {}
    nodes: dict[str, GraphNode] = {}

    def _touch(node_id: str, *, in_m: float = 0, out_m: float = 0, actions: int = 0) -> None:
        kind, label = _parse_node_id(node_id)
        if node_id not in nodes:
            nodes[node_id] = GraphNode(
                id=node_id,
                label=label,
                kind=kind,
                hop=hop_map.get(node_id, 0),
            )
        n = nodes[node_id]
        n.millions_in += in_m
        n.millions_out += out_m
        n.actions += actions

    for e in edges:
        _touch(e.source, out_m=e.millions, actions=e.actions)
        _touch(e.target, in_m=e.millions, actions=e.actions)
    return list(nodes.values())


async def _obligation_edges(
    session: AsyncSession,
    facet_sql: str,
    facet_params: dict[str, Any],
    *,
    focus_prime: str | None = None,
    focus_agency: str | None = None,
    limit: int = BFS_DEGREE_CAP,
    hop: int = 0,
) -> list[GraphEdge]:
    extra = ""
    params = dict(facet_params)
    if focus_prime:
        extra += " AND recipient_name = :focus_prime"
        params["focus_prime"] = focus_prime
    if focus_agency:
        extra += f" AND ({AGENCY_EXPR}) = :focus_agency"
        params["focus_agency"] = focus_agency
    sql = f"""
        SELECT
            ({AGENCY_EXPR}) AS agency,
            recipient_name AS prime,
            COUNT(*) AS actions,
            {round_numeric("SUM(COALESCE(federal_action_obligation, 0)) / 1000000.0")} AS millions
        FROM {PRIME_TABLE}
        WHERE recipient_name IS NOT NULL
          {facet_sql}
          {extra}
        GROUP BY agency, prime
        ORDER BY millions DESC NULLS LAST
        LIMIT :limit
    """
    rows = (await session.execute(text(sql), {**params, "limit": limit})).all()
    return [
        GraphEdge(
            source=_node_id(NodeKind.AGENCY, r.agency),
            target=_node_id(NodeKind.PRIME, r.prime),
            kind=EdgeKind.OBLIGATION,
            millions=float(r.millions or 0),
            actions=int(r.actions),
            hop=hop,
        )
        for r in rows
    ]


async def _teaming_edges(
    session: AsyncSession,
    query: InsightFacetQuery,
    *,
    focus_prime: str | None = None,
    limit: int = BFS_DEGREE_CAP,
    hop: int = 0,
) -> list[GraphEdge]:
    if not await table_exists(session, SUB_TABLE):
        return []
    extra = ""
    params: dict[str, Any] = {}
    if focus_prime:
        extra += " AND prime_awardee_name = :focus_prime"
        params["focus_prime"] = focus_prime
    from thread.intel.charts import _subaward_facet_sql

    sub_facet, sub_params = _subaward_facet_sql(query)
    where_extra = f"AND {sub_facet}" if sub_facet else ""
    sql = f"""
        SELECT
            prime_awardee_name AS prime,
            subawardee_name AS sub,
            COUNT(*) AS links,
            {round_numeric("SUM(COALESCE(NULLIF(subaward_amount, '')::DOUBLE PRECISION, 0)) / 1000000.0")} AS millions
        FROM {SUB_TABLE}
        WHERE prime_awardee_name IS NOT NULL
          AND subawardee_name IS NOT NULL
          {where_extra}
          {extra}
        GROUP BY prime, sub
        ORDER BY millions DESC NULLS LAST
        LIMIT :limit
    """
    rows = (await session.execute(text(sql), {**params, **sub_params, "limit": limit})).all()
    return [
        GraphEdge(
            source=_node_id(NodeKind.PRIME, r.prime),
            target=_node_id(NodeKind.SUB, r.sub),
            kind=EdgeKind.TEAMING,
            millions=float(r.millions or 0),
            actions=int(r.links),
            hop=hop,
        )
        for r in rows
    ]


async def _teaming_network_edges(
    session: AsyncSession,
    query: InsightFacetQuery,
    sub_name: str,
    *,
    exclude_prime: str | None = None,
    limit: int = BFS_DEGREE_CAP,
    hop: int = 0,
) -> list[GraphEdge]:
    """2-hop teaming: other primes sharing the same subcontractor."""
    if not await table_exists(session, SUB_TABLE):
        return []
    from thread.intel.charts import _subaward_facet_sql

    sub_facet, sub_params = _subaward_facet_sql(query)
    where_extra = f"AND {sub_facet}" if sub_facet else ""
    extra = " AND subawardee_name = :sub_name"
    params: dict[str, Any] = {"sub_name": sub_name}
    if exclude_prime:
        extra += " AND prime_awardee_name != :exclude_prime"
        params["exclude_prime"] = exclude_prime
    sql = f"""
        SELECT
            prime_awardee_name AS prime,
            subawardee_name AS sub,
            COUNT(*) AS links,
            {round_numeric("SUM(COALESCE(NULLIF(subaward_amount, '')::DOUBLE PRECISION, 0)) / 1000000.0")} AS millions
        FROM {SUB_TABLE}
        WHERE subawardee_name IS NOT NULL
          {where_extra}
          {extra}
        GROUP BY prime, sub
        ORDER BY millions DESC NULLS LAST
        LIMIT :limit
    """
    rows = (await session.execute(text(sql), {**params, **sub_params, "limit": limit})).all()
    edges: list[GraphEdge] = []
    sub_id = _node_id(NodeKind.SUB, sub_name)
    for r in rows:
        prime_id = _node_id(NodeKind.PRIME, r.prime)
        edges.append(
            GraphEdge(
                source=prime_id,
                target=sub_id,
                kind=EdgeKind.TEAMING_NETWORK,
                millions=float(r.millions or 0),
                actions=int(r.links),
                hop=hop,
            )
        )
    return edges


async def _co_occurrence_edges(
    session: AsyncSession,
    facet_sql: str,
    facet_params: dict[str, Any],
    focus_prime: str,
    *,
    limit: int = BFS_DEGREE_CAP,
    hop: int = 0,
) -> list[GraphEdge]:
    """Adjacent competitors at shared agencies — relation beyond one obligation hop."""
    params = {**facet_params, "focus_prime": focus_prime}
    sql = f"""
        WITH target_agencies AS (
            SELECT DISTINCT ({AGENCY_EXPR}) AS agency
            FROM {PRIME_TABLE}
            WHERE recipient_name = :focus_prime
              {facet_sql}
        ),
        overlap AS (
            SELECT
                p.recipient_name AS other_prime,
                ({AGENCY_EXPR}) AS agency,
                COUNT(*) AS actions,
                {round_numeric("SUM(COALESCE(p.federal_action_obligation, 0)) / 1000000.0")} AS millions
            FROM {PRIME_TABLE} p
            WHERE p.recipient_name != :focus_prime
              {facet_sql}
              AND ({AGENCY_EXPR}) IN (SELECT agency FROM target_agencies)
            GROUP BY other_prime, agency
        )
        SELECT other_prime, agency, actions, millions
        FROM overlap
        ORDER BY millions DESC NULLS LAST
        LIMIT :limit
    """
    rows = (await session.execute(text(sql), {**params, "limit": limit})).all()
    seed = _node_id(NodeKind.PRIME, focus_prime)
    edges: list[GraphEdge] = []
    for r in rows:
        other = _node_id(NodeKind.PRIME, r.other_prime)
        edges.append(
            GraphEdge(
                source=seed,
                target=other,
                kind=EdgeKind.CO_OCCURRENCE,
                millions=float(r.millions or 0),
                actions=int(r.actions),
                hop=hop,
                meta={"shared_agency": r.agency},
            )
        )
    return edges


async def _vehicle_peer_edges(
    session: AsyncSession,
    facet_sql: str,
    facet_params: dict[str, Any],
    *,
    focus_prime: str | None = None,
    focus_vehicle_piid: str | None = None,
    limit: int = BFS_DEGREE_CAP,
    hop: int = 0,
) -> list[GraphEdge]:
    extra = ""
    params = dict(facet_params)
    if focus_prime:
        extra += " AND recipient_name = :focus_prime"
        params["focus_prime"] = focus_prime
    if focus_vehicle_piid:
        extra += (
            " AND COALESCE(NULLIF(TRIM(parent_award_id_piid), ''), NULLIF(TRIM(award_id_piid), ''))"
            " = :focus_vehicle_piid"
        )
        params["focus_vehicle_piid"] = focus_vehicle_piid
    sql = f"""
        WITH vehicle_primes AS (
            SELECT
                COALESCE(NULLIF(TRIM(parent_award_id_piid), ''), NULLIF(TRIM(award_id_piid), '')) AS vehicle_piid,
                recipient_name AS prime,
                COUNT(*) AS actions,
                {round_numeric("SUM(COALESCE(federal_action_obligation, 0)) / 1000000.0")} AS millions
            FROM {PRIME_TABLE}
            WHERE recipient_name IS NOT NULL
              AND COALESCE(NULLIF(TRIM(parent_award_id_piid), ''), NULLIF(TRIM(award_id_piid), '')) IS NOT NULL
              {facet_sql}
              {extra}
            GROUP BY vehicle_piid, prime
        )
        SELECT vehicle_piid, prime, actions, millions
        FROM vehicle_primes
        ORDER BY millions DESC NULLS LAST
        LIMIT :limit
    """
    rows = (await session.execute(text(sql), {**params, "limit": limit})).all()
    edges: list[GraphEdge] = []
    for r in rows:
        vehicle_label = f"IDV {r.vehicle_piid}"
        edges.append(
            GraphEdge(
                source=_node_id(NodeKind.VEHICLE, vehicle_label),
                target=_node_id(NodeKind.PRIME, r.prime),
                kind=EdgeKind.VEHICLE_MEMBER,
                millions=float(r.millions or 0),
                actions=int(r.actions),
                hop=hop,
                meta={"vehicle_piid": r.vehicle_piid},
            )
        )
    return edges


async def fetch_edges_for_node(
    session: AsyncSession,
    query: InsightFacetQuery,
    node_id: str,
    *,
    hop: int = 0,
    limit: int = BFS_DEGREE_CAP,
    seed_prime: str | None = None,
) -> list[GraphEdge]:
    """Fetch all relation families touching one node — used per BFS hop and browse expand."""
    kind, label = _parse_node_id(node_id)
    facet_sql, facet_params = build_facet_sql(query)
    edges: list[GraphEdge] = []

    if kind == NodeKind.PRIME:
        edges.extend(
            await _obligation_edges(
                session, facet_sql, facet_params, focus_prime=label, limit=limit, hop=hop
            )
        )
        edges.extend(await _teaming_edges(session, query, focus_prime=label, limit=limit, hop=hop))
        edges.extend(
            await _vehicle_peer_edges(
                session, facet_sql, facet_params, focus_prime=label, limit=limit, hop=hop
            )
        )
        if seed_prime and label != seed_prime:
            pass
        edges.extend(
            await _co_occurrence_edges(
                session, facet_sql, facet_params, label, limit=min(limit, 6), hop=hop
            )
        )
    elif kind == NodeKind.SUB:
        edges.extend(
            await _teaming_network_edges(
                session, query, label, exclude_prime=seed_prime, limit=limit, hop=hop
            )
        )
        edges.extend(
            await _obligation_edges(
                session, facet_sql, facet_params, focus_prime=label, limit=limit, hop=hop
            )
        )
    elif kind == NodeKind.AGENCY:
        edges.extend(
            await _obligation_edges(
                session, facet_sql, facet_params, focus_agency=label, limit=limit, hop=hop
            )
        )
    elif kind == NodeKind.VEHICLE:
        piid = label.replace("IDV ", "", 1).strip()
        edges.extend(
            await _vehicle_peer_edges(
                session,
                facet_sql,
                facet_params,
                focus_vehicle_piid=piid or None,
                limit=limit,
                hop=hop,
            )
        )
    return edges


async def resolve_graph_seeds(
    session: AsyncSession,
    query: InsightFacetQuery,
    *,
    seed_recipient: str = "",
    seed_agency: str = "",
) -> tuple[str, str, str | None]:
    """Pick BFS seeds — explicit facet wins; NAICS-only slices auto-seed top recipient + agency."""
    recipient = (seed_recipient or query.recipient or "").strip()
    agency = (seed_agency or query.agency or "").strip()
    note: str | None = None
    facet_sql, facet_params = build_facet_sql(query)

    if not recipient:
        sql = f"""
            SELECT recipient_name AS recipient
            FROM {PRIME_TABLE}
            WHERE recipient_name IS NOT NULL
              {facet_sql}
            GROUP BY recipient_name
            ORDER BY SUM(COALESCE(federal_action_obligation, 0)) DESC NULLS LAST
            LIMIT 1
        """
        row = (await session.execute(text(sql), facet_params)).first()
        if row and row.recipient:
            recipient = str(row.recipient).strip()
            note = f"Auto-seeded from top recipient in slice: {recipient}"

    if not agency:
        sql = f"""
            SELECT ({AGENCY_EXPR}) AS agency
            FROM {PRIME_TABLE}
            WHERE ({AGENCY_EXPR}) IS NOT NULL
              {facet_sql}
            GROUP BY agency
            ORDER BY SUM(COALESCE(federal_action_obligation, 0)) DESC NULLS LAST
            LIMIT 1
        """
        row = (await session.execute(text(sql), facet_params)).first()
        if row and row.agency:
            agency = str(row.agency).strip()
            agency_note = f"Auto-seeded agency: {agency}"
            note = f"{note} · {agency_note}" if note else agency_note

    return recipient, agency, note


async def build_relations_graph(
    session: AsyncSession,
    query: InsightFacetQuery,
    *,
    seed_recipient: str = "",
    seed_agency: str = "",
    max_hops: int = DEFAULT_MAX_HOPS,
    max_nodes: int = MAX_GRAPH_NODES,
) -> dict[str, Any]:
    """Multi-hop BFS — competitor/agency seed expands through teaming, vehicle, co-occurrence."""
    if not query.has_filters():
        return {"error": "Facet slice required.", "status": "no_query"}
    if not await table_exists(session, PRIME_TABLE):
        return {"error": "Prime awards table missing.", "status": "loading"}

    recipient, agency, seed_note = await resolve_graph_seeds(
        session, query, seed_recipient=seed_recipient, seed_agency=seed_agency
    )

    seeds: list[str] = []
    if recipient:
        seeds.append(_node_id(NodeKind.PRIME, recipient))
    if agency:
        seeds.append(_node_id(NodeKind.AGENCY, agency))
    if not seeds:
        return {"error": "No award rows in slice to seed relations trace.", "status": "no_seed"}

    visited: set[str] = set(seeds)
    hop_map: dict[str, int] = {s: 0 for s in seeds}
    all_edges: list[GraphEdge] = []
    frontier = list(seeds)

    for hop in range(1, max_hops + 1):
        if len(visited) >= max_nodes or not frontier:
            break
        next_frontier: list[str] = []
        for node_id in frontier:
            batch = await fetch_edges_for_node(
                session,
                query,
                node_id,
                hop=hop,
                limit=BFS_DEGREE_CAP,
                seed_prime=recipient or None,
            )
            for e in batch:
                all_edges.append(e)
                for nid in (e.source, e.target):
                    if nid not in visited and len(visited) < max_nodes:
                        visited.add(nid)
                        hop_map[nid] = hop
                        next_frontier.append(nid)
        frontier = next_frontier

    deduped = _dedupe_edges(all_edges)
    nodes = _nodes_from_edges(deduped, hop_map)
    if len(nodes) < MIN_EXPOSE_NODES and recipient:
        extra = await fetch_edges_for_node(
            session, query, _node_id(NodeKind.PRIME, recipient), hop=1, limit=BFS_DEGREE_CAP * 2
        )
        deduped = _dedupe_edges(all_edges + extra)
        nodes = _nodes_from_edges(deduped, hop_map)

    families = sorted({e.as_dict()["family"] for e in deduped})
    total_m = sum(n.millions_in + n.millions_out for n in nodes) / 2 if nodes else 0

    return {
        "mode": "relations_graph",
        "method": (
            f"Multi-hop BFS ({max_hops} hops) — org money, teaming network, vehicle peers, "
            "co-occurrence; people overlay when MCP available."
        ),
        "nodes": [n.as_dict() for n in nodes],
        "edges": [e.as_dict() for e in deduped],
        "relation_families": families,
        "summary": {
            "node_count": len(nodes),
            "edge_count": len(deduped),
            "max_hop": max(hop_map.values()) if hop_map else 0,
            "millions_in_subgraph": round(total_m, 2),
            "seed_recipient": recipient or None,
            "seed_agency": agency or None,
            "seed_note": seed_note,
        },
    }


async def build_expose_graph(
    session: AsyncSession,
    query: InsightFacetQuery,
    **kwargs: Any,
) -> dict[str, Any]:
    """Alias — expose is relations graph with multi-hop BFS."""
    return await build_relations_graph(session, query, **kwargs)


def build_browse_funnel(graph: dict[str, Any]) -> dict[str, Any]:
    """DR browse analogue — layered Sankey from relations graph edges."""
    edges = graph.get("edges") or []
    if not edges:
        return {"mode": "browse_funnel", "flows": []}
    flows: list[dict[str, Any]] = []
    for e in edges:
        src_label = e["source"].split("::", 1)[-1]
        tgt_label = e["target"].split("::", 1)[-1]
        flows.append({
            "source": src_label,
            "target": tgt_label,
            "millions": e.get("millions", 0),
            "kind": e.get("kind"),
            "family": e.get("family"),
        })
    return {
        "mode": "browse_funnel",
        "flows": flows[:MAX_SANKEY_LINKS],
        "summary": f"{len(flows)} relation flows across {', '.join(graph.get('relation_families') or [])}",
    }


MAX_SANKEY_LINKS = 24


async def expand_node_neighbors(
    session: AsyncSession,
    query: InsightFacetQuery,
    node_id: str,
    *,
    batch: int = EXPAND_BATCH,
    seed_prime: str | None = None,
) -> dict[str, Any]:
    """DR browse '+' — next hidden edges from one node."""
    edges = await fetch_edges_for_node(
        session, query, node_id, hop=0, limit=batch, seed_prime=seed_prime
    )
    trimmed = edges[:batch]
    nodes = _nodes_from_edges(trimmed)
    return {
        "mode": "browse_expand",
        "node_id": node_id,
        "nodes": [n.as_dict() for n in nodes],
        "edges": [e.as_dict() for e in trimmed],
    }


def merge_graph_expand(
    graph: dict[str, Any],
    expansion: dict[str, Any],
) -> dict[str, Any]:
    """Merge browse-expand batch into an existing relations graph payload."""
    if graph.get("error"):
        return graph
    node_by_id = {n["id"]: dict(n) for n in graph.get("nodes") or []}
    edge_keys = {
        (e["source"], e["target"], e.get("kind"))
        for e in graph.get("edges") or []
    }
    for n in expansion.get("nodes") or []:
        node_by_id.setdefault(n["id"], n)
    new_edges = list(graph.get("edges") or [])
    for e in expansion.get("edges") or []:
        key = (e["source"], e["target"], e.get("kind"))
        if key not in edge_keys:
            edge_keys.add(key)
            new_edges.append(e)
    merged = dict(graph)
    merged["nodes"] = list(node_by_id.values())[:MAX_GRAPH_NODES]
    merged["edges"] = new_edges[:MAX_GRAPH_EDGES]
    merged["summary"] = {
        **(graph.get("summary") or {}),
        "node_count": len(merged["nodes"]),
        "edge_count": len(merged["edges"]),
        "expanded_from": expansion.get("node_id"),
    }
    return merged


def encode_graph_path(edges: list[dict[str, Any]]) -> str:
    from thread.clew.path_link import encode_path_param

    return encode_path_param(
        [
            {
                "source": e["source"].split("::", 1)[-1],
                "target": e["target"].split("::", 1)[-1],
                "value": e["millions"],
            }
            for e in edges
        ]
    )


def _parse_json_payload(raw: str | dict[str, Any]) -> Any:
    if isinstance(raw, dict):
        return raw
    text = str(raw).strip()
    if not text:
        return {}
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        match = re.search(r"\{[\s\S]*\}|\[[\s\S]*\]", text)
        if match:
            return json.loads(match.group(0))
    return {}


def _person_display_name(record: dict[str, Any]) -> str | None:
    first = str(record.get("firstName") or "").strip()
    last = str(record.get("lastName") or "").strip()
    full = f"{first} {last}".strip()
    if full:
        return full
    for key in ("fullName", "name", "contactName"):
        val = str(record.get(key) or "").strip()
        if val:
            return val
    return None


def extract_people_from_sam_entity(payload: Any) -> list[dict[str, str]]:
    """Parse SAM Entity Management v3 payload — principals/POCs, not the whole relations graph."""
    rows: list[dict[str, str]] = []
    seen: set[str] = set()
    entities = payload.get("entityData") if isinstance(payload, dict) else None
    if not isinstance(entities, list):
        return rows

    def _add(name: str, title: str) -> None:
        key = name.lower()
        if key in seen:
            return
        seen.add(key)
        rows.append({"name": name, "title": title})

    for block in entities:
        if not isinstance(block, dict):
            continue
        poc_root = block.get("pointsOfContact")
        if isinstance(poc_root, dict):
            for poc in poc_root.values():
                if not isinstance(poc, dict):
                    continue
                name = _person_display_name(poc)
                if name:
                    _add(name, str(poc.get("title") or "").strip())
        core = block.get("coreData")
        if isinstance(core, dict):
            nested_poc = core.get("pointsOfContact")
            if isinstance(nested_poc, dict):
                for poc in nested_poc.values():
                    if not isinstance(poc, dict):
                        continue
                    name = _person_display_name(poc)
                    if name:
                        _add(name, str(poc.get("title") or "").strip())
    return rows[:_MAX_PEOPLE_EDGES]


def people_edges_from_records(
    prime_name: str,
    people: list[dict[str, str]],
    *,
    hop: int = 0,
) -> list[GraphEdge]:
    """Build person_affiliation edges — one family layered onto org/teaming/vehicle graph."""
    if not prime_name or not people:
        return []
    prime_id = _node_id(NodeKind.PRIME, prime_name)
    edges: list[GraphEdge] = []
    for row in people:
        name = (row.get("name") or "").strip()
        if not name:
            continue
        person_id = _node_id(NodeKind.PERSON, name)
        edges.append(
            GraphEdge(
                source=prime_id,
                target=person_id,
                kind=EdgeKind.PERSON_AFFILIATION,
                millions=0.0,
                actions=0,
                hop=hop,
                meta={"title": row.get("title") or "", "source": "sam_entity"},
            )
        )
    return edges


async def fetch_sam_people_edges(
    settings: Any,
    *,
    recipient_uei: str,
    prime_name: str,
) -> list[GraphEdge]:
    """Optional people overlay — SAM POCs when MCP + API key configured."""
    uei = (recipient_uei or "").strip()
    if not uei or not settings.enable_live_mcps:
        return []

    from thread.mcp.service import MCPService

    mcp = MCPService(settings)
    sam = next((s for s in mcp.list_servers() if s["id"] == "sam_gov"), None)
    if not sam or not sam.get("configured"):
        return []

    result = await mcp.invoke(
        "sam_gov",
        "lookup_entity_by_uei",
        {
            "uei": uei,
            "include_sections": ["entityRegistration", "coreData", "pointsOfContact"],
        },
    )
    if not result.get("ok"):
        return []
    payload = _parse_json_payload(result.get("output") or "")
    people = extract_people_from_sam_entity(payload)
    return people_edges_from_records(prime_name, people)


def merge_people_into_graph(
    graph: dict[str, Any],
    people_edges: list[GraphEdge],
) -> dict[str, Any]:
    """Merge people family into an existing relations graph without replacing other families."""
    if graph.get("error") or not people_edges:
        return graph
    existing = [GraphEdge(
        source=e["source"],
        target=e["target"],
        kind=EdgeKind(e["kind"]),
        millions=float(e.get("millions") or 0),
        actions=int(e.get("actions") or 0),
        hop=int(e.get("hop") or 0),
        meta={k: v for k, v in e.items() if k not in {
            "source", "target", "kind", "family", "millions", "actions", "hop",
        }},
    ) for e in graph.get("edges") or []]
    merged_edges = _dedupe_edges(existing + people_edges)
    hop_map = {
        n["id"]: int(n.get("hop") or 0)
        for n in graph.get("nodes") or []
    }
    for e in people_edges:
        for nid in (e.source, e.target):
            hop_map.setdefault(nid, e.hop)
    nodes = _nodes_from_edges(merged_edges, hop_map)
    families = sorted({e.as_dict()["family"] for e in merged_edges})
    out = dict(graph)
    out["nodes"] = [n.as_dict() for n in nodes]
    out["edges"] = [e.as_dict() for e in merged_edges]
    out["relation_families"] = families
    summary = dict(graph.get("summary") or {})
    summary["node_count"] = len(nodes)
    summary["edge_count"] = len(merged_edges)
    summary["people_overlay"] = len(people_edges)
    out["summary"] = summary
    return out


async def enrich_relations_graph(
    graph: dict[str, Any],
    settings: Any | None,
    *,
    recipient_uei: str | None,
    seed_prime: str | None,
) -> dict[str, Any]:
    """Attach people relation family when SAM MCP is available — does not replace other traces."""
    if not settings or graph.get("error") or not seed_prime:
        return graph
    uei = (recipient_uei or "").strip()
    if not uei:
        return graph
    people_edges = await fetch_sam_people_edges(
        settings,
        recipient_uei=uei,
        prime_name=seed_prime,
    )
    return merge_people_into_graph(graph, people_edges)


def format_relation_families(families: list[str] | None) -> str:
    """Human-readable family list for UI copy."""
    if not families:
        return "org money, teaming, vehicle peers, co-occurrence"
    return ", ".join(RELATION_FAMILY_LABELS.get(f, f) for f in families)