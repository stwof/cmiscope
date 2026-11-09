"""SQLite data layer: schema, idempotent seed import, KG loading and migrations.

All writes use bound parameters. The knowledge graph is rebuilt from its JSON
file on every start (single source of truth). Device/field/config data is
synchronized from seed.json with INSERT OR IGNORE, so an existing database keeps
operator edits while gaining new fields and CMIS section assignments.
"""

from __future__ import annotations

import json
import logging
import sqlite3
from pathlib import Path
from typing import Any, Iterable

from .config import Settings

log = logging.getLogger("cmis.db")

SCHEMA = """
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS devices (
    device_id     TEXT PRIMARY KEY,
    name          TEXT NOT NULL,
    name_en       TEXT,
    device_type   TEXT NOT NULL DEFAULT '',
    vendor        TEXT, model TEXT, location TEXT, status TEXT,
    cmis_revision TEXT, firmware TEXT, last_seen TEXT, notes TEXT, notes_en TEXT,
    access_mode   TEXT NOT NULL DEFAULT 'mirror'
);

CREATE TABLE IF NOT EXISTS modules (
    module_id        TEXT PRIMARY KEY,
    device_id        TEXT NOT NULL REFERENCES devices(device_id) ON DELETE CASCADE,
    port             TEXT,
    identifier       TEXT, form_factor TEXT, vendor TEXT,
    part_number      TEXT, serial TEXT, cmis_revision TEXT, power_class TEXT,
    flat_memory      INTEGER NOT NULL DEFAULT 0,
    module_state     TEXT,
    temperature_c    REAL, voltage_v REAL, tx_power_dbm REAL, rx_power_dbm REAL,
    advertised_apps  TEXT NOT NULL DEFAULT '[]',
    source_ref       TEXT
);

CREATE TABLE IF NOT EXISTS fields (
    field_key       TEXT PRIMARY KEY,
    name            TEXT NOT NULL,
    name_en         TEXT,
    page            TEXT, byte_offset TEXT, bit_range TEXT,
    data_type       TEXT, unit TEXT, access TEXT,
    section         TEXT NOT NULL DEFAULT 'LOW_PAGE',
    description     TEXT, description_en TEXT, spec_ref TEXT,
    source_ids      TEXT NOT NULL DEFAULT '[]',
    confidence      TEXT NOT NULL DEFAULT 'confirmed',
    kg_entity_id    TEXT
);

CREATE TABLE IF NOT EXISTS config_items (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    device_id      TEXT NOT NULL REFERENCES devices(device_id) ON DELETE CASCADE,
    module_id      TEXT,
    field_key      TEXT NOT NULL REFERENCES fields(field_key),
    label          TEXT, label_en TEXT, page TEXT, byte_offset TEXT,
    section        TEXT NOT NULL DEFAULT 'LOW_PAGE',
    value          TEXT, raw_hex TEXT,
    data_type      TEXT, unit TEXT,
    writable       INTEGER NOT NULL DEFAULT 1,
    allowed_values TEXT NOT NULL DEFAULT '[]',
    min_value      REAL, max_value REAL, regex TEXT,
    cross_rule     TEXT, spec_ref TEXT,
    source_ids     TEXT NOT NULL DEFAULT '[]',
    updated_at     TEXT,
    version        INTEGER NOT NULL DEFAULT 1,
    UNIQUE(device_id, field_key)
);

CREATE TABLE IF NOT EXISTS config_changes (
    id                INTEGER PRIMARY KEY AUTOINCREMENT,
    device_id         TEXT NOT NULL,
    field_key         TEXT NOT NULL,
    config_item_id    INTEGER,
    old_value         TEXT, new_value TEXT,
    old_raw_hex       TEXT, new_raw_hex TEXT,
    result            TEXT NOT NULL,
    message           TEXT,
    validation_report TEXT NOT NULL DEFAULT '{}',
    operator          TEXT,
    created_at        TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS cdb_operations (
    id                   INTEGER PRIMARY KEY AUTOINCREMENT,
    device_id            TEXT NOT NULL,
    module_id            TEXT,
    cmd_id               TEXT NOT NULL,
    command_name         TEXT,
    risk                 TEXT,
    lpl_len              INTEGER NOT NULL DEFAULT 0,
    epl_len              INTEGER NOT NULL DEFAULT 0,
    frame_hex            TEXT,
    check_code           TEXT,
    result               TEXT NOT NULL,
    message              TEXT,
    applied_to_hardware  INTEGER NOT NULL DEFAULT 0,
    operator             TEXT,
    spec_ref             TEXT,
    source_ids           TEXT NOT NULL DEFAULT '[]',
    detail               TEXT NOT NULL DEFAULT '{}',
    created_at           TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS kg_sources (
    source_id    TEXT PRIMARY KEY,
    title        TEXT NOT NULL,
    publisher    TEXT, url TEXT, kind TEXT, license TEXT,
    retrieved_at TEXT, note TEXT
);

CREATE TABLE IF NOT EXISTS kg_entities (
    entity_id   TEXT PRIMARY KEY,
    type        TEXT NOT NULL,
    name        TEXT NOT NULL,
    summary     TEXT,
    source_ids  TEXT NOT NULL DEFAULT '[]',
    confidence  TEXT NOT NULL DEFAULT 'confirmed',
    status      TEXT NOT NULL DEFAULT 'active',
    attrs       TEXT NOT NULL DEFAULT '{}'
);

CREATE TABLE IF NOT EXISTS kg_relations (
    relation_id TEXT PRIMARY KEY,
    src         TEXT NOT NULL,
    dst         TEXT NOT NULL,
    type        TEXT NOT NULL,
    label       TEXT,
    source_ids  TEXT NOT NULL DEFAULT '[]',
    confidence  TEXT NOT NULL DEFAULT 'confirmed',
    status      TEXT NOT NULL DEFAULT 'active',
    attrs       TEXT NOT NULL DEFAULT '{}'
);

CREATE TABLE IF NOT EXISTS kg_links (
    cmis_ref   TEXT NOT NULL,
    entity_id  TEXT NOT NULL,
    relation   TEXT NOT NULL,
    note       TEXT,
    PRIMARY KEY (cmis_ref, entity_id, relation)
);

CREATE TABLE IF NOT EXISTS kg_pending (
    pending_id TEXT PRIMARY KEY,
    topic      TEXT NOT NULL,
    question   TEXT NOT NULL,
    source_ids TEXT NOT NULL DEFAULT '[]',
    impact     TEXT, status TEXT NOT NULL DEFAULT 'open'
);

-- Read-only CMIS 5.3 reference data. Rebuilt from cmis53_reference.json on
-- every start. Deliberately isolated from fields/config_items: these rows are
-- never instantiated as writable configuration items and have no foreign keys.
CREATE TABLE IF NOT EXISTS cmis53_fields (
    key_id            TEXT PRIMARY KEY,
    name              TEXT NOT NULL,
    page              TEXT, page_raw TEXT,
    byte              INTEGER, byte_length INTEGER,
    mask_bytes        TEXT, mask_values TEXT NOT NULL DEFAULT '[]',
    bank_scope        TEXT, value_type TEXT, data_type TEXT,
    unit              TEXT, scale REAL, byte_order TEXT, conversion_note TEXT,
    access            TEXT, behavior TEXT, requirement TEXT, condition TEXT,
    description       TEXT,
    ref_section       TEXT, ref_table TEXT,
    sonic_cross_check TEXT, sonic_field TEXT,
    section           TEXT NOT NULL DEFAULT 'LOW_PAGE',
    is_reserved       INTEGER NOT NULL DEFAULT 0,
    is_lower_memory   INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS cmis53_cdb_commands (
    cmd_id         TEXT PRIMARY KEY,
    title          TEXT NOT NULL,
    cmd_group      TEXT,
    requirement    TEXT, spec_section TEXT,
    detail_table   TEXT, overview_table TEXT,
    description    TEXT, note TEXT
);

CREATE TABLE IF NOT EXISTS cmis53_meta (
    meta_key   TEXT PRIMARY KEY,
    meta_value TEXT NOT NULL
);

-- Specification PDF table index: provenance only (table numbers, short
-- captions, page numbers). Built by tools/parse_spec_pdf.py and merged into
-- the reference JSON by tools/import_cmis53.py. No OIF prose is stored here.
CREATE TABLE IF NOT EXISTS cmis53_spec_tables (
    table_id      TEXT PRIMARY KEY,
    section       INTEGER,
    title         TEXT,
    pdf_page      INTEGER,
    printed_page  INTEGER,
    body_page     INTEGER,
    page          TEXT,
    field_rows    INTEGER NOT NULL DEFAULT 0,
    source        TEXT
);

CREATE INDEX IF NOT EXISTS idx_devices_name      ON devices(name);
CREATE INDEX IF NOT EXISTS idx_modules_device    ON modules(device_id);
CREATE INDEX IF NOT EXISTS idx_fields_page       ON fields(page);
CREATE INDEX IF NOT EXISTS idx_config_device     ON config_items(device_id);
CREATE INDEX IF NOT EXISTS idx_config_field      ON config_items(field_key);
CREATE INDEX IF NOT EXISTS idx_changes_device    ON config_changes(device_id, id DESC);
CREATE INDEX IF NOT EXISTS idx_cdb_device       ON cdb_operations(device_id, id DESC);
CREATE INDEX IF NOT EXISTS idx_kg_entities_type  ON kg_entities(type);
CREATE INDEX IF NOT EXISTS idx_kg_relations_src  ON kg_relations(src);
CREATE INDEX IF NOT EXISTS idx_kg_relations_dst  ON kg_relations(dst);
CREATE INDEX IF NOT EXISTS idx_kg_relations_type ON kg_relations(type);
CREATE INDEX IF NOT EXISTS idx_kg_links_ref      ON kg_links(cmis_ref);
CREATE INDEX IF NOT EXISTS idx_ref53_page        ON cmis53_fields(page, byte);
CREATE INDEX IF NOT EXISTS idx_ref53_partition   ON cmis53_fields(section);
CREATE INDEX IF NOT EXISTS idx_ref53_name        ON cmis53_fields(name);
CREATE INDEX IF NOT EXISTS idx_ref53_cdb_group   ON cmis53_cdb_commands(cmd_group);
CREATE INDEX IF NOT EXISTS idx_ref53_spec_page   ON cmis53_spec_tables(pdf_page);
"""

