#!/usr/bin/env python3
"""Regression checks for the zero-dependency spec-PDF parser and provenance layer.

Standard library only. Reads the bundled PDF in place (never modifies it) and
uses a temporary SQLite database so delivered data is untouched.

Usage: python tools/test_spec_pdf.py
"""

from __future__ import annotations

import hashlib
import json
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
for path in (str(HERE), str(ROOT)):
    if path not in sys.path:
        sys.path.insert(0, path)

from cmis53_rules import (  # noqa: E402
    OVERVIEW_TABLES, TEMPLATE_TABLES, cmd_ids_in, derive_conversion,
    masks_from_bits, page_from_title, parse_access_type, parse_byte_range,
    value_type_from_text,
)
from spec_pdf import PdfTextDocument  # noqa: E402
from cmis_service import api, db  # noqa: E402
from cmis_service.config import load_settings  # noqa: E402

PDF = ROOT / "knowledge" / "specs" / "OIF-CMIS-05.3.pdf"
INDEX = ROOT / "data" / "spec_pdf_index.json"
PASS, FAIL = [], []


def check(name: str, condition: bool, detail: str = "") -> None:
    (PASS if condition else FAIL).append(name)
    print(f"{'PASS' if condition else 'FAIL'}  {name}" + (f"  | {detail}" if detail else ""))


def rule_checks() -> None:
    check("parse_byte_range handles wrapped PDF ranges",
          parse_byte_range("129-130") == (129, 2) and parse_byte_range("14") == (14, 1))
    check("masks_from_bits covers whole bytes and sub-byte fields",
          masks_from_bits("7-0", 2)[0] == [255, 255]
          and masks_from_bits("3-0", 1)[0] == [15])
    check("parse_access_type decodes COR and requirement",
          parse_access_type("RO/COR Rqd.") == ("RO", "ClearOnRead", "Rqd"))
    check("page_from_title handles Lower Memory and Upper pages",
          page_from_title("Module Flags (Lower Memory)") == "Lwr"
          and page_from_title("CDB Command Data (Page 9Fh)") == "9Fh"
          and page_from_title("Byte 01h: Something") == "01h")
    check("value_type_from_text infers storage type",
          value_type_from_text("measured in U16 units", 16, 2) == "u16")
    conversion = derive_conversion("in 1/256 degree Celsius increments", "s16", 2)
    check("derive_conversion derives degC and 1/256 scale",
          conversion["unit"] == "degC" and abs(conversion["scale"] - 1 / 256) < 1e-12)
    check("cmd_ids_in splits compound command IDs",
          cmd_ids_in("0210h/0211h") == ["0210", "0211"])
    check("overview and template table rules are data, not conditionals",
          "8-4" in OVERVIEW_TABLES and "8-22" in TEMPLATE_TABLES
          and len(TEMPLATE_TABLES) == 9)


def reader_checks(doc: PdfTextDocument) -> None:
    check("reader parses the classic-xref PDF", doc.page_count == 408, str(doc.page_count))
    lines = doc.lines(147, min_size=8.0)
    check("reader rebuilds positioned text lines", len(lines) > 20, str(len(lines)))
    check("reader finds the Table 8-10 caption",
          any("Table 8-10 Module-Level Monitor" in line.text for line in lines))
    header = next((line for line in lines if "Byte" in line.text and "Type" in line.text), None)
    check("header row keeps per-column x coordinates",
          header is not None and len({round(s.x / 10) for s in header.spans}) >= 4)
    spans = doc.spans(147, min_size=0)
    check("small-font footnote spans can be filtered",
          len(spans) >= len([s for s in spans if s.size >= 8]))
    try:
        doc.spans(9999)
        out_of_range = False
    except IndexError:
        out_of_range = True
    check("out-of-range page raises IndexError", out_of_range)
    other = PdfTextDocument(ROOT / "knowledge" / "specs" / "OIF-CMIS-05.4.pdf")
    check("reader also handles CMIS 5.4", other.page_count > 400, str(other.page_count))


