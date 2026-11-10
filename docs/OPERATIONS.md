# CMIScope Operations Guide

This guide covers everyday use of the dashboard and the equivalent REST calls.
All examples assume `http://127.0.0.1:8787`. Replace the base URL if `--port`
was changed.

## 1. Dashboard views

| View | What it does |
| --- | --- |
| Overview | counts, device status distribution, recent changes, graph statistics |
| Devices | search/filter devices, open a device detail with modules and config items |
| Module CMIS | registers grouped by the four CMIS partitions: `LOW_PAGE`, `VDM`, `CDB`, `CONTROL` |
| Configuration | search config items, edit a value, run pre-save validation, save |
| Knowledge graph | entity/relation browsing, source coverage, SVG graph |
| Sources & pending | 38 sources and 19 pending confirmations |
| **Access targets** | edit target devices, switch the test interface, probe, save |
| About | delivery notes, access modes, endpoint list |

Use the **EN / 中文** button in the header to switch language. Chinese is the
default; the choice is stored in `localStorage['cmiscope.lang']`.

## 2. Switching and editing the test interface

Open **Access targets**. The `Active test target` dropdown selects which
device/mode the service uses for probes and register operations. To change a
device, click **Edit**, adjust the fields and click **Apply to list**, then
**Save configuration**. Adding a device requires no code change.

### Field reference

| Field | Meaning |
| --- | --- |
| `device_id` | unique key; letters, digits, dot, underscore, hyphen |
| `name`, `notes` | free text |
| `enabled` | whether the target participates in resolution |
| `access_mode` | `mirror` / `ssh-i2c` / `rest-api` |
| `host` | IP address or hostname of the switch / device (required for hardware modes) |
| `port` | SSH port (default 22) or HTTPS port (default 443); 0 for mirror |
| `ssh_user`, `i2c_bus`, `i2c_addr` | Mode A parameters (default `0x50`) - **ssh-i2c targets only** |
| `rest_scheme`, `rest_base_path` | Mode B URL construction, e.g. `https://10.0.0.9:8443/api` - **rest-api targets only** |
| `token_env` | **name** of the environment variable holding the REST token, never the token itself - **rest-api targets only** |
| `module_ids` | optional list of module identifiers for CDB execution |

**Mode A and Mode B are strictly mutually exclusive.** A target may contain only the fields of its selected `access_mode`; `mirror` targets carry neither set. The dashboard shows and submits only the selected mode's fields, `GET /api/targets` returns only those fields, and a `PUT` containing the other mode's fields is rejected with `TARGETS_VALIDATION_FAILED`. The unselected transport's endpoint is blanked at load and resolve time, so it cannot take effect.

Literal credentials are rejected by the validator with
`TARGETS_VALIDATION_FAILED`. Use `token_env` plus an environment variable.

### Equivalent REST calls

```bash
# Inspect the registry, allowed modes, field metadata and file paths
curl http://127.0.0.1:8787/api/targets

# Replace the whole registry (validated, atomically written, LF/UTF-8)
curl -X PUT http://127.0.0.1:8787/api/targets \
  -H "Content-Type: application/json" \
  -d '{"version":1,"active_target":"LAB-SW-01","targets":[
        {"device_id":"LAB-SW-01","access_mode":"ssh-i2c",
         "host":"10.0.0.2","port":22,"ssh_user":"lab"}]}'

# Probe the active target, or a named one
curl -X POST http://127.0.0.1:8787/api/targets/probe \
  -H "Content-Type: application/json" -d '{}'
curl -X POST http://127.0.0.1:8787/api/targets/probe \
  -H "Content-Type: application/json" -d '{"device_id":"LAB-SW-01"}'
```

`PUT` writes `config/targets.json`. Deleting that file makes the service fall
back to `config/targets.example.json` again. With `read_only = true`, `PUT`
returns `409 SERVICE_READ_ONLY`.

## 3. Reading registers

```bash
curl "http://127.0.0.1:8787/api/registers/read?device_id=SW-CORE-01&page=00h&offset=0&length=16"
curl "http://127.0.0.1:8787/api/cmis/module?device_id=SW-CORE-01&section=VDM"
curl http://127.0.0.1:8787/api/sections
curl http://127.0.0.1:8787/api/sections/CDB
```

In `mirror` mode reads return cached values with a clear message; no hardware
is contacted. In hardware modes the per-target parameters determine the SSH
command or REST URL.

## 4. Composing and executing CDB commands

