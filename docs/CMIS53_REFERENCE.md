# CMIS 5.3 Field Reference (read-only)

This document describes the integration of the field-level CMIS 5.3 map from
[jimfred/CMIS](https://github.com/jimfred/CMIS) into CMIScope.

## 1. Design decision

The upstream data has **2442 field rows** (21 columns) and **48 CDB commands**.
CMIScope's operational model has 64 synthetic `fields` and 512 `config_items`
with `UNIQUE(device_id, field_key)`, a foreign key, editable values with
optimistic locking, and a fixed `LIMIT 300` on `/api/fields`.

Merging 2442 authoritative rows into that model would have produced roughly
19,500 configuration items, broken `tools/smoke_test.py` (which asserts 64
fields), changed the meaning of `data_nature: synthetic-demo`, and made
specification text appear as writable device state. It would also have been
overwritten the next time `tools/build_seed.py` runs.

Therefore the reference data is a **separate, isolated, read-only layer**:

```
knowledge/specs/OIF-CMIS-05.3.pdf   (bundled offline copy, (c) OIF)
        |
        |  python tools/parse_spec_pdf.py       (standard library only)
        |    -> tools/spec_pdf.py              (xref / FlateDecode / positioned text)
        |    -> tools/cmis53_rules.py          (shared normalization rules)
        v
data/spec_pdf_index.json            (table + field provenance, PDF checksum, verification)
        |
        +----------------------------+
                                     |
data/upstream/*.csv                  |   (unmodified upstream assets, MIT + OIF + Apache-2.0)
        |                           |
        |  python tools/import_cmis53.py <-------+   (merges both sources)
        |    -> tools/cmis53_rules.py          (page/mask/type/section normalization)
        v
data/cmis53_reference.json          (portable UTF-8/LF, SHA-256 of every input)
        |
        |  db.initialize() -> _import_reference()  (DELETE + reinsert on each start)
        v
cmis53_fields / cmis53_cdb_commands / cmis53_meta / cmis53_spec_tables
        |                                    (no foreign keys, no writes)
        v
GET /api/reference/*               (paginated, read-only)
```

Nothing in `cmis_spec.py`, `cmis_catalog.py`, `seed.json`, `validation.py` or
`config_items` was modified. `/api/fields` still returns 64 rows.

## 2. Provenance and license boundaries

This is a **mixed** dataset; do not relicense it as a whole.

| Content | Terms |
| --- | --- |
| Scripts, normalization, Key IDs, workbook structure, column definitions, unit/scale/conversion columns, `corrections.csv`, SONiC cross-check columns | MIT, Copyright (c) 2026 Jim Frederick. Full text preserved at `data/upstream/LICENSE` |
| `CMIS Name`, `Page`, `Byte`, `Byte Length`, `Mask Bytes`, `Access`, `Behavior`, `Requirement`, `Reference Table` / `Reference Section`, verbatim `Description` | Derived from *OIF-CMIS-05.3* (4 Sept 2024), (c) Optical Internetworking Forum, <https://www.oiforum.com/>. **Not MIT**; subject to OIF terms |
| `SONiC Cross-check`, `SONiC Field` | Derived from `sonic-net/sonic-platform-common`, Apache-2.0, at a pinned commit. Comparison result only, not a compliance claim |

The OIF specification is authoritative. A local copy is bundled at
`knowledge/specs/OIF-CMIS-05.3.pdf`. Verify timing- or safety-critical details
against it before any hardware use. See `NOTICE` sections 5-7.

## 3. What was optimized from the upstream code

The upstream repository contains a rebuild chain that requires `pdfplumber`,
`openpyxl`, the OIF PDF and a `git clone` of SONiC. The third-party libraries,
the XLSX writer and the SONiC clone are **not** brought into CMIScope, which
must stay zero-dependency and portable. The PDF parsing *ability*, however, is
re-implemented with the standard library (section 7), so the bundled spec can
be read without installing anything.

Instead, `tools/cmis53_rules.py` extracts the reusable domain logic and fixes
the problems found in the upstream scripts:

- **De-duplication.** Page normalization and mask parsing were each implemented
  four times (`extract_memory_map.page_of`, `normalize_memory_map.bank_scope`,
  `rebuild_memory_map.page_cell/page_key`, `update_param_reference.masks_of`).
  They are now single functions: `parse_page()` and `parse_masks()`.
- **Explicit encoding.** Upstream `open()` calls relied on the process locale,
  which breaks on Windows with `degC` / `µV` / quoted description text. All I/O
  here uses `encoding="utf-8-sig"` and `newline=""`.
- **Injected paths, no hard-coded PDF page ranges.** The importer takes
  `--source` / `--out`; the PDF parser discovers the Section 8/9 range from
  the document's own table of contents instead of upstream's fixed 120..290.
  Paths resolve relative to the project root so the whole directory stays
  movable. Upstream's table blacklists are retained as auditable data
  (`OVERVIEW_TABLES`, `TEMPLATE_TABLES`) instead of scattered conditionals.
- **One normalization path for CSV and PDF.** `parse_byte_range()`,
  `masks_from_bits()`, `parse_access_type()`, `page_from_title()`,
  `value_type_from_text()` and `derive_conversion()` replace the logic
  duplicated across `normalize_memory_map.py` and `conversions.py`. Both
  sources now normalize through the same functions, so their rows can be
  compared directly.
- **Error handling.** Missing columns, duplicate keys and malformed numeric or
  mask values are reported or ignored per row rather than aborting via
  `SystemExit`. `key_ids()` upstream raised on collision; here uniqueness is
  validated with a clear message.
- **No `group` SQL keyword.** The CDB `Group` column is renamed `cmd_group`,
  avoiding a reserved-word collision in SQLite.
- **Auditable section mapping.** The page-to-section rules live in
  `SECTION_RULES` / `VDM_PAGES` / `CDB_PAGES` and are serialized into the
  generated JSON, instead of being scattered conditionals.
- **Reproducible output.** `write_bytes(...encode("utf-8"))` keeps LF endings;
  `meta.source_assets` records SHA-256 and byte size of every input.

The generated JSON also carries the 21 column meanings (`field_columns`) and
9 CDB column meanings (`cdb_columns`) so the schema is self-documenting.

## 4. Schema

### `cmis53_fields` (2442 rows)

Identity: `key_id` (primary key), `name`, `page`, `page_raw`.
Location: `byte`, `byte_length`, `mask_bytes` (raw string), `mask_values`
(JSON array of per-byte masks; blank upstream masks become `0xFF`).
Semantics: `bank_scope`, `value_type` (spec types such as `u8`, `bitfield4`,
`f16`), `data_type` (mapped into CMIScope's validation vocabulary), `unit`,
`scale`, `byte_order`, `conversion_note`, `access`, `behavior`, `requirement`,
`condition`, `description`, `ref_section`, `ref_table`.
Cross-check: `sonic_cross_check`, `sonic_field`.
Derived: `section`, `is_reserved`, `is_lower_memory`.

`section` uses CMIScope's four partition keys, based on the partition
definitions in `cmis_service/cmis_spec.py`:

| `section` | Rule |
| --- | --- |
| `LOW_PAGE` | Lower bytes 0-13, 26-36, 39-117, 126-127; Upper page `00h` |
| `VDM` | Lower bytes 14-25; Upper pages `02h`, `10h`, `11h`, `20h-2Fh` |
| `CDB` | Lower bytes 37-38 and 118-125; Upper pages `9Fh`, `A0h-AFh` |
| `CONTROL` | Remaining Upper pages |

This is a deterministic classification for browsing, **not** an OIF statement.
The canonical partition definition remains `cmis_spec.SECTIONS`.

### `cmis53_cdb_commands` (48 rows)

`cmd_id` (4 hex digits, matching `cmis_spec.CDB_COMMANDS`), `title`,
`cmd_group`, `requirement`, `spec_section`, `detail_table`, `overview_table`,
`description`, `note`. CDB **payload field layouts are not covered** by the
upstream dataset.

### `cmis53_spec_tables` (238 rows)

Provenance only: `table_id` (e.g. `8-10`), `section` (8 or 9), short `title`,
`pdf_page` / `printed_page` / `body_page`, memory `page` (`Lwr` / `NNh`),
`field_rows` extracted from the PDF, and `source` (`toc` or `body`). No OIF
prose is stored. Rebuilt from the JSON on every start.

### `cmis53_meta` (7 rows)

JSON-serialized `meta`, `field_columns`, `cdb_columns`, `section_rules`,
`stats`, `spec_pdf_meta`, `spec_verification`, so `/api/reference/meta` never
has to parse the 2.7 MB reference file.

## 5. Build and configuration

```bash
python tools/parse_spec_pdf.py                 # PDF -> data/spec_pdf_index.json
python tools/import_cmis53.py                 # CSV + PDF index -> reference JSON
python tools/import_cmis53.py --no-spec-index # CSV only (provenance disabled)
python tools/parse_spec_pdf.py --pdf knowledge/specs/OIF-CMIS-05.4.pdf \
    --out data/spec_pdf_54_index.json --no-reference
```

No third-party packages and no network access. The PDF index is optional: if it
is missing, the importer prints a note and still produces a complete reference
JSON without provenance. `db.initialize()` rebuilds the four tables from the
JSON on every start (`DELETE` + insert, like the knowledge graph).
Configuration:

```ini
[paths]
reference_file = data/cmis53_reference.json
```

Override with `CMIS_REFERENCE_FILE`. The file is **optional**: if it is absent,
the service logs a warning, the `/api/reference/*` endpoints report
`available: false`, and all other endpoints work normally. Relative paths are
anchored to `base_dir`.

## 6. API

| Endpoint | Notes |
| --- | --- |
| `GET /api/reference/meta` | Provenance, license summary, column meanings, section rules, statistics, checksums |
| `GET /api/reference/fields` | Paginated. `q`, `page`, `section`, `access`, `value_type`, `data_type`, `requirement`, `sonic`, `ref_table`, `name`, `lower=1`, `reserved=0`, `limit` (1-500, default 50), `offset`. Returns `total` from `COUNT(*)` |
| `GET /api/reference/fields/{key_id}` | One row plus its `cmis_spec` section definition and `spec_sources` (PDF table/page provenance). 404 `REFERENCE_FIELD_NOT_FOUND` |
| `GET /api/reference/cdb-commands` | All 48 commands, optional `q` / `group`; each row has `in_runtime_catalog` and `spec_pdf_page` |
| `GET /api/reference/spec-tables` | Paginated 238-table directory. Filters: `section`, `page`, `q`, `limit`, `offset` |
| `GET /api/reference/spec-tables/{table_id}` | One table plus the reference fields citing it (handles `8-28; 8-30`). 404 `SPEC_TABLE_NOT_FOUND` |
| `GET /api/reference/verify` | PDF-vs-CSV cross-check summary; `available=false` when the index was not generated |

```bash
curl "http://127.0.0.1:8787/api/reference/fields?section=VDM&access=RO&limit=20"
curl "http://127.0.0.1:8787/api/reference/fields/MemoryModel"
curl "http://127.0.0.1:8787/api/reference/cdb-commands"
curl "http://127.0.0.1:8787/api/reference/spec-tables?section=9&limit=10"
curl "http://127.0.0.1:8787/api/reference/spec-tables/8-10"
curl "http://127.0.0.1:8787/api/reference/verify"
```

`GET /api/reference/cdb-commands` also returns `runtime_catalog_size` (26).
Of the 48 upstream commands, 26 already exist in `cmis_spec.CDB_COMMANDS`;
the remaining 22 are visible here for review but are **not** executable.
`/api/cdb/commands` remains the executable catalog and is unchanged.

## 7. Specification PDF parsing (zero-dependency refactor)

The second upstream repository's main capability is **rebuilding the field map
from the OIF PDF**. CMIScope now has that capability, re-implemented without
`pdfplumber` and wired into the reference layer above:

| Module | Responsibility |
| --- | --- |
| `tools/spec_pdf.py` | Classic-xref reader: xref table (with `/Prev` chains), `/Pages` tree, FlateDecode streams, and `BT/ET` text runs with `(x, y, size)` from `Tm` / `Tf`. Handles WinAnsi escapes and optional ToUnicode CMaps. Read-only and best-effort: a damaged page yields no spans instead of an exception. |
| `tools/parse_spec_pdf.py` | Discovers the TOC, collects `Table 8-N` / `Table 9-N` captions and page numbers, rebuilds column ranges from the header row's character x-coordinates, extracts data rows, and emits `data/spec_pdf_index.json`. |
| `tools/cmis53_rules.py` | The normalization rules from section 3, shared with the CSV importer. |

Refactor highlights over upstream:

- **No third-party libraries.** `pdfplumber`, `openpyxl` and the SONiC clone
  are gone; only standard-library modules are used. The 5.3 PDF (408 pages,
  14 MB) parses in roughly 3 seconds.
- **Dynamic page range.** Upstream hardcoded pages 120..290; this parser reads
  the document's own TOC and body captions, so CMIS 5.4 (456 pages) works via
  `--pdf` without code changes.
- **Columns reconstructed from coordinates.** Word emits each table cell as
  positioned text runs; mapping header characters back to their x coordinate
  reproduces the Byte / Bit / Name / Description / Type columns. Small-font
  footnote markers are filtered by font size, as upstream did.
- **One normalization path.** Wrapped byte ranges (`129-` + `130`), per-lane
  `<n>` expansion, bit masks, access/behavior/requirement tokens and
  engineering-unit derivation all go through `cmis53_rules.py`, so PDF and CSV
  rows can be compared directly.
- **Provenance and verification.** The index records the PDF SHA-256, TOC
  pages, scanned range, table captions and page numbers, plus a cross-check
  against the CSV reference.
- **Compliance.** Verbatim OIF descriptions are used in memory for unit
  derivation but are **not written to the index**. Only factual identifiers
  (table numbers, short captions, page numbers, field names, addresses,
  access types) are persisted. See `NOTICE` section 8.

Current 5.3 result:

| Metric | Value |
| --- | --- |
| Tables discovered | 238 (181 in Section 8, 57 in Section 9) |
| Reference tables resolved to a PDF page | 129 / 129 |
| Field rows extracted (best-effort) | 721 (685 detail + 36 overview) |
| Exact `(page, byte, name)` matches against CSV | 627 / 685 (91.5%) |
| CDB commands resolved | 48 / 48 |
| Fields / commands carrying `spec_pdf_page` after merge | 2442 / 2442, 48 / 48 |

Unmatched rows come from tables with a different column layout (e.g. Table
8-28) or from descriptive overview labels; they are a limitation of coordinate
extraction, **not** a CSV error. The CSV (itself produced upstream from this
PDF with hand corrections) remains the authority for field values, and the OIF
specification remains authoritative overall. `/api/reference/verify` exposes
the numbers, including a unit/scale derivation comparison.

Rebuild order matters: run `parse_spec_pdf.py` before `import_cmis53.py`, then
restart the service so `db.initialize()` reloads the JSON. Run
`tools/test_spec_pdf.py` (33 checks) to validate the reader, the rules, the
index and the endpoints.

## 8. Derived reports (P-01 / P-02)

Two advisory reports reuse the zero-dependency reader. Neither changes the
runtime schema, the API, `seed.json`, or the hardware write path.

| Tool | Outputs | Purpose |
| --- | --- | --- |
| `tools/diff_spec_versions.py` | `data/spec_version_diff.json`, `docs/CMIS_53_54_DIFF.md` | 5.3 -> 5.4 diff of tables, field rows and CDB commands (knowledge-graph item `P-02`) |
| `tools/verify_seed_fields.py` | `data/seed_field_verification.json`, `docs/SEED_FIELD_VERIFICATION.md` | Cross-check the 64 demo fields against the 2442 authoritative rows (item `P-01`) |

### 8.1 Version diff: align captions, not table numbers

CMIS 5.4 inserts tables in the middle of Section 8. 102 matched tables are
therefore renumbered by +10 and most PDF pages shift by +25..+30.  Comparing
`table_id` directly reports hundreds of false "renames" and "page changes".
`diff_tables()` uses `difflib.SequenceMatcher` on normalized captions, folds
the global wording swap (`paged memory modules only` -> `not for static memory
modules`) into a separate `terminology_updates` bucket, and reports page shifts
as layout metadata. The 5.3 index is reused only when its embedded PDF
SHA-256 matches; the 5.4 index is parsed in memory, so no second large index
is shipped.

Observed on the bundled PDFs: 238 -> 258 tables (+26 / -6, 42 substantive
caption edits, 5 terminology swaps), CDB commands 48 -> 51 (+5 / -2).
Field-level differences are explicitly `indicative`: coordinate extraction is
incomplete, so they are review candidates, not statements about the spec.

```bash
python tools/diff_spec_versions.py   # ~3 s; writes both outputs
python tools/test_spec_diff.py       # 22 regression checks
```

### 8.2 Demo field verification: advisory only

`seed.json` uses hand-written `field_key` aliases and coarse display types, so
`classify()` matches in three stages: exact name -> exact `(page, byte)` ->
fuzzy name (`difflib`, cutoff 0.62). Candidates carry a confidence grade;
`low` results are address coincidences and must be treated as unresolved.
Compound page labels (`Lower/11h`, `A0h-AFh`) are expanded; placeholders
(`pending`, `banked`, `Staged Control Set`) never become addresses.

**The tool never edits `seed.json`.** It emits a P-01 review checklist with
the authoritative byte, `key_id`, source table and PDF page. `--strict`
returns 1 on exact-name page/byte mismatches for CI use.

```bash
python tools/verify_seed_fields.py
python tools/verify_seed_fields.py --strict
python tools/test_seed_verification.py   # 28 regression checks
```

Both reports persist only factual identifiers (table numbers, short captions,
page numbers, field names, addresses, access tokens). Verbatim OIF prose is
not written to disk; see `NOTICE` section 8. The OIF specification remains
authoritative.

## 9. Deliberately not integrated (follow-up candidates)

- **Applying the P-01 findings to `seed.json`.** The verification report gives
  candidate offsets, but editing demo data requires human confirmation against
  OIF text and must not silently turn reference rows into writable items.
- **Extending the version diff to 5.2 or to clause-level text** (would require
  persisting specification prose, which the content policy forbids).
- **Extending `cmis_spec.CDB_COMMANDS` from 26 to 48 entries.** Changes
  `/api/cdb/commands`, `compose_frame()` risk classification and firmware
  gating, so it needs a separate safety review.
- **Knowledge-graph links / a new source entry** (`tools/build_kg.py`, then
  `tools/build_knowledge_docs.py`) so the reference fields appear in the graph.
  `build_kg.py` validates every `source_id` and `entity_id`, so this must be
  added carefully.
- **A Dashboard view** in `static/index.html` / `app.js` / `i18n.js` for
  browsing the field map with pagination and filters.
- **Bundling the raw SONiC field map** for live bit-level re-computation
  (requires Apache-2.0 NOTICE handling and adds a dependency on an external
  pinned checkout).
