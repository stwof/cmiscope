#!/usr/bin/env python3
"""Regression checks for the read-only CMIS 5.3 reference layer.

Standard library only. Uses a temporary database so neither the delivered
data/cmis.db nor any operator data is touched.

Usage: python tools/test_reference.py
"""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from cmis_service import api, db  # noqa: E402
from cmis_service.config import load_settings  # noqa: E402

PASS, FAIL = [], []


def check(name: str, condition: bool, detail: str = "") -> None:
    (PASS if condition else FAIL).append(name)
    print(f"{'PASS' if condition else 'FAIL'}  {name}" + (f"  | {detail}" if detail else ""))


def main() -> int:
    tmp = Path(tempfile.mkdtemp(prefix="cmiscope-ref-test-")) / "cmis.db"
    settings = load_settings(environ={"CMIS_DB_FILE": str(tmp)})
    conn = db.initialize(settings)

    def call(path: str, query: dict | None = None):
        return api.dispatch(conn, settings, "GET", path, query or {}, None)

    counts = {
        "ref_fields": conn.execute("SELECT COUNT(*) FROM cmis53_fields").fetchone()[0],
        "ref_cdb": conn.execute("SELECT COUNT(*) FROM cmis53_cdb_commands").fetchone()[0],
        "meta": conn.execute("SELECT COUNT(*) FROM cmis53_meta").fetchone()[0],
        "fields": conn.execute("SELECT COUNT(*) FROM fields").fetchone()[0],
        "config_items": conn.execute("SELECT COUNT(*) FROM config_items").fetchone()[0],
    }
    check("reference field count is 2442", counts["ref_fields"] == 2442, str(counts["ref_fields"]))
    check("reference CDB command count is 48", counts["ref_cdb"] == 48, str(counts["ref_cdb"]))
    check("reference meta has 7 rows (5 original + PDF provenance + verification)",
          counts["meta"] == 7, str(counts["meta"]))
    check("original demo fields unchanged (64)", counts["fields"] == 64, str(counts["fields"]))
    check("original config items unchanged (512)", counts["config_items"] == 512,
          str(counts["config_items"]))

    status, meta = call("/api/reference/meta")
    data = meta.get("data", {})
    check("meta endpoint is available", status == 200 and data.get("available") is True)
    check("meta records all three license boundaries",
          all(k in data.get("meta", {}).get("license", {}) for k in
              ("scripts_and_structure", "specification_content", "sonic_cross_check")))
    check("meta exposes column dictionary", len(data.get("field_columns", {})) == 21)
    check("meta records source checksums", len(data.get("meta", {}).get("source_assets", {})) == 3)

    status, payload = call("/api/reference/fields", {"limit": ["10"]})
    fields = payload.get("data", {})
    check("field list is paginated with real total",
          status == 200 and fields.get("total") == 2442 and len(fields.get("items", [])) == 10,
          f"total={fields.get('total')} items={len(fields.get('items', []))}")
    check("mask_values decoded to a list",
          all(isinstance(i.get("mask_values"), list) for i in fields.get("items", [])))

    status, payload = call("/api/reference/fields", {"section": ["VDM"], "limit": ["5"]})
    vdm = payload.get("data", {})
    check("section filter works", status == 200 and vdm.get("total", 0) > 0
          and all(i["section"] == "VDM" for i in vdm.get("items", [])),
          f"total={vdm.get('total')}")

    status, payload = call("/api/reference/fields", {"q": ["CmisRevision"], "limit": ["500"]})
    check("text search finds CmisRevision",
          any(i["name"] == "CmisRevision" for i in payload.get("data", {}).get("items", [])))

    status, payload = call("/api/reference/fields/MemoryModel")
    field = payload.get("data", {}).get("field", {})
    check("detail returns canonical page and masks",
          status == 200 and field.get("page") == "Lwr" and field.get("mask_values") == [128],
          f"page={field.get('page')} masks={field.get('mask_values')}")

    status, payload = call("/api/reference/fields/definitely-not-a-key")
    check("unknown key returns 404 with English code",
          status == 404 and payload["error"]["code"] == "REFERENCE_FIELD_NOT_FOUND")

    status, payload = call("/api/reference/cdb-commands")
    cdb = payload.get("data", {})
    in_runtime = sum(1 for i in cdb.get("items", []) if i.get("in_runtime_catalog"))
    check("CDB directory has 48 commands", status == 200 and cdb.get("total") == 48)
    check("26 commands overlap the executable catalog", in_runtime == 26, str(in_runtime))
    check("22 commands are reference-only", 48 - in_runtime == 22)

    _, existing = call("/api/fields")
    _, existing_cdb = call("/api/cdb/commands")
    check("/api/fields still reports 64", existing["data"]["total"] == 64)
    check("/api/cdb/commands still reports 26",
          len(existing_cdb["data"]["items"]) == 26)

    print(f"\n{len(PASS)} passed, {len(FAIL)} failed")
    for name in FAIL:
        print(f"  FAILED: {name}")
    return 1 if FAIL else 0


if __name__ == "__main__":
    raise SystemExit(main())
