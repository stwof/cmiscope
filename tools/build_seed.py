"""Build data/seed.json (devices / modules / fields / config items).

Usage: python tools/build_seed.py

The generated data is synthetic demo content for INTERNAL devices. To connect a
real CMDB/NMS, replace data/seed.json or rewrite this generator; the service
code does not need to change.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from cmis_catalog import (DCO_EXTRA_KEYS, DEFAULT_FIELD_KEYS, DEVICE_PROFILES,
                          FIELD_BY_KEY)

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "data" / "seed.json"
STAMP = "2026-11-08T10:00:00Z"

DEVICE_COLUMNS = ("device_id", "name", "name_en", "device_type", "vendor", "model",
                  "location", "status", "cmis_revision", "firmware", "last_seen",
                  "notes", "notes_en", "access_mode")
FIELD_COLUMNS = ("field_key", "name", "name_en", "page", "byte_offset", "bit_range",
                 "data_type", "unit", "access", "section", "description",
                 "description_en", "spec_ref", "source_ids", "confidence", "kg_entity_id")
ITEM_COLUMNS = ("device_id", "module_id", "field_key", "label", "label_en", "page",
                "byte_offset", "section", "value", "raw_hex", "data_type", "unit",
                "writable", "allowed_values", "min_value", "max_value", "regex",
                "cross_rule", "spec_ref", "source_ids", "updated_at", "version")


def to_raw_hex(field: dict, value) -> str | None:
    """Derive a display-only raw hex representation from a field value."""
    dtype = field["data_type"]
    try:
        if dtype == "hex":
            return str(value)
        if dtype == "bool":
            return f"0x{int(bool(value)):02X}"
        if dtype in ("int", "uint"):
            return f"0x{int(value):02X}"
        if dtype == "float":
            return f"0x{int(round(float(value) * 256)) & 0xFFFF:04X}"
        if dtype == "ascii":
            return "0x" + str(value).encode("ascii", "replace").hex().upper()
    except (TypeError, ValueError):
        return None
    return None


def build() -> dict:
    fields = [{k: f.get(k) for k in FIELD_COLUMNS} for f in
              (FIELD_BY_KEY[k] for k in dict.fromkeys(DEFAULT_FIELD_KEYS + DCO_EXTRA_KEYS))]

    devices, modules, items = [], [], []
    for profile in DEVICE_PROFILES:
        device_id = profile["device_id"]
        devices.append({k: profile.get(k) for k in DEVICE_COLUMNS})
        module_id = f"{device_id}-M1"
        mod = dict(profile["module"])
        mod.update({"module_id": module_id, "device_id": device_id,
                    "cmis_revision": profile["cmis_revision"],
                    "source_ref": "S-INTERNAL"})
        modules.append(mod)

        keys = list(dict.fromkeys(DEFAULT_FIELD_KEYS + DCO_EXTRA_KEYS))
        for key in keys:
            field = FIELD_BY_KEY[key]
            value = profile.get("values", {}).get(key, field["default_value"])
            row = {
                "device_id": device_id,
                "module_id": module_id,
                "field_key": key,
                "label": f"{field['name']} @ {field['page']}:{field['byte_offset']}",
                "label_en": f"{field['name_en']} @ {field['page']}:{field['byte_offset']}",
                "page": field["page"],
                "byte_offset": field["byte_offset"],
                "section": field["section"],
                "value": str(value),
                "raw_hex": to_raw_hex(field, value),
                "data_type": field["data_type"],
                "unit": field["unit"],
                "writable": field["writable"],
                "allowed_values": field["allowed_values"],
                "min_value": field["min_value"],
                "max_value": field["max_value"],
                "regex": field["regex"],
                "cross_rule": field["cross_rule"],
                "spec_ref": field["spec_ref"],
                "source_ids": field["source_ids"],
                "updated_at": STAMP,
                "version": 1,
            }
            items.append({k: row.get(k) for k in ITEM_COLUMNS})

    return {
        "meta": {
            "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "generator": "tools/build_seed.py",
            "project": "CMIScope",
            "data_nature": "synthetic-demo",
            "cmis_reference": ["OIF-CMIS-05.3", "OIF-CMIS-05.4", "OIF-CMIS-05-Errata-01.0"],
            "sections": ["LOW_PAGE", "VDM", "CDB", "CONTROL"],
            "note": "Internal device data is synthetic, not real network assets. Register offsets and clause numbers marked pending are listed in knowledge_graph.json -> pending_confirmations.",
            "counts": {"devices": len(devices), "modules": len(modules),
                       "fields": len(fields), "config_items": len(items)},
        },
        "fields": fields,
        "devices": devices,
        "modules": modules,
        "config_items": items,
    }


if __name__ == "__main__":
    data = build()
    OUT.parent.mkdir(parents=True, exist_ok=True)
    # write_bytes keeps LF on every platform (write_text would emit CRLF on Windows).
    OUT.write_bytes((json.dumps(data, ensure_ascii=False, indent=2) + "\n").encode("utf-8"))
    print(f"wrote {OUT} | {data['meta']['counts']}")
