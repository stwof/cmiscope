"""REST API: CMIS query/display, configuration management, CDB operations and KG.

Uniform response envelope: {"ok": true, "data": ...} /
{"ok": false, "error": {...}}. All SQL uses bound parameters and every write is
re-validated on the server. Hardware access is delegated to the configured
transport adapter and is disabled by default.
"""

from __future__ import annotations

import json
import logging
import re
import sqlite3
from datetime import datetime, timezone
from typing import Any

from . import cmis_spec, kg, targets
from .adapters import AdapterError, get_adapter
from .config import Settings, public_settings
from .db import insert_row, rows_as_dicts
from .validation import validate, _json_list

log = logging.getLogger("cmis.api")

PROJECT_NAME = "CMIScope"
PROJECT_TAGLINE = "Lightweight CMIS dashboard for optical modules"

_FIELD_JSON_KEYS = ("source_ids",)
_ITEM_JSON_KEYS = ("allowed_values", "source_ids")
_CDB_JSON_KEYS = ("source_ids", "detail")


class ApiError(Exception):
    def __init__(self, status: int, code: str, message: str, details: Any = None):
        super().__init__(message)
        self.status = status
        self.code = code
        self.message = message
        self.details = details

    def payload(self) -> dict:
        err: dict[str, Any] = {"code": self.code, "message": self.message}
        if self.details is not None:
            err["details"] = self.details
        return {"ok": False, "error": err}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _decode_json_fields(row: dict, keys: tuple[str, ...]) -> dict:
    for key in keys:
        raw = row.get(key)
        if isinstance(raw, str):
            try:
                row[key] = json.loads(raw)
            except ValueError:
                pass
    return row


def _int(query: dict, name: str, default: int, low: int, high: int) -> int:
    raw = query.get(name, [str(default)])[0] if isinstance(query.get(name), list) else query.get(name, default)
    try:
        return max(low, min(high, int(raw)))
    except (TypeError, ValueError):
        raise ApiError(400, "BAD_PARAM", f"Parameter {name} must be an integer")


def _q(query: dict, name: str, default: str = "") -> str:
    val = query.get(name, default)
    if isinstance(val, list):
        val = val[0] if val else default
    return str(val).strip()


def _like(value: str) -> str:
    escaped = value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    return f"%{escaped}%"


def ok(data: Any, **extra) -> tuple[int, dict]:
    payload: dict[str, Any] = {"ok": True, "data": data}
    payload.update(extra)
    return 200, payload


def _parse_register_location(item: sqlite3.Row) -> tuple[str, int]:
    """Extract a numeric byte offset, or reject pending register mappings."""
    text = str(item["byte_offset"] or "")
    match = re.search(r"\d+", text)
    if match is None:
        raise ApiError(409, "REGISTER_OFFSET_PENDING",
                       f"Byte offset for {item['field_key']} is still pending ({text!r}); "
                       "hardware writes are refused until the OIF clause is verified",
                       {"field_key": item["field_key"], "byte_offset": text})
    return str(item["page"] or ""), int(match.group(0))


# --------------------------------------------------------------------------- overview

def overview(conn: sqlite3.Connection, settings: Settings) -> tuple[int, dict]:
    scalar = lambda sql: conn.execute(sql).fetchone()[0]  # noqa: E731
    status_counts = {
        r["status"]: r["n"]
        for r in conn.execute("SELECT status, COUNT(*) AS n FROM devices GROUP BY status")
    }
    section_counts = {
        r["section"]: r["n"]
        for r in conn.execute("SELECT section, COUNT(*) AS n FROM fields GROUP BY section")
    }
    recent = rows_as_dicts(conn.execute(
        """SELECT c.id, c.device_id, d.name AS device_name, c.field_key,
                  c.old_value, c.new_value, c.result, c.created_at, c.operator
           FROM config_changes c LEFT JOIN devices d ON d.device_id = c.device_id
           ORDER BY c.id DESC LIMIT 8"""
    ).fetchall())
    return ok({
        "devices": scalar("SELECT COUNT(*) FROM devices"),
        "modules": scalar("SELECT COUNT(*) FROM modules"),
        "fields": scalar("SELECT COUNT(*) FROM fields"),
        "config_items": scalar("SELECT COUNT(*) FROM config_items"),
        "writable_items": scalar("SELECT COUNT(*) FROM config_items WHERE writable = 1"),
        "changes": scalar("SELECT COUNT(*) FROM config_changes"),
        "cdb_operations": scalar("SELECT COUNT(*) FROM cdb_operations"),
        "status_counts": status_counts,
        "section_counts": section_counts,
        "kg": kg.stats(conn),
        "recent_changes": recent,
        "service": public_settings(settings),
        "project": {"name": PROJECT_NAME, "tagline": PROJECT_TAGLINE},
        "framework": {"name": "Tabler", "version": "1.7.3", "license": "MIT",
                      "url": "https://github.com/tabler/tabler"},
        "access": get_adapter(settings).capabilities(),
        "generated_at": _now(),
    })


# --------------------------------------------------------------------------- search

def search(conn: sqlite3.Connection, query: dict) -> tuple[int, dict]:
    term = _q(query, "q")
    scope = _q(query, "scope", "all").lower()
    if scope not in ("all", "device", "field", "config", "kg"):
        raise ApiError(400, "BAD_PARAM", "scope must be one of all/device/field/config/kg")
    if not term:
        raise ApiError(400, "MISSING_QUERY", "Query parameter q is required")
    pattern = _like(term)
    groups: dict[str, list] = {}

    if scope in ("all", "device"):
        groups["devices"] = rows_as_dicts(conn.execute(
            """SELECT device_id, name, device_type, vendor, model, location, status, cmis_revision
               FROM devices
               WHERE device_id LIKE ? ESCAPE '\\' OR name LIKE ? ESCAPE '\\'
                  OR vendor LIKE ? ESCAPE '\\' OR model LIKE ? ESCAPE '\\'
                  OR location LIKE ? ESCAPE '\\'
               ORDER BY device_id LIMIT 20""", (pattern,) * 5).fetchall())
    if scope in ("all", "field"):
        groups["fields"] = rows_as_dicts(conn.execute(
            """SELECT field_key, name, name_en, page, byte_offset, data_type, access,
                      section, spec_ref, description, confidence
               FROM fields
               WHERE field_key LIKE ? ESCAPE '\\' OR name LIKE ? ESCAPE '\\'
                  OR name_en LIKE ? ESCAPE '\\' OR description LIKE ? ESCAPE '\\'
                  OR description_en LIKE ? ESCAPE '\\' OR page LIKE ? ESCAPE '\\'
                  OR spec_ref LIKE ? ESCAPE '\\'
               ORDER BY field_key LIMIT 20""", (pattern,) * 7).fetchall())
    if scope in ("all", "config"):
        groups["config_items"] = rows_as_dicts(conn.execute(
            """SELECT c.id, c.device_id, d.name AS device_name, c.field_key, c.label,
                      c.page, c.byte_offset, c.section, c.value, c.raw_hex, c.writable, c.spec_ref
               FROM config_items c JOIN devices d ON d.device_id = c.device_id
               WHERE c.field_key LIKE ? ESCAPE '\\' OR c.label LIKE ? ESCAPE '\\'
                  OR c.value LIKE ? ESCAPE '\\' OR c.spec_ref LIKE ? ESCAPE '\\'
                  OR d.name LIKE ? ESCAPE '\\'
               ORDER BY c.device_id, c.field_key LIMIT 30""", (pattern,) * 5).fetchall())
    if scope in ("all", "kg"):
        groups["kg_entities"] = kg.list_entities(conn, q=term, limit=20)["items"]

    return ok({"query": term, "scope": scope, "groups": groups,
               "total": sum(len(v) for v in groups.values())})