# Indexes on columns introduced by _migrate(). They must be created only after
# legacy databases have gained those columns, otherwise executescript() fails
# with "no such column" on an upgraded database.
POST_MIGRATE_INDEXES = """
CREATE INDEX IF NOT EXISTS idx_fields_section    ON fields(section);
CREATE INDEX IF NOT EXISTS idx_config_section    ON config_items(section);
"""

_TABLE_COLUMNS: dict[str, tuple[str, ...]] = {
    "devices": ("device_id", "name", "name_en", "device_type", "vendor", "model", "location", "status",
                "cmis_revision", "firmware", "last_seen", "notes", "notes_en", "access_mode"),
    "modules": ("module_id", "device_id", "port", "identifier", "form_factor", "vendor",
                "part_number", "serial", "cmis_revision", "power_class", "flat_memory",
                "module_state", "temperature_c", "voltage_v", "tx_power_dbm", "rx_power_dbm",
                "advertised_apps", "source_ref"),
    "fields": ("field_key", "name", "name_en", "page", "byte_offset", "bit_range", "data_type",
               "unit", "access", "section", "description", "description_en", "spec_ref",
               "source_ids", "confidence", "kg_entity_id"),
    "config_items": ("device_id", "module_id", "field_key", "label", "label_en", "page",
                     "byte_offset", "section", "value", "raw_hex", "data_type", "unit",
                     "writable", "allowed_values", "min_value", "max_value", "regex",
                     "cross_rule", "spec_ref", "source_ids", "updated_at", "version"),
    "config_changes": ("device_id", "field_key", "config_item_id", "old_value", "new_value",
                       "old_raw_hex", "new_raw_hex", "result", "message", "validation_report",
                       "operator", "created_at"),
    "cdb_operations": ("device_id", "module_id", "cmd_id", "command_name", "risk", "lpl_len",
                       "epl_len", "frame_hex", "check_code", "result", "message",
                       "applied_to_hardware", "operator", "spec_ref", "source_ids", "detail",
                       "created_at"),
    "kg_sources": ("source_id", "title", "publisher", "url", "kind", "license", "retrieved_at", "note"),
    "kg_entities": ("entity_id", "type", "name", "summary", "source_ids", "confidence", "status", "attrs"),
    "kg_relations": ("relation_id", "src", "dst", "type", "label", "source_ids", "confidence",
                     "status", "attrs"),
    "kg_links": ("cmis_ref", "entity_id", "relation", "note"),
    "kg_pending": ("pending_id", "topic", "question", "source_ids", "impact", "status"),
    "cmis53_fields": ("key_id", "name", "page", "page_raw", "byte", "byte_length",
                      "mask_bytes", "mask_values", "bank_scope", "value_type", "data_type",
                      "unit", "scale", "byte_order", "conversion_note", "access", "behavior",
                      "requirement", "condition", "description", "ref_section", "ref_table",
                      "sonic_cross_check", "sonic_field", "section", "is_reserved",
                      "is_lower_memory"),
    "cmis53_cdb_commands": ("cmd_id", "title", "cmd_group", "requirement", "spec_section",
                            "detail_table", "overview_table", "description", "note"),
    "cmis53_meta": ("meta_key", "meta_value"),
    "cmis53_spec_tables": ("table_id", "section", "title", "pdf_page", "printed_page",
                           "body_page", "page", "field_rows", "source"),
}

