# Upstream CMIS 5.3 reference assets

These CSV files are **unmodified** copies from
[jimfred/CMIS](https://github.com/jimfred/CMIS), used as the read-only input of
`tools/import_cmis53.py`. They are kept in the repository so that
`data/cmis53_reference.json` can be rebuilt offline and the whole directory
stays portable. None of these files are parsed at runtime.

| File | Rows | Content |
| --- | --- | --- |
| `CMIS_5.3_Memory_Map.csv` | 2442 + header | Field-level map of OIF-CMIS-05.3 Section 8 |
| `CMIS_5.3_CDB_Commands.csv` | 48 + header | Section 9 CDB command directory |
| `corrections.csv` | 2 + header | Hand corrections applied by the upstream project before CSV export |

## License boundaries (important)

This is a **mixed** dataset. Do not relicense it as a whole.

- **MIT** — Copyright (c) 2026 Jim Frederick. Covers the upstream scripts, the
  workbook structure, normalization, Key IDs, the unit/scale and conversion
  columns, the corrections and the SONiC cross-check columns. The full MIT text
  is in the upstream `LICENSE`; the attribution is reproduced in `NOTICE`.
- **OIF (not covered by MIT)** — field names (`CMIS Name`), register addresses
  (`Page`, `Byte`, `Byte Length`, `Mask Bytes`), `Access`, `Behavior`,
  `Requirement`, `Reference Table` / `Reference Section`, and the verbatim
  `Description` text. These are derived from
  *OIF-CMIS-05.3, Common Management Interface Specification revision 5.3*
  (4 Sept 2024), (c) Optical Internetworking Forum, <https://www.oiforum.com/>,
  and remain subject to the OIF's terms.
- **Apache-2.0** — the `SONiC Cross-check` / `SONiC Field` values are derived
  from [sonic-net/sonic-platform-common](https://github.com/sonic-net/sonic-platform-common)
  at a pinned commit. They are comparison results only, not a compliance claim.

The OIF specification is authoritative. Verify timing- or safety-critical
details against the PDF (`knowledge/specs/OIF-CMIS-05.3.pdf`) before any
hardware use. CMIScope never turns this reference data into writable
configuration items.

## Rebuild

```bash
python tools/import_cmis53.py
```

The generator uses only the Python standard library. It writes UTF-8 / LF and
records SHA-256 checksums of every input in `data/cmis53_reference.json`.
See `docs/CMIS53_REFERENCE.md` for the schema and API surface.
