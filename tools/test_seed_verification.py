#!/usr/bin/env python3
"""Regression checks for the demo-field vs CMIS 5.3 reference verifier.

Standard library only. Pure normalization/matching is exercised on synthetic
rows; the delivered report is checked without regenerating it.

Usage: python tools/test_seed_verification.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
for path in (str(HERE), str(ROOT)):
    if path not in sys.path:
        sys.path.insert(0, path)

from verify_seed_fields import (  # noqa: E402
    build_report, classify, norm_access, norm_name, norm_pages, render_markdown,
    seed_byte, similarity,
)

REPORT = ROOT / "data" / "seed_field_verification.json"
MARKDOWN = ROOT / "docs" / "SEED_FIELD_VERIFICATION.md"
PASS, FAIL = [], []


def check(name: str, condition: bool, detail: str = "") -> None:
    (PASS if condition else FAIL).append(name)
    print(f"{'PASS' if condition else 'FAIL'}  {name}" + (f"  | {detail}" if detail else ""))


def normalization_checks() -> None:
    check("Lower maps to the reference Lwr page",
          norm_pages("Lower") == ["Lwr"])
    check("compound page labels expand",
          norm_pages("Lower/11h") == ["Lwr", "11h"])
    pages = norm_pages("A0h-AFh")
    check("page ranges expand to every page",
          len(pages) == 16 and pages[0] == "A0h" and pages[-1] == "AFh",
          str(len(pages)))
    check("byte offsets prefer explicit hex in parentheses",
          seed_byte("85 (0x55)") == 85 and seed_byte("128 (0x80)") == 128)
    check("plain hex suffix offsets parse",
          seed_byte("00h") == 0 and seed_byte("01h") == 1 and seed_byte("7Fh") == 127)
    check("range and bit annotations use their first byte",
          seed_byte("08-13") == 8 and seed_byte("26 bit4") == 26
          and seed_byte("37-38 (0x25-0x26)") == 37
          and seed_byte("136-255 (0x88-0xFF)") == 136)
    check("placeholders never become addresses",
          all(seed_byte(x) is None for x in
              ("pending", "banked", "Staged Control Set", "CMD 0040h reply", "")))
    check("compound access keeps its primary mode",
          norm_access("RO/CoR") == "RO" and norm_access("RW") == "RW")
    check("name normalization is case/punctuation insensitive",
          norm_name("Temp Mon High Alarm") == "tempmonhighalarm"
          and similarity("TempHighAlarmThreshold", "TempMonHighAlarmThreshold") > 0.8)


def synthetic_matching_checks() -> None:
    rows = [
        {"key_id": "CmisRevision", "name": "CmisRevision", "page": "Lwr", "byte": 1,
         "access": "RO", "data_type": "hex", "value_type": "u8", "ref_table": "8-2",
         "ref_section": "8.2", "spec_pdf_page": 137, "byte_length": 1},
        {"key_id": "ModuleStateChangedFlag.Lwr.8", "name": "ModuleStateChangedFlag",
         "page": "Lwr", "byte": 8, "access": "RO", "data_type": "bool",
         "value_type": "bool", "ref_table": "8-9", "ref_section": "8.2",
         "spec_pdf_page": 144, "byte_length": 1},
        {"key_id": "VendorPN.00h.148", "name": "VendorPN", "page": "00h", "byte": 148,
         "access": "RO", "data_type": "ascii", "value_type": "u8", "ref_table": "8-28",
         "ref_section": "8.2", "spec_pdf_page": 176, "byte_length": 16},
    ]
    by_name, by_address, name_rows = {}, {}, {}
    for row in rows:
        key = norm_name(row["name"])
        by_name.setdefault(key, []).append(row)
        name_rows.setdefault(key, []).append(row)
        by_address.setdefault((row["page"], row["byte"]), []).append(row)
    name_pool = sorted(by_name)

    verified = classify(
        {"field_key": "CmisRevision", "page": "Lower", "byte_offset": "01h",
         "section": "LOW_PAGE", "access": "RO", "data_type": "hex"},
        by_name, by_address, name_pool, name_rows)
    check("exact name with matching page/byte is verified",
          verified["status"] == "verified" and verified["match_kind"] == "exact_name")

    resolved = classify(
        {"field_key": "VendorPN", "page": "00h", "byte_offset": "pending",
         "section": "LOW_PAGE", "access": "RO", "data_type": "ascii"},
        by_name, by_address, name_pool, name_rows)
    check("pending offset with exact name is resolvable",
          resolved["status"] == "address_resolved"
          and resolved["reference"]["byte"] == 148)

    mismatch = classify(
        {"field_key": "CmisRevision", "page": "Lower", "byte_offset": "05h",
         "section": "LOW_PAGE", "access": "RO", "data_type": "hex"},
        by_name, by_address, name_pool, name_rows)
    check("exact name with a wrong address is a mismatch",
          mismatch["status"] == "mismatch"
          and mismatch["checks"]["byte_match"] is False)

    coincidence = classify(
        {"field_key": "TotallyUnrelatedName", "page": "Lower", "byte_offset": "08-13",
         "section": "LOW_PAGE", "access": "RO", "data_type": "hex"},
        by_name, by_address, name_pool, name_rows)
    check("address-only coincidence is low confidence",
          coincidence["status"] == "candidate"
          and coincidence["checks"]["confidence"] == "low"
          and any("address coincidence" in note for note in coincidence["notes"]))

    unresolved = classify(
        {"field_key": "NonexistentDemoField", "page": "13h", "byte_offset": "pending",
         "section": "CONTROL", "access": "RW", "data_type": "enum"},
        by_name, by_address, name_pool, name_rows)
    check("unmatched demo field stays unresolved",
          unresolved["status"] == "unresolved" and unresolved["reference"] is None)

    seed = {"fields": [{"field_key": "CmisRevision", "page": "Lower",
                        "byte_offset": "01h", "access": "RO", "data_type": "hex",
                        "section": "LOW_PAGE"}]}
    reference = {"fields": rows}
    report = build_report(seed, reference)
    md = render_markdown(report)
    check("report builder returns summary and markdown",
          report["summary"]["total"] == 1
          and report["summary"]["by_status"]["verified"] == 1
          and "## 1. 结论" in md and "P-01" in md)
    check("markdown never claims to write seed data",
          "不修改 `seed.json`" in md)


def delivered_report_checks() -> None:
    check("delivered verification JSON exists", REPORT.is_file(), str(REPORT))
    check("delivered verification Markdown exists", MARKDOWN.is_file(), str(MARKDOWN))
    if not REPORT.is_file():
        return
    data = json.loads(REPORT.read_text(encoding="utf-8"))
    meta, summary, fields = data["meta"], data["summary"], data["fields"]
    check("report covers all 64 demo fields",
          summary["total"] == 64 and len(fields) == 64, str(summary["total"]))
    check("report uses the full 2442-row reference",
          meta["reference_fields"] == 2442, str(meta["reference_fields"]))
    check("status counts agree with per-field results",
          sum(summary["by_status"].values()) == 64
          and all(summary["by_status"].get(name, 0)
                  == sum(1 for row in fields if row["status"] == name)
                  for name in ("verified", "address_resolved", "mismatch",
                               "candidate", "unresolved")))
    check("P-01 linkage and three-stage matching recorded",
          meta["knowledge_graph_item"].startswith("P-01")
          and "exact_name" in meta["matching"]
          and "fuzzy_name" in meta["matching"])
    check("exact-name rows are verified or resolvable",
          all(row["status"] in ("verified", "address_resolved", "mismatch")
              for row in fields if row["match_kind"] == "exact_name"))
    check("every candidate carries a confidence grade",
          all(row["checks"].get("confidence") in ("high", "medium", "low")
              for row in fields if row["status"] == "candidate"))
    # Offsets verified against OIF-CMIS-05.3 no longer need the
    # "address_resolved" fallback: exact-name rows become "verified" directly.
    # The report must still expose actionable offsets (verified or resolved)
    # and keep high-confidence pending candidates visible.
    verified = summary["by_status"].get("verified", 0)
    check("actionable offsets are reported for P-01",
          (summary["resolvable_offsets"] + verified) >= 4
          and summary["high_confidence_pending_candidates"] >= 1,
          f"verified={verified} address_resolved={summary['resolvable_offsets']}")
    check("report is advisory and license-aware",
          "never modified" in meta["policy"] and "OIF" in meta["license_note"])
    if MARKDOWN.is_file():
        text = MARKDOWN.read_text(encoding="utf-8")
        check("Markdown has all eight sections",
              all(f"## {n}." in text for n in range(1, 9)))
        check("Markdown distinguishes high-confidence candidates",
              "高置信度可回填候选" in text and "置信度" in text)


def main() -> int:
    normalization_checks()
    synthetic_matching_checks()
    delivered_report_checks()
    print(f"\n{len(PASS)} passed, {len(FAIL)} failed")
    if FAIL:
        print("FAILED: " + ", ".join(FAIL))
    return 1 if FAIL else 0


if __name__ == "__main__":
    sys.exit(main())