# --------------------------------------------------------------------------- devices

def list_devices(conn: sqlite3.Connection, query: dict) -> tuple[int, dict]:
    term, status = _q(query, "q"), _q(query, "status")
    access_mode = _q(query, "access_mode")
    limit, offset = _int(query, "limit", 100, 1, 500), _int(query, "offset", 0, 0, 100000)
    where, params = [], []
    if term:
        where.append("(device_id LIKE ? ESCAPE '\\' OR name LIKE ? ESCAPE '\\' OR vendor LIKE ? ESCAPE '\\' OR model LIKE ? ESCAPE '\\')")
        params.extend([_like(term)] * 4)
    if status:
        where.append("status = ?"); params.append(status)
    if access_mode:
        where.append("access_mode = ?"); params.append(access_mode)
    clause = "WHERE " + " AND ".join(where) if where else ""
    total = conn.execute(f"SELECT COUNT(*) FROM devices {clause}", params).fetchone()[0]
    rows = conn.execute(
        f"""SELECT d.*, (SELECT COUNT(*) FROM modules m WHERE m.device_id = d.device_id) AS module_count,
                   (SELECT COUNT(*) FROM config_items c WHERE c.device_id = d.device_id) AS config_count
            FROM devices d {clause} ORDER BY d.device_id LIMIT ? OFFSET ?""",
        (*params, limit, offset),
    ).fetchall()
    return ok({"total": total, "items": rows_as_dicts(rows)})


def device_detail(conn: sqlite3.Connection, device_id: str) -> tuple[int, dict]:
    dev = conn.execute("SELECT * FROM devices WHERE device_id = ?", (device_id,)).fetchone()
    if dev is None:
        raise ApiError(404, "DEVICE_NOT_FOUND", f"Device not found: {device_id}")
    modules = rows_as_dicts(conn.execute(
        "SELECT * FROM modules WHERE device_id = ? ORDER BY module_id", (device_id,)).fetchall())
    for m in modules:
        _decode_json_fields(m, ("advertised_apps",))
    items = rows_as_dicts(conn.execute(
        """SELECT c.*, f.description, f.description_en, f.name_en, f.access AS field_access,
                  f.confidence AS field_confidence, f.kg_entity_id, f.name AS field_name
           FROM config_items c JOIN fields f ON f.field_key = c.field_key
           WHERE c.device_id = ? ORDER BY c.section, c.page, c.field_key""", (device_id,)).fetchall())
    for it in items:
        _decode_json_fields(it, _ITEM_JSON_KEYS)
    changes = rows_as_dicts(conn.execute(
        "SELECT * FROM config_changes WHERE device_id = ? ORDER BY id DESC LIMIT 10", (device_id,)).fetchall())
    return ok({"device": dict(dev), "modules": modules, "config_items": items,
               "fields": items, "recent_changes": changes,
               "kg_links": kg.links_for(conn, device_id)["items"]})


def list_fields(conn: sqlite3.Connection, query: dict) -> tuple[int, dict]:
    term, page, access = _q(query, "q"), _q(query, "page"), _q(query, "access")
    section = _q(query, "section")
    where, params = [], []
    if term:
        where.append("(field_key LIKE ? ESCAPE '\\' OR name LIKE ? ESCAPE '\\' OR name_en LIKE ? ESCAPE '\\' OR description LIKE ? ESCAPE '\\' OR spec_ref LIKE ? ESCAPE '\\')")
        params.extend([_like(term)] * 5)
    if page:
        where.append("page = ?"); params.append(page)
    if access:
        where.append("access = ?"); params.append(access)
    if section:
        where.append("section = ?"); params.append(section.upper())
    clause = "WHERE " + " AND ".join(where) if where else ""
    rows = conn.execute(f"SELECT * FROM fields {clause} ORDER BY section, page, field_key LIMIT 300",
                        params).fetchall()
    items = [_decode_json_fields(dict(r), _FIELD_JSON_KEYS) for r in rows]
    return ok({"total": len(items), "items": items})


def list_config_items(conn: sqlite3.Connection, query: dict) -> tuple[int, dict]:
    term, device_id = _q(query, "q"), _q(query, "device_id")
    field_key, writable = _q(query, "field_key"), _q(query, "writable")
    section = _q(query, "section").upper()
    limit, offset = _int(query, "limit", 200, 1, 1000), _int(query, "offset", 0, 0, 100000)
    where, params = [], []
    if term:
        where.append("(c.field_key LIKE ? ESCAPE '\\' OR c.label LIKE ? ESCAPE '\\' OR c.value LIKE ? ESCAPE '\\' OR c.spec_ref LIKE ? ESCAPE '\\' OR d.name LIKE ? ESCAPE '\\')")
        params.extend([_like(term)] * 5)
    if device_id:
        where.append("c.device_id = ?"); params.append(device_id)
    if field_key:
        where.append("c.field_key = ?"); params.append(field_key)
    if section:
        where.append("c.section = ?"); params.append(section)
    if writable in ("0", "1"):
        where.append("c.writable = ?"); params.append(int(writable))
    clause = "WHERE " + " AND ".join(where) if where else ""
    total = conn.execute(
        f"SELECT COUNT(*) FROM config_items c JOIN devices d ON d.device_id = c.device_id {clause}", params
    ).fetchone()[0]
    rows = conn.execute(
        f"""SELECT c.*, d.name AS device_name, d.name_en AS device_name_en,
                   f.description AS field_description, f.description_en AS field_description_en,
                   f.name_en AS field_name_en, f.access AS field_access,
                   f.confidence AS field_confidence
            FROM config_items c JOIN devices d ON d.device_id = c.device_id
            JOIN fields f ON f.field_key = c.field_key
            {clause} ORDER BY c.device_id, c.section, c.page, c.field_key LIMIT ? OFFSET ?""",
        (*params, limit, offset),
    ).fetchall()
    items = [_decode_json_fields(dict(r), _ITEM_JSON_KEYS) for r in rows]
    return ok({"total": total, "items": items})


