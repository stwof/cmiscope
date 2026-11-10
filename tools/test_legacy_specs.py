#!/usr/bin/env python3
"""Cross-version validation against the CMIS 5.1 / 5.2 specification PDFs.

CMIS 5.1 states that all later revisions with the same major version are
backwards specification-compatible with 5.1. This suite checks that promise
against the project's normalized 5.3 dataset and, at the same time, exercises
the zero-dependency PDF reader on older, differently produced documents.

The PDFs are large, third-party copyrighted documents and are NOT bundled in
this repository. Point the suite at locally downloaded copies with:

    CMIS_LEGACY_SPEC_DIR=/path/to/pdfs python tools/test_legacy_specs.py

Default lookup: <workspace>/spec_downloads, then knowledge/specs. Canonical
download URLs are printed for any missing version; those checks are reported
as SKIP, not FAIL, so CI without network access stays green.

Usage: python tools/test_legacy_specs.py
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TOOLS = ROOT / "tools"
for p in (str(ROOT), str(TOOLS)):
    if p not in sys.path:
        sys.path.insert(0, p)

from spec_pdf import PdfTextDocument  # noqa: E402

PASS, FAIL, SKIP = [], [], []


def check(name: str, condition: bool, detail: str = "") -> None:
    (PASS if condition else FAIL).append(name)
    print(f"{'PASS' if condition else 'FAIL'}  {name}" + (f"  | {detail}" if detail else ""))


def skip(name: str, reason: str) -> None:
    SKIP.append(name)
    print(f"SKIP  {name}  | {reason}")


SPECS = [
    {
        "version": "5.1",
        "names": ("OIF-CMIS-05.1.pdf", "CMIS5p1_Third_Party_Spec.pdf", "CMIS5p1.pdf"),
        "url": ("https://www.oiforum.com/wp-content/uploads/"
                "CMIS5p1_Third_Party_Spec.pdf"),
        "published": "Rev 5.1, 2 November 2021 (QSFP-DD MSA, hosted by OIF)",
    },
    {
        "version": "5.2",
        "names": ("OIF-CMIS-05.2.pdf",),
        "url": "https://www.oiforum.com/wp-content/uploads/OIF-CMIS-05.2.pdf",
        "published": "OIF-CMIS-05.2, 25 May 2022",
    },
]

# Normative concepts that both revisions must define. Matched against the
# front matter + table of contents, where the specification enumerates them.
CORE_TERMS = (
    "memory map", "command data block", "lower memory", "upper memory",
    "two-wire", "module state machine", "versatile diagnostic", "page 00h",
    "page 9fh", "byte 128",
)


def candidate_dirs() -> list[Path]:
    env = os.environ.get("CMIS_LEGACY_SPEC_DIR")
    dirs = [Path(env)] if env else []
    dirs += [ROOT.parent / "spec_downloads", ROOT / "knowledge" / "specs",
             ROOT / "knowledge" / "specs" / "legacy"]
    return dirs


def locate(spec: dict) -> Path | None:
    for directory in candidate_dirs():
        for name in spec["names"]:
            path = directory / name
            if path.is_file() and path.stat().st_size > 1_000_000:
                return path
    return None


def normalize(text: str) -> str:
    return re.sub(r"\s+", " ", text.replace("\u00ad", "").replace("\ufb01", "fi")
                  .replace("\ufb02", "fl")).lower()


def front_text(doc: PdfTextDocument, pages: int = 26) -> str:
    chunks = []
    for page_no in range(1, min(pages, doc.page_count) + 1):
        try:
            chunks.extend(line.text for line in doc.lines(page_no, min_size=6.0))
        except Exception:  # noqa: BLE001 - one unreadable page must not abort
            continue
    return normalize(" ".join(chunks))


def table_ids(text: str, section: int) -> set[int]:
    pattern = re.compile(rf"table\s*{section}\s*[-\u2013]\s*(\d{{1,3}})")
    return {int(n) for n in pattern.findall(text)}


def validate(spec: dict, path: Path, reference_tables: set[str]) -> dict:
    version = spec["version"]
    raw = path.read_bytes()
    digest = hashlib.sha256(raw).hexdigest()
    check(f"CMIS {version} PDF is structurally complete",
          raw[:5] == b"%PDF-" and b"%%EOF" in raw[-4096:]
          and len(raw) > 1_000_000,
          f"{len(raw):,} bytes, sha256={digest[:16]}...")

    doc = PdfTextDocument(path)
    check(f"CMIS {version} PDF opens with the project's zero-dependency reader",
          doc.page_count > 200, f"{doc.page_count} pages")

    front = front_text(doc)
    check(f"CMIS {version} front matter is readable text, not an image scan",
          len(front) > 4000, f"{len(front)} normalized chars")

    revision_markers = (f"rev {version}", f"revision {version}",
                        f"cmis {version}", f"5.{version[-1]}")
    # "5.1"/"5.2" alone is too weak; require an explicit revision phrase or the
    # document identifier (OIF-CMIS-05.2 style).
    revision_ok = any(marker in front for marker in revision_markers[:3]) or \
        f"cmis-05.{version[-1]}" in front or f"cmis5p{version[-1]}" in front
    check(f"CMIS {version} front matter identifies revision {version}",
          revision_ok)

    matched = [term for term in CORE_TERMS if term in front]
    check(f"CMIS {version} table of contents covers the core normative concepts",
          len(matched) >= 6,
          f"{len(matched)}/{len(CORE_TERMS)}: {', '.join(matched)}")

    section8 = table_ids(front, 8)
    check(f"CMIS {version} enumerates Section 8 memory-map tables",
          len(section8) >= 20,
          f"{len(section8)} distinct Table 8-N ids, max={max(section8) if section8 else 0}")

    ref8 = {int(t.split("-")[1]) for t in reference_tables
            if t.startswith("8-") and t.split("-")[1].isdigit()}
    extra = sorted(section8 - ref8)
    check(f"CMIS {version} Section 8 table numbering is consistent with the 5.3 index",
          bool(section8) and len(extra) <= max(3, len(section8) // 10),
          f"{len(extra)} ids not present in the 5.3 index: {extra[:8]}")

    # Reader robustness: sample pages across the whole document.
    sampled = sorted({1, max(1, doc.page_count // 4), max(1, doc.page_count // 2),
                      max(1, 3 * doc.page_count // 4), doc.page_count,
                      7, 13, 41, 97, 151, 211, 301})
    readable = 0
    errors = []
    for page_no in sampled:
        if page_no > doc.page_count:
            continue
        try:
            if any(line.stripped for line in doc.lines(page_no, min_size=8.0)):
                readable += 1
        except Exception as exc:  # noqa: BLE001
            errors.append(f"p{page_no}:{type(exc).__name__}")
    check(f"CMIS {version} PDF text layer is readable across sampled pages",
          not errors and readable >= len(sampled) - 2,
          f"{readable} readable pages, errors={errors[:3]}")

    return {
        "version": version,
        "published": spec["published"],
        "file": path.name,
        "bytes": len(raw),
        "sha256": digest,
        "pdf_pages": doc.page_count,
        "front_matter_chars": len(front),
        "core_terms_matched": matched,
        "section8_table_ids": len(section8),
        "section8_max_table": max(section8) if section8 else 0,
        "section8_ids_not_in_53": extra,
        "sampled_pages_readable": readable,
        "sampled_pages": len([p for p in sampled if p <= doc.page_count]),
        "reader": "tools/spec_pdf.py (standard library only)",
    }


def main() -> int:
    index_path = ROOT / "data" / "spec_pdf_index.json"
    reference_tables: set[str] = set()
    if index_path.is_file():
        index = json.loads(index_path.read_text(encoding="utf-8"))
        reference_tables = {str(t.get("table_id")) for t in index.get("tables", [])}
    check("Local 5.3 spec-table index is available for cross-version comparison",
          len(reference_tables) > 100, f"{len(reference_tables)} tables")

    results = []
    for spec in SPECS:
        path = locate(spec)
        if path is None:
            skip(f"CMIS {version_label(spec)} cross-version validation",
                 f"manual PDF not found; download {spec['url']} into "
                 "spec_downloads/ (or set CMIS_LEGACY_SPEC_DIR)")
            continue
        print(f"\n--- CMIS {spec['version']}: {path} ---")
        try:
            results.append(validate(spec, path, reference_tables))
        except Exception as exc:  # noqa: BLE001 - report, do not crash the suite
            check(f"CMIS {spec['version']} validation completes",
                  False, f"{type(exc).__name__}: {exc}")

    if len(results) == 2:
        by_version = {r["version"]: r for r in results}
        v51, v52 = by_version["5.1"], by_version["5.2"]
        check("Section 8 table count grows monotonically 5.1 -> 5.2 -> 5.3",
              v51["section8_table_ids"] <= v52["section8_table_ids"] <= len(reference_tables),
              f"5.1={v51['section8_table_ids']} 5.2={v52['section8_table_ids']} "
              f"5.3={len(reference_tables)}")
        check("Both legacy revisions are readable by the same PDF reader",
              v51["sampled_pages_readable"] > 0 and v52["sampled_pages_readable"] > 0)

    report = os.environ.get("CMIS_LEGACY_REPORT")
    if report and results:
        Path(report).write_bytes(
            (json.dumps({"versions": results, "skipped": SKIP},
                        ensure_ascii=False, indent=2) + "\n").encode("utf-8"))
        print(f"\nWrote {report}")

    print(f"\n{len(PASS)} passed, {len(FAIL)} failed, {len(SKIP)} skipped")
    for name in FAIL:
        print(f"  FAILED: {name}")
    return 1 if FAIL else 0


def version_label(spec: dict) -> str:
    return spec["version"]


if __name__ == "__main__":
    raise SystemExit(main())