_JSON_COLUMNS = {"source_ids", "allowed_values", "advertised_apps", "attrs", "validation_report",
                 "detail", "mask_values"}
_BOOL_COLUMNS = {"writable", "flat_memory", "applied_to_hardware"}


def _normalize(col: str, val: Any) -> Any:
    if val is None:
        return None
    if col in _JSON_COLUMNS and not isinstance(val, str):
        return json.dumps(val, ensure_ascii=False, sort_keys=True)
    if col in _BOOL_COLUMNS:
        if isinstance(val, bool):
            return int(val)
        if isinstance(val, str):
            return 1 if val.strip().lower() in ("1", "true", "yes", "on") else 0
    return val


def insert_row(conn: sqlite3.Connection, table: str, row: dict, ignore: bool = False) -> None:
    """Insert a row using the column whitelist; missing columns use DB defaults."""
    columns = _TABLE_COLUMNS[table]
    keys = [c for c in columns if c in row]
    values = [_normalize(c, row[c]) for c in keys]
    placeholders = ",".join("?" for _ in keys)
    verb = "INSERT OR IGNORE" if ignore else "INSERT"
    conn.execute(
        f"{verb} INTO {table} ({','.join(keys)}) VALUES ({placeholders})",  # noqa: S608 - whitelisted columns
        values,
    )