def config_item_detail(conn: sqlite3.Connection, item_id: int) -> tuple[int, dict]:
    row = conn.execute("SELECT * FROM config_items WHERE id = ?", (item_id,)).fetchone()
    if row is None:
        raise ApiError(404, "CONFIG_ITEM_NOT_FOUND", f"Configuration item not found: id={item_id}")
    item = _decode_json_fields(dict(row), _ITEM_JSON_KEYS)
    field = conn.execute("SELECT * FROM fields WHERE field_key = ?", (item["field_key"],)).fetchone()
    field_dict = _decode_json_fields(dict(field), _FIELD_JSON_KEYS) if field else None
    history = rows_as_dicts(conn.execute(
        "SELECT * FROM config_changes WHERE config_item_id = ? ORDER BY id DESC LIMIT 20", (item_id,)).fetchall())
    return ok({
        "item": item,
        "field": field_dict,
        "section": cmis_spec.SECTION_BY_KEY.get(item.get("section") or "LOW_PAGE"),
        "rules": {
            "data_type": item["data_type"], "allowed_values": item["allowed_values"],
            "min_value": item["min_value"], "max_value": item["max_value"],
            "regex": item["regex"], "writable": bool(item["writable"]),
            "cross_rule": item["cross_rule"], "spec_ref": item["spec_ref"],
        },
        "kg": kg.links_for(conn, item["field_key"]),
        "kg_by_device": kg.links_for(conn, item["device_id"])["items"],
        "history": history,
    })


# --------------------------------------------------------------------------- configuration writes

def _get_item(conn: sqlite3.Connection, item_id: int) -> sqlite3.Row:
    row = conn.execute("SELECT * FROM config_items WHERE id = ?", (item_id,)).fetchone()
    if row is None:
        raise ApiError(404, "CONFIG_ITEM_NOT_FOUND", f"Configuration item not found: id={item_id}")
    return row


def _body_value(body: Any) -> Any:
    if not isinstance(body, dict):
        raise ApiError(400, "BAD_REQUEST", "Request body must be a JSON object")
    if "value" not in body:
        raise ApiError(400, "MISSING_VALUE", "Request body is missing the value field")
    return body["value"]


def validate_item(conn: sqlite3.Connection, settings: Settings, item_id: int,
                  body: Any) -> tuple[int, dict]:
    item = _get_item(conn, item_id)
    report = validate(conn, item, _body_value(body))
    report["read_only_service"] = settings.read_only
    report["access_mode"] = settings.access_mode
    if settings.read_only:
        report["warnings"].append({"code": "SERVICE_READ_ONLY",
                                   "message": "Service is read-only; validation may pass but saving is refused"})
    return ok({"report": report})


