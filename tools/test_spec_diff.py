#!/usr/bin/env python3
"""Regression checks for the 5.3 -> 5.4 specification difference report.

Standard library only. Pure diff logic is exercised on small synthetic inputs;
the delivered report is checked for structure without regenerating it.

Usage: python tools/test_spec_diff.py
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

from diff_spec_versions import (  # noqa: E402
    _loose, _norm, _terminology, build_diff, diff_commands, diff_fields,
    diff_tables, render_markdown,
)

REPORT = ROOT / "data" / "spec_version_diff.json"
MARKDOWN = ROOT / "docs" / "CMIS_53_54_DIFF.md"
PASS, FAIL = [], []


def check(name: str, condition: bool, detail: str = "") -> None:
    (PASS if condition else FAIL).append(name)
    print(f"{'PASS' if condition else 'FAIL'}  {name}" + (f"  | {detail}" if detail else ""))


def table(**kw) -> dict:
    base = {"section": 8, "title": "", "pdf_page": 100, "field_rows": 0}
    base.update(kw)
    return base


def synthetic_checks() -> None:
    check("normalization ignores case, spacing and punctuation",
          _norm("  List of  CMIS Pages ") == "list of cmis pages"
          and _loose("List of CMIS Pages") == _loose("list, of cmis-pages"))
    check("5.3 -> 5.4 global wording swap folds to one identity",
          _terminology("Module Flags (paged memory modules only) (Lower Memory)")
          == _terminology("Module Flags (not for static memory modules) (Lower Memory)"))

    # An inserted table in the middle renumbers everything after it.
    old = {
        "8-1": table(title="List of CMIS Pages", pdf_page=136),
        "8-2": table(title="Vendor Information (Page 00h)", pdf_page=160),
        "8-3": table(title="Date Code (Page 00h)", pdf_page=162),
    }
    new = {
        "8-1": table(title="List of CMIS 128-Byte Pages and Banks", pdf_page=161),
        "8-2": table(title="Newly Inserted Table", pdf_page=163),
        "8-3": table(title="Vendor Information (Page 00h)", pdf_page=164),
        "8-4": table(title="Date Code (Page 00h)", pdf_page=166),
    }
    for collection in (old, new):
        for table_id, row in collection.items():
            row["table_id"] = table_id
    result = diff_tables(old, new)
    check("alignment finds the single real insertion",
          [r["table_id"] for r in result["added"]] == ["8-2"],
          str([r["table_id"] for r in result["added"]]))
    check("alignment reports no phantom deletions",
          result["removed"] == [], str(result["removed"]))
    check("alignment keeps renumbered tables as matches",
          result["alignment"]["matched_pairs"] == 2
          and result["alignment"]["dominant_number_shift"] == 1,
          str(result["alignment"]))
    check("alignment isolates the one substantive caption edit",
          len(result["renamed"]) == 1 and result["renamed"][0]["table_id_53"] == "8-1",
          str(result["renamed"]))
    check("page shift is reported as layout metadata",
          result["page_shift"]["min_delta"] > 0
          and "layout" in result["page_shift"]["note"])

    commands_old = {"0000": {"cmd_id": "0000", "title": "Query Status",
                             "spec_section": "9.3.1", "detail_table": "9-3",
                             "pdf_page": 290}}
    commands_new = {
        "0000": {"cmd_id": "0000", "title": "Query Status",
                 "spec_section": "9.3.1", "detail_table": "9-4", "pdf_page": 320},
        "0005": {"cmd_id": "0005", "title": "Get Module Time",
                 "spec_section": "9.3.5", "detail_table": "9-7", "pdf_page": 332},
    }
    commands = diff_commands(commands_old, commands_new)
    check("command diff finds added commands",
          [r["cmd_id"] for r in commands["added"]] == ["0005"])
    check("command diff tracks detail-table renumbering",
          len(commands["changed"]) == 1
          and "detail_table" in commands["changed"][0]["changes"])

    fields_old = {("02h", 128, "tempmonhighalarmthreshold"):
                  {"page": "02h", "byte": 128, "name": "TempMonHighAlarmThreshold",
                   "access": "RW", "byte_length": 2, "table_id": "8-62",
                   "value_type": "s16", "unit": None, "scale": None,
                   "is_reserved": 0, "pdf_page": 185}}
    fields_new = {("02h", 128, "tempmonhighalarmthreshold"):
                  dict(fields_old[("02h", 128, "tempmonhighalarmthreshold")], access="RO")}
    fields = diff_fields(fields_old, fields_new)
    check("field diff reports attribute changes only",
          len(fields["changed"]) == 1
          and "access" in fields["changed"][0]["changes"]
          and fields["added"] == [] and fields["removed"] == [])

    old_index = {"tables": [dict(v, table_id=k) for k, v in old.items()],
                 "cdb_commands": [], "fields": [],
                 "meta": {"specification": "OIF-CMIS-05.3", "pdf_pages": 408}}
    new_index = {"tables": [dict(v, table_id=k) for k, v in new.items()],
                 "cdb_commands": [], "fields": [],
                 "meta": {"specification": "OIF-CMIS-05.4", "pdf_pages": 456}}
    sources = {
        "53": {"pdf_file": "synthetic-5.3.pdf", "pdf_sha256": "a" * 64,
               "pdf_pages": 408, "source": "synthetic"},
        "54": {"pdf_file": "synthetic-5.4.pdf", "pdf_sha256": "b" * 64,
               "pdf_pages": 456, "source": "synthetic"},
    }
    payload = build_diff(old_index, new_index, sources)
    md = render_markdown(payload, 20)
    check("markdown render includes alignment caveat and all sections",
          "SequenceMatcher" in md and all(
              heading in md for heading in ("## 2.", "## 3.", "## 4.",
                                            "## 4b.", "## 4c.", "## 5.",
                                            "## 6.", "## 7.")))


def delivered_report_checks() -> None:
    check("delivered diff JSON exists", REPORT.is_file(), str(REPORT))
    check("delivered Markdown report exists", MARKDOWN.is_file(), str(MARKDOWN))
    if not REPORT.is_file():
        return
    data = json.loads(REPORT.read_text(encoding="utf-8"))
    meta, summary = data["meta"], data["summary"]
    check("report declares both bundled PDF versions",
          meta["versions"]["53"]["specification"] == "OIF-CMIS-05.3"
          and meta["versions"]["54"]["specification"] == "OIF-CMIS-05.4")
    check("report records PDF hashes for reproducibility",
          len(meta["versions"]["53"]["pdf_sha256"]) == 64
          and len(meta["versions"]["54"]["pdf_sha256"]) == 64)
    check("report uses caption alignment rather than table IDs",
          "SequenceMatcher" in summary["tables"]["alignment"]["method"]
          and summary["tables"]["alignment"]["matched_pairs"] > 150)
    check("report exposes real additions and deletions",
          summary["tables"]["added"] > 0 and summary["tables"]["removed"] >= 0)
    check("summary counts match the detailed lists",
          summary["tables"]["added"] == len(data["tables"]["added"])
          and summary["tables"]["renamed"] == len(data["tables"]["renamed"])
          and summary["cdb_commands"]["added"] == len(data["cdb_commands"]["added"]))
    check("field-level diff carries its caveat",
          "caveat" in data["fields_indicative"]
          and "best-effort" in data["fields_indicative"]["caveat"])
    check("report states OIF authority and content policy",
          "authoritative" in meta["authority_note"]
          and "not written to disk" in meta["content_policy"])
    if MARKDOWN.is_file():
        text = MARKDOWN.read_text(encoding="utf-8")
        check("Markdown explains the renumbering pitfall",
              "表号不能直接对比" in text and "P-02" in text)
        check("Markdown lists the CDB changes and caveats",
              "CDB 命令变化" in text and "指示性" in text)


def main() -> int:
    synthetic_checks()
    delivered_report_checks()
    print(f"\n{len(PASS)} passed, {len(FAIL)} failed")
    if FAIL:
        print("FAILED: " + ", ".join(FAIL))
    return 1 if FAIL else 0


if __name__ == "__main__":
    sys.exit(main())
