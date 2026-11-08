# Knowledge Graph Directory

This directory is the single home for **CMIS knowledge-graph documentation and
reference material**. Runtime graph data lives in `data/knowledge_graph.json`;
this directory holds the human-readable documentation, the machine-readable
link manifest, and downloadable copies of the stable OIF specifications.

## Contents

| Path | Purpose |
| --- | --- |
| [`CMIS_KNOWLEDGE_GRAPH.md`](CMIS_KNOWLEDGE_GRAPH.md) | Graph scale, confidence rules, source categories, 19 pending confirmations and cross-link queries |
| [`SCHEMA.md`](SCHEMA.md) | JSON schema of the graph, entity/relation types, and the SQLite table mapping |
| [`SOURCES.md`](SOURCES.md) | All 38 sources with canonical URLs and bundled-copy links (generated) |
| [`links.json`](links.json) | Machine-readable link manifest for tooling and offline checks (generated) |
| [`specs/README.md`](specs/README.md) | Bundled OIF CMIS 5.3 / 5.4 PDFs, provenance, copyright and canonical links |
| [`specs/*.pdf`](specs/) | Downloadable local copies of the two primary specification PDFs |

## Data flow

```
tools/cmis_catalog.py   (field and device catalogue)
        |
        +--> tools/build_seed.py          --> data/seed.json
        |
        +--> tools/build_kg.py            --> data/knowledge_graph.json
                                                  |
                    tools/build_knowledge_docs.py +--> knowledge/SOURCES.md
                                                  +--> knowledge/links.json
        cmis_service/db.py imports the JSON into SQLite kg_* tables on startup
        cmis_service/kg.py  serves /api/kg/* queries over those tables
```

Rebuild everything after editing the catalogue or the graph:

```bash
python tools/build_seed.py
python tools/build_kg.py
python tools/build_knowledge_docs.py
python tools/fetch_specs.py --check     # verify the bundled PDFs
python tools/smoke_test.py              # end-to-end regression
```

## Stability and provenance

- Every graph entity and relation carries `source_ids`, `confidence` and
  `status`. Claims that could not be verified against an official document are
  marked `partial` or `pending` and listed in the pending-confirmation table.
- Canonical OIF URLs are always authoritative; the bundled PDFs are offline
  snapshots retrieved on 2026-11-08. See [`specs/README.md`](specs/README.md).
- The graph contains **no copied source code** from any referenced open-source
  project; only README/documentation content, kernel symbol names and
  repository metadata are cited.
- Synthetic device and module data is marked with `S-INTERNAL` and must not be
  interpreted as real network inventory.