def save_item(conn: sqlite3.Connection, settings: Settings, item_id: int,
              body: Any) -> tuple[int, dict]:
    if settings.read_only:
        raise ApiError(409, "SERVICE_READ_ONLY",
                       "Service is read-only (read_only=true); configuration writes are refused")
    item = _get_item(conn, item_id)
    if not isinstance(body, dict):
        raise ApiError(400, "BAD_REQUEST", "Request body must be a JSON object")
    value = _body_value(body)

    expected = body.get("expected_version")
    if expected is not None:
        try:
            expected = int(expected)
        except (TypeError, ValueError):
            raise ApiError(400, "BAD_PARAM", "expected_version must be an integer")
        if expected != item["version"]:
            raise ApiError(409, "VERSION_CONFLICT",
                           f"Item was modified by another operation (current version={item['version']}, "
                           f"submitted version={expected})",
                           {"current_version": item["version"], "current_value": item["value"]})

    report = validate(conn, item, value)
    if not report["valid"]:
        raise ApiError(400, "VALIDATION_FAILED", "Pre-save validation failed; nothing was written", report)

    before = {"value": item["value"], "raw_hex": item["raw_hex"], "version": item["version"]}
    normalized = report["normalized"]
    operator = str(body.get("operator") or settings.operator)[:64]
    note = str(body.get("note") or "")[:200]
    ts = _now()

    # Apply through the configured transport when hardware writes are enabled.
    applied = False
    transport_result: dict[str, Any] = {}
    effective, _ = _device_settings(settings, item["device_id"])
    if effective.access_mode != "mirror" and settings.allow_hardware_write:
        adapter = get_adapter(effective)
        page, offset = _parse_register_location(item)
        try:
            adapter.enforce_write_policy(page, offset)
            adapter.write_register(item["device_id"], item["module_id"], page, offset,
                                    normalized["raw_hex"] or "0x00")
            applied = True
            transport_result = {"adapter": settings.access_mode, "page": page, "offset": offset}
        except AdapterError as exc:
            raise ApiError(exc.status, exc.code, exc.message, exc.details)

    result = "applied" if applied else "staged"
    message = (f"Saved {'to the target device' if applied else 'to the local mirror (staged, no hardware write)'}: "
               f"{item['field_key']} {before['value']} -> {normalized['value']}")
    if note:
        message += f"; note: {note}"

    with conn:
        conn.execute(
            "UPDATE config_items SET value = ?, raw_hex = ?, updated_at = ?, version = version + 1 WHERE id = ?",
            (normalized["value"], normalized["raw_hex"], ts, item_id),
        )
        cur = conn.execute(
            """INSERT INTO config_changes
               (device_id, field_key, config_item_id, old_value, new_value, old_raw_hex, new_raw_hex,
                result, message, validation_report, operator, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (item["device_id"], item["field_key"], item_id, before["value"], normalized["value"],
             before["raw_hex"], normalized["raw_hex"], result, message,
             json.dumps(report, ensure_ascii=False), operator, ts),
        )
        change_id = cur.lastrowid

    updated = _decode_json_fields(dict(conn.execute(
        "SELECT * FROM config_items WHERE id = ?", (item_id,)).fetchone()), _ITEM_JSON_KEYS)
    change = dict(conn.execute("SELECT * FROM config_changes WHERE id = ?", (change_id,)).fetchone())
    return ok({
        "item": updated,
        "change": change,
        "diff": {"before": before, "after": {"value": normalized["value"],
                                             "raw_hex": normalized["raw_hex"],
                                             "version": updated["version"]}},
        "validation": report,
        "result": result,
        "applied_to_hardware": applied,
        "transport": transport_result,
        "message": message,
    })


def list_changes(conn: sqlite3.Connection, query: dict) -> tuple[int, dict]:
    device_id = _q(query, "device_id")
    limit = _int(query, "limit", 100, 1, 500)
    where, params = ("WHERE c.device_id = ?", [device_id]) if device_id else ("", [])
    rows = conn.execute(
        f"""SELECT c.*, d.name AS device_name FROM config_changes c
            LEFT JOIN devices d ON d.device_id = c.device_id
            {where} ORDER BY c.id DESC LIMIT ?""", (*params, limit)).fetchall()
    return ok({"total": len(rows),
               "items": [_decode_json_fields(dict(r), ("validation_report",)) for r in rows]})


# --------------------------------------------------------------------------- CMIS partitions

def list_sections(conn: sqlite3.Connection) -> tuple[int, dict]:
    counts = {r["section"]: r["n"] for r in
              conn.execute("SELECT section, COUNT(*) AS n FROM fields GROUP BY section")}
    sections = []
    for item in cmis_spec.SECTIONS:
        section = dict(item)
        section["field_count"] = counts.get(item["key"], 0)
        sections.append(section)
    return ok({
        "items": sections,
        "lower_memory_map": cmis_spec.LOWER_MEMORY_MAP,
        "upper_page_00h": cmis_spec.UPPER_PAGE_00H,
        "cdb_frame": cmis_spec.CDB_FRAME,
        "cdb_status": cmis_spec.CDB_STATUS,
        "spec_releases": cmis_spec.SPEC_RELEASES,
        "source_ids": cmis_spec.SOURCE_IDS,
    })


def module_cmis_view(conn: sqlite3.Connection, query: dict) -> tuple[int, dict]:
    """Group a module's registers by the CMIS partitions defined in cmis_spec."""
    device_id = _q(query, "device_id")
    wanted = _q(query, "section").upper()
    if not device_id:
        rows = conn.execute("SELECT device_id FROM devices ORDER BY device_id LIMIT 1").fetchall()
        if not rows:
            raise ApiError(404, "DEVICE_NOT_FOUND", "No devices are configured")
        device_id = rows[0]["device_id"]
    dev = conn.execute("SELECT * FROM devices WHERE device_id = ?", (device_id,)).fetchone()
    if dev is None:
        raise ApiError(404, "DEVICE_NOT_FOUND", f"Device not found: {device_id}")
    module = conn.execute("SELECT * FROM modules WHERE device_id = ? ORDER BY module_id LIMIT 1",
                          (device_id,)).fetchone()
    module_dict = dict(module) if module else None
    if module_dict:
        _decode_json_fields(module_dict, ("advertised_apps",))

    items = rows_as_dicts(conn.execute(
        """SELECT c.*, f.description, f.description_en, f.name_en, f.name AS field_name,
                  f.access AS field_access, f.confidence AS field_confidence,
                  f.kg_entity_id, f.bit_range
           FROM config_items c JOIN fields f ON f.field_key = c.field_key
           WHERE c.device_id = ? ORDER BY c.section, c.page, c.field_key""", (device_id,)).fetchall())
    for item in items:
        _decode_json_fields(item, _ITEM_JSON_KEYS)

    sections = []
    for spec in cmis_spec.SECTIONS:
        if wanted and spec["key"] != wanted:
            continue
        group = [i for i in items if (i.get("section") or "LOW_PAGE") == spec["key"]]
        entry = dict(spec)
        entry["items"] = group
        entry["writable_count"] = sum(1 for i in group if i["writable"])
        entry["registers"] = (cmis_spec.LOWER_MEMORY_MAP if spec["key"] == "LOW_PAGE"
                              else cmis_spec.CDB_FRAME if spec["key"] == "CDB" else [])
        sections.append(entry)
    return ok({"device": dict(dev), "module": module_dict,
               "sections": sections, "total_items": len(items),
               "spec_releases": cmis_spec.SPEC_RELEASES})


# --------------------------------------------------------------------------- CDB operations

def cdb_commands(conn: sqlite3.Connection) -> tuple[int, dict]:
    return ok({"items": cmis_spec.CDB_COMMANDS, "total": len(cmis_spec.CDB_COMMANDS),
               "page": cmis_spec.CDB_PAGE, "epl_pages": cmis_spec.CDB_EPL_PAGES,
               "lpl_max": cmis_spec.CDB_LPL_MAX, "epl_max": cmis_spec.CDB_EPL_MAX,
               "i2c_addr": cmis_spec.CDB_I2C_ADDR,
               "frame": cmis_spec.CDB_FRAME, "status_registers": cmis_spec.CDB_STATUS,
               "spec_releases": cmis_spec.SPEC_RELEASES})


def cdb_compose(body: Any) -> tuple[int, dict]:
    if not isinstance(body, dict):
        raise ApiError(400, "BAD_REQUEST", "Request body must be a JSON object")
    frame = cmis_spec.compose_frame(str(body.get("cmd_id") or ""),
                                    str(body.get("lpl_hex") or ""),
                                    str(body.get("epl_hex") or ""))
    if not frame["valid"]:
        raise ApiError(400, "CDB_VALIDATION_FAILED",
                       "CDB frame validation failed; nothing was sent to hardware", frame["errors"])
    return ok({"frame": frame, "applied_to_hardware": False})


def cdb_execute(conn: sqlite3.Connection, settings: Settings, body: Any) -> tuple[int, dict]:
    if not isinstance(body, dict):
        raise ApiError(400, "BAD_REQUEST", "Request body must be a JSON object")
    frame = cmis_spec.compose_frame(str(body.get("cmd_id") or ""),
                                    str(body.get("lpl_hex") or ""),
                                    str(body.get("epl_hex") or ""))
    if not frame["valid"]:
        raise ApiError(400, "CDB_VALIDATION_FAILED",
                       "CDB frame validation failed; nothing was sent to hardware", frame["errors"])
    device_id = str(body.get("device_id") or "").strip()
    if not device_id:
        raise ApiError(400, "MISSING_PARAM", "device_id is required")
    dev = conn.execute("SELECT * FROM devices WHERE device_id = ?", (device_id,)).fetchone()
    effective, target = _device_settings(settings, device_id)
    if dev is None and target is None:
        raise ApiError(404, "DEVICE_NOT_FOUND", f"Device not found: {device_id}")
    module = conn.execute("SELECT module_id FROM modules WHERE device_id = ? ORDER BY module_id LIMIT 1",
                          (device_id,)).fetchone()
    module_id = module["module_id"] if module else ""
    if not module_id and target:
        module_ids = target.get("module_ids") or []
        module_id = module_ids[0] if module_ids else ""

    cmd = cmis_spec.CDB_COMMAND_BY_ID.get(frame["cmd_id"], {})
    adapter = get_adapter(effective)
    applied = False
    result = "staged"
    message = "Frame validated and recorded in the local audit log; no hardware command was sent"
    transport: dict[str, Any] = {"adapter": effective.access_mode}
    if effective.access_mode != "mirror":
        try:
            adapter.enforce_cdb_policy(frame["cmd_id"], str(body.get("confirm") or ""))
            outcome = adapter.execute_cdb(device_id, module_id, frame["frame_hex"],
                                          frame["epl_hex"], frame["cmd_id"])
            applied = bool(outcome.get("applied_to_hardware"))
            result = outcome.get("result", "executed")
            message = outcome.get("message", "CDB command dispatched")
            transport.update({k: v for k, v in outcome.items()
                              if k not in ("message", "result", "applied_to_hardware")})
        except AdapterError as exc:
            raise ApiError(exc.status, exc.code, exc.message, exc.details)

    operator = str(body.get("operator") or settings.operator)[:64]
    row = {
        "device_id": device_id, "module_id": module_id, "cmd_id": frame["cmd_id"],
        "command_name": cmd.get("en", frame["command"]), "risk": frame["risk"],
        "lpl_len": frame["lpl_len"], "epl_len": frame["epl_len"],
        "frame_hex": frame["frame_hex"], "check_code": frame["check_code"],
        "result": result, "message": message,
        "applied_to_hardware": int(applied), "operator": operator,
        "spec_ref": frame["spec_ref"],
        "source_ids": [cmis_spec.SOURCE_IDS["oif_53"], cmis_spec.SOURCE_IDS["kernel"]],
        "detail": {"frame": frame, "transport": transport},
        "created_at": _now(),
    }
    with conn:
        insert_row(conn, "cdb_operations", row)
    record = dict(conn.execute("SELECT * FROM cdb_operations ORDER BY id DESC LIMIT 1").fetchone())
    _decode_json_fields(record, _CDB_JSON_KEYS)
    return ok({"operation": record, "frame": frame, "result": result,
               "applied_to_hardware": applied, "message": message, "transport": transport})


def cdb_history(conn: sqlite3.Connection, query: dict) -> tuple[int, dict]:
    device_id = _q(query, "device_id")
    limit = _int(query, "limit", 100, 1, 500)
    where, params = ("WHERE device_id = ?", [device_id]) if device_id else ("", [])
    rows = conn.execute(f"SELECT * FROM cdb_operations {where} ORDER BY id DESC LIMIT ?",
                        (*params, limit)).fetchall()
    items = [_decode_json_fields(dict(r), _CDB_JSON_KEYS) for r in rows]
    return ok({"total": len(items), "items": items})


def cdb_status(conn: sqlite3.Connection, query: dict) -> tuple[int, dict]:
    device_id = _q(query, "device_id")
    latest = None
    if device_id:
        row = conn.execute("SELECT * FROM cdb_operations WHERE device_id = ? ORDER BY id DESC LIMIT 1",
                           (device_id,)).fetchone()
        latest = _decode_json_fields(dict(row), _CDB_JSON_KEYS) if row else None
    status_item = conn.execute(
        "SELECT value, raw_hex, spec_ref, byte_offset FROM config_items "
        "WHERE field_key = 'CdbStatusLower' ORDER BY id LIMIT 1").fetchone()
    return ok({"device_id": device_id, "latest_operation": latest,
               "status_register": dict(status_item) if status_item else None,
               "status_registers": cmis_spec.CDB_STATUS})


# --------------------------------------------------------------------------- editable target registry

def _registry(settings: Settings) -> dict:
    """Load the editable target list; the shipped example is the fallback."""
    example = settings.base_dir / "config" / "targets.example.json"
    return targets.load_registry(settings.targets_file, example)


def _device_settings(settings: Settings, device_id: str = "") -> tuple[Settings, dict | None]:
    """Resolve the transport for one device, falling back to the global mode."""
    target = targets.find_target(_registry(settings), device_id)
    return targets.resolve_settings(settings, target), target


def list_targets(settings: Settings) -> tuple[int, dict]:
    registry = _registry(settings)
    return ok({
        "version": registry.get("version", targets.REGISTRY_VERSION),
        "active_target": registry.get("active_target", ""),
        "targets": [targets.public_target(t) for t in registry.get("targets", [])],
        "access_modes": list(targets.ACCESS_MODES),
        "fields": targets.TARGET_FIELDS,
        "mode_fields": {mode: sorted(keys) for mode, keys in targets.MODE_FIELD_KEYS.items()},
        "file": str(settings.targets_file),
        "example_file": str(settings.base_dir / "config" / "targets.example.json"),
        "writable": not settings.read_only,
        "credential_fields_forbidden": sorted(targets.SENSITIVE_KEYS),
        "note": ("ssh+i2c and restful API are mutually exclusive: each target carries "
                 "only the fields of its selected mode, and the unselected transport "
                 "is rejected on save and disabled at runtime. Credentials are never "
                 "stored here; reference them with token_env."),
    })


def save_targets(settings: Settings, body: Any) -> tuple[int, dict]:
    if settings.read_only:
        raise ApiError(409, "SERVICE_READ_ONLY",
                       "Service is read-only; target configuration cannot be saved")
    if not isinstance(body, dict):
        raise ApiError(400, "BAD_REQUEST", "Request body must be a JSON object")
    try:
        cleaned = targets.save_registry(settings.targets_file, body)
    except targets.TargetError as exc:
        raise ApiError(400, "TARGETS_VALIDATION_FAILED", exc.message, {"errors": exc.errors})
    except OSError as exc:
        raise ApiError(500, "IO_ERROR", "Could not write the target registry", {"detail": str(exc)})
    return ok({"version": cleaned["version"],
               "active_target": cleaned["active_target"],
               "targets": [targets.public_target(t) for t in cleaned["targets"]],
               "saved": True,
               "message": "Target registry saved; new devices are available immediately"})


def probe_target(settings: Settings, body: Any) -> tuple[int, dict]:
    device_id = str((body or {}).get("device_id") or "").strip() if isinstance(body, dict) else ""
    effective, target = _device_settings(settings, device_id)
    try:
        result = get_adapter(effective).probe()
    except AdapterError as exc:
        raise ApiError(exc.status, exc.code, exc.message, exc.details)
    return ok({"probe": result,
               "device_id": (target or {}).get("device_id", ""),
               "access_mode": effective.access_mode,
               "target": targets.public_target(target) if target else None})


# --------------------------------------------------------------------------- access paths

def access_info(conn: sqlite3.Connection, settings: Settings) -> tuple[int, dict]:
    adapter = get_adapter(settings)
    registry = _registry(settings)
    active = targets.find_target(registry, None)
    return ok({"active": adapter.capabilities(), "modes": cmis_spec.ACCESS_MODES,
               "service": public_settings(settings),
               "spec_releases": cmis_spec.SPEC_RELEASES,
               "targets": {"file": str(settings.targets_file),
                           "active_target": registry.get("active_target", ""),
                           "count": len(registry.get("targets", [])),
                           "active": targets.public_target(active) if active else None}})


def access_probe(conn: sqlite3.Connection, settings: Settings, body: Any) -> tuple[int, dict]:
    device_id = str((body or {}).get("device_id") or "").strip() if isinstance(body, dict) else ""
    effective, target = _device_settings(settings, device_id)
    try:
        result = get_adapter(effective).probe()
    except AdapterError as exc:
        raise ApiError(exc.status, exc.code, exc.message, exc.details)
    return ok({"probe": result, "access_mode": effective.access_mode,
               "device_id": (target or {}).get("device_id", "")})


def register_read(conn: sqlite3.Connection, settings: Settings, query: dict) -> tuple[int, dict]:
    device_id = _q(query, "device_id")
    if not device_id:
        raise ApiError(400, "MISSING_PARAM", "device_id is required")
    page = _q(query, "page") or "00h"
    offset = _int(query, "offset", 0, 0, 255)
    length = _int(query, "length", 1, 1, 128)
    effective, _ = _device_settings(settings, device_id)
    try:
        result = get_adapter(effective).read_registers(device_id, "", page, offset, length)
    except AdapterError as exc:
        raise ApiError(exc.status, exc.code, exc.message, exc.details)
    return ok({"read": result})


def register_write(conn: sqlite3.Connection, settings: Settings, body: Any) -> tuple[int, dict]:
    if not isinstance(body, dict):
        raise ApiError(400, "BAD_REQUEST", "Request body must be a JSON object")
    device_id = str(body.get("device_id") or "")
    page = str(body.get("page") or "")
    data_hex = str(body.get("data_hex") or "")
    if not device_id or not page or not data_hex:
        raise ApiError(400, "MISSING_PARAM", "device_id, page and data_hex are required")
    try:
        offset = int(body.get("offset", 0))
    except (TypeError, ValueError):
        raise ApiError(400, "BAD_PARAM", "offset must be an integer")
    effective, _ = _device_settings(settings, device_id)
    adapter = get_adapter(effective)
    try:
        adapter.enforce_write_policy(page, offset)
        result = adapter.write_register(device_id, "", page, offset, data_hex)
    except AdapterError as exc:
        raise ApiError(exc.status, exc.code, exc.message, exc.details)
    return ok({"write": result})


# --------------------------------------------------------------------------- CMIS 5.3 reference

_REF_FIELD_COLUMNS = (
    "key_id, name, page, page_raw, byte, byte_length, mask_bytes, mask_values, "
    "bank_scope, value_type, data_type, unit, scale, byte_order, conversion_note, "
    "access, behavior, requirement, condition, description, ref_section, ref_table, "
    "sonic_cross_check, sonic_field, section, is_reserved, is_lower_memory"
)
_REF_CDB_COLUMNS = (
    "cmd_id, title, cmd_group, requirement, spec_section, detail_table, "
    "overview_table, description, note"
)


def reference_fields(conn: sqlite3.Connection, query: dict) -> tuple[int, dict]:
    """Paginated read-only lookup over the CMIS 5.3 field map.

    The reference table has 2442 rows, so this endpoint deliberately does not
    reuse the fixed 300-row cap of /api/fields; callers page explicitly.
    """
    where: list[str] = []
    params: list[Any] = []
    term = _q(query, "q")
    if term:
        where.append("(name LIKE ? ESCAPE '\\' OR key_id LIKE ? ESCAPE '\\' "
                     "OR description LIKE ? ESCAPE '\\' OR ref_table LIKE ? ESCAPE '\\')")
        params.extend([_like(term)] * 4)
    filters = (("page", "page"), ("section", "section"), ("access", "access"),
               ("value_type", "value_type"), ("data_type", "data_type"),
               ("requirement", "requirement"), ("sonic", "sonic_cross_check"),
               ("ref_table", "ref_table"), ("name", "name"))
    for key, column in filters:
        value = _q(query, key)
        if value:
            where.append(f"{column} = ?")
            params.append(value.upper() if key == "section" else value)
    if _q(query, "lower").lower() in ("1", "true", "yes"):
        where.append("is_lower_memory = 1")
    if _q(query, "reserved").lower() in ("0", "false", "no"):
        where.append("is_reserved = 0")
    clause = "WHERE " + " AND ".join(where) if where else ""

    total = conn.execute(f"SELECT COUNT(*) FROM cmis53_fields {clause}", params).fetchone()[0]
    limit = _int(query, "limit", 50, 1, 500)
    offset = _int(query, "offset", 0, 0, 100000)
    rows = conn.execute(
        f"SELECT {_REF_FIELD_COLUMNS} FROM cmis53_fields {clause} "
        "ORDER BY page, byte, key_id LIMIT ? OFFSET ?",  # noqa: S608 - fixed column list
        (*params, limit, offset),
    ).fetchall()
    items = [_decode_json_fields(dict(r), ("mask_values",)) for r in rows]
    return ok({"total": total, "limit": limit, "offset": offset, "items": items})


def reference_field_detail(conn: sqlite3.Connection, key_id: str) -> tuple[int, dict]:
    """Return one reference row together with its CMIScope section definition."""
    row = conn.execute(
        f"SELECT {_REF_FIELD_COLUMNS} FROM cmis53_fields WHERE key_id = ?",  # noqa: S608
        (key_id,),
    ).fetchone()
    if row is None:
        raise ApiError(404, "REFERENCE_FIELD_NOT_FOUND",
                       f"CMIS 5.3 reference field not found: {key_id}")
    field = _decode_json_fields(dict(row), ("mask_values",))
    tokens = [t.strip() for t in re.split(r"[;,\s]+", field["ref_table"] or "") if t.strip()]
    spec_sources: list[dict] = []
    if tokens:
        placeholders = ",".join("?" for _ in tokens)
        spec_sources = rows_as_dicts(conn.execute(
            "SELECT table_id, title, pdf_page, page, field_rows FROM cmis53_spec_tables "
            f"WHERE table_id IN ({placeholders}) ORDER BY table_id",  # noqa: S608 - fixed placeholders
            tuple(tokens)).fetchall())
    return ok({"field": field,
               "section": cmis_spec.SECTION_BY_KEY.get(field["section"]),
               "spec_sources": spec_sources,
               "note": "Reference only; never used for hardware writes."})


def reference_cdb_commands(conn: sqlite3.Connection, query: dict) -> tuple[int, dict]:
    """Full Section 9 command directory with a runtime-catalog comparison."""
    where: list[str] = []
    params: list[Any] = []
    term = _q(query, "q")
    if term:
        where.append("(title LIKE ? ESCAPE '\\' OR cmd_id LIKE ? ESCAPE '\\' "
                     "OR description LIKE ? ESCAPE '\\')")
        params.extend([_like(term)] * 3)
    group = _q(query, "group")
    if group:
        where.append("cmd_group = ?")
        params.append(group)
    clause = "WHERE " + " AND ".join(where) if where else ""
    rows = conn.execute(
        f"SELECT {_REF_CDB_COLUMNS} FROM cmis53_cdb_commands {clause} ORDER BY cmd_id",  # noqa: S608
        params,
    ).fetchall()
    items = rows_as_dicts(rows)
    spec_pages = {r["table_id"]: r["pdf_page"] for r in conn.execute(
        "SELECT table_id, pdf_page FROM cmis53_spec_tables").fetchall()}
    for item in items:
        item["spec_pdf_page"] = spec_pages.get(item["detail_table"])
        item["in_runtime_catalog"] = item["cmd_id"] in cmis_spec.CDB_COMMAND_BY_ID
    return ok({"total": len(items), "items": items,
               "runtime_catalog_size": len(cmis_spec.CDB_COMMANDS),
               "note": "Reference only; /api/cdb/commands remains the executable catalog."})


def reference_spec_tables(conn: sqlite3.Connection, query: dict) -> tuple[int, dict]:
    """Paginated directory of specification tables with their PDF page numbers."""
    where: list[str] = []
    params: list[Any] = []
    section = _q(query, "section")
    if section in ("8", "9"):
        where.append("section = ?")
        params.append(int(section))
    page = _q(query, "page")
    if page:
        where.append("page = ?")
        params.append(page)
    term = _q(query, "q")
    if term:
        where.append("(table_id LIKE ? ESCAPE '\\' OR title LIKE ? ESCAPE '\\')")
        params.extend([_like(term)] * 2)
    clause = "WHERE " + " AND ".join(where) if where else ""
    total = conn.execute(f"SELECT COUNT(*) FROM cmis53_spec_tables {clause}", params).fetchone()[0]
    limit = _int(query, "limit", 50, 1, 500)
    offset = _int(query, "offset", 0, 0, 100000)
    rows = conn.execute(
        f"SELECT * FROM cmis53_spec_tables {clause} "
        "ORDER BY section, pdf_page, table_id LIMIT ? OFFSET ?",  # noqa: S608
        (*params, limit, offset),
    ).fetchall()
    return ok({"total": total, "limit": limit, "offset": offset,
               "items": rows_as_dicts(rows),
               "note": "Provenance only; captions are short OIF table identifiers."})


def reference_spec_table_detail(conn: sqlite3.Connection, table_id: str,
                                query: dict) -> tuple[int, dict]:
    """One specification table plus the reference fields that cite it."""
    row = conn.execute(
        "SELECT * FROM cmis53_spec_tables WHERE table_id = ?", (table_id,)
    ).fetchone()
    if row is None:
        raise ApiError(404, "SPEC_TABLE_NOT_FOUND",
                       f"Specification table not found: {table_id}")
    candidates = conn.execute(
        "SELECT key_id, name, page, byte, byte_length, ref_table FROM cmis53_fields "
        "WHERE ref_table LIKE ? ESCAPE '\\' ORDER BY page, byte, key_id",
        (_like(table_id),),
    ).fetchall()
    # A ref_table cell may list several tables ("8-28; 8-30"); match exactly.
    items = [dict(r) for r in candidates
             if table_id in re.split(r"[;,\s]+", r["ref_table"] or "")]
    limit = _int(query, "limit", 50, 1, 500)
    offset = _int(query, "offset", 0, 0, 100000)
    return ok({"table": dict(row), "total": len(items),
               "limit": limit, "offset": offset,
               "items": items[offset:offset + limit],
               "note": "Fields come from the normalized reference dataset; the PDF index supplies the page."})


def reference_verification(conn: sqlite3.Connection) -> tuple[int, dict]:
    """Report the PDF-vs-dataset cross-check produced by tools/parse_spec_pdf.py."""
    rows = conn.execute(
        "SELECT meta_key, meta_value FROM cmis53_meta "
        "WHERE meta_key IN ('spec_verification', 'spec_pdf_meta', 'stats')"
    ).fetchall()
    data = {r["meta_key"]: json.loads(r["meta_value"]) for r in rows}
    verification = data.get("spec_verification", {})
    if not verification.get("available"):
        return ok({"available": False,
                   "hint": "Run tools/parse_spec_pdf.py then tools/import_cmis53.py"})
    return ok({"available": True, "verification": verification,
               "pdf": data.get("spec_pdf_meta", {}),
               "reference_stats": data.get("stats", {}),
               "note": "Best-effort coordinate extraction; the normalized dataset remains authoritative."})


def reference_meta(conn: sqlite3.Connection) -> tuple[int, dict]:
    """Expose provenance, column meanings and statistics of the reference data."""
    rows = conn.execute("SELECT meta_key, meta_value FROM cmis53_meta").fetchall()
    data = {r["meta_key"]: json.loads(r["meta_value"]) for r in rows}
    if not data:
        return ok({"available": False,
                   "hint": "Generate data/cmis53_reference.json with tools/import_cmis53.py"})
    return ok({"available": True, **data,
               "runtime_catalog_size": len(cmis_spec.CDB_COMMANDS),
               "endpoints": [e for e in ENDPOINTS if e.startswith("GET /api/reference")]})


# --------------------------------------------------------------------------- routing

ENDPOINTS = [
    "GET /api/health", "GET /api/meta", "GET /api/overview",
    "GET /api/search?q=&scope=all|device|field|config|kg",
    "GET /api/devices", "GET /api/devices/{id}",
    "GET /api/fields", "GET /api/config-items", "GET /api/config-items/{id}",
    "POST /api/config-items/{id}/validate", "PUT /api/config-items/{id}",
    "GET /api/changes", "GET /api/sections", "GET /api/cmis/module?device_id=&section=",
    "GET /api/access", "POST /api/access/probe",
    "GET /api/targets", "PUT /api/targets", "POST /api/targets/probe",
    "GET /api/registers/read", "POST /api/registers/write",
    "GET /api/cdb/commands", "POST /api/cdb/compose", "POST /api/cdb/execute",
    "GET /api/cdb/status", "GET /api/cdb/history",
    "GET /api/kg/stats", "GET /api/kg/entities", "GET /api/kg/entity/{id}",
    "GET /api/kg/relations", "GET /api/kg/sources", "GET /api/kg/sources/coverage",
    "GET /api/kg/pending", "GET /api/kg/link?cmis=", "GET /api/kg/graph",
    "GET /api/reference/meta", "GET /api/reference/fields?q=&page=&section=&limit=&offset=",
    "GET /api/reference/fields/{key_id}", "GET /api/reference/cdb-commands",
    "GET /api/reference/spec-tables?section=&page=&q=&limit=&offset=",
    "GET /api/reference/spec-tables/{table_id}", "GET /api/reference/verify",
]


def _route(conn: sqlite3.Connection, settings: Settings, method: str, path: str,
           query: dict, body: Any) -> tuple[int, dict]:
    if path == "/api/health" and method == "GET":
        return ok({"status": "up", "time": _now(), "read_only": settings.read_only,
                   "access_mode": settings.access_mode, "project": PROJECT_NAME})
    if path == "/api/meta" and method == "GET":
        return ok({"service": public_settings(settings),
                   "project": {"name": PROJECT_NAME, "tagline": PROJECT_TAGLINE,
                               "default_language": settings.default_language},
                   "framework": {"name": "Tabler", "version": "1.7.3", "license": "MIT",
                                 "url": "https://github.com/tabler/tabler",
                                 "vendored_at": "cmis_service/static/vendor/tabler/"},
                   "cmis_specs": cmis_spec.SPEC_RELEASES,
                   "sections": [s["key"] for s in cmis_spec.SECTIONS],
                   "access_modes": [m["key"] for m in cmis_spec.ACCESS_MODES],
                   "endpoints": ENDPOINTS})
    if path == "/api/overview" and method == "GET":
        return overview(conn, settings)
    if path == "/api/search" and method == "GET":
        return search(conn, query)
    if path == "/api/devices" and method == "GET":
        return list_devices(conn, query)
    m = re.fullmatch(r"/api/devices/([^/]+)", path)
    if m and method == "GET":
        return device_detail(conn, m.group(1))
    if path == "/api/fields" and method == "GET":
        return list_fields(conn, query)
    if path == "/api/config-items" and method == "GET":
        return list_config_items(conn, query)
    m = re.fullmatch(r"/api/config-items/(\d+)/validate", path)
    if m and method == "POST":
        return validate_item(conn, settings, int(m.group(1)), body)
    m = re.fullmatch(r"/api/config-items/(\d+)", path)
    if m:
        if method == "GET":
            return config_item_detail(conn, int(m.group(1)))
        if method in ("PUT", "POST"):
            return save_item(conn, settings, int(m.group(1)), body)
        raise ApiError(405, "METHOD_NOT_ALLOWED", f"{method} is not supported on this resource")
    if path == "/api/changes" and method == "GET":
        return list_changes(conn, query)

    if path == "/api/sections" and method == "GET":
        return list_sections(conn)
    m = re.fullmatch(r"/api/sections/([A-Za-z_]+)", path)
    if m and method == "GET":
        key = m.group(1).upper()
        if key not in cmis_spec.SECTION_BY_KEY:
            raise ApiError(404, "SECTION_NOT_FOUND", f"Unknown CMIS section: {key}")
        _, fields_payload = list_fields(conn, {"section": [key]})
        return ok({"section": cmis_spec.SECTION_BY_KEY[key],
                   "fields": fields_payload["data"]["items"]})
    if path == "/api/cmis/module" and method == "GET":
        return module_cmis_view(conn, query)

    if path == "/api/access" and method == "GET":
        return access_info(conn, settings)
    if path == "/api/access/probe" and method == "POST":
        return access_probe(conn, settings, body)
    if path == "/api/targets" and method == "GET":
        return list_targets(settings)
    if path == "/api/targets" and method == "PUT":
        return save_targets(settings, body)
    if path == "/api/targets/probe" and method == "POST":
        return probe_target(settings, body)
    if path == "/api/registers/read" and method == "GET":
        return register_read(conn, settings, query)
    if path == "/api/registers/write" and method == "POST":
        return register_write(conn, settings, body)

    if path == "/api/cdb/commands" and method == "GET":
        return cdb_commands(conn)
    if path == "/api/cdb/compose" and method == "POST":
        return cdb_compose(body)
    if path == "/api/cdb/execute" and method == "POST":
        return cdb_execute(conn, settings, body)
    if path == "/api/cdb/status" and method == "GET":
        return cdb_status(conn, query)
    if path == "/api/cdb/history" and method == "GET":
        return cdb_history(conn, query)

    if path == "/api/kg/stats" and method == "GET":
        return ok(kg.stats(conn))
    if path == "/api/kg/entities" and method == "GET":
        return ok(kg.list_entities(conn, entity_type=_q(query, "type"), q=_q(query, "q"),
                                   confidence=_q(query, "confidence"),
                                   limit=_int(query, "limit", 100, 1, 500),
                                   offset=_int(query, "offset", 0, 0, 100000)))
    m = re.fullmatch(r"/api/kg/entity/([^/]+)", path)
    if m and method == "GET":
        detail = kg.entity_detail(conn, m.group(1), depth=_int(query, "depth", 1, 1, 2))
        if detail is None:
            raise ApiError(404, "KG_ENTITY_NOT_FOUND", f"Graph entity not found: {m.group(1)}")
        return ok(detail)
    if path == "/api/kg/relations" and method == "GET":
        return ok(kg.list_relations(conn, relation_type=_q(query, "type"), src=_q(query, "src"),
                                    dst=_q(query, "dst"), q=_q(query, "q"),
                                    limit=_int(query, "limit", 200, 1, 1000)))
    if path == "/api/kg/sources" and method == "GET":
        return ok({"total": len(kg.list_sources(conn)), "items": kg.list_sources(conn)})
    if path == "/api/kg/sources/coverage" and method == "GET":
        return ok(kg.sources_coverage(conn))
    if path == "/api/kg/pending" and method == "GET":
        return ok({"items": kg.list_pending(conn)})
    if path == "/api/kg/link" and method == "GET":
        ref, entity = _q(query, "cmis"), _q(query, "entity")
        if not ref and not entity:
            raise ApiError(400, "MISSING_PARAM", "cmis or entity parameter is required")
        return ok(kg.links_for_entity(conn, entity) if entity else kg.links_for(conn, ref))
    if path == "/api/kg/graph" and method == "GET":
        return ok(kg.graph(conn, entity_type=_q(query, "type"), limit=_int(query, "limit", 300, 10, 1000)))

    if path == "/api/reference/meta" and method == "GET":
        return reference_meta(conn)
    if path == "/api/reference/fields" and method == "GET":
        return reference_fields(conn, query)
    m = re.fullmatch(r"/api/reference/fields/([^/]+)", path)
    if m and method == "GET":
        return reference_field_detail(conn, m.group(1))
    if path == "/api/reference/cdb-commands" and method == "GET":
        return reference_cdb_commands(conn, query)
    if path == "/api/reference/spec-tables" and method == "GET":
        return reference_spec_tables(conn, query)
    m = re.fullmatch(r"/api/reference/spec-tables/([^/]+)", path)
    if m and method == "GET":
        return reference_spec_table_detail(conn, m.group(1), query)
    if path == "/api/reference/verify" and method == "GET":
        return reference_verification(conn)

    if path.startswith("/api/"):
        known = path.split("?")[0]
        for probe in ("/api/devices", "/api/fields", "/api/config-items", "/api/changes",
                      "/api/kg", "/api/cdb", "/api/access", "/api/registers", "/api/sections",
                      "/api/targets", "/api/reference"):
            if known.startswith(probe):
                raise ApiError(405, "METHOD_NOT_ALLOWED", f"{method} {known} is not supported")
        raise ApiError(404, "ENDPOINT_NOT_FOUND", f"Unknown endpoint: {known}")
    raise ApiError(404, "NOT_FOUND", f"Path not found: {path}")


def dispatch(conn: sqlite3.Connection, settings: Settings, method: str, path: str,
             query: dict, body: Any) -> tuple[int, dict]:
    """Dispatch a request and return (http_status, payload)."""
    try:
        return _route(conn, settings, method, path, query, body)
    except ApiError as exc:
        return exc.status, exc.payload()
    except AdapterError as exc:
        return exc.status, ApiError(exc.status, exc.code, exc.message, exc.details).payload()
    except sqlite3.Error as exc:
        log.exception("Database operation failed")
        return 500, {"ok": False, "error": {"code": "DB_ERROR",
                                            "message": "Database operation failed", "details": str(exc)}}
    except Exception as exc:  # Keep stack traces out of client responses
        log.exception("API handler failed")
        return 500, {"ok": False, "error": {"code": "INTERNAL_ERROR",
                                            "message": "Internal service error", "details": str(exc)}}