```bash
curl http://127.0.0.1:8787/api/cdb/commands        # 26 CMDIDs from OIF-CMIS-05.3 section 9

# Offline frame composition with checksum; nothing is sent
curl -X POST http://127.0.0.1:8787/api/cdb/compose \
  -H "Content-Type: application/json" \
  -d '{"cmd_id":"0040","lpl_hex":"00 01"}'

# Execute (staged in mirror mode; audited in cdb_operations)
curl -X POST http://127.0.0.1:8787/api/cdb/execute \
  -H "Content-Type: application/json" \
  -d '{"cmd_id":"0040","lpl_hex":"00 01","device_id":"SW-CORE-01","confirm":"EXECUTE"}'

curl "http://127.0.0.1:8787/api/cdb/history?device_id=SW-CORE-01"
curl "http://127.0.0.1:8787/api/cdb/status?device_id=SW-CORE-01"
```

The frame is a 128-byte Page 9Fh structure. The server computes
`check_code = (-sum(body)) & 0xFF`; invalid CMDID, oversized LPL (>120) or EPL
(>2048) are rejected before anything is dispatched. Hardware dispatch further
requires `allow_hardware_write`, `confirm`, and (for REST CDB)
`cdb_rest_allowed`.

## 5. Editing a configuration value

Search in **Configuration**, click **Edit**, then use **Validate** before
**Save**. The server re-validates on save; client-side checks are advisory.

```bash
curl "http://127.0.0.1:8787/api/config-items?q=AppSelLane1&writable=1"
curl -X POST http://127.0.0.1:8787/api/config-items/17/validate \
  -H "Content-Type: application/json" -d '{"value":"0x21"}'
curl -X PUT http://127.0.0.1:8787/api/config-items/17 \
  -H "Content-Type: application/json" \
  -d '{"value":"0x21","expected_version":1,"note":"switch to Application 2"}'
```

Validation covers read-only bits, types, ranges, enumerations, regexes,
cross-field rules and field confidence. `expected_version` implements
optimistic locking; a mismatch returns `409 VERSION_CONFLICT`. Every write is
recorded in `config_changes` with a before/after diff and the validation report.

## 6. Knowledge graph queries

```bash
curl "http://127.0.0.1:8787/api/kg/stats"
curl "http://127.0.0.1:8787/api/kg/link?cmis=AppSelLane1"
curl "http://127.0.0.1:8787/api/kg/link?cmis=CdbCmdId"
curl "http://127.0.0.1:8787/api/kg/link?entity=CFG-APPSEL"
curl "http://127.0.0.1:8787/api/kg/entities?type=AccessPath"
curl "http://127.0.0.1:8787/api/kg/pending"
```

Documentation, the JSON schema, the 38-entry source manifest and the bundled
OIF PDFs are consolidated under `knowledge/`. See `knowledge/README.md`.

## 7. Troubleshooting

| Symptom | Likely cause / action |
| --- | --- |
| `sqlite3.OperationalError: no such column: section` | Older database. Handled automatically by `_migrate()`; restart the service |
| `TARGETS_VALIDATION_FAILED` | Read `error.details.errors`: a required `host` is missing, `device_id` is invalid/duplicated, or a literal credential field was used |
| `HARDWARE_WRITE_DISABLED` | Set `allow_hardware_write = true` only on lab hardware |
| `LOWER_MEMORY_PROTECTED` / `CDB_PAGE_PROTECTED` | Intentional page-level write protection; cannot be overridden |
| `CONFIRMATION_REQUIRED` | Add `"confirm": "EXECUTE"` to the CDB request |
| `SSH_COMMAND_FAILED` / `REST_UNREACHABLE` | Check host/port, ssh-agent keys, or the device API; use `GET /api/access` and `POST /api/access/probe` first |
| `VERSION_CONFLICT` | Refresh the item and resubmit with the current `version` |
| Target edits disappear after restart | Only `Apply to list` was clicked; click `Save configuration` to persist |

Enable verbose logging with `CMIS_LOG_LEVEL=DEBUG` or `log_level = DEBUG` in
`config.ini`. Stack traces are logged server-side only and never returned to
the browser.

## 8. Rebuilding generated artefacts

```bash
python tools/build_seed.py             # data/seed.json
python tools/build_kg.py               # data/knowledge_graph.json
python tools/build_knowledge_docs.py   # knowledge/SOURCES.md + links.json
python tools/fetch_specs.py            # knowledge/specs/*.pdf
python tools/smoke_test.py             # full regression
```

Restart the service afterwards so the new graph JSON is reloaded into SQLite.
