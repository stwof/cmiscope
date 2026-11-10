#!/usr/bin/env python3
"""Regression checks for source cleanup and strict access-mode exclusivity.

Standard library only. Covers:

  * no external repository source assets or residual references remain,
  * the CMIScope-normalized dataset rebuilds the read-only reference layer,
  * ssh+i2c and restful API never appear, submit or take effect together.

Usage: python tools/test_access_modes.py
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from cmis_service import targets  # noqa: E402
from cmis_service.config import load_settings, public_settings  # noqa: E402

PASS, FAIL = [], []


def check(name: str, condition: bool, detail: str = "") -> None:
    (PASS if condition else FAIL).append(name)
    print(f"{'PASS' if condition else 'FAIL'}  {name}" + (f"  | {detail}" if detail else ""))


SSH_KEYS = set(targets.MODE_FIELD_KEYS["ssh-i2c"])
REST_KEYS = set(targets.MODE_FIELD_KEYS["rest-api"])


def one(raw: dict) -> tuple[dict, list[str]]:
    return targets.validate_registry({"version": 1, "active_target": "",
                                      "targets": [raw]})


def source_cleanup_checks() -> None:
    check("No vendored external asset directory",
          not (ROOT / "data" / "".join(("up", "stream"))).exists())
    dataset = ROOT / "data" / "cmis53_dataset.json"
    reference = ROOT / "data" / "cmis53_reference.json"
    check("Project-owned normalized dataset exists", dataset.is_file())
    if dataset.is_file():
        data = json.loads(dataset.read_text(encoding="utf-8"))
        check("Dataset holds the full 2442/48 normalized rows",
              len(data.get("fields", [])) == 2442
              and len(data.get("cdb_commands", [])) == 48)
    if reference.is_file():
        ref = json.loads(reference.read_text(encoding="utf-8"))
        check("Generated reference still carries 2442 fields / 48 commands",
              len(ref.get("fields", [])) == 2442
              and len(ref.get("cdb_commands", [])) == 48)
        check("Generated reference declares the project-owned dataset",
              "cmis53_dataset.json" in str(ref.get("meta", {}).get("dataset", "")))

    scan_skip = {".git", ".workbuddy", "__pycache__", "vendor", "specs"}
    scan_exts = {".py", ".js", ".html", ".css", ".json", ".md", ".ini", ".example"}
    # Built at runtime (join, not literal concatenation) so neither this file
    # nor its bytecode cache contains the markers being searched for.
    parts = ("jim", "fred", "Jim", " Frederick", "data/", "up", "stream",
             "github.com/")
    names = ("".join(parts[0:2]), "".join(parts[2:4]), "".join(parts[4:7]),
             parts[7] + "".join(parts[0:2]))
    markers = re.compile("|".join(re.escape(n) for n in names), re.I)
    bad = []
    for path in ROOT.rglob("*"):
        if not path.is_file() or any(part in scan_skip for part in path.parts):
            continue
        if path.suffix not in scan_exts and path.name not in ("NOTICE", "LICENSE"):
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        if markers.search(text):
            bad.append(str(path.relative_to(ROOT)))
    check("No residual external repository references in shipped text",
          not bad, ", ".join(bad[:5]))


def mutual_exclusion_checks() -> None:
    ssh = {"device_id": "LAB-SSH", "access_mode": "ssh-i2c", "host": "192.0.2.10",
           "port": 22, "ssh_user": "lab", "i2c_bus": "0", "i2c_addr": "0x50"}
    rest = {"device_id": "LAB-REST", "access_mode": "rest-api", "host": "192.0.2.20",
            "port": 443, "rest_scheme": "https", "rest_base_path": "/api",
            "token_env": "CMIS_REST_TOKEN"}

    cleaned, errors = one(dict(ssh))
    item = cleaned["targets"][0] if cleaned["targets"] else {}
    check("ssh-i2c target keeps only ssh fields",
          not errors and SSH_KEYS <= set(item) and not (REST_KEYS & set(item)),
          str(sorted(set(item) & (SSH_KEYS | REST_KEYS))))
    check("ssh-i2c target exposes no token metadata",
          "token_present" not in targets.public_target(item))

    cleaned, errors = one(dict(rest))
    item = cleaned["targets"][0] if cleaned["targets"] else {}
    check("rest-api target keeps only REST fields",
          not errors and REST_KEYS <= set(item) and not (SSH_KEYS & set(item)),
          str(sorted(set(item) & (SSH_KEYS | REST_KEYS))))
    check("rest-api target still exposes token_env name",
          targets.public_target(item).get("token_env") == "CMIS_REST_TOKEN")

    cleaned, errors = one({"device_id": "DEMO", "access_mode": "mirror"})
    item = cleaned["targets"][0] if cleaned["targets"] else {}
    check("mirror target carries neither transport's fields",
          not errors and not ((SSH_KEYS | REST_KEYS) & set(item)))

    mixed_ssh = {**ssh, "rest_scheme": "https", "token_env": "CMIS_REST_TOKEN"}
    cleaned, errors = one(mixed_ssh)
    check("ssh-i2c + rest fields rejected on submission",
          bool(errors) and not cleaned["targets"]
          and any("unselected access mode" in e for e in errors))

    mixed_rest = {**rest, "ssh_user": "lab", "i2c_bus": "0"}
    cleaned, errors = one(mixed_rest)
    check("rest-api + ssh fields rejected on submission",
          bool(errors) and not cleaned["targets"])

    mirror_mixed = {"device_id": "M", "access_mode": "mirror", "ssh_user": "lab"}
    cleaned, errors = one(mirror_mixed)
    check("mirror + transport fields rejected", bool(errors) and not cleaned["targets"])

    registry, errors = targets.validate_registry(
        {"targets": [dict(ssh), dict(rest)]})
    check("Registry may contain different devices in different modes",
          not errors and len(registry["targets"]) == 2
          and all(not (SSH_KEYS & REST_KEYS & set(t)) for t in registry["targets"]))

    check("Field metadata declares mode ownership",
          all("modes" in meta for meta in targets.TARGET_FIELDS.values())
          and targets.TARGET_FIELDS["ssh_user"]["modes"] == "ssh-i2c"
          and targets.TARGET_FIELDS["token_env"]["modes"] == "rest-api"
          and targets.TARGET_FIELDS["host"]["modes"] == "ssh-i2c,rest-api")


def runtime_checks() -> None:
    ssh = {"device_id": "LAB-SSH", "access_mode": "ssh-i2c", "host": "192.0.2.10",
           "port": 22, "ssh_user": "lab", "i2c_bus": "0", "i2c_addr": "0x50"}
    rest = {"device_id": "LAB-REST", "access_mode": "rest-api", "host": "192.0.2.20",
            "port": 8443, "rest_scheme": "https", "rest_base_path": "/api",
            "token_env": "CMIS_REST_TOKEN"}

    base = load_settings(environ={
        "CMIS_ACCESS_MODE": "mirror",
        "CMIS_SSH_HOST": "192.0.2.99",
        "CMIS_REST_BASE_URL": "https://192.0.2.99/api",
    })
    check("Global mirror mode disables both transports",
          base.ssh_host == "" and base.rest_base_url == ""
          and "ssh" not in public_settings(base) and "rest" not in public_settings(base))

    global_ssh = load_settings(environ={
        "CMIS_ACCESS_MODE": "ssh-i2c", "CMIS_SSH_HOST": "192.0.2.10",
        "CMIS_REST_BASE_URL": "https://192.0.2.99/api"})
    check("Global ssh-i2c mode disables REST endpoint",
          global_ssh.ssh_host == "192.0.2.10" and global_ssh.rest_base_url == ""
          and "ssh" in public_settings(global_ssh)
          and "rest" not in public_settings(global_ssh))

    global_rest = load_settings(environ={
        "CMIS_ACCESS_MODE": "rest-api", "CMIS_SSH_HOST": "192.0.2.10",
        "CMIS_REST_BASE_URL": "https://192.0.2.99/api"})
    check("Global rest-api mode disables SSH endpoint",
          global_rest.ssh_host == "" and global_rest.rest_base_url.startswith("https://")
          and "rest" in public_settings(global_rest)
          and "ssh" not in public_settings(global_rest))

    eff_ssh = targets.resolve_settings(base, one(dict(ssh))[0]["targets"][0])
    check("Resolved ssh-i2c target cannot fall through to REST",
          eff_ssh.access_mode == "ssh-i2c" and eff_ssh.ssh_host == "192.0.2.10"
          and eff_ssh.rest_base_url == "" and eff_ssh.rest_token_env == "")

    eff_rest = targets.resolve_settings(base, one(dict(rest))[0]["targets"][0])
    check("Resolved rest-api target cannot fall through to SSH",
          eff_rest.access_mode == "rest-api"
          and eff_rest.rest_base_url == "https://192.0.2.20:8443/api"
          and eff_rest.ssh_host == "")

    eff_mirror = targets.resolve_settings(base, one(
        {"device_id": "M", "access_mode": "mirror"})[0]["targets"][0])
    check("Resolved mirror target has no active endpoint",
          eff_mirror.access_mode == "mirror" and eff_mirror.ssh_host == ""
          and eff_mirror.rest_base_url == "")


def api_checks() -> None:
    import tempfile

    from cmis_service import api

    tmp = Path(tempfile.mkdtemp(prefix="cmiscope-modes-")) / "targets.json"
    settings = load_settings(environ={"CMIS_TARGETS_FILE": str(tmp)})
    mixed = {"device_id": "MIXED", "access_mode": "ssh-i2c", "host": "192.0.2.10",
             "ssh_user": "lab", "rest_scheme": "https", "token_env": "CMIS_REST_TOKEN"}
    rejected = False
    try:
        api.save_targets(settings, {"version": 1, "active_target": "MIXED",
                                    "targets": [mixed]})
    except api.ApiError as exc:
        rejected = exc.status == 400 and exc.code == "TARGETS_VALIDATION_FAILED"
    check("PUT /api/targets rejects a mixed-mode submission", rejected)
    check("Rejected save leaves no registry on disk", not tmp.exists())

    good = [
        {"device_id": "LAB-SSH", "access_mode": "ssh-i2c", "host": "192.0.2.10",
         "ssh_user": "lab"},
        {"device_id": "LAB-REST", "access_mode": "rest-api", "host": "192.0.2.20",
         "rest_scheme": "https", "token_env": "CMIS_REST_TOKEN"},
    ]
    targets.save_registry(tmp, {"version": 1, "active_target": "LAB-SSH", "targets": good})
    status, payload = api.list_targets(settings)
    rows = payload.get("data", {}).get("targets", [])
    check("GET /api/targets returns only one mode per device",
          status == 200 and len(rows) == 2
          and all(not (SSH_KEYS & set(r)) or not (REST_KEYS & set(r)) for r in rows)
          and "mode_fields" in payload["data"])


def frontend_checks() -> None:
    html = (ROOT / "cmis_service" / "static" / "index.html").read_text(encoding="utf-8")
    js = (ROOT / "cmis_service" / "static" / "js" / "app.js").read_text(encoding="utf-8")
    ssh_boxes = re.findall(r'data-tg-modes="([^"]*)"[\s\S]*?data-tg="([^"]*)"', html)
    mode_boxes = [m for m, _ in ssh_boxes]
    check("Editor marks mode-specific field groups",
          set(mode_boxes) == {"ssh-i2c", "rest-api", "ssh-i2c rest-api"}
          and len([m for m in mode_boxes if m == "ssh-i2c"]) == 3
          and len([m for m in mode_boxes if m == "rest-api"]) == 3)
    check("Editor hides inactive groups and reads only visible inputs",
          "syncTargetModeFields" in js and "box.hidden" in js
          and "data-tg-modes" in js and "TG_MODE_KEYS" in js)
    check("Form strips keys owned by the unselected mode",
          "TG_ALL_MODE_KEYS" in js and "delete obj[k]" in js)


def validation_edge_checks() -> None:
    """Boundary and exception cases of the registry validator."""
    _, errors = one({"device_id": "X", "access_mode": "telnet"})
    check("Unknown access_mode is rejected",
          bool(errors) and "access_mode must be one of" in errors[0])

    cleaned, errors = one({"device_id": "X", "access_mode": " SSH-I2C ",
                           "host": "192.0.2.1", "ssh_user": "u"})
    check("access_mode is case- and whitespace-normalized",
          not errors and cleaned["targets"][0]["access_mode"] == "ssh-i2c")

    # An inactive-mode key is refused even when its value is empty or null:
    # presence, not content, decides ownership.
    for key in ("ssh_user", "i2c_bus", "i2c_addr"):
        _, errors = one({"device_id": "X", "access_mode": "rest-api",
                         "host": "h", key: ""})
        check(f"Empty {key} on a rest-api target is still rejected", bool(errors))
    for key in ("rest_scheme", "rest_base_path", "token_env"):
        _, errors = one({"device_id": "X", "access_mode": "ssh-i2c",
                         "host": "h", key: None})
        check(f"Null {key} on an ssh-i2c target is still rejected", bool(errors))

    cleaned, errors = one({"device_id": "X", "access_mode": "mirror", "bogus": 123})
    check("Unknown keys are ignored, not stored",
          not errors and "bogus" not in cleaned["targets"][0])
    _, errors = one({"device_id": "X", "access_mode": "mirror", "password": "p"})
    check("Literal credential fields are rejected",
          bool(errors) and "credential" in errors[0])
    _, errors = targets.validate_registry({"targets": [1]})
    check("Non-object target entries are rejected", bool(errors))
    _, errors = targets.validate_registry({"targets": [
        {"device_id": "DUP", "access_mode": "mirror"},
        {"device_id": "DUP", "access_mode": "mirror"}]})
    check("Duplicate device_id is rejected", len(errors) == 1 and "duplicate" in errors[0])
    _, errors = one({"device_id": "bad id!", "access_mode": "mirror"})
    check("Invalid device_id is rejected", bool(errors))
    _, errors = one({"device_id": "X", "access_mode": "ssh-i2c"})
    check("Connected mode without host is rejected", bool(errors))
    _, errors = one({"device_id": "X", "access_mode": "ssh-i2c", "host": "a;rm -rf"})
    check("Host with shell metacharacters is rejected", bool(errors))
    cleaned, errors = one({"device_id": "X", "access_mode": "rest-api", "host": "[::1]"})
    check("Bracketed IPv6 host is accepted", not errors)

    for port, valid in ((0, True), (1, True), (65535, True), (65536, False),
                        (-1, False), ("abc", False)):
        _, errors = one({"device_id": "X", "access_mode": "ssh-i2c",
                         "host": "h", "port": port})
        check(f"Port boundary {port!r} handled", bool(errors) != valid,
              "; ".join(errors)[:80])
    _, errors = one({"device_id": "X", "access_mode": "rest-api",
                     "host": "h", "rest_scheme": "ftp"})
    check("Invalid rest_scheme is rejected", bool(errors))
    cleaned, errors = one({"device_id": "X", "access_mode": "rest-api",
                           "host": "h", "rest_scheme": "HTTPS"})
    check("rest_scheme is normalized to lowercase",
          not errors and cleaned["targets"][0]["rest_scheme"] == "https")
    _, errors = one({"device_id": "X", "access_mode": "mirror",
                     "module_ids": "not-a-list"})
    check("Non-list module_ids is rejected", bool(errors))
    cleaned, errors = one({"device_id": "X", "access_mode": "mirror",
                           "enabled": "false", "notes": "n" * 400})
    item = cleaned["targets"][0]
    check("String boolean and overlong notes are normalized",
          not errors and item["enabled"] is False and len(item["notes"]) == 300)

    registry, errors = targets.validate_registry({"active_target": "GHOST", "targets": [
        {"device_id": "A", "access_mode": "mirror"}]})
    check("Unknown active_target falls back to the first enabled device",
          bool(errors) and registry["active_target"] == "A")
    registry, errors = targets.validate_registry({"targets": [
        {"device_id": "A", "access_mode": "mirror", "enabled": False}]})
    check("All-disabled registry has no active target", registry["active_target"] == "")

    for bad in ("not-an-object", {"targets": "nope"}):
        registry, errors = targets.validate_registry(bad)
        check("Malformed registry root degrades to an empty registry",
              bool(errors) and registry == targets.empty_registry())


def public_and_resolve_edge_checks() -> None:
    """public_target and resolve_settings boundary behaviour."""
    import os

    check("public_target(None) is an empty view", targets.public_target(None) == {})
    ssh = {"device_id": "S", "access_mode": "ssh-i2c", "ssh_user": "u"}
    check("public_target never adds token metadata to ssh targets",
          "token_present" not in targets.public_target(ssh))
    rest = {"device_id": "R", "access_mode": "rest-api",
            "token_env": "CMISCOPE_TEST_TOKEN_DO_NOT_SET"}
    previous = os.environ.pop("CMISCOPE_TEST_TOKEN_DO_NOT_SET", None)
    try:
        view = targets.public_target(rest)
        check("public_target reports a missing REST token as absent",
              view.get("token_present") is False
              and view.get("token_env") == "CMISCOPE_TEST_TOKEN_DO_NOT_SET")
        os.environ["CMISCOPE_TEST_TOKEN_DO_NOT_SET"] = "dummy-value"
        view = targets.public_target(rest)
        check("public_target reports a present token without exposing its value",
              view.get("token_present") is True
              and "dummy-value" not in json.dumps(view))
    finally:
        os.environ.pop("CMISCOPE_TEST_TOKEN_DO_NOT_SET", None)
        if previous is not None:
            os.environ["CMISCOPE_TEST_TOKEN_DO_NOT_SET"] = previous

    base = load_settings(environ={"CMIS_ACCESS_MODE": "mirror"})
    check("Disabled target resolves to the untouched base settings",
          targets.resolve_settings(base, {"device_id": "D", "enabled": False,
                                          "access_mode": "rest-api"}) == base)
    check("Unknown mode resolves to the untouched base settings",
          targets.resolve_settings(base, {"device_id": "D", "access_mode": "telnet"}) == base)
    check("resolve_settings(None) returns the base settings",
          targets.resolve_settings(base, None) == base)

    cases = [
        ({"rest_scheme": "https", "port": 443, "rest_base_path": "/api/"},
         "https://h/api"),
        ({"rest_scheme": "http", "port": 80, "rest_base_path": ""},
         "http://h"),
        ({"rest_scheme": "https", "port": 8443, "rest_base_path": "/api/"},
         "https://h:8443/api"),
        ({"rest_scheme": "http", "port": 8080, "rest_base_path": "/v1/device/"},
         "http://h:8080/v1/device"),
    ]
    for extra, expected in cases:
        raw = {"device_id": "R", "access_mode": "rest-api", "host": "h", **extra}
        eff = targets.resolve_settings(base, one(raw)[0]["targets"][0])
        check(f"REST URL built correctly for {extra}",
              eff.rest_base_url == expected and eff.ssh_host == "",
              f"got {eff.rest_base_url!r}, expected {expected!r}")

    eff = targets.resolve_settings(base, one(
        {"device_id": "S", "access_mode": "ssh-i2c", "host": "h",
         "port": 22})[0]["targets"][0])
    check("ssh target inherits global I2C defaults but no REST endpoint",
          eff.ssh_host == "h" and eff.i2c_addr == "0x50"
          and eff.rest_base_url == "" and eff.rest_token_env == "")


def config_ini_edge_checks() -> None:
    """Both ini sections present at once: only the selected mode may survive."""
    import tempfile

    ini = """[server]
