"""Knowledge graph query layer.

The graph uses data/knowledge_graph.json as its single source of truth and is
loaded into SQLite at startup. It supports entity search, neighbor traversal,
relation-type filtering and bidirectional CMIS field/item/device linkage."""

from __future__ import annotations

import json
import sqlite3
from collections import defaultdict
from typing import Any

from .db import rows_as_dicts


def _like(value: str) -> str:
    """Escape LIKE wildcards so user input is never treated as a pattern."""
    escaped = value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    return f"%{escaped}%"


def _decode(row: dict, keys: tuple[str, ...]) -> dict:
    for key in keys:
        raw = row.get(key)
        if isinstance(raw, str):
            try:
                row[key] = json.loads(raw)
            except ValueError:
                pass
    return row


def stats(conn: sqlite3.Connection) -> dict:
    by_type = {
        r["type"]: r["n"]
        for r in conn.execute("SELECT type, COUNT(*) AS n FROM kg_entities GROUP BY type ORDER BY n DESC")
    }
    by_relation = {
        r["type"]: r["n"]
        for r in conn.execute("SELECT type, COUNT(*) AS n FROM kg_relations GROUP BY type ORDER BY n DESC")
    }
    confidence = {
        r["confidence"]: r["n"]
        for r in conn.execute("SELECT confidence, COUNT(*) AS n FROM kg_entities GROUP BY confidence")
    }
    return {
        "entities": sum(by_type.values()),
        "relations": conn.execute("SELECT COUNT(*) FROM kg_relations").fetchone()[0],
        "sources": conn.execute("SELECT COUNT(*) FROM kg_sources").fetchone()[0],
        "links": conn.execute("SELECT COUNT(*) FROM kg_links").fetchone()[0],
        "pending": conn.execute("SELECT COUNT(*) FROM kg_pending WHERE status = 'open'").fetchone()[0],
        "entities_by_type": by_type,
        "relations_by_type": by_relation,
        "entities_by_confidence": confidence,
    }


def list_entities(conn: sqlite3.Connection, *, entity_type: str = "", q: str = "",
                  confidence: str = "", limit: int = 100, offset: int = 0) -> dict:
    where, params = [], []
    if entity_type:
        where.append("type = ?"); params.append(entity_type)
    if confidence:
        where.append("confidence = ?"); params.append(confidence)
    if q:
        where.append("(name LIKE ? ESCAPE '\\' OR summary LIKE ? ESCAPE '\\' OR entity_id LIKE ? ESCAPE '\\')")
        params.extend([_like(q)] * 3)
    clause = "WHERE " + " AND ".join(where) if where else ""
    total = conn.execute(f"SELECT COUNT(*) FROM kg_entities {clause}", params).fetchone()[0]
    rows = conn.execute(
        f"SELECT * FROM kg_entities {clause} ORDER BY type, entity_id LIMIT ? OFFSET ?",
        (*params, min(limit, 500), max(offset, 0)),
    ).fetchall()
    return {"total": total, "items": [_decode(dict(r), ("source_ids", "attrs")) for r in rows]}


def entity_detail(conn: sqlite3.Connection, entity_id: str, depth: int = 1) -> dict | None:
    row = conn.execute("SELECT * FROM kg_entities WHERE entity_id = ?", (entity_id,)).fetchone()
    if row is None:
        return None
    entity = _decode(dict(row), ("source_ids", "attrs"))

    def edges(direction: str) -> list[dict]:
        col = "src" if direction == "out" else "dst"
        other = "dst" if direction == "out" else "src"
        sql = f"""
            SELECT r.*, e.name AS neighbor_name, e.type AS neighbor_type, e.confidence AS neighbor_confidence
            FROM kg_relations r JOIN kg_entities e ON e.entity_id = r.{other}
            WHERE r.{col} = ? ORDER BY r.type, r.{other}
        """
        return [_decode(dict(r), ("source_ids", "attrs"))
                for r in conn.execute(sql, (entity_id,)).fetchall()]

    outgoing, incoming = edges("out"), edges("in")
    result = {"entity": entity, "outgoing": outgoing, "incoming": incoming, "depth": depth, "two_hop": []}
    if depth >= 2:
        seen = {entity_id}
        frontier = [e["dst"] for e in outgoing] + [e["src"] for e in incoming]
        for nid in frontier:
            if nid in seen:
                continue
            seen.add(nid)
            nrow = conn.execute("SELECT * FROM kg_entities WHERE entity_id = ?", (nid,)).fetchone()
            if nrow:
                result["two_hop"].append(_decode(dict(nrow), ("source_ids", "attrs")))
    result["sources"] = resolve_sources(conn, entity.get("source_ids", []))
    return result


