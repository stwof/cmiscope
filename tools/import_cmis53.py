#!/usr/bin/env python3
"""Build the portable CMIS 5.3 reference JSON from the upstream CSV assets.

Pure standard library: no third-party packages, no network access, no PDF or
XLSX parsing here. The heavyweight upstream rebuild chain (pdfplumber,
openpyxl, SONiC git clone) stays outside this project. Its published CSV
output is the authority; an optional PDF-derived index
(data/spec_pdf_index.json, built by tools/parse_spec_pdf.py with the standard
library) is merged in for specification page provenance and verification.

Usage:
    python tools/parse_spec_pdf.py            # optional: build the PDF index first
    python tools/import_cmis53.py
    python tools/import_cmis53.py --source data/upstream --out data/cmis53_reference.json
    python tools/import_cmis53.py --no-spec-index   # CSV only

The generated file is imported into SQLite at service start. Re-run this script
whenever the upstream CSV assets or the PDF index are refreshed.
See docs/CMIS53_REFERENCE.md.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import re
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

from cmis53_rules import (  # noqa: E402 - path bootstrapped above
    CDB_COLUMN_NOTES, CDB_COLUMNS, FIELD_COLUMN_NOTES, FIELD_COLUMNS,
    SECTION_RULES, normalize_cdb, normalize_field,
)

DEFAULT_SOURCE = ROOT / "data" / "upstream"
DEFAULT_OUTPUT = ROOT / "data" / "cmis53_reference.json"
DEFAULT_SPEC_INDEX = ROOT / "data" / "spec_pdf_index.json"

FIELD_CSV = "CMIS_5.3_Memory_Map.csv"
CDB_CSV = "CMIS_5.3_CDB_Commands.csv"
CORRECTIONS_CSV = "corrections.csv"

SPEC = "OIF-CMIS-05.3, Common Management Interface Specification revision 5.3 (4 Sept 2024)"
UPSTREAM_REPO = "https://github.com/jimfred/CMIS"
OIF_URL = "https://www.oiforum.com/"
SPEC_PDF_URL = "https://www.oiforum.com/wp-content/uploads/OIF-CMIS-05.3.pdf"


def read_csv(path: Path, required: dict) -> list[dict]:
    """Read a UTF-8 CSV with explicit encoding and header validation."""
    if not path.is_file():
        raise SystemExit(f"ERROR: upstream asset is missing: {path}")
    with path.open("r", encoding="utf-8-sig", newline="") as fh:
        reader = csv.DictReader(fh)
        headers = reader.fieldnames or []
        missing = [name for name in required if name not in headers]
        if missing:
            raise SystemExit(f"ERROR: {path.name} is missing columns: {', '.join(missing)}")
        return [dict(row) for row in reader]


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def count_by(rows: list[dict], key: str) -> dict:
    return dict(sorted(Counter(str(r.get(key) or "") for r in rows).items(),
                       key=lambda pair: (-pair[1], pair[0])))


def require_unique(rows: list[dict], key: str, label: str) -> None:
    seen = [r[key] for r in rows]
    duplicates = [value for value, n in Counter(seen).items() if n > 1]
    if duplicates:
        raise SystemExit(f"ERROR: duplicate {key} in {label}: {', '.join(duplicates[:5])}")


def load_spec_index(path: Path) -> dict | None:
    """Load the optional PDF-derived provenance index (never required)."""
    if not path.is_file():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def attach_spec_provenance(payload: dict, index: dict | None) -> None:
    """Join the PDF table index onto the CSV-derived field/command rows.

    The PDF index supplies where a table lives in the specification; the CSV
    remains the authority for field values.  Extra keys on the field rows are
    in the JSON only - the SQLite column whitelist intentionally leaves them
    out, and the API resolves provenance through the spec-tables table.
    """
    tables = {str(t.get("table_id")): t for t in (index or {}).get("tables", [])}
    meta = (index or {}).get("meta", {})
    pdf_file = meta.get("pdf_file")
    resolved = 0
    for row in payload["fields"]:
        for token in re.split(r"[;,\s]+", str(row.get("ref_table") or "")):
            table = tables.get(token.strip())
            if table and table.get("pdf_page"):
                row["spec_pdf_page"] = table["pdf_page"]
                row["spec_pdf_file"] = pdf_file
                row["spec_table_title"] = table.get("title")
                resolved += 1
                break
    for command in payload["cdb_commands"]:
        table = tables.get(str(command.get("detail_table") or "").strip())
        if table:
            command["spec_pdf_page"] = table.get("pdf_page")
            command["spec_pdf_file"] = pdf_file
    payload["stats"]["fields_with_spec_page"] = resolved
    payload["meta"]["spec_pdf_provenance"] = {
        "available": bool(index),
        "generator": meta.get("generator"),
        "pdf_file": pdf_file,
        "pdf_sha256": meta.get("pdf_sha256"),
        "pdf_pages": meta.get("pdf_pages"),
        "reader": meta.get("reader"),
        "content_policy": meta.get("content_policy"),
        "note": ("Table captions, field names and addresses are OIF factual "
                 "identifiers used for cross-referencing; no verbatim "
                 "specification prose is stored."),
    }
    payload["spec_pdf_meta"] = meta
    payload["spec_tables"] = sorted(
        (dict(t) for t in tables.values()),
        key=lambda t: (int(t.get("section") or 0),
                       int(str(t.get("table_id", "0-0")).split("-")[-1] or 0)))
    payload["spec_verification"] = (index or {}).get(
        "verification", {"available": False,
                         "hint": "Generate data/spec_pdf_index.json with tools/parse_spec_pdf.py"})


def build(source: Path, spec_index: dict | None = None) -> dict:
    field_csv = source / FIELD_CSV
    cdb_csv = source / CDB_CSV
    corrections = source / CORRECTIONS_CSV

    raw_fields = read_csv(field_csv, FIELD_COLUMNS)
    raw_cdb = read_csv(cdb_csv, CDB_COLUMNS)
    fields = [normalize_field(row) for row in raw_fields]
    commands = [normalize_cdb(row) for row in raw_cdb]
    require_unique(fields, "key_id", FIELD_CSV)
    require_unique(commands, "cmd_id", CDB_CSV)

    correction_rows = 0
    if corrections.is_file():
        with corrections.open("r", encoding="utf-8-sig", newline="") as fh:
            correction_rows = sum(1 for _ in csv.DictReader(fh))

    assets = {}
    for path in (field_csv, cdb_csv, corrections):
        if path.is_file():
            assets[path.name] = {"sha256": sha256(path), "bytes": path.stat().st_size}

    stats = {
        "fields": len(fields),
        "cdb_commands": len(commands),
        "reserved_rows": sum(r["is_reserved"] for r in fields),
        "lower_memory_rows": sum(r["is_lower_memory"] for r in fields),
        "upper_memory_rows": sum(1 - r["is_lower_memory"] for r in fields),
        "by_section": count_by(fields, "section"),
        "by_page": count_by(fields, "page"),
        "by_access": count_by(fields, "access"),
        "by_value_type": count_by(fields, "value_type"),
        "by_sonic_cross_check": count_by(fields, "sonic_cross_check"),
        "cdb_by_group": count_by(commands, "cmd_group"),
    }

    payload = {
        "meta": {
            "generator": "tools/import_cmis53.py",
            "schema_version": "1.0",
            "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "specification": SPEC,
            "specification_url": SPEC_PDF_URL,
            "upstream_repository": UPSTREAM_REPO,
            "source_directory": "data/upstream",
            "source_assets": assets,
            "upstream_corrections": correction_rows,
            "data_nature": "specification-derived reference, read-only",
            "authority_note": ("The OIF specification is authoritative. Verify timing- or "
                               "safety-critical details against the PDF before hardware use."),
            "license": {
                "scripts_and_structure": "MIT, Copyright (c) 2026 Jim Frederick",
                "specification_content": ("Field names, register addresses, access/requirement "
                                          "types and verbatim Description text remain "
                                          "(c) Optical Internetworking Forum and are NOT "
                                          "covered by MIT; subject to OIF terms."),
                "sonic_cross_check": ("Derived from sonic-net/sonic-platform-common, "
                                      "Apache-2.0; comparison result only, not a "
                                      "compliance statement."),
            },
            "attribution": {
                "oif": OIF_URL,
                "upstream": UPSTREAM_REPO,
                "notice": "See NOTICE sections 5-7 and data/upstream/README.md",
            },
        },
        "field_columns": FIELD_COLUMN_NOTES,
        "cdb_columns": CDB_COLUMN_NOTES,
        "section_rules": SECTION_RULES,
        "stats": stats,
        "fields": fields,
        "cdb_commands": commands,
    }
    attach_spec_provenance(payload, spec_index)
    return payload


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--source", type=Path, default=DEFAULT_SOURCE,
                        help=f"directory holding the upstream CSV assets (default: {DEFAULT_SOURCE})")
    parser.add_argument("--out", type=Path, default=DEFAULT_OUTPUT,
                        help=f"output JSON path (default: {DEFAULT_OUTPUT})")
    parser.add_argument("--spec-index", type=Path, default=DEFAULT_SPEC_INDEX,
                        help=f"PDF-derived provenance index (default: {DEFAULT_SPEC_INDEX})")
    parser.add_argument("--no-spec-index", action="store_true",
                        help="build the CSV reference without PDF provenance")
    args = parser.parse_args()

    source = args.source if args.source.is_absolute() else (ROOT / args.source)
    out = args.out if args.out.is_absolute() else (ROOT / args.out)
    spec_index = None
    if not args.no_spec_index:
        spec_path = (args.spec_index if args.spec_index.is_absolute()
                     else (ROOT / args.spec_index))
        spec_index = load_spec_index(spec_path)
        if spec_index is None:
            print(f"  NOTE: {spec_path.name} not found; run tools/parse_spec_pdf.py "
                  "to enable PDF provenance")
    payload = build(source.resolve(), spec_index)
    out.parent.mkdir(parents=True, exist_ok=True)
    # write_bytes keeps LF line endings on every platform (.gitattributes).
    out.write_bytes((json.dumps(payload, ensure_ascii=False, indent=2) + "\n").encode("utf-8"))

    stats = payload["stats"]
    print(f"Wrote {out} ({out.stat().st_size:,} bytes)")
    print(f"  fields={stats['fields']} cdb_commands={stats['cdb_commands']} "
          f"reserved={stats['reserved_rows']} lower={stats['lower_memory_rows']}")
    print(f"  by_section={stats['by_section']}")
    print(f"  spec_tables={len(payload['spec_tables'])} "
          f"fields_with_spec_page={stats['fields_with_spec_page']}/{stats['fields']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
