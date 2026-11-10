#!/usr/bin/env python3
"""Functional, exception and boundary tests for the project-owned dataset build.

Covers the refactor that removed the external CSV tool chain: the canonical
input is now ``data/cmis53_dataset.json`` and ``tools/import_cmis53.py`` rebuilds
``data/cmis53_reference.json`` from it (plus the optional PDF provenance index).

Standard library only. All writes go to a temporary directory; no delivered
data file, database or configuration is modified.

Usage: python tools/test_dataset_build.py
"""

from __future__ import annotations

import copy
import json
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TOOLS = ROOT / "tools"
for p in (str(ROOT), str(TOOLS)):
    if p not in sys.path:
        sys.path.insert(0, p)

import import_cmis53 as build_mod  # noqa: E402
from cmis_service import api, db  # noqa: E402
from cmis_service.config import load_settings  # noqa: E402

PASS, FAIL, SKIP = [], [], []


def check(name: str, condition: bool, detail: str = "") -> None:
    (PASS if condition else FAIL).append(name)
    print(f"{'PASS' if condition else 'FAIL'}  {name}" + (f"  | {detail}" if detail else ""))


def skip(name: str, reason: str) -> None:
    SKIP.append(name)
    print(f"SKIP  {name}  | {reason}")


def writes(path: Path, obj) -> Path:
    path.write_bytes((json.dumps(obj, ensure_ascii=False) + "\n").encode("utf-8"))
    return path


def expect_system_exit(name: str, call, needle: str = "") -> None:
    """Assert a malformed input is refused with a diagnostic SystemExit."""
    try:
        call()
    except SystemExit as exc:
        msg = str(exc)
        check(name, not needle or needle in msg, msg[:110])
    except Exception as exc:  # noqa: BLE001 - an unexpected exception is a failure
        check(name, False, f"unexpected {type(exc).__name__}: {exc}")
    else:
        check(name, False, "invalid input was accepted")


def minimal_dataset(dataset: dict, *, fields: int = 1, commands: int = 1) -> dict:
    small = {
        "meta": dataset["meta"],
        "field_columns": dataset["field_columns"],
        "cdb_columns": dataset["cdb_columns"],
        "section_rules": dataset["section_rules"],
        "fields": [copy.deepcopy(dataset["fields"][i]) for i in range(fields)],
        "cdb_commands": [copy.deepcopy(dataset["cdb_commands"][i])
                         for i in range(commands)],
    }
    return small


def functional_checks(tmp: Path, dataset: dict) -> dict | None:
    """Happy path: dataset -> reference payload, with and without PDF index."""
    index = json.loads((ROOT / "data" / "spec_pdf_index.json").read_text(encoding="utf-8"))
    spec_pdf = ROOT / "knowledge" / "specs" / "OIF-CMIS-05.3.pdf"

    payload = build_mod.build(copy.deepcopy(dataset),
                              ROOT / "data" / "cmis53_dataset.json",
                              ROOT / "data" / "spec_pdf_index.json",
                              spec_pdf, index)
    check("Build emits the full 2442 fields / 48 CDB commands",
          len(payload["fields"]) == 2442 and len(payload["cdb_commands"]) == 48)
    check("Build stats agree with emitted rows",
          payload["stats"]["fields"] == len(payload["fields"])
          and payload["stats"]["cdb_commands"] == len(payload["cdb_commands"]))
    check("Build declares only project-owned inputs",
          "cmis53_dataset.json" in payload["meta"]["dataset"]
          and set(payload["meta"]["source_assets"]) ==
          {"cmis53_dataset.json", "spec_pdf_index.json", "OIF-CMIS-05.3.pdf"})
    check("Build checksums each input with SHA-256",
          all(len(v.get("sha256", "")) == 64
              for v in payload["meta"]["source_assets"].values()))
    check("Build keeps the three license boundaries",
          set(payload["meta"]["license"]) ==
          {"scripts_and_structure", "specification_content", "sonic_cross_check"})
    check("Build attaches PDF provenance to fields and commands",
          payload["stats"]["fields_with_spec_page"] > 0
          and any("spec_pdf_page" in r for r in payload["fields"])
          and any("spec_pdf_page" in r for r in payload["cdb_commands"]))
    check("Build exposes sorted spec tables and verification summary",
          len(payload["spec_tables"]) > 0
          and payload["spec_verification"].get("available") is True
          and payload["meta"]["spec_pdf_provenance"]["available"] is True)

    # Reproducibility: rebuilding from the same dataset must not change field rows.
    again = build_mod.build(copy.deepcopy(dataset),
                            ROOT / "data" / "cmis53_dataset.json",
                            ROOT / "data" / "spec_pdf_index.json", spec_pdf, index)
    check("Rebuild is deterministic for field and command rows",
          again["fields"] == payload["fields"]
          and again["cdb_commands"] == payload["cdb_commands"])

    # The delivered artifact must match a fresh build (timestamps aside).
    delivered = json.loads((ROOT / "data" / "cmis53_reference.json").read_text(encoding="utf-8"))
    check("Delivered reference matches a fresh build (fields/commands/stats)",
          delivered["fields"] == payload["fields"]
          and delivered["cdb_commands"] == payload["cdb_commands"]
          and delivered["stats"] == payload["stats"])

    # Dataset-only build: PDF index is optional.
    plain = build_mod.build(copy.deepcopy(dataset),
                            ROOT / "data" / "cmis53_dataset.json",
                            ROOT / "data" / "spec_pdf_index.json", spec_pdf, None)
    check("Dataset-only build keeps every field and command",
          len(plain["fields"]) == 2442 and len(plain["cdb_commands"]) == 48)
    check("Dataset-only build marks provenance unavailable with a hint",
          plain["meta"]["spec_pdf_provenance"]["available"] is False
          and plain["spec_verification"].get("available") is False
          and "hint" in plain["spec_verification"]
          and plain["stats"]["fields_with_spec_page"] == 0)
    return payload