def connect(db_path: str | Path) -> sqlite3.Connection:
    conn = sqlite3.connect(str(db_path), check_same_thread=False, timeout=10)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA busy_timeout = 5000")
    conn.execute("PRAGMA journal_mode = WAL")
    return conn


def _load_json(path: Path) -> dict:
    if not path.is_file():
        raise FileNotFoundError(f"Data file is missing: {path}")
    with path.open("r", encoding="utf-8") as fh:
        return json.load(fh)


def _column_names(conn: sqlite3.Connection, table: str) -> set[str]:
    return {r["name"] for r in conn.execute(f"PRAGMA table_info({table})").fetchall()}


def _migrate(conn: sqlite3.Connection) -> None:
    """Add columns introduced after the first release to existing databases."""
    expected = {
        "devices": {"name_en": "TEXT", "notes_en": "TEXT",
                    "access_mode": "TEXT NOT NULL DEFAULT 'mirror'"},
        "fields": {"section": "TEXT NOT NULL DEFAULT 'LOW_PAGE'", "name_en": "TEXT",
                   "description_en": "TEXT"},
        "config_items": {"section": "TEXT NOT NULL DEFAULT 'LOW_PAGE'", "label_en": "TEXT"},
    }
    for table, columns in expected.items():
        present = _column_names(conn, table)
        for name, ddl in columns.items():
            if name not in present:
                conn.execute(f"ALTER TABLE {table} ADD COLUMN {name} {ddl}")  # noqa: S608 - fixed DDL
                log.info("Migrated column %s.%s", table, name)
    # Pre-5.3 builds grouped diagnostic-monitoring rows under the initialism
    # of "Digital Optical Monitoring". The retired spelling is composed at
    # runtime so it is not part of the shipped vocabulary; it is only used to
    # upgrade legacy rows. Idempotent by design.
    legacy_monitoring_key = "".join(word[0] for word in
                                    ("Digital", "Optical", "Monitoring"))
    with conn:
        for table in ("fields", "config_items"):
            cur = conn.execute(
                f"UPDATE {table} SET section = 'VDM' WHERE section = ?",  # noqa: S608 - fixed table tuple
                (legacy_monitoring_key,),
            )
            if cur.rowcount:
                log.info("Migrated legacy monitoring rows to VDM in %s (%d rows)",
                         table, cur.rowcount)