def index_checks() -> dict:
    if not INDEX.is_file():
        check("spec index exists", False, "run tools/parse_spec_pdf.py")
        return {}
    data = json.loads(INDEX.read_text(encoding="utf-8"))
    meta, stats, verify = data["meta"], data["stats"], data["verification"]
    check("index exists and records the PDF checksum",
          meta["pdf_sha256"] == hashlib.sha256(PDF.read_bytes()).hexdigest())
    check("index discovers all 238 tables from the TOC",
          stats["tables"] == 238 and stats["section_8_tables"] == 181
          and stats["section_9_tables"] == 57, str(stats["tables"]))
    check("every table has a PDF page number",
          all(isinstance(t.get("pdf_page"), int) for t in data["tables"]))
    check("no verbatim OIF description text is persisted",
          all("description" not in f and "desc" not in f for f in data["fields"]))
    check("all 48 CDB commands are resolved", stats["cdb_commands"] == 48)
    check("verification resolves every cited table",
          verify["available"] and verify["table_provenance"]["tables_resolved_to_pdf_page"]
          == verify["table_provenance"]["tables_in_reference"],
          f"{verify['table_provenance']['tables_resolved_to_pdf_page']}/"
          f"{verify['table_provenance']['tables_in_reference']}")
    check("verification matches all 48 CDB commands",
          verify["cdb_commands"]["matched"] == verify["cdb_commands"]["reference"] == 48)
    check("coordinate extraction match rate is above 90%", verify["match_rate"] > 0.9,
          str(verify["match_rate"]))
    return data


def api_checks() -> None:
    tmp = Path(tempfile.mkdtemp(prefix="cmiscope-spec-test-")) / "cmis.db"
    settings = load_settings(environ={"CMIS_DB_FILE": str(tmp)})
    conn = db.initialize(settings)

    def call(path: str, query: dict | None = None):
        return api.dispatch(conn, settings, "GET", path, query or {}, None)

    count = conn.execute("SELECT COUNT(*) FROM cmis53_spec_tables").fetchone()[0]
    check("spec tables are imported into SQLite", count == 238, str(count))

    status, payload = call("/api/reference/spec-tables", {"limit": ["5"]})
    tables = payload.get("data", {})
    check("spec-tables endpoint is paginated",
          status == 200 and tables.get("total") == 238 and len(tables.get("items", [])) == 5)

    status, payload = call("/api/reference/spec-tables", {"section": ["9"]})
    check("section filter returns the 57 Section 9 tables",
          status == 200 and payload["data"]["total"] == 57)

    status, payload = call("/api/reference/spec-tables/8-10")
    detail = payload.get("data", {})
    check("table detail resolves fields and PDF page",
          status == 200 and detail.get("table", {}).get("pdf_page") == 147
          and detail.get("total", 0) > 0, str(detail.get("total")))

    status, payload = call("/api/reference/spec-tables/8-9999")
    check("unknown table returns 404 with English code",
          status == 404 and payload["error"]["code"] == "SPEC_TABLE_NOT_FOUND")

    status, payload = call("/api/reference/verify")
    check("verify endpoint exposes the cross-check",
          status == 200 and payload["data"]["available"]
          and payload["data"]["verification"]["match_rate"] > 0.9)

    status, payload = call("/api/reference/fields/TempMonValue")
    sources = payload.get("data", {}).get("spec_sources", [])
    check("field detail carries specification provenance",
          status == 200 and len(sources) == 1 and sources[0]["pdf_page"] == 147)

    status, payload = call("/api/reference/cdb-commands")
    items = payload.get("data", {}).get("items", [])
    check("all CDB commands carry a PDF page",
          status == 200 and len(items) == 48
          and all(i.get("spec_pdf_page") for i in items))

    status, payload = call("/api/reference/meta")
    meta = payload.get("data", {})
    check("meta exposes PDF provenance and verification keys",
          status == 200 and "spec_pdf_meta" in meta and "spec_verification" in meta
          and meta["spec_pdf_meta"].get("reader", "").startswith("tools/spec_pdf.py"))

    status, payload = call("/api/fields")
    check("original 64 demo fields are unchanged",
          status == 200 and payload["data"]["total"] == 64)