def list_relations(conn: sqlite3.Connection, *, relation_type: str = "", src: str = "",
                   dst: str = "", q: str = "", limit: int = 200, offset: int = 0) -> dict:
    where, params = [], []
    if relation_type:
        where.append("r.type = ?"); params.append(relation_type)
    if src:
        where.append("r.src = ?"); params.append(src)
    if dst:
        where.append("r.dst = ?"); params.append(dst)
    if q:
        where.append("(r.label LIKE ? ESCAPE '\\' OR r.src LIKE ? ESCAPE '\\' OR r.dst LIKE ? ESCAPE '\\')")
        params.extend([_like(q)] * 3)
    clause = "WHERE " + " AND ".join(where) if where else ""
    total = conn.execute(f"SELECT COUNT(*) FROM kg_relations r {clause}", params).fetchone()[0]
    rows = conn.execute(
        f"""SELECT r.*, s.name AS src_name, d.name AS dst_name
            FROM kg_relations r
            LEFT JOIN kg_entities s ON s.entity_id = r.src
            LEFT JOIN kg_entities d ON d.entity_id = r.dst
            {clause} ORDER BY r.type, r.relation_id LIMIT ? OFFSET ?""",
        (*params, min(limit, 1000), max(offset, 0)),
    ).fetchall()
    return {"total": total, "items": [_decode(dict(r), ("source_ids", "attrs")) for r in rows]}


def resolve_sources(conn: sqlite3.Connection, source_ids: list[str]) -> list[dict]:
    if not source_ids:
        return []
    placeholders = ",".join("?" for _ in source_ids)
    return rows_as_dicts(conn.execute(
        f"SELECT * FROM kg_sources WHERE source_id IN ({placeholders})", tuple(source_ids)
    ).fetchall())


def list_sources(conn: sqlite3.Connection) -> list[dict]:
    return rows_as_dicts(conn.execute("SELECT * FROM kg_sources ORDER BY kind, source_id").fetchall())


def list_pending(conn: sqlite3.Connection) -> list[dict]:
    rows = conn.execute("SELECT * FROM kg_pending ORDER BY pending_id").fetchall()
    return [_decode(dict(r), ("source_ids",)) for r in rows]


def links_for(conn: sqlite3.Connection, cmis_ref: str, *, include_sources: bool = True) -> dict:
    """Resolve CMIS field/item/device references to graph entities."""
    rows = conn.execute(
        """SELECT l.*, e.name, e.type, e.summary, e.confidence, e.source_ids
           FROM kg_links l LEFT JOIN kg_entities e ON e.entity_id = l.entity_id
           WHERE l.cmis_ref = ? ORDER BY l.relation, l.entity_id""",
        (cmis_ref,),
    ).fetchall()
    items = []
    for r in rows:
        d = _decode(dict(r), ("source_ids",))
        if include_sources:
            d["sources"] = resolve_sources(conn, d.get("source_ids", []))
        items.append(d)
    return {"cmis_ref": cmis_ref, "total": len(items), "items": items}


def links_for_entity(conn: sqlite3.Connection, entity_id: str) -> dict:
    """Reverse lookup: which CMIS fields/items/devices reference a graph entity."""
    rows = conn.execute(
        """SELECT cmis_ref, relation, note FROM kg_links
           WHERE entity_id = ? ORDER BY relation, cmis_ref""", (entity_id,)
    ).fetchall()
    return {"entity_id": entity_id, "total": len(rows), "items": rows_as_dicts(rows)}


def graph(conn: sqlite3.Connection, *, entity_type: str = "", limit: int = 300) -> dict:
    """Return the node/edge subset used by the graph visualization."""
    params: list[Any] = []
    clause = ""
    if entity_type:
        clause = "WHERE type = ?"; params.append(entity_type)
    nodes = rows_as_dicts(conn.execute(
        f"SELECT entity_id, type, name, summary, confidence FROM kg_entities {clause} ORDER BY entity_id LIMIT ?",
        (*params, limit),
    ).fetchall())
    ids = {n["entity_id"] for n in nodes}
    edges = [dict(r) for r in conn.execute(
        "SELECT relation_id, src, dst, type, label, confidence FROM kg_relations ORDER BY type, relation_id"
    ).fetchall() if r["src"] in ids and r["dst"] in ids]
    return {"nodes": nodes, "edges": edges, "truncated": len(nodes) >= limit}


def sources_coverage(conn: sqlite3.Connection) -> dict:
    """Count entities and relations supported by each source, for source coverage."""
    ent: dict[str, int] = defaultdict(int)
    rel: dict[str, int] = defaultdict(int)
    for row in conn.execute("SELECT source_ids FROM kg_entities"):
        for sid in _decode(dict(row), ("source_ids",))["source_ids"] or []:
            ent[sid] += 1
    for row in conn.execute("SELECT source_ids FROM kg_relations"):
        for sid in _decode(dict(row), ("source_ids",))["source_ids"] or []:
            rel[sid] += 1
    out = []
    for src in list_sources(conn):
        sid = src["source_id"]
        out.append({**src, "entities": ent.get(sid, 0), "relations": rel.get(sid, 0)})
    return {"sources": out}
