#!/usr/bin/env python3
"""Parse the bundled OIF CMIS specification PDF into a provenance index.

This is CMIScope's zero-dependency specification extraction pipeline:

  * Table columns are rebuilt from positioned text runs of each header row by
    ``tools/spec_pdf.py`` (standard library only, no third-party PDF library).
  * The Section 8/9 page range is discovered from the document's own table of
    contents and body captions instead of hardcoded page numbers.
  * Normalization rules live in ``tools/cmis53_rules.py`` and are shared with
    the reference builder, so PDF rows and normalized dataset rows go through
    identical logic.
  * Paths are injected, every malformed row is reported rather than aborting,
    and the output carries provenance (file hash, page numbers, caveats).
  * Only factual identifiers are persisted (table numbers, short captions,
    page numbers, field names, addresses, access types).  Verbatim OIF
    description text is used in memory for unit derivation and is NOT written
    to the index.  See NOTICE and knowledge/specs/README.md.

Usage:
    python tools/parse_spec_pdf.py
    python tools/parse_spec_pdf.py --pdf knowledge/specs/OIF-CMIS-05.4.pdf \
        --out data/spec_pdf_54_index.json --no-reference
    python tools/parse_spec_pdf.py --reference data/cmis53_reference.json

The generated index is consumed by ``tools/import_cmis53.py``, which attaches
PDF page numbers to the read-only reference layer exposed at /api/reference/*.
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
    CMD_SECTION_RE, CMD_TITLE_RE, HEADER_ALIASES, OVERVIEW_TABLES, TABLE_TITLE,
    TEMPLATE_TABLES, classify_section, clean_cell, cmd_ids_in, derive_conversion,
    masks_from_bits, page_from_title, parse_access_type, parse_byte_range,
    value_type_from_text,
)
from spec_pdf import Line, PdfTextDocument  # noqa: E402

DEFAULT_PDF = ROOT / "knowledge" / "specs" / "OIF-CMIS-05.3.pdf"
DEFAULT_OUT = ROOT / "data" / "spec_pdf_index.json"
DEFAULT_REFERENCE = ROOT / "data" / "cmis53_reference.json"

_TOC_LINE = re.compile(r"^\s*Table\s+([89]-\d+)\s+(.*?)(\d{2,3})\s*$", re.I)
_SECTION_HEADING = re.compile(r"^\s*\d+\.\d+(?:\.\d+)?\s+[A-Z]")
_LANE_TOKEN = re.compile(r"<[ni]>", re.I)
_REFERENCE_ONLY_ROW = re.compile(r"^\s*[0-9A-F]{4}h\s+\S", re.I)


# --------------------------------------------------------------------------- column layout

def column_layout(line: Line) -> dict[str, tuple[float, float]] | None:
    """Derive logical column x-ranges from a table header row.

    Word emits each header cell as one or more positioned text runs.  Mapping
    header characters back to their x coordinate lets us find the start of
    Byte / Bit / Name / Description / Type without a table-grid library.
    """
    text = line.text
    if not re.search(r"\b(Bytes?|Address)\b", text, re.I):
        return None
    buffer: list[str] = []
    char_x: list[float] = []
    for span in line.spans:
        for char in span.text:
            buffer.append(char)
            char_x.append(span.x)
    if not buffer:
        return None
    joined = "".join(buffer)
    found: dict[str, float] = {}
    for key, aliases in HEADER_ALIASES:
        for alias in aliases:
            match = re.search(re.escape(alias), joined, re.I)
            if match:
                found[key] = char_x[match.start()]
                break
    if "byte" not in found or len(found) < 2:
        return None
    ordered = sorted((x, key) for key, x in found.items())
    layout: dict[str, tuple[float, float]] = {}
    for index, (x, key) in enumerate(ordered):
        upper = ordered[index + 1][0] if index + 1 < len(ordered) else 620.0
        layout[key] = (x - 6.0, upper - 6.0)
    return layout


def split_cells(line: Line, layout: dict[str, tuple[float, float]]) -> dict[str, str]:
    """Assign every text run of a row to the column that contains its x."""
    buckets: dict[str, list] = {key: [] for key in layout}
    for span in line.spans:
        for key, (low, high) in layout.items():
            if low <= span.x < high:
                buckets[key].append(span)
                break
    return {key: "".join(s.text for s in sorted(value, key=lambda item: item.x))
            for key, value in buckets.items()}


# --------------------------------------------------------------------------- row normalization

def _clean_name(text: str | None) -> str:
    tokens = (text or "").split()
    if len(tokens) > 1 and re.fullmatch(r"[a-z]", tokens[-1]):
        tokens = tokens[:-1]  # trailing math symbol, e.g. "...Exponent e"
    joined = "".join(tokens)
    if not joined.lower().startswith("reserved"):
        joined = re.sub(r"\[\d+\]$", "", joined)
    if joined in ("", "-"):
        return "Reserved"
    if joined.lower().startswith("reserved"):
        return "Reserved"
    return joined


def finalize_row(pending: dict, table: dict, pdf_page: int) -> list[dict]:
    """Turn one extracted table row (plus continuation text) into field rows."""
    parsed = parse_byte_range(pending["byte"])
    # The normalized dataset drops rows whose page cannot be derived from the
    # caption and reports them as issues; do the same rather than emitting
    # location-less records that can never be cross-referenced.
    if not parsed or not table.get("page"):
        return []
    start, nbytes = parsed
    bits = re.sub(r"\s+", "", pending.get("bits") or "")
    masks, width, _ = masks_from_bits(bits, nbytes)
    name = pending["name"]
    description = clean_cell(pending.get("desc")) or ""
    access, behavior, requirement = parse_access_type(pending.get("type"))
    if not access and table["table_id"] == "8-129":
        access, behavior = "RO", "Normal"  # diagnostics data table has no Type column
    value_type = None if name == "Reserved" else value_type_from_text(
        description, width, nbytes if width < 8 or nbytes > 1 else 1)
    conversion = ({} if name == "Reserved" else
                  derive_conversion(description, value_type, nbytes, name))

    base = {
        "table_id": table["table_id"],
        "pdf_page": pdf_page,
        "page": table["page"],
        "is_overview": 1 if table["table_id"] in OVERVIEW_TABLES else 0,
        "section": classify_section(table["page"], start) if table["page"] else None,
        "name": name,
        "byte": start,
        "byte_length": nbytes,
        "bits": bits or None,
        "mask_values": masks,
        "access": access,
        "behavior": behavior,
        "requirement": None if name == "Reserved" else requirement,
        "value_type": value_type,
        "unit": conversion.get("unit"),
        "scale": conversion.get("scale"),
        "byte_order": conversion.get("byte_order"),
        "is_reserved": 1 if name == "Reserved" else 0,
    }
    lane = _LANE_TOKEN.search(name)
    if lane and nbytes % 8 == 0 and nbytes >= 8:
        step = nbytes // 8
        return [dict(base, name=name.replace(lane.group(0), str(i + 1)),
                     byte=start + i * step, byte_length=step,
                     mask_values=masks[:step]) for i in range(8)]
    if lane and nbytes == 1 and masks == [0xFF]:
        return [dict(base, name=name.replace(lane.group(0), str(i + 1)),
                     mask_values=[1 << i], value_type="bool") for i in range(8)]
    return [base]


# --------------------------------------------------------------------------- document scan

def discover_tables(doc: PdfTextDocument) -> tuple[dict[str, dict], list[int], int]:
    """Find the TOC and all Section 8/9 table captions in the body."""
    table_titles: dict[str, dict] = {}
    toc_pages: list[int] = []
    body_first: dict[str, int] = {}
    for page_no in range(1, doc.page_count + 1):
        lines = doc.lines(page_no, min_size=8.0)
        candidates = [ln.stripped for ln in lines if TABLE_TITLE.match(ln.stripped)]
        if page_no <= 60 and len(candidates) >= 5:
            toc_pages.append(page_no)
            for text in candidates:
                match = _TOC_LINE.match(text)
                if match:
                    table_id, title, printed = (match.group(1), match.group(2).strip(),
                                                int(match.group(3)))
                    table_titles.setdefault(table_id, {
                        "table_id": table_id,
                        "section": int(table_id.split("-")[0]),
                        "title": title,
                        "pdf_page": printed,
                        "printed_page": printed,
                        "source": "toc",
                    })
            continue
        for line in lines:
            text = line.stripped
            match = TABLE_TITLE.match(text)
            if not match or len(match.group(3)) < 12 or text.rstrip().endswith("."):
                continue
            if re.search(r"\bsee\b", text, re.I):
                continue
            table_id = f"{match.group(1)}-{match.group(2)}"
            body_first.setdefault(table_id, page_no)
            entry = table_titles.get(table_id)
            if entry is None:
                table_titles[table_id] = {
                    "table_id": table_id,
                    "section": int(match.group(1)),
                    "title": match.group(3).strip(),
                    "pdf_page": page_no,
                    "printed_page": None,
                    "source": "body",
                }
            elif entry.get("source") == "toc" and entry["pdf_page"] != page_no:
                # TOC page numbers are the printed page; body captions are the
                # physical page. Keep both when they differ.
                entry["body_page"] = page_no
    for table_id, page_no in body_first.items():
        table_titles[table_id].setdefault("body_page", page_no)
    for entry in table_titles.values():
        entry["page"] = page_from_title(entry["title"])
    # The TOC page numbers are authoritative for the start of Section 8.
    # Body "see Table 8-N" references must not drag the scan back to page 7.
    section8_pages = [entry["pdf_page"] for entry in table_titles.values()
                      if entry["section"] == 8 and entry["pdf_page"] > 60]
    first_page = min(section8_pages) if section8_pages else (
        min(body_first.values()) if body_first else 1)
    return table_titles, toc_pages, first_page


def extract_fields(doc: PdfTextDocument, tables: dict[str, dict],
                   first_page: int, last_page: int) -> tuple[list[dict], list[dict], int]:
    """Walk the table region and extract best-effort field rows by column x."""
    fields: list[dict] = []
    issues: list[dict] = []
    template_rows = 0
    current: dict | None = None
    layout: dict[str, tuple[float, float]] | None = None
    pending: dict | None = None

    def flush(page_no: int) -> None:
        nonlocal pending
        if pending is not None and current is not None:
            rows = finalize_row(pending, current, page_no)
            if rows:
                fields.extend(rows)
            else:
                issues.append({"table_id": current["table_id"], "pdf_page": page_no,
                               "reason": "page not determined from caption"})
        pending = None

    stop = min(last_page, doc.page_count)
    for page_no in range(max(1, first_page - 1), stop + 1):
        for line in doc.lines(page_no, min_size=8.0):
            text = line.stripped
            match = TABLE_TITLE.match(text)
            if (match and len(match.group(3)) >= 12 and not text.rstrip().endswith(".")
                    and not re.search(r"\bsee\b", text, re.I)):
                flush(page_no)
                table_id = f"{match.group(1)}-{match.group(2)}"
                entry = tables.get(table_id)
                if entry is None:
                    entry = {"table_id": table_id, "section": int(match.group(1)),
                             "title": match.group(3).strip(), "pdf_page": page_no,
                             "page": page_from_title(match.group(3))}
                    tables[table_id] = entry
                current = dict(entry, pdf_page=page_no)
                layout = None
                continue
            if current is None:
                continue
            header = column_layout(line)
            if header:
                flush(page_no)
                layout = header
                continue
            if layout is None:
                continue
            cells = split_cells(line, layout)
            byte_text = re.sub(r"\s+", "", cells.get("byte") or "")
            if parse_byte_range(byte_text):
                flush(page_no)
                if current["table_id"] in TEMPLATE_TABLES:
                    template_rows += 1
                    pending = None
                    continue
                pending = {
                    "byte": byte_text,
                    "bits": cells.get("bits") or "",
                    "name": _clean_name(cells.get("name")),
                    "type": cells.get("type") or "",
                    "desc": cells.get("desc") or "",
                }
                continue
            if pending is not None:
                # Description text wrapped onto another visual line.
                extra = (cells.get("desc") or "").strip()
                if extra and not (cells.get("bits") or "").strip() \
                        and not (cells.get("name") or "").strip():
                    pending["desc"] = (pending["desc"] + " " + extra).strip()
        # A page break resets the column geometry but keeps the table context.
        flush(page_no)
        layout = None
    return fields, issues, template_rows


def extract_cdb_commands(doc: PdfTextDocument, first_page: int,
                         last_page: int) -> list[dict]:
    """Collect Section 9 command IDs from captions, headings and overview rows."""
    commands: dict[str, dict] = {}
    stop = min(last_page, doc.page_count)
    for page_no in range(max(1, first_page - 1), stop + 1):
        for line in doc.lines(page_no, min_size=8.0):
            text = line.stripped
            for match in CMD_TITLE_RE.finditer(text):
                for cmd_id in cmd_ids_in(match.group(1)):
                    entry = commands.setdefault(cmd_id, {
                        "cmd_id": cmd_id, "title": None, "spec_section": None,
                        "detail_table": None, "pdf_page": page_no,
                    })
                    entry["detail_table"] = re.search(
                        r"Table\s+(9-\d+)", match.group(0), re.I).group(1) \
                        if re.search(r"Table\s+(9-\d+)", match.group(0), re.I) else None
                    if entry["title"] is None:
                        entry["title"] = match.group(2).strip()[:160]
            for match in CMD_SECTION_RE.finditer(text):
                for cmd_id in cmd_ids_in(match.group(2)):
                    entry = commands.setdefault(cmd_id, {
                        "cmd_id": cmd_id, "title": None, "spec_section": None,
                        "detail_table": None, "pdf_page": page_no,
                    })
                    entry["spec_section"] = entry["spec_section"] or match.group(1)
            if _REFERENCE_ONLY_ROW.match(text) and len(text.split()) >= 3:
                parts = text.split()
                cmd_id = parts[0].rstrip("hH").upper()
                if re.fullmatch(r"[0-9A-F]{4}", cmd_id) and cmd_id in commands:
                    entry = commands[cmd_id]
                    if not entry["title"] or entry["title"].startswith("-"):
                        entry["title"] = " ".join(parts[1:4])[:160]
    # 4-hex-digit values also occur in status/error-code tables. A real command
    # always has a Section 9 clause or a detail table, so drop those stray rows
    # (the normalized dataset likewise omits reserved IDs).
    return sorted((item for item in commands.values()
                   if item.get("spec_section") or item.get("detail_table")),
                  key=lambda item: item["cmd_id"])


# --------------------------------------------------------------------------- verification

def verify_against_reference(fields: list[dict], tables: dict[str, dict],
                             commands: list[dict], reference_path: Path) -> dict:
    """Cross-check PDF-extracted rows against the normalized reference dataset."""
    if not reference_path.is_file():
        return {"available": False, "hint": f"missing {reference_path.name}"}
    data = json.loads(reference_path.read_text(encoding="utf-8"))
    reference = data.get("fields", [])
    keys = {(row.get("page"), row.get("byte"), row.get("name")) for row in reference}
    # Overview rows duplicate detail tables and use descriptive labels rather
    # than register names, so they are reported separately.
    detail_rows = [row for row in fields if not row.get("is_overview")]
    matched = [row for row in detail_rows
               if (row.get("page"), row.get("byte"), row.get("name")) in keys]
    unmatched = [row for row in detail_rows
                 if (row.get("page"), row.get("byte"), row.get("name")) not in keys]

    unit_by_key = {(row.get("page"), row.get("byte"), row.get("name")): row
                   for row in reference}
    unit_checked = unit_agree = scale_agree = 0
    for row in matched:
        expected = unit_by_key[(row["page"], row["byte"], row["name"])]
        if row.get("unit") is not None or expected.get("unit"):
            unit_checked += 1
            if (row.get("unit") or "") == (expected.get("unit") or ""):
                unit_agree += 1
        if row.get("scale") is not None or expected.get("scale") is not None:
            if row.get("scale") is not None and expected.get("scale") is not None \
                    and abs(float(row["scale"]) - float(expected["scale"])) < 1e-9:
                scale_agree += 1

    # A reference row may cite several source tables, e.g. "8-28; 8-30".
    ref_tables: Counter = Counter()
    for row in reference:
        for token in re.split(r"[;,\s]+", str(row.get("ref_table") or "")):
            if token:
                ref_tables[token] += 1
    resolved = {t: tables.get(t, {}).get("pdf_page") for t in ref_tables}
    ref_cmds = {str(row.get("cmd_id") or "").upper() for row in data.get("cdb_commands", [])}
    pdf_cmds = {row["cmd_id"] for row in commands}

    try:
        ref_display = str(reference_path.relative_to(ROOT)).replace("\\", "/")
    except ValueError:
        ref_display = str(reference_path)
    return {
        "available": True,
        "reference_file": ref_display,
        "reference_fields": len(reference),
        "pdf_field_rows": len(fields),
        "detail_rows": len(detail_rows),
        "overview_rows": len(fields) - len(detail_rows),
        "matched_rows": len(matched),
        "match_rate": round(len(matched) / len(detail_rows), 4) if detail_rows else 0.0,
        "unmatched_rows": len(unmatched),
        "unmatched_samples": [
            {"table_id": r["table_id"], "page": r["page"], "byte": r["byte"],
             "name": r["name"]} for r in unmatched[:8]
        ],
        "table_provenance": {
            "tables_in_reference": len([t for t in ref_tables if t]),
            "tables_resolved_to_pdf_page": len([t for t, p in resolved.items() if t and p]),
            "unresolved_tables": [t for t, p in sorted(resolved.items()) if t and not p][:10],
        },
        "cdb_commands": {
            "reference": len(ref_cmds), "pdf": len(pdf_cmds),
            "matched": len(ref_cmds & pdf_cmds),
            "pdf_only": sorted(pdf_cmds - ref_cmds)[:8],
        },
        "derived_conversion_check": {
            "unit_pairs_compared": unit_checked,
            "unit_agreement": unit_agree,
            "scale_agreement": scale_agree,
        },
        "caveat": ("PDF rows are a best-effort coordinate reconstruction; the normalized "
                   "reference dataset remains authoritative for field data. Only factual "
                   "identifiers are stored."),
    }


# --------------------------------------------------------------------------- entry point

def build(pdf_path: Path, reference_path: Path | None) -> dict:
    doc = PdfTextDocument(pdf_path)
    tables, toc_pages, first_page = discover_tables(doc)
    last_page = min(doc.page_count,
                    max((entry.get("body_page") or entry["pdf_page"])
                        for entry in tables.values()) + 3) if tables else doc.page_count
    last_page = max(last_page, first_page)
    fields, issues, template_rows = extract_fields(doc, tables, first_page, last_page)
    commands = extract_cdb_commands(doc,
                                    first_page=max(first_page, last_page - 80),
                                    last_page=last_page)
    for entry in tables.values():
        entry["field_rows"] = sum(1 for row in fields if row["table_id"] == entry["table_id"])
    verification = (verify_against_reference(fields, tables, commands, reference_path)
                    if reference_path else {"available": False, "hint": "--no-reference"})

    label = re.search(r"CMIS-(\d+\.\d+)", pdf_path.name, re.I)
    return {
        "meta": {
            "generator": "tools/parse_spec_pdf.py",
            "schema_version": "1.0",
            "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "specification": f"OIF-CMIS-{label.group(1)}" if label else pdf_path.stem,
            "pdf_file": str(pdf_path.relative_to(ROOT)).replace("\\", "/")
            if pdf_path.is_relative_to(ROOT) else str(pdf_path),
            "pdf_sha256": hashlib.sha256(pdf_path.read_bytes()).hexdigest(),
            "pdf_bytes": pdf_path.stat().st_size,
            "pdf_pages": doc.page_count,
            "toc_pages": toc_pages,
            "scanned_pages": [max(1, first_page - 1), last_page],
            "reader": "tools/spec_pdf.py (Python standard library only)",
            "extraction": "coordinate-based best-effort; no pdfplumber/openpyxl dependency",
            "content_policy": ("Verbatim OIF description text is not persisted. Table "
                               "captions, field names and addresses are factual "
                               "identifiers used for cross-referencing only."),
            "authority_note": ("The OIF specification is authoritative; this index "
                               "is a navigation aid, not a compliance statement."),
        },
        "stats": {
            "tables": len(tables),
            "section_8_tables": sum(1 for t in tables.values() if t["section"] == 8),
            "section_9_tables": sum(1 for t in tables.values() if t["section"] == 9),
            "field_rows": len(fields),
            "cdb_commands": len(commands),
            "reserved_rows": sum(r["is_reserved"] for r in fields),
            "overview_rows": sum(r["is_overview"] for r in fields),
            "template_rows_skipped": template_rows,
            "by_section": dict(sorted(Counter(str(r["section"]) for r in fields).items())),
            "rows_without_page": len(issues),
        },
        "tables": sorted(tables.values(), key=lambda t: (t["section"], int(t["table_id"].split("-")[1]))),
        "fields": fields,
        "cdb_commands": commands,
        "verification": verification,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--pdf", type=Path, default=DEFAULT_PDF,
                        help=f"specification PDF (default: {DEFAULT_PDF})")
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT,
                        help=f"output JSON (default: {DEFAULT_OUT})")
    parser.add_argument("--reference", type=Path, default=DEFAULT_REFERENCE,
                        help=f"reference JSON for verification (default: {DEFAULT_REFERENCE})")
    parser.add_argument("--no-reference", action="store_true",
                        help="skip the cross-check against the reference JSON")
    args = parser.parse_args()

    pdf = args.pdf if args.pdf.is_absolute() else (ROOT / args.pdf)
    out = args.out if args.out.is_absolute() else (ROOT / args.out)
    reference = None if args.no_reference else (
        args.reference if args.reference.is_absolute() else (ROOT / args.reference))
    if not pdf.is_file():
        print(f"ERROR: specification PDF not found: {pdf}", file=sys.stderr)
        return 1

    payload = build(pdf.resolve(), reference.resolve() if reference else None)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_bytes((json.dumps(payload, ensure_ascii=False, indent=2) + "\n").encode("utf-8"))

    stats, verify = payload["stats"], payload["verification"]
    print(f"Wrote {out} ({out.stat().st_size:,} bytes)")
    print(f"  PDF pages={payload['meta']['pdf_pages']} scanned={payload['meta']['scanned_pages']} "
          f"TOC={payload['meta']['toc_pages']}")
    print(f"  tables={stats['tables']} (8-x={stats['section_8_tables']}, "
          f"9-x={stats['section_9_tables']}) field_rows={stats['field_rows']} "
          f"cdb_commands={stats['cdb_commands']}")
    if verify.get("available"):
        print(f"  verification: matched={verify['matched_rows']}/{verify['detail_rows']} "
              f"({verify['match_rate']:.1%}) tables_resolved="
              f"{verify['table_provenance']['tables_resolved_to_pdf_page']}/"
              f"{verify['table_provenance']['tables_in_reference']} "
              f"cmd_matched={verify['cdb_commands']['matched']}/{verify['cdb_commands']['reference']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