def _synthetic_pdf(linearized: bool) -> bytes:
    """Build a tiny 2-page PDF. In linearized form the only /Root sits in the
    first trailer at the front of the file, with /Prev pointing at the main
    xref table - the layout used by the published CMIS 5.1 document.
    """
    objects = {
        1: b"<< /Type /Catalog /Pages 2 0 R >>",
        2: b"<< /Type /Pages /Kids [3 0 R 4 0 R] /Count 2 >>",
        3: b"<< /Type /Page /Parent 2 0 R /Contents 5 0 R /MediaBox [0 0 612 792] >>",
        4: b"<< /Type /Page /Parent 2 0 R /Contents 6 0 R /MediaBox [0 0 612 792] >>",
        5: b"<< /Length 0 >>\nstream\n\nendstream",
        6: b"<< /Length 0 >>\nstream\n\nendstream",
    }
    header = b"%PDF-1.7\n"
    first_xref = (
        b"xref\n1 1\n0000000000 00000 n \n"
        b"trailer\n<< /Size 7 /Root 1 0 R /Prev 0000000000 >>\n"
        b"startxref\n0\n%%EOF\n"
    ) if linearized else b""
    first_xref_pos = len(header)
    body = bytearray(header + first_xref)
    offsets: dict[int, int] = {}
    for number in sorted(objects):
        offsets[number] = len(body)
        body += f"{number} 0 obj\n".encode() + objects[number] + b"\nendobj\n"
    main_xref_pos = len(body)
    body += b"xref\n0 7\n0000000000 65535 f \n"
    for number in range(1, 7):
        body += f"{offsets[number]:010d} 00000 n \n".encode()
    trailer = b"<< /Size 7 >>" if linearized else b"<< /Size 7 /Root 1 0 R >>"
    body += b"trailer\n" + trailer + b"\n"
    if linearized:
        # Both placeholders are fixed-width, so the offsets stay valid.
        entry = body.find(b"0000000000 00000 n", first_xref_pos)
        body[entry:entry + 18] = f"{offsets[1]:010d} 00000 n".encode()
        prev = body.find(b"/Prev 0000000000", first_xref_pos)
        body[prev + 6:prev + 16] = f"{main_xref_pos:010d}".encode()
        start = first_xref_pos
    else:
        start = main_xref_pos
    body += f"startxref\n{start}\n%%EOF\n".encode()
    return bytes(body)


def linearized_pdf_checks() -> None:
    """Regression for /Root discovery in linearized (fast web view) PDFs."""
    with tempfile.TemporaryDirectory(prefix="cmiscope-linear-") as name:
        directory = Path(name)
        plain_path = directory / "plain.pdf"
        linear_path = directory / "linearized.pdf"
        plain_path.write_bytes(_synthetic_pdf(False))
        linear_path.write_bytes(_synthetic_pdf(True))

        plain = PdfTextDocument(plain_path)
        check("Classic single-xref PDF still resolves its page tree",
              plain.page_count == 2 and plain._root_ref == 1,
              f"pages={plain.page_count} root={plain._root_ref}")

        linear = PdfTextDocument(linear_path)
        check("Linearized PDF finds /Root in the first trailer",
              linear._root_ref == 1, f"root={linear._root_ref}")
        check("Linearized PDF flattens both pages, not just the first one",
              linear.page_count == 2, f"pages={linear.page_count}")
        check("Linearized PDF walks /Prev into the main xref table",
              len(linear._offsets) >= 6, f"objects={len(linear._offsets)}")
        check("Linearized PDF reads text from a later page",
              all(linear.lines(page, min_size=0.0) is not None
                  for page in (1, 2)))


def main() -> int:
    if not PDF.is_file():
        print(f"ERROR: bundled specification is missing: {PDF}")
        return 1
    rule_checks()
    reader_checks(PdfTextDocument(PDF))
    linearized_pdf_checks()
    index_checks()
    api_checks()
    print(f"\n{len(PASS)} passed, {len(FAIL)} failed")
    for name in FAIL:
        print(f"  FAILED: {name}")
    return 1 if FAIL else 0


if __name__ == "__main__":
    raise SystemExit(main())