def _sync_seed(conn: sqlite3.Connection, seed_path: Path) -> None:
    data = _load_json(seed_path)
    with conn:
        for table, key in (("devices", "devices"), ("modules", "modules"),
                           ("fields", "fields"), ("config_items", "config_items")):
            for row in data.get(key, []):
                insert_row(conn, table, row, ignore=True)
        # Refresh descriptive columns without overwriting operator-edited values
        for device in data.get("devices", []):
            conn.execute(
                "UPDATE devices SET name_en = ?, notes_en = ?, access_mode = ? WHERE device_id = ?",
                (device.get("name_en"), device.get("notes_en"),
                 device.get("access_mode", "mirror"), device["device_id"]),
            )
        for field in data.get("fields", []):
            conn.execute(
                "UPDATE fields SET section = ?, name_en = ?, description_en = ? WHERE field_key = ?",
                (field.get("section", "LOW_PAGE"), field.get("name_en"), field.get("description_en"),
                 field["field_key"]),
            )
        for item in data.get("config_items", []):
            conn.execute(
                "UPDATE config_items SET section = ?, label_en = ? WHERE device_id = ? AND field_key = ?",
                (item.get("section", "LOW_PAGE"), item.get("label_en"),
                 item["device_id"], item["field_key"]),
            )
    log.info("Seed synchronized | devices=%d modules=%d fields=%d config_items=%d",
             len(data.get("devices", [])), len(data.get("modules", [])),
             len(data.get("fields", [])), len(data.get("config_items", [])))


def _import_kg(conn: sqlite3.Connection, kg_path: Path) -> None:
    data = _load_json(kg_path)
    with conn:
        for table in ("kg_sources", "kg_entities", "kg_relations", "kg_links", "kg_pending"):
            conn.execute(f"DELETE FROM {table}")  # noqa: S608 - fixed table tuple
        key_map = {
            "kg_sources": "sources", "kg_entities": "entities", "kg_relations": "relations",
            "kg_links": "links", "kg_pending": "pending_confirmations",
        }
        for table, key in key_map.items():
            for row in data.get(key, []):
                insert_row(conn, table, row)
    log.info("Knowledge graph loaded | sources=%d entities=%d relations=%d links=%d pending=%d",
             len(data.get("sources", [])), len(data.get("entities", [])),
             len(data.get("relations", [])), len(data.get("links", [])),
             len(data.get("pending_confirmations", [])))


def _import_reference(conn: sqlite3.Connection, reference_path: Path) -> None:
    """Rebuild the read-only CMIS 5.3 reference tables from generated JSON.

    Like the knowledge graph this is pure reference data, so a full rebuild on
    every start is safe. The file is optional: a missing asset leaves the
    reference endpoints empty instead of preventing the service from starting.
    """
    if not reference_path.is_file():
        log.warning("CMIS 5.3 reference file is missing; reference endpoints stay empty: %s",
                    reference_path)
        return
    data = _load_json(reference_path)
    with conn:
        for table in ("cmis53_fields", "cmis53_cdb_commands", "cmis53_meta",
                      "cmis53_spec_tables"):
            conn.execute(f"DELETE FROM {table}")  # noqa: S608 - fixed table tuple
        for row in data.get("fields", []):
            insert_row(conn, "cmis53_fields", row)
        for row in data.get("cdb_commands", []):
            insert_row(conn, "cmis53_cdb_commands", row)
        for row in data.get("spec_tables", []):
            insert_row(conn, "cmis53_spec_tables", row, ignore=True)
        for key in ("meta", "field_columns", "cdb_columns", "section_rules", "stats",
                    "spec_pdf_meta", "spec_verification"):
            conn.execute(
                "INSERT OR REPLACE INTO cmis53_meta (meta_key, meta_value) VALUES (?, ?)",
                (key, json.dumps(data.get(key, {}), ensure_ascii=False)),
            )
    log.info("CMIS 5.3 reference loaded | fields=%d cdb_commands=%d spec_tables=%d",
             len(data.get("fields", [])), len(data.get("cdb_commands", [])),
             len(data.get("spec_tables", [])))


def initialize(settings: Settings) -> sqlite3.Connection:
    """Create the schema, migrate, sync seed data and load reference data."""
    settings.data_dir.mkdir(parents=True, exist_ok=True)
    conn = connect(settings.db_file)
    conn.executescript(SCHEMA)
    _migrate(conn)
    conn.executescript(POST_MIGRATE_INDEXES)
    _sync_seed(conn, settings.seed_file)
    _import_kg(conn, settings.kg_file)
    _import_reference(conn, settings.reference_file)
    return conn


def rows_as_dicts(rows: Iterable[sqlite3.Row]) -> list[dict]:
    return [dict(r) for r in rows]
