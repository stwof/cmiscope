# Bundled CMIS Specifications

This directory contains **directly downloadable local copies** of the two
primary OIF CMIS specification PDFs, so the dashboard can be deployed and
reviewed in an offline or air-gapped lab. The canonical OIF URLs are listed
below and in [`../links.json`](../links.json); they are always authoritative.

## Bundled files

| File | Document | Revision / date | Canonical URL |
| --- | --- | --- | --- |
| [`OIF-CMIS-05.3.pdf`](OIF-CMIS-05.3.pdf) | Common Management Interface Specification | Rev 5.3, September 2024 | https://www.oiforum.com/wp-content/uploads/OIF-CMIS-05.3.pdf |
| [`OIF-CMIS-05.4.pdf`](OIF-CMIS-05.4.pdf) | Common Management Interface Specification | Rev 5.4, May 2026 | https://www.oiforum.com/wp-content/uploads/OIF-CMIS-05.4.pdf |

CMIS 5.3 is the primary reference for the register partitions, Lower/Upper
memory layout, CDB command frame (Page 9Fh) and the CMDID catalogue used by
`cmis_service/cmis_spec.py`. CMIS 5.4 is included for version-diff work; see
pending item `P-02` in [`../CMIS_KNOWLEDGE_GRAPH.md`](../CMIS_KNOWLEDGE_GRAPH.md).

## Other stable references (link only)

| Document | Link |
| --- | --- |
| OIF Implementation Agreements index (authoritative revision list) | https://www.oiforum.com/technical-work/implementation-agreements/ |
| OIF-CMIS-05.2 (Rev 5.2, April 2022) | https://www.oiforum.com/wp-content/uploads/OIF-CMIS-05.2.pdf |
| OIF-CMIS-05-Errata-01.0 (February 2025) | https://www.oiforum.com/wp-content/uploads/OIF-CMIS-05-Errata-01.0.pdf |
| OIF-C-CMIS-01.3 / 01.5 (coherent CMIS) | https://www.oiforum.com/wp-content/uploads/OIF-C-CMIS-01.3.pdf · https://www.oiforum.com/wp-content/uploads/OIF-C-CMIS-01.5.pdf |
| IETF `draft-hi-ccamp-cmis-control-yang-04` (page-level read/write policy) | https://datatracker.ietf.org/doc/html/draft-hi-ccamp-cmis-control-yang-04 |
| Linux kernel `net/ethtool/cmis_cdb.c` (CDB frame implementation, GPL-2.0) | https://github.com/torvalds/linux/blob/master/net/ethtool/cmis_cdb.c |
| SFF-8024 identifier codes | https://www.snia.org/technology-communities/sff/specifications |

The full 38-entry source manifest, including GitHub repositories and vendor
guides, is in [`../SOURCES.md`](../SOURCES.md).

## Refreshing the copies

```bash
python tools/fetch_specs.py            # resume / download missing PDFs
python tools/fetch_specs.py --check    # verify completeness without network
python tools/fetch_specs.py --force    # re-download from scratch
```

The script uses only the Python standard library, supports resumable HTTP
Range requests, and verifies the `%PDF-` header and `%%EOF` trailer so an HTML
error page can never be mistaken for a specification.

## Copyright and licensing

The CMIS Implementation Agreements are published by the **Optical
Internetworking Forum (OIF)** and remain the property of OIF and its
contributors. They are publicly downloadable from the OIF website; the copies
in this repository are provided **for offline reference only**. No ownership
is claimed, and no OIF text is reproduced inside the project source code.
If OIF updates or withdraws a document, use the canonical link and remove or
replace the local copy. Redistribution terms are governed by OIF's own notices
contained in each PDF.

For third-party code assets bundled elsewhere in this repository, see the
repository-level `NOTICE` file and `cmis_service/static/vendor/tabler/LICENSE`.