def exception_checks(tmp: Path, dataset: dict) -> None:
    """Malformed inputs must fail loudly instead of producing a partial file."""
    expect_system_exit("Missing dataset file is rejected",
                       lambda: build_mod.read_dataset(tmp / "absent.json"), "missing")
    expect_system_exit("Non-object dataset root is rejected",
                       lambda: build_mod.read_dataset(writes(tmp / "list.json", [1, 2])),
                       "root must be")
    expect_system_exit("Empty fields section is rejected",
                       lambda: build_mod.read_dataset(writes(
                           tmp / "empty_fields.json", {"fields": [], "cdb_commands": [{}]})),
                       "non-empty list")
    expect_system_exit("Non-list cdb_commands section is rejected",
                       lambda: build_mod.read_dataset(writes(
                           tmp / "bad_cdb.json",
                           {"fields": [dataset["fields"][0]], "cdb_commands": "nope"})),
                       "non-empty list")
    expect_system_exit("Non-object field rows are rejected",
                       lambda: build_mod.read_dataset(writes(
                           tmp / "bad_rows.json",
                           {"fields": [dataset["fields"][0], "oops"],
                            "cdb_commands": [dataset["cdb_commands"][0]]})),
                       "non-object")
    incomplete = copy.deepcopy(minimal_dataset(dataset))
    del incomplete["fields"][0]["key_id"]
    expect_system_exit("Field rows missing required columns are rejected",
                       lambda: build_mod.read_dataset(writes(tmp / "missing_col.json",
                                                             incomplete)),
                       "lack columns")
    broken = tmp / "broken.json"
    broken.write_text("{not json", encoding="utf-8")
    try:
        build_mod.read_dataset(broken)
    except json.JSONDecodeError:
        check("Malformed JSON is surfaced, not silently ignored", True)
    except Exception as exc:  # noqa: BLE001
        check("Malformed JSON is surfaced, not silently ignored", False,
              f"unexpected {type(exc).__name__}")
    else:
        check("Malformed JSON is surfaced, not silently ignored", False,
              "invalid JSON was accepted")

    dup = minimal_dataset(dataset, fields=2)
    dup["fields"][1]["key_id"] = dup["fields"][0]["key_id"]
    expect_system_exit("Duplicate field key_id is rejected",
                       lambda: build_mod.build(dup, tmp / "d.json", tmp / "i.json",
                                               tmp / "p.pdf", None), "duplicate key_id")
    dup_cmd = minimal_dataset(dataset, commands=2)
    dup_cmd["cdb_commands"][1]["cmd_id"] = dup_cmd["cdb_commands"][0]["cmd_id"]
    expect_system_exit("Duplicate CDB cmd_id is rejected",
                       lambda: build_mod.build(dup_cmd, tmp / "d.json", tmp / "i.json",
                                               tmp / "p.pdf", None), "duplicate cmd_id")


