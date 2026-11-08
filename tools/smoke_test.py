"""End-to-end smoke test: start the local service, exercise the REST API,
static assets, error handling and the CMIS/CDB partition endpoints, then stop.

Usage: python tools/smoke_test.py
No third-party dependencies. A temporary database is used so the delivered
data/cmis.db is never modified.
"""

from __future__ import annotations

import json
import os
import re
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

# Historic partition key used by pre-5.3 builds. Composed at runtime so the
# retired abbreviation is not part of the delivered vocabulary.
LEGACY_MONITORING_KEY = "".join(word[0] for word in
                                ("Digital", "Optical", "Monitoring"))


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
    targets_path = Path(tmp) / "targets.json"
    env = {**os.environ,
           "CMIS_HOST": "127.0.0.1",
           "CMIS_PORT": str(port),
           "CMIS_DB_FILE": str(Path(tmp) / "smoke.db"),
           "CMIS_TARGETS_FILE": str(targets_path),
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

        # Editable target registry: switch the test interface and add a device
        # through configuration alone. A temp registry keeps the operator's
        # config/targets.json untouched.
        st, p = req("GET", "/api/targets")
        tg = p["data"] if st == 200 else {}
        tg_modes = {t["access_mode"] for t in tg.get("targets", [])}
        check("Target registry: example fallback, modes and editable fields",
              st == 200 and len(tg.get("targets", [])) == 3
              and tg_modes == {"mirror", "ssh-i2c", "rest-api"}
              and len(tg.get("access_modes", [])) == 3
              and {"host", "port", "access_mode", "token_env"} <= set(tg.get("fields", {}))
              and "token" in tg.get("credential_fields_forbidden", [])
              and tg.get("writable") is True,
              f"targets={len(tg.get('targets', []))} modes={sorted(tg_modes)}")
        check("Target registry endpoints advertised in meta",
              {"GET /api/targets", "PUT /api/targets", "POST /api/targets/probe"}
              <= set(req("GET", "/api/meta")[1]["data"].get("endpoints", [])))
        st, p = req("POST", "/api/targets/probe", {"device_id": "DEMO-MIRROR"})
        check("Probe a target by device_id (mirror)",
              st == 200 and p["data"]["probe"]["ok"] is True
              and p["data"]["access_mode"] == "mirror"
              and p["data"]["target"]["device_id"] == "DEMO-MIRROR")
        st, p = req("GET", "/api/access")
        check("Access view reports active target",
              st == 200 and p["data"]["targets"]["active_target"] == "DEMO-MIRROR"
              and p["data"]["targets"]["count"] == 3)

        registry = {
            "version": 1,
            "active_target": "SMOKE-NEW",
            "targets": [
                {"device_id": "SMOKE-NEW", "name": "New device via config",
                 "access_mode": "mirror", "host": "", "port": 0},
                {"device_id": "SMOKE-SSH", "name": "SSH + I2C endpoint",
                 "access_mode": "ssh-i2c", "host": "127.0.0.1", "port": 22,
                 "ssh_user": "lab", "i2c_bus": "0", "i2c_addr": "0x50"},
                {"device_id": "SMOKE-REST", "name": "REST endpoint",
                 "access_mode": "rest-api", "host": "127.0.0.1", "port": 8443,
                 "rest_scheme": "https", "rest_base_path": "/api",
                 "token_env": "CMIS_REST_TOKEN", "module_ids": ["OSFP-NEW"]},
            ],
        }
        st, p = req("PUT", "/api/targets", registry)
        check("Save a new target device registry (add devices by config)",
              st == 200 and p["data"]["saved"] is True
              and len(p["data"]["targets"]) == 3
              and p["data"]["active_target"] == "SMOKE-NEW",
              f"status={st} targets={len(p['data'].get('targets', []))}")
        st, p = req("GET", "/api/targets")
        check("Saved registry is immediately visible",
              st == 200 and {t["device_id"] for t in p["data"]["targets"]}
              == {"SMOKE-NEW", "SMOKE-SSH", "SMOKE-REST"})
        raw_registry = targets_path.read_bytes()
        check("Registry persisted as UTF-8 with LF endings",
              b"\r\n" not in raw_registry and b"SMOKE-REST" in raw_registry
              and json.loads(raw_registry)["active_target"] == "SMOKE-NEW")
        st, p = req("POST", "/api/targets/probe", {"device_id": "SMOKE-NEW"})
        check("New device is usable without a service restart",
              st == 200 and p["data"]["probe"]["ok"] is True
              and p["data"]["device_id"] == "SMOKE-NEW")
        st, p = req("POST", "/api/cdb/execute",
                    {"device_id": "SMOKE-NEW", "cmd_id": "0040", "lpl_hex": "00 01",
                     "confirm": "EXECUTE", "operator": "smoke-test"})
        check("CDB accepts a device defined only in the target registry",
              st == 200 and p["data"]["result"] == "staged"
              and p["data"]["applied_to_hardware"] is False,
              f"status={st} code={p.get('error', {}).get('code', '-')}")
        bad = {**registry, "targets": registry["targets"] + [
            {"device_id": "SMOKE-BAD", "access_mode": "rest-api",
             "host": "127.0.0.1", "token": "must-never-be-stored"}]}
        st, p = req("PUT", "/api/targets", bad)
        check("Literal credentials rejected by target validation",
              st == 400 and p["error"]["code"] == "TARGETS_VALIDATION_FAILED"
              and any("credential" in e for e in p["error"]["details"]["errors"]))
        st, p = req("PUT", "/api/targets",
                    {**registry, "targets": [{"device_id": "X", "access_mode": "telnet"}]})
        check("Unknown access_mode rejected", st == 400
              and p["error"]["code"] == "TARGETS_VALIDATION_FAILED")
        st, p = req("PUT", "/api/targets",
                    {**registry, "targets": [registry["targets"][0],
                                             dict(registry["targets"][0])]})
        check("Duplicate device_id rejected", st == 400
              and p["error"]["code"] == "TARGETS_VALIDATION_FAILED")
        st, p = req("GET", "/api/targets")
        check("Failed saves leave the registry unchanged",
              st == 200 and len(p["data"]["targets"]) == 3
              and "token" not in json.loads(targets_path.read_text(encoding="utf-8")).get(
                  "targets", [{}])[0])

        # Device-level settings are resolved from the registry without changing
        # adapter internals, so the same adapter serves several test setups.
        from cmis_service import targets as targetsmod
        base_settings = load_settings()
        reg = targetsmod.load_registry(targets_path)
        eff_rest = targetsmod.resolve_settings(
            base_settings, targetsmod.find_target(reg, "SMOKE-REST"))
        eff_ssh = targetsmod.resolve_settings(
            base_settings, targetsmod.find_target(reg, "SMOKE-SSH"))
        eff_mirror = targetsmod.resolve_settings(
            base_settings, targetsmod.find_target(reg, "SMOKE-NEW"))
        check("Device-level transport resolution (rest / ssh / mirror)",
              eff_rest.access_mode == "rest-api"
              and eff_rest.rest_base_url == "https://127.0.0.1:8443/api"
              and eff_ssh.access_mode == "ssh-i2c" and eff_ssh.ssh_host == "127.0.0.1"
              and eff_ssh.ssh_port == 22
              and eff_mirror.access_mode == "mirror"
              and base_settings.access_mode == "mirror",
              f"rest={eff_rest.rest_base_url} ssh={eff_ssh.access_mode}:{eff_ssh.ssh_port} "
              f"global={base_settings.access_mode}")
        public_rest = targetsmod.public_target(targetsmod.find_target(reg, "SMOKE-REST"))
        check("Token stays an environment-variable reference",
              eff_rest.rest_token_env == "CMIS_REST_TOKEN"
              and public_rest["token_env"] == "CMIS_REST_TOKEN"
              and "token_present" in public_rest
              and not any(k in public_rest for k in targetsmod.SENSITIVE_KEYS))

        st, p = req("GET", "/api/sections")
        sec = p["data"]
        check("CMIS partition definitions", st == 200 and len(sec["items"]) == 4)
        sec_keys = [s["key"] for s in sec["items"]]
        check("Partitions use VDM terminology (no retired section key)",
              set(sec_keys) == {"LOW_PAGE", "VDM", "CDB", "CONTROL"}
              and LEGACY_MONITORING_KEY not in sec_keys
              and all(LEGACY_MONITORING_KEY not in (s.get("en", "") + s.get("zh", ""))
                      for s in sec["items"]),
              f"keys={sec_keys}")
        st, p = req("GET", "/api/sections/VDM")
        check("VDM partition detail", st == 200 and p["data"]["section"]["key"] == "VDM"
              and p["data"]["fields"])
        st, p = req("GET", "/api/cmis/module?device_id=SW-CORE-01&section=VDM")
        check("Module CMIS VDM partition items",
              st == 200 and p["data"]["sections"][0]["key"] == "VDM"
              and len(p["data"]["sections"][0]["items"]) > 0)
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

        # Knowledge assets live in a dedicated directory with machine-readable
        # links and offline copies of the two primary OIF specifications.
        knowledge = ROOT / "knowledge"
        required_knowledge = ("README.md", "SCHEMA.md", "SOURCES.md", "links.json",
                              "CMIS_KNOWLEDGE_GRAPH.md", "specs/README.md")
        check("Dedicated knowledge directory with all documents",
              all((knowledge / name).is_file() for name in required_knowledge),
              ", ".join(required_knowledge))
        links = json.loads((knowledge / "links.json").read_text(encoding="utf-8"))
        by_id = {s["source_id"]: s for s in links.get("sources", [])}
        external = [s for s in by_id.values() if s.get("kind") != "internal_dataset"]
        check("Machine-readable canonical source links",
              links.get("count") == 38 and len(by_id) == 38
              and all(s.get("url", "").startswith(("http://", "https://"))
                      for s in external)
              and by_id["S-OIF-053"]["url"].endswith("OIF-CMIS-05.3.pdf")
              and by_id["S-OIF-054"]["url"].endswith("OIF-CMIS-05.4.pdf")
              and by_id["S-OIF-053"]["bundled_copy"]
              and by_id["S-OIF-054"]["bundled_copy"],
              f"count={links.get('count')}")
        check("OIF canonical links also documented for humans",
              "OIF-CMIS-05.3.pdf" in (knowledge / "specs" / "README.md").read_text("utf-8")
              and "OIF-CMIS-05.4.pdf" in (knowledge / "SOURCES.md").read_text("utf-8"))
        pdf_ok, pdf_sizes = [], {}
        for name in ("OIF-CMIS-05.3.pdf", "OIF-CMIS-05.4.pdf"):
            spec_path = knowledge / "specs" / name
            if not spec_path.is_file():
                pdf_ok.append(False)
                pdf_sizes[name] = 0
                continue
            blob = spec_path.read_bytes()
            pdf_sizes[name] = len(blob)
            pdf_ok.append(blob.startswith(b"%PDF-") and b"%%EOF" in blob[-2048:]
                          and len(blob) > 100_000)
        check("Bundled OIF CMIS 5.3 / 5.4 PDF copies are complete",
              all(pdf_ok), str(pdf_sizes))

        # Terminology and credential hygiene across every delivered text file.
        scan_exts = {".py", ".js", ".html", ".css", ".json", ".md", ".ini",
                     ".example", ".txt", ".gitattributes"}
        scan_skip = {".git", ".workbuddy", "vendor", "__pycache__", "specs"}
        # Built at runtime so the scanner itself carries no token-shaped text.
        secret_markers = ("gh" + "p_", "git" + "hub_pat_", "gh" + "o_",
                          "gh" + "s_", "gh" + "u_", "gl" + "pat-")
        residual, leaks = [], []
        for p in ROOT.rglob("*"):
            if not p.is_file() or any(part in scan_skip for part in p.parts):
                continue
            if p.suffix not in scan_exts and p.name not in ("LICENSE", "NOTICE", ".gitignore"):
                continue
            try:
                text = p.read_text(encoding="utf-8")
            except (OSError, UnicodeDecodeError):
                continue
            rel = str(p.relative_to(ROOT))
            if re.search(r"\b" + LEGACY_MONITORING_KEY + r"\b", text):
                residual.append(rel)
            if any(marker in text for marker in secret_markers):
                leaks.append(rel)
        check("No retired monitoring abbreviation remains in shipped text",
              not residual, ", ".join(residual) if residual else "sources and docs clean")
        check("No hard-coded access tokens in shipped files",
              not leaks, ", ".join(leaks) if leaks else "no token-shaped strings")
        gitignore = (ROOT / ".gitignore").read_text(encoding="utf-8")
        check("Runtime data, operator inventory and local state stay out of git",
              "config/targets.json" in gitignore and "data/cmis.db" in gitignore
              and ".workbuddy/" in gitignore
              and not (ROOT / "config" / "targets.json").exists(),
              f"ignore_entries=3 operator_file_exists="
              f"{(ROOT / 'config' / 'targets.json').exists()}")
        check("Deployment and operations guides are present and in English",
              all((ROOT / "docs" / n).is_file() for n in ("DEPLOYMENT.md", "OPERATIONS.md"))
              and "Portability" in (ROOT / "docs" / "DEPLOYMENT.md").read_text("utf-8")
              and "Troubleshooting" in (ROOT / "docs" / "OPERATIONS.md").read_text("utf-8"))

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