host = 127.0.0.1
port = 8787

[app]
access_mode = MODE_TOKEN

[ssh]
host = 192.0.2.10
user = lab
port = 22
i2c_bus = 1
i2c_addr = 0x51

[rest]
base_url = https://192.0.2.20/api
token_env = CMIS_REST_TOKEN
"""
    with tempfile.TemporaryDirectory(prefix="cmiscope-ini-") as name:
        path = Path(name) / "config.ini"
        for mode, expect_ssh, expect_rest in (
                ("ssh-i2c", True, False), ("rest-api", False, True),
                ("mirror", False, False)):
            path.write_text(ini.replace("MODE_TOKEN", mode), encoding="utf-8")
            settings = load_settings(config_path=path, environ={})
            view = public_settings(settings)
            check(f"ini with both transports: {mode} activates only that mode",
                  (settings.ssh_host != "") == expect_ssh
                  and (settings.rest_base_url != "") == expect_rest
                  and ("ssh" in view) == expect_ssh
                  and ("rest" in view) == expect_rest)
        path.write_text(ini.replace("MODE_TOKEN", "mirror"), encoding="utf-8")
        env_override = load_settings(config_path=path,
                                     environ={"CMIS_ACCESS_MODE": "rest-api"})
        check("Environment access_mode overrides ini and re-applies exclusion",
              env_override.access_mode == "rest-api"
              and env_override.rest_base_url.startswith("https://")
              and env_override.ssh_host == "")

    bad_values = [
        ({"CMIS_ACCESS_MODE": "telnet"}, "access_mode must be one of"),
        ({"CMIS_PORT": "70000"}, "Port out of range"),
        ({"CMIS_MAX_BODY_BYTES": "10"}, "at least 1024"),
        ({"CMIS_DEFAULT_LANGUAGE": "fr"}, "default_language"),
    ]
    for env, needle in bad_values:
        try:
            load_settings(environ=env)
        except ValueError as exc:
            check(f"Invalid setting {env} rejected", needle in str(exc), str(exc)[:70])
        else:
            check(f"Invalid setting {env} rejected", False, "was accepted")


def api_end_to_end_checks() -> None:
    """Save, reject, display and resolve through the real API helpers."""
    import tempfile

    from cmis_service import api

    with tempfile.TemporaryDirectory(prefix="cmiscope-api-") as name:
        tmp = Path(name) / "targets.json"
        settings = load_settings(environ={"CMIS_TARGETS_FILE": str(tmp)})

        def expect_error(name, call, status_expected, code_expected):
            try:
                call()
            except api.ApiError as exc:
                check(name, exc.status == status_expected and exc.code == code_expected,
                      f"{exc.status} {exc.code}")
            else:
                check(name, False, "request was accepted")

        expect_error("PUT with a non-object body is rejected",
                     lambda: api.save_targets(settings, [1, 2]), 400, "BAD_REQUEST")
        mixed = {"device_id": "MIX", "access_mode": "ssh-i2c", "host": "h",
                 "ssh_user": "u", "rest_scheme": "https"}
        try:
            api.save_targets(settings, {"targets": [mixed]})
        except api.ApiError as exc:
            check("PUT mixed-mode error carries the validator diagnostics",
                  exc.status == 400 and exc.code == "TARGETS_VALIDATION_FAILED"
                  and any("unselected access mode" in e
                          for e in exc.details.get("errors", [])))
        else:
            check("PUT mixed-mode error carries the validator diagnostics", False)
        check("A rejected save never writes the registry", not tmp.exists())

        good = [
            {"device_id": "S", "access_mode": "ssh-i2c", "host": "192.0.2.10",
             "ssh_user": "lab", "i2c_bus": "0", "i2c_addr": "0x50"},
            {"device_id": "R", "access_mode": "rest-api", "host": "192.0.2.20",
             "port": 443, "rest_scheme": "https", "token_env": "CMIS_REST_TOKEN"},
        ]
        status, body = api.save_targets(settings, {"version": 1, "active_target": "S",
                                                   "targets": good})
        on_disk = json.loads(tmp.read_text(encoding="utf-8"))["targets"]
        check("PUT returns success and persists the registry",
              status == 200 and body["data"].get("saved") is True
              and len(on_disk) == 2)
        check("Persisted file contains only one mode per device",
              all(not (SSH_KEYS & set(t)) or not (REST_KEYS & set(t)) for t in on_disk))
        check("PUT response also contains only one mode per device",
              all(not (SSH_KEYS & set(t)) or not (REST_KEYS & set(t))
                  for t in body["data"]["targets"]))

        status, body = api.list_targets(settings)
        data = body["data"]
        check("GET /api/targets advertises modes, per-mode fields and the rule",
              status == 200 and data["access_modes"] == list(targets.ACCESS_MODES)
              and all(k in data["mode_fields"] for k in targets.ACCESS_MODES)
              and "mutually exclusive" in data["note"])
        check("GET /api/targets field metadata matches backend ownership",
              all(data["fields"][key]["modes"] ==
                  targets.TARGET_FIELDS[key]["modes"] for key in data["fields"]))

        effective_ssh, target_ssh = api._device_settings(settings, "S")
        effective_rest, target_rest = api._device_settings(settings, "R")
        check("Resolving an ssh target leaves no REST endpoint",
              effective_ssh.ssh_host == "192.0.2.10"
              and effective_ssh.rest_base_url == ""
              and "token_present" not in targets.public_target(target_ssh))
        check("Resolving a REST target leaves no SSH endpoint",
              effective_rest.rest_base_url.startswith("https://192.0.2.20")
              and effective_rest.ssh_host == ""
              and "token_present" in targets.public_target(target_rest))

        status, body = api.access_info(None, settings)
        service = body["data"]["service"]
        check("GET /api/access exposes only the global mode's connection block",
              status == 200 and "ssh" not in service and "rest" not in service)

        # Stub the adapter so a probe never opens an SSH/REST connection; the
        # recorded Settings object still proves which transport was activated.
        seen: list = []

        class _StubAdapter:
            def __init__(self, effective):
                seen.append(effective)

            def probe(self):
                return {"ok": True, "mode": "stub", "checked": True}

        original_get_adapter = api.get_adapter
        api.get_adapter = _StubAdapter
        try:
            for device, expect_rest in (("S", False), ("R", True)):
                status, body = api.probe_target(settings, {"device_id": device})
                effective = seen[-1]
                check(f"Probe of {device} activates exactly one transport",
                      status == 200 and body["data"]["access_mode"] != "mirror"
                      and (effective.rest_base_url != "") == expect_rest
                      and (effective.ssh_host != "") == (not expect_rest))
        finally:
            api.get_adapter = original_get_adapter

        ro = load_settings(environ={"CMIS_READ_ONLY": "true",
                                    "CMIS_TARGETS_FILE": str(tmp)})
        expect_error("Read-only service refuses target saves",
                     lambda: api.save_targets(ro, {"targets": good}),
                     409, "SERVICE_READ_ONLY")


def consistency_checks() -> None:
    """Shipped examples, frontend declarations and backend must agree."""
    example = ROOT / "config" / "targets.example.json"
    registry, errors = targets.validate_registry(
        json.loads(example.read_text(encoding="utf-8")))
    check("Shipped targets.example.json passes strict validation", not errors,
          "; ".join(errors[:2]))
    check("Every shipped example target carries exactly one mode",
          all(not (SSH_KEYS & set(t)) or not (REST_KEYS & set(t))
              for t in registry["targets"]))

    ini = (ROOT / "config.ini.example").read_text(encoding="utf-8")
    active_sections = [line.strip() for line in ini.splitlines()
                       if re.match(r"^\[(ssh|rest)\]\s*$", line.strip())]
    check("config.ini.example keeps both transport sections disabled by default",
          not active_sections, str(active_sections))

    js = (ROOT / "cmis_service" / "static" / "js" / "app.js").read_text(encoding="utf-8")
    i18n = (ROOT / "cmis_service" / "static" / "js" / "i18n.js").read_text(encoding="utf-8")
    css = (ROOT / "cmis_service" / "static" / "css" / "app.css").read_text(encoding="utf-8")
    check("Frontend mode-key map matches the backend field sets",
          all(f"'{key}'" in js for key in SSH_KEYS | REST_KEYS)
          and "'mirror': []" in js)
    check("Both locales explain the mutual-exclusion rule",
          all(i18n.count(f"'tg.{k}'") == 2
              for k in ("modeHint", "modeOnly", "offlineOnly", "note")))
    check("CSS enforces hidden groups even against framework overrides",
          "#tgFormFields [data-tg-modes][hidden]" in css)

    html = (ROOT / "cmis_service" / "static" / "index.html").read_text(encoding="utf-8")
    boxes = re.findall(r'data-tg-modes="([^"]+)"[^>]*>\s*<label[^>]*>'
                       r'[\s\S]*?data-tg="([^"]+)"', html)
    ownership_ok = bool(boxes)
    for modes, key in boxes:
        expected = targets.TARGET_FIELDS.get(key, {}).get("modes", "")
        # HTML uses space-separated groups; TARGET_FIELDS uses a comma list.
        if set(expected.replace(",", " ").split()) != set(modes.split()):
            ownership_ok = False
    check("HTML field groups match TARGET_FIELDS mode ownership", ownership_ok,
          str(boxes))


def main() -> int:
    source_cleanup_checks()
    mutual_exclusion_checks()
    validation_edge_checks()
    runtime_checks()
    public_and_resolve_edge_checks()
    config_ini_edge_checks()
    api_checks()
    api_end_to_end_checks()
    frontend_checks()
    consistency_checks()
    print(f"\n{len(PASS)} passed, {len(FAIL)} failed")
    for name in FAIL:
        print(f"  FAILED: {name}")
    return 1 if FAIL else 0


if __name__ == "__main__":
    raise SystemExit(main())
