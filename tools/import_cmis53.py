#!/usr/bin/env python3
"""Build the portable CMIS 5.3 reference JSON from CMIScope's own dataset.

Pure standard library: no third-party packages, no network access, no PDF or
XLSX parsing here. The canonical input is ``data/cmis53_dataset.json``, a
normalized, project-owned record set; an optional PDF-derived index
(``data/spec_pdf_index.json``, built by ``tools/parse_spec_pdf.py`` with the
standard library) is merged in for specification page provenance and
verification. No external repository or its exported files are required.

Usage:
    python tools/parse_spec_pdf.py            # optional: build the PDF index first
    python tools/import_cmis53.py
    python tools/import_cmis53.py --dataset data/cmis53_dataset.json \
        --out data/cmis53_reference.json
    python tools/import_cmis53.py --no-spec-index   # dataset only

The generated file is imported into SQLite at service start. Re-run this script
whenever the normalized dataset or the PDF index is refreshed.
See docs/CMIS53_REFERENCE.md.
"""

from __future__ import annotations

import argparse
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
    SECTION_RULES,
)

DEFAULT_DATASET = ROOT / "data" / "cmis53_dataset.json"
DEFAULT_OUTPUT = ROOT / "data" / "cmis53_reference.json"
DEFAULT_SPEC_INDEX = ROOT / "data" / "spec_pdf_index.json"
DEFAULT_SPEC_PDF = ROOT / "knowledge" / "specs" / "OIF-CMIS-05.3.pdf"

SPEC = "OIF-CMIS-05.3, Common Management Interface Specification revision 5.3 (4 Sept 2024)"
OIF_URL = "https://www.oiforum.com/"
SPEC_PDF_URL = "https://www.oiforum.com/wp-content/uploads/OIF-CMIS-05.3.pdf"

DATASET_SECTIONS = ("fields", "cdb_commands")
DERIVED_FIELD_KEYS = ("spec_pdf_page", "spec_pdf_file", "spec_table_title")
DERIVED_CDB_KEYS = ("spec_pdf_page", "spec_pdf_file")


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def asset(path: Path) -> dict:
    """Checksum one build input; always return the same shape."""
    if not path.is_file():
        return {"sha256": "", "bytes": 0, "missing": True}
    return {"sha256": sha256(path), "bytes": path.stat().st_size}


def count_by(rows: list[dict], key: str) -> dict:
    return dict(sorted(Counter(str(r.get(key) or "") for r in rows).items(),
                       key=lambda pair: (-pair[1], pair[0])))


def require_unique(rows: list[dict], key: str, label: str) -> None:
    seen = [r[key] for r in rows]
    duplicates = [value for value, n in Counter(seen).items() if n > 1]
    if duplicates:
        raise SystemExit(f"ERROR: duplicate {key} in {label}: {', '.join(duplicates[:5])}")


def read_dataset(path: Path) -> dict:
    """Load the canonical normalized dataset and validate its shape."""
    if not path.is_file():
        raise SystemExit(f"ERROR: normalized dataset is missing: {path}")
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise SystemExit("ERROR: dataset root must be a JSON object")
    for section in DATASET_SECTIONS:
        rows = data.get(section)
        if not isinstance(rows, list) or not rows:
            raise SystemExit(f"ERROR: dataset section {section!r} must be a non-empty list")
        if not all(isinstance(row, dict) for row in rows):
            raise SystemExit(f"ERROR: dataset section {section!r} contains non-object rows")
    missing = [name for name in FIELD_COLUMNS.values()
               if name not in data["fields"][0]]
    if missing:
        raise SystemExit(f"ERROR: dataset field rows lack columns: {', '.join(missing[:8])}")
    return data


def load_spec_index(path: Path) -> dict | None:
    """Load the optional PDF-derived provenance index (never required)."""
    if not path.is_file():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def attach_spec_provenance(payload: dict, index: dict | None) -> None:
    """Join the PDF table index onto the canonical field/command rows.

    The PDF index supplies where a table lives in the specification; the
    normalized dataset remains the authority for field values. Extra keys on
    the field rows are in the JSON only - the SQLite column whitelist
    intentionally leaves them out, and the API resolves provenance through the
    spec-tables table.
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


def build(dataset: dict, dataset_path: Path, spec_index_path: Path,
          spec_pdf_path: Path, spec_index: dict | None = None) -> dict:
    fields = []
    for row in dataset["fields"]:
        clean = {k: v for k, v in row.items() if k not in DERIVED_FIELD_KEYS}
        fields.append(clean)
    commands = []
    for row in dataset["cdb_commands"]:
        clean = {k: v for k, v in row.items() if k not in DERIVED_CDB_KEYS}
        commands.append(clean)
    require_unique(fields, "key_id", "normalized field dataset")
    require_unique(commands, "cmd_id", "normalized CDB dataset")

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
            "dataset": "data/cmis53_dataset.json (CMIScope normalized, project-owned)",
            "source_assets": {
                "cmis53_dataset.json": asset(dataset_path),
                "spec_pdf_index.json": asset(spec_index_path),
                "OIF-CMIS-05.3.pdf": asset(spec_pdf_path),
            },
            "data_nature": "specification-derived reference, read-only",
            "authority_note": ("The OIF specification is authoritative. Verify timing- or "
                               "safety-critical details against the PDF before hardware use."),
            "license": {
                "scripts_and_structure": ("Normalized schema, partition mapping, key IDs and "
                                          "build tooling are CMIScope original work under the "
                                          "repository MIT License (see LICENSE)."),
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
                "notice": "See NOTICE for the OIF and Apache-2.0 terms that apply to this data",
            },
        },
        "field_columns": dataset.get("field_columns") or FIELD_COLUMN_NOTES,
        "cdb_columns": dataset.get("cdb_columns") or CDB_COLUMN_NOTES,
        "section_rules": dataset.get("section_rules") or SECTION_RULES,
        "stats": stats,
        "fields": fields,
        "cdb_commands": commands,
    }
    attach_spec_provenance(payload, spec_index)
    return payload


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--dataset", type=Path, default=DEFAULT_DATASET,
                        help=f"normalized, project-owned input (default: {DEFAULT_DATASET})")
    parser.add_argument("--out", type=Path, default=DEFAULT_OUTPUT,
                        help=f"output JSON path (default: {DEFAULT_OUTPUT})")
    parser.add_argument("--spec-index", type=Path, default=DEFAULT_SPEC_INDEX,
                        help=f"PDF-derived provenance index (default: {DEFAULT_SPEC_INDEX})")
    parser.add_argument("--spec-pdf", type=Path, default=DEFAULT_SPEC_PDF,
                        help=f"bundled OIF PDF for checksums (default: {DEFAULT_SPEC_PDF})")
    parser.add_argument("--no-spec-index", action="store_true",
                        help="build the reference without PDF provenance")
    args = parser.parse_args()

    def resolve(path: Path) -> Path:
        return path if path.is_absolute() else (ROOT / path)

    dataset_path = resolve(args.dataset)
    out = resolve(args.out)
    spec_index_path = resolve(args.spec_index)
    spec_pdf_path = resolve(args.spec_pdf)

    spec_index = None
    if not args.no_spec_index:
        spec_index = load_spec_index(spec_index_path)
        if spec_index is None:
            print(f"  NOTE: {spec_index_path.name} not found; run tools/parse_spec_pdf.py "
                  "to enable PDF provenance")
    payload = build(read_dataset(dataset_path), dataset_path,
                    spec_index_path, spec_pdf_path, spec_index)
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