def boundary_checks(tmp: Path, dataset: dict) -> None:
    """Small, empty and partially structured inputs stay well-behaved."""
    tiny = minimal_dataset(dataset)
    built = build_mod.build(tiny, tmp / "d.json", tmp / "i.json", tmp / "p.pdf", None)
    check("Single-row dataset builds successfully",
          len(built["fields"]) == 1 and len(built["cdb_commands"]) == 1
          and built["stats"]["fields"] == 1)
    check("Missing input files are checksummed as missing",
          build_mod.asset(tmp / "not-there.pdf") ==
          {"sha256": "", "bytes": 0, "missing": True})
    check("Empty row set produces empty counters", build_mod.count_by([], "section") == {})

    index_variants = [
        ("{}", "empty index object"),
        ('{"meta": {}}', "index without tables"),
        ('{"meta": {"pdf_file": "x.pdf"}, "tables": []}', "index with empty tables"),
    ]
    for raw, label in index_variants:
        payload = build_mod.build(copy.deepcopy(tiny), tmp / "d.json", tmp / "i.json",
                                  tmp / "p.pdf", json.loads(raw))
        check(f"PDF index degradation is handled: {label}",
              len(payload["fields"]) == 1
              and payload["stats"]["fields_with_spec_page"] == 0
              and payload["spec_tables"] == [])

    # A row may cite several tables; the first resolvable one wins.
    multi = minimal_dataset(dataset)
    multi["fields"][0]["ref_table"] = "NO-SUCH; 8-28"
    idx = {"meta": {"pdf_file": "x.pdf"},
           "tables": [{"table_id": "8-28", "pdf_page": 10, "title": "T"}]}
    payload = build_mod.build(multi, tmp / "d.json", tmp / "i.json", tmp / "p.pdf", idx)
    check("Multiple ref_table tokens resolve to the first known table",
          payload["fields"][0].get("spec_pdf_page") == 10)

    # Derived provenance keys must never be trusted from the input dataset.
    seeded = minimal_dataset(dataset)
    seeded["fields"][0]["spec_pdf_page"] = 9999
    seeded["fields"][0]["spec_table_title"] = "stale"
    payload = build_mod.build(seeded, tmp / "d.json", tmp / "i.json", tmp / "p.pdf", None)
    check("Stale derived provenance keys are stripped from the dataset",
          "spec_pdf_page" not in payload["fields"][0]
          and "spec_table_title" not in payload["fields"][0])


def regression_checks(tmp: Path, payload: dict) -> None:
    """A freshly built artifact still drives the shipped DB and REST API."""
    reference = writes(tmp / "reference.json", payload)
    settings = load_settings(environ={
        "CMIS_DB_FILE": str(tmp / "cmis.db"),
        "CMIS_REFERENCE_FILE": str(reference),
    })
    conn = db.initialize(settings)
    counts = {
        "ref": conn.execute("SELECT COUNT(*) FROM cmis53_fields").fetchone()[0],
        "cdb": conn.execute("SELECT COUNT(*) FROM cmis53_cdb_commands").fetchone()[0],
        "meta": conn.execute("SELECT COUNT(*) FROM cmis53_meta").fetchone()[0],
        "spec": conn.execute("SELECT COUNT(*) FROM cmis53_spec_tables").fetchone()[0],
        "demo": conn.execute("SELECT COUNT(*) FROM fields").fetchone()[0],
        "cfg": conn.execute("SELECT COUNT(*) FROM config_items").fetchone()[0],
    }
    check("Fresh build imports 2442 fields / 48 commands into SQLite",
          counts["ref"] == 2442 and counts["cdb"] == 48, str(counts))
    check("Fresh build imports meta and spec tables",
          counts["meta"] == 7 and counts["spec"] > 0)
    check("Demo field catalog and config items stay unchanged",
          counts["demo"] == 64 and counts["cfg"] == 512)
    check("Reference build never writes to the CDB operation log",
          conn.execute("SELECT COUNT(*) FROM cdb_operations").fetchone()[0] == 0)

    try:
        def call(path: str, query: dict | None = None):
            return api.dispatch(conn, settings, "GET", path, query or {}, None)

        status, body = call("/api/reference/meta")
        check("GET /api/reference/meta works on a fresh build",
              status == 200 and body["data"].get("available") is True)
        status, body = call("/api/reference/fields", {"q": "Temperature", "limit": "5"})
        check("GET /api/reference/fields query works on a fresh build",
              status == 200 and len(body["data"].get("items", [])) <= 5)
        status, body = call("/api/reference/verify")
        check("GET /api/reference/verify works on a fresh build", status == 200)
        status, body = call("/api/reference/spec-tables", {"limit": "3"})
        check("GET /api/reference/spec-tables works on a fresh build", status == 200)
        status, body = call("/api/reference/cdb-commands")
        check("GET /api/reference/cdb-commands works on a fresh build",
              status == 200 and len(body["data"].get("items", [])) == 48)
    finally:
        conn.close()


def main() -> int:
    dataset_path = ROOT / "data" / "cmis53_dataset.json"
    if not dataset_path.is_file():
        skip("dataset build tests", "data/cmis53_dataset.json is missing")
        return 0
    dataset = json.loads(dataset_path.read_text(encoding="utf-8"))
    with tempfile.TemporaryDirectory(prefix="cmiscope-dataset-") as name:
        tmp = Path(name)
        payload = functional_checks(tmp, dataset)
        exception_checks(tmp, dataset)
        boundary_checks(tmp, dataset)
        if payload:
            regression_checks(tmp, payload)
    print(f"\n{len(PASS)} passed, {len(FAIL)} failed, {len(SKIP)} skipped")
    for name in FAIL:
        print(f"  FAILED: {name}")
    return 1 if FAIL else 0


if __name__ == "__main__":
    raise SystemExit(main())
