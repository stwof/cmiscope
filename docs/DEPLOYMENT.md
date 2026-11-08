# CMIScope Deployment Guide

CMIScope is a self-contained local web service. It uses **only the Python
standard library** (`http.server`, `sqlite3`, `urllib`, `configparser`) and
ships its CSS/JS assets locally, so there is no `pip install`, no Node build,
no container and no external database.

## 1. Requirements

| Item | Requirement |
| --- | --- |
| Python | 3.9 or newer (3.10+ recommended for `tuple[int, dict]` annotations via `from __future__`) |
| OS | Windows, Linux, macOS; all paths are `pathlib.Path`-based |
| Disk | ~5 MB for code and data, plus optional OIF PDF copies under `knowledge/specs/` |
| Network | None for the default `mirror` mode; outbound SSH/HTTPS only if a hardware mode is enabled |
| Port | `8787` by default, bound to `127.0.0.1` |

Check with:

```bash
python --version
python -m py_compile run.py cmis_service/*.py tools/*.py
```

## 2. Start / stop

```bash
python run.py                          # http://127.0.0.1:8787/
python run.py --port 9000
python run.py --host 0.0.0.0 --port 9000   # only inside a trusted, firewalled network
python run.py --config /etc/cmiscope.ini
```

Stop with `Ctrl+C`. The service is a `ThreadingHTTPServer`; the SQLite file is
opened in WAL mode and closed on process exit.

Verify:

```bash
curl http://127.0.0.1:8787/api/health
# {"ok":true,"data":{"status":"up", ...}}
```

## 3. Configuration precedence

`built-in defaults` < `config.ini` < `CMIS_*` environment variables.

```bash
cp config.ini.example config.ini       # optional; config.ini is git-ignored
```

All relative paths resolve against `base_dir`, which defaults to the project
root. To move the whole installation, copy the directory and, if needed, set:

```bash
CMIS_BASE_DIR=/opt/cmiscope python /opt/cmiscope/run.py
CMIS_DATA_DIR=/var/lib/cmiscope CMIS_DB_FILE=/var/lib/cmiscope/cmis.db python run.py
CMIS_TARGETS_FILE=/etc/cmiscope/targets.json python run.py
```

`config.ini` and `config/targets.json` are deliberately excluded from version
control (see `.gitignore`) because they may contain internal host names.

## 4. Access modes and target devices

The global fallback mode is set by `access_mode` in `config.ini`. Per-device
overrides live in **`config/targets.json`** (edit it in a terminal or from the
dashboard's **Access targets** view). If that file is absent, the shipped
`config/targets.example.json` is used read-only.

| Mode | Topology | Use case |
| --- | --- | --- |
| `mirror` | browser -> service -> SQLite | default; offline review, training, CI. Writes are staged only |
| `ssh-i2c` | service -> SSH to test switch -> `i2cget`/`i2cset` -> module EEPROM at `0x50` | lab bring-up, module characterization |
| `rest-api` | service -> northbound REST API of the target device / NOS | integration and multi-device automation |

Minimal example of adding a device without touching code:

```json
{
  "version": 1,
  "active_target": "LAB-SW-01",
  "targets": [
    {
      "device_id": "LAB-SW-01",
      "name": "Bench switch",
      "access_mode": "ssh-i2c",
      "host": "10.0.0.2",
      "port": 22,
      "ssh_user": "lab",
      "i2c_bus": "0",
      "i2c_addr": "0x50"
    },
    {
      "device_id": "CORE-01",
      "access_mode": "rest-api",
      "host": "10.0.0.9",
      "port": 443,
      "rest_scheme": "https",
      "rest_base_path": "/api",
      "token_env": "CMIS_REST_TOKEN"
    }
  ]
}
```

The registry is validated on every read and write. Literal credential fields
(`token`, `password`, `secret`, ...) are **rejected**, so secrets can never be
written into the config file or the repository. See `docs/OPERATIONS.md` for
the full field list and the API equivalents.

## 5. Credentials and security

- REST token: set the environment variable named by `token_env`, e.g.
  `CMIS_REST_TOKEN`. It is never written to disk, never returned by any API,
  and never placed in a Git remote URL.
- SSH: uses the system `ssh` binary with `BatchMode=yes` and the operator's
  existing ssh-agent keys. Command templates are `shlex`-split argv arrays,
  never a shell string.
- Hardware writes are **off by default**: `allow_hardware_write = false`.
  Lower Memory writes and CDB page writes are blocked unconditionally,
  following IETF `draft-hi-ccamp-cmis-control-yang-04` section 9.1.
- Firmware-class CDB commands require `cdb_allow_firmware = true` and an
  explicit `confirm = EXECUTE` token.
- `read_only = true` disables every configuration write (including target
  editing) and is recommended for shared demo instances.
- Do not expose the service directly to an untrusted network; it has no
  authentication layer by design. Put it behind a reverse proxy with
  authentication, or bind to `127.0.0.1` and use an SSH tunnel.

## 6. Data and upgrades

| File | Purpose | Regenerated |
| --- | --- | --- |
| `data/seed.json` | synthetic devices, modules, fields, config items | `tools/build_seed.py` |
| `data/knowledge_graph.json` | graph data, 38 sources | `tools/build_kg.py` |
| `data/cmis.db` | runtime SQLite database (git-ignored) | on first start |
| `knowledge/specs/*.pdf` | offline OIF CMIS 5.3 / 5.4 copies | `tools/fetch_specs.py` |

On startup the service creates missing tables, adds newly introduced columns
(`_migrate`), maps the retired pre-5.3 diagnostic-monitoring partition key to
`VDM`, creates indexes on migrated columns, synchronizes seed rows with
`INSERT OR IGNORE`, and reloads the graph JSON. **Operator edits to
configuration values are preserved.**
To reset completely, stop the service and remove `data/cmis.db*`.

## 7. Portability checklist

- Copy the whole directory; no absolute paths are hard-coded.
- Text files are UTF-8 with LF endings (`.gitattributes` enforces this).
- No native extensions, no compiled assets, no OS-specific shell commands in
  the request path (`subprocess` is used only in `ssh-i2c` mode).
- Bundled fonts/CSS/JS are vendored under `cmis_service/static/vendor/tabler/`;
  the dashboard works fully offline.
- To relocate runtime state, set `CMIS_DATA_DIR` / `CMIS_DB_FILE`; to relocate
  the operator inventory, set `CMIS_TARGETS_FILE`.

## 8. Validation after deployment

```bash
python tools/smoke_test.py              # temporary port + temporary DB, no data pollution
python tools/fetch_specs.py --check     # verify bundled PDF copies
python tools/build_knowledge_docs.py    # regenerate SOURCES.md / links.json
```

A green regression run reports `Result: 87 passed / 0 failed` and exercises
health, metadata, VDM-named partitions, CDB framing and safety gates,
configuration validation, graph queries, static assets, editable target
registries, knowledge assets and credential hygiene, directory-traversal
protection and the legacy-database upgrade path.
