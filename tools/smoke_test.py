"""End-to-end smoke test: start the local service, exercise the REST API,
static assets, error handling and the CMIS/CDB partition endpoints, then stop.

Usage: python tools/smoke_test.py
No third-party dependencies. A temporary database is used so the delivered
data/cmis.db is never modified.
"""

from __future__ import annotations

import json
import os
import socket
import sqlite3
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))  # imports work when run as `python tools/smoke_test.py`

from dataclasses import replace
from cmis_service import db as dbmod
from cmis_service.config import load_settings

PASS, FAIL = [], []


def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def check(name: str, condition: bool, detail: str = "") -> None:
    (PASS if condition else FAIL).append(name)
    print(f"{'PASS' if condition else 'FAIL'}  {name}" + (f"  | {detail}" if detail else ""))


def main() -> int:
    port = free_port()
    base = f"http://127.0.0.1:{port}"
    tmp = tempfile.mkdtemp(prefix="cmiscope-smoke-")
    env = {**os.environ,
           "CMIS_HOST": "127.0.0.1",
           "CMIS_PORT": str(port),
           "CMIS_DB_FILE": str(Path(tmp) / "smoke.db"),
           "CMIS_LOG_LEVEL": "WARNING"}
    proc = subprocess.Popen(
        [sys.executable, "run.py", "--port", str(port)], cwd=str(ROOT), env=env,
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
    )

    def req(method: str, path: str, body=None):
        data = json.dumps(body, ensure_ascii=False).encode("utf-8") if body is not None else None
        headers = {"Content-Type": "application/json"} if body is not None else {}
        request = urllib.request.Request(base + path, data=data, method=method, headers=headers)
        try:
            with urllib.request.urlopen(request, timeout=6) as resp:
                raw = resp.read()
                return resp.status, (json.loads(raw) if "json" in resp.headers.get("Content-Type", "") else raw)
        except urllib.error.HTTPError as err:
            raw = err.read()
            try:
                return err.code, json.loads(raw)
            except (ValueError, UnicodeDecodeError):
                return err.code, raw

    try:
        ready = False
        for _ in range(40):
            try:
                st, payload = req("GET", "/api/health")
                if st == 200 and payload.get("ok"):
                    ready = True
                    break
            except Exception:
                pass
            time.sleep(0.25)
        check("Service startup / health", ready, f"port={port}")
        if not ready:
            return finish(proc, tmp)

        st, p = req("GET", "/api/health")
        check("Health response shape", st == 200 and p["data"]["status"] == "up"
              and p["data"]["project"] == "CMIScope")

        st, p = req("GET", "/api/meta")
        check("Meta: project, specs, sections, access modes",
              st == 200 and p["data"]["project"]["name"] == "CMIScope"
              and len(p["data"]["cmis_specs"]) >= 4
              and len(p["data"]["sections"]) == 4
              and len(p["data"]["access_modes"]) == 3)

        st, p = req("GET", "/api/overview")
        d = p["data"]
        check("Overview statistics",
              d["devices"] == 8 and d["config_items"] >= 500 and d["kg"]["entities"] >= 120,
              f"devices={d['devices']} items={d['config_items']} kg={d['kg']['entities']}")
        check("Overview includes framework, access and section counts",
              d["framework"]["license"] == "MIT" and d["access"]["mode"] == "mirror"
              and len(d["section_counts"]) == 4)

        st, p = req("GET", "/api/access")
        modes = {m["key"] for m in p["data"]["modes"]}
        check("Two production access paths + mirror",
              modes == {"mirror", "ssh-i2c", "rest-api"}
              and p["data"]["active"]["allow_hardware_write"] is False)
        st, p = req("POST", "/api/access/probe", {})
        check("Access probe in mirror mode", st == 200 and p["data"]["probe"]["ok"] is True)

        st, p = req("GET", "/api/sections")
        sec = p["data"]
        check("CMIS partition definitions", st == 200 and len(sec["items"]) == 4)
        check("Low Page register map", len(sec["lower_memory_map"]) >= 14)
        check("CDB frame layout", len(sec["cdb_frame"]) == 6
              and sec["cdb_frame"][5]["size"] == 120)
        st, p = req("GET", "/api/sections/CDB")
        check("Single section detail", st == 200 and p["data"]["section"]["key"] == "CDB"
              and p["data"]["fields"])

        st, p = req("GET", "/api/cmis/module?device_id=SW-CORE-01")
        check("Module CMIS grouped by partition",
              st == 200 and len(p["data"]["sections"]) == 4
              and p["data"]["total_items"] >= 60)
        st, p = req("GET", "/api/cmis/module?device_id=SW-CORE-01&section=CDB")
        cdb_section = p["data"]["sections"][0]
        check("CDB partition with register map",
              cdb_section["key"] == "CDB" and len(cdb_section["registers"]) == 6
              and len(cdb_section["items"]) >= 10)

        st, p = req("GET", "/api/cdb/commands")
        cmds = p["data"]["items"]
        check("CDB command catalog (OIF-CMIS-05.3 section 9)",
              st == 200 and len(cmds) >= 25
              and any(c["cmd_id"] == "0040" for c in cmds)
              and any(c["cmd_id"] == "0101" for c in cmds))

        st, p = req("POST", "/api/cdb/compose", {"cmd_id": "0040", "lpl_hex": "00 01", "epl_hex": ""})
        frame = p["data"]["frame"] if st == 200 else {}
        check("CDB frame composition + checksum",
              st == 200 and len(frame.get("frame_hex", "")) == 256
              and frame["lpl_len"] == 2 and frame["check_code"].startswith("0x"))
        st, p = req("POST", "/api/cdb/compose", {"cmd_id": "ZZZZ", "lpl_hex": ""})
        check("Invalid CMDID rejected", st == 400 and p["error"]["code"] == "CDB_VALIDATION_FAILED")
        st, p = req("POST", "/api/cdb/compose", {"cmd_id": "0103", "lpl_hex": "AB" * 121})
        check("Oversized LPL rejected", st == 400 and p["error"]["code"] == "CDB_VALIDATION_FAILED")

        st, p = req("POST", "/api/cdb/execute",
                    {"device_id": "SW-CORE-01", "cmd_id": "0040", "lpl_hex": "00 01",
                     "confirm": "EXECUTE", "operator": "smoke-test"})
        check("CDB execution staged in mirror mode",
              st == 200 and p["data"]["result"] == "staged"
              and p["data"]["applied_to_hardware"] is False)
        st, p = req("GET", "/api/cdb/history?device_id=SW-CORE-01")
        check("CDB audit log", st == 200 and p["data"]["total"] >= 1)
        st, p = req("GET", "/api/cdb/status?device_id=SW-CORE-01")
        check("CDB status register", st == 200 and p["data"]["status_register"] is not None)
        st, p = req("POST", "/api/cdb/execute", {"cmd_id": "0040"})
        check("CDB execute requires device_id", st == 400 and p["error"]["code"] == "MISSING_PARAM")

        st, p = req("GET", "/api/registers/read?device_id=SW-CORE-01&page=00h&offset=0&length=4")
        check("Register read via mirror adapter", st == 200 and p["data"]["read"]["mode"] == "mirror")
        st, p = req("POST", "/api/registers/write",
                    {"device_id": "SW-CORE-01", "page": "10h", "offset": 130, "data_hex": "0x11"})
        check("Hardware write blocked by default",
              st == 409 and p["error"]["code"] == "HARDWARE_WRITE_DISABLED")
        st, p = req("POST", "/api/registers/write",
                    {"device_id": "SW-CORE-01", "page": "Lower", "offset": 3, "data_hex": "0x01"})
        check("Lower Memory write blocked", st == 409)

        st, p = req("GET", "/api/devices?q=SW")
        check("Device list and filter", st == 200 and p["data"]["total"] >= 4)
        st, p = req("GET", "/api/devices/SW-CORE-01")
        check("Device detail", st == 200 and len(p["data"]["modules"]) == 1
              and len(p["data"]["config_items"]) >= 60)
        st, p = req("GET", "/api/devices/NOT-EXIST")
        check("Unknown device -> 404", st == 404 and p["error"]["code"] == "DEVICE_NOT_FOUND")
        st, p = req("GET", "/api/devices?access_mode=rest-api")
        check("Filter devices by access path", st == 200 and p["data"]["total"] >= 4)

        st, p = req("GET", "/api/fields?section=CDB")
        check("Field dictionary filtered by section", st == 200 and p["data"]["total"] >= 10)
        st, p = req("GET", "/api/config-items?q=AppSelLane1")
        check("Configuration item search", st == 200 and p["data"]["total"] == 8)
        item_id = p["data"]["items"][0]["id"]
        version = p["data"]["items"][0]["version"]
        st, p = req("GET", f"/api/config-items/{item_id}")
        check("Config item detail with rules and KG links",
              st == 200 and "rules" in p["data"] and p["data"]["kg"]["total"] > 0)

        st, p = req("POST", f"/api/config-items/{item_id}/validate", {"value": "0x21"})
        check("Pre-save validation: valid value", st == 200 and p["data"]["report"]["valid"] is True)
        st, p = req("POST", f"/api/config-items/{item_id}/validate", {"value": "0xF1"})
        rep = p["data"]["report"]
        check("Pre-save validation: invalid AppSel rejected",
              rep["valid"] is False and any(e["code"] in ("INVALID_APPSEL", "APP_NOT_ADVERTISED")
                                           for e in rep["errors"]))
        st, p = req("PUT", f"/api/config-items/{item_id}", {"value": "0xF1", "expected_version": version})
        check("Saving invalid value rejected", st == 400 and p["error"]["code"] == "VALIDATION_FAILED")
        st, p = req("PUT", f"/api/config-items/{item_id}",
                    {"value": "0x21", "expected_version": version, "note": "smoke test"})
        saved = p["data"] if st == 200 else {}
        check("Saving valid value + change feedback",
              st == 200 and saved.get("result") == "staged"
              and saved["diff"]["before"]["value"] != saved["diff"]["after"]["value"]
              and saved["applied_to_hardware"] is False)
        st, p = req("PUT", f"/api/config-items/{item_id}", {"value": "0x11", "expected_version": version})
        check("Optimistic lock conflict -> 409", st == 409 and p["error"]["code"] == "VERSION_CONFLICT")
        st, p = req("GET", "/api/config-items?writable=0&limit=5")
        ro_id = p["data"]["items"][0]["id"]
        st, p = req("PUT", f"/api/config-items/{ro_id}", {"value": "x"})
        check("Read-only field write rejected",
              st == 400 and p["error"]["code"] == "VALIDATION_FAILED"
              and p["error"]["details"]["errors"][0]["code"] == "READ_ONLY_FIELD")
        changed_device = saved.get("item", {}).get("device_id", "SW-CORE-01")
        st, p = req("GET", "/api/changes?device_id=" + changed_device)
        check("Change audit records", st == 200 and p["data"]["total"] >= 1)

        st, p = req("GET", "/api/search?q=AppSel&scope=config")
        check("Unified search (config)", st == 200 and p["data"]["groups"]["config_items"])
        st, p = req("GET", "/api/search?q=CMIS&scope=kg")
        check("Unified search (graph)", st == 200 and p["data"]["total"] > 0)

        st, p = req("GET", "/api/kg/stats")
        k = p["data"]
        check("Knowledge graph statistics",
              k["entities"] == 129 and k["relations"] == 257 and k["pending"] == 19,
              f"entities={k['entities']} relations={k['relations']} pending={k['pending']}")
        check("Relation types cover contains/defines/constrains/implements/references",
              all(x in k["relations_by_type"] for x in
                  ("CONTAINS", "DEFINES", "CONSTRAINS", "IMPLEMENTS", "REFERENCES")))
        st, p = req("GET", "/api/kg/entity/CFG-APPSEL?depth=2")
        check("Entity neighbor traversal", st == 200 and p["data"]["sources"])
        st, p = req("GET", "/api/kg/relations?type=CONSTRAINS")
        check("Relation type filter", st == 200 and p["data"]["total"] >= 10)
        st, p = req("GET", "/api/kg/link?cmis=AppSelLane1")
        check("CMIS field -> graph link", st == 200 and p["data"]["total"] > 0)
        st, p = req("GET", "/api/kg/link?entity=CFG-APPSEL")
        check("Graph entity -> CMIS reverse link", st == 200 and p["data"]["total"] > 0)
        st, p = req("GET", "/api/kg/link?cmis=CdbCmdId")
        check("CDB field -> partition link", st == 200 and p["data"]["total"] > 0)
        st, p = req("GET", "/api/kg/graph?limit=200")
        check("Graph visualization data", st == 200 and len(p["data"]["nodes"]) > 100)
        st, p = req("GET", "/api/kg/sources/coverage")
        check("Source coverage", st == 200 and len(p["data"]["sources"]) >= 35)
        st, p = req("GET", "/api/kg/pending")
        check("Pending confirmations", st == 200 and len(p["data"]["items"]) == 19)

        st, p = req("GET", "/api/nope")
        check("Unknown endpoint -> 404", st == 404 and p["error"]["code"] == "ENDPOINT_NOT_FOUND")
        st, p = req("DELETE", "/api/devices")
        check("Unsupported method -> 405", st == 405)
        st, p = req("POST", f"/api/config-items/{item_id}/validate", {"other": 1})
        check("Missing value -> 400", st == 400 and p["error"]["code"] == "MISSING_VALUE")
        st, p = req("GET", "/api/kg/link")
        check("Missing parameter -> 400", st == 400 and p["error"]["code"] == "MISSING_PARAM")

        for path, needle in (("/", b"CMIScope"),
                             ("/vendor/tabler/tabler.min.css", b"Tabler v1.7.3"),
                             ("/css/app.css", b"app-shell"),
                             ("/js/app.js", b"CMIS_I18N"),
                             ("/js/i18n.js", b"CMIS_I18N")):
            st, raw = req("GET", path)
            check(f"Static asset {path}", st == 200 and needle in raw,
                  f"bytes={len(raw) if isinstance(raw, bytes) else 0}")
        st, raw = req("GET", "/../config.ini.example")
        check("Directory traversal protection", st in (403, 404))

        # Regression: a first-release database has no `section` columns. Schema
        # indexes on those columns must be created after migration, and seed
        # synchronization must not overwrite operator-edited values.
        legacy_path = Path(tmp) / "legacy.db"
        legacy = sqlite3.connect(str(legacy_path))
        legacy.executescript("""
            CREATE TABLE devices (
                device_id TEXT PRIMARY KEY, name TEXT NOT NULL,
                device_type TEXT NOT NULL DEFAULT '', vendor TEXT, model TEXT,
                location TEXT, status TEXT, cmis_revision TEXT, firmware TEXT,
                last_seen TEXT, notes TEXT
            );
            CREATE TABLE fields (
                field_key TEXT PRIMARY KEY, name TEXT NOT NULL, page TEXT,
                byte_offset TEXT, bit_range TEXT, data_type TEXT, unit TEXT,
                access TEXT, description TEXT, spec_ref TEXT,
                source_ids TEXT NOT NULL DEFAULT '[]',
                confidence TEXT NOT NULL DEFAULT 'confirmed', kg_entity_id TEXT
            );
            CREATE TABLE config_items (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                device_id TEXT NOT NULL, module_id TEXT, field_key TEXT NOT NULL,
                label TEXT, page TEXT, byte_offset TEXT, value TEXT, raw_hex TEXT,
                data_type TEXT, unit TEXT, writable INTEGER NOT NULL DEFAULT 1,
                allowed_values TEXT NOT NULL DEFAULT '[]', min_value REAL,
                max_value REAL, regex TEXT, cross_rule TEXT, spec_ref TEXT,
                source_ids TEXT NOT NULL DEFAULT '[]', updated_at TEXT,
                version INTEGER NOT NULL DEFAULT 1, UNIQUE(device_id, field_key)
            );
            INSERT INTO devices (device_id, name) VALUES ('SW-CORE-01', 'Legacy Device');
            INSERT INTO fields (field_key, name) VALUES ('AppSelLane1', 'AppSel Lane 1');
            INSERT INTO config_items (device_id, field_key, value, version)
                VALUES ('SW-CORE-01', 'AppSelLane1', '0x99', 7);
        """)
        legacy.close()
        upgraded = dbmod.initialize(replace(load_settings(), db_file=legacy_path))
        cols_f = {r["name"] for r in upgraded.execute("PRAGMA table_info(fields)")}
        cols_c = {r["name"] for r in upgraded.execute("PRAGMA table_info(config_items)")}
        idx = {r["name"] for r in upgraded.execute(
            "SELECT name FROM sqlite_master WHERE type='index' AND name LIKE 'idx_%_section'")}
        kept = upgraded.execute(
            "SELECT value, version FROM config_items "
            "WHERE device_id='SW-CORE-01' AND field_key='AppSelLane1'").fetchone()
        field_count = upgraded.execute("SELECT COUNT(*) FROM fields").fetchone()[0]
        upgraded.close()
        check("Legacy database upgrade without 'no such column: section'",
              {"section", "name_en"} <= cols_f and {"section", "label_en"} <= cols_c
              and len(idx) == 2 and field_count == 64
              and kept["value"] == "0x99" and kept["version"] == 7,
              f"fields={field_count} indexes={len(idx)} kept_value={kept['value']}")

        return finish(proc, tmp)
    except Exception as exc:
        import traceback
        check("Test harness raised no exception", False, repr(exc) + "\n" + traceback.format_exc())
        return finish(proc, tmp)


def finish(proc, tmp) -> int:
    proc.terminate()
    try:
        out, _ = proc.communicate(timeout=6)
    except subprocess.TimeoutExpired:
        proc.kill()
        out, _ = proc.communicate(timeout=3)
    if out and FAIL:
        print("\n--- service output (tail) ---")
        print("\n".join(out.splitlines()[-12:]))
    import shutil
    shutil.rmtree(tmp, ignore_errors=True)
    print(f"\nResult: {len(PASS)} passed / {len(FAIL)} failed")
    if FAIL:
        print("Failed: " + ", ".join(FAIL))
    return 1 if FAIL else 0


if __name__ == "__main__":
    sys.exit(main())
