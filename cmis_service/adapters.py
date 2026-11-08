"""Pluggable access adapters for reading and configuring CMIS registers.

Two production access paths are supported, plus an offline mirror:

Mode A (ssh-i2c)
    The service itself runs on a TEST SERVER. It opens an SSH session to a TEST
    SWITCH and executes a switch-side command (i2cget / i2cset / vendor CLI).
    The switch performs the two-wire (I2C) transaction against the module
    EEPROM at address 0x50. Page selection is done by writing Lower byte 127.

Mode B (rest-api)
    The service calls the northbound RESTful API exposed by the target device
    or its NOS. The device owns the I2C transaction and returns normalized
    CMIS resources. Access is governed by page-level read/write allowlists.

mirror (default)
    No physical I/O. Values come from the local SQLite mirror and every write
    is recorded as "staged" in the audit log. This keeps the service safe and
    fully runnable on a laptop with no lab hardware attached.

Only the Python standard library is used: subprocess for SSH and urllib for
REST. Credentials are never stored in config.ini; the REST token is read from
an environment variable named by rest_token_env, and SSH relies on the
operator's existing ssh-agent / key configuration (BatchMode=yes).
"""

from __future__ import annotations

import json
import os
import re
import shlex
import subprocess
import urllib.error
import urllib.parse
import urllib.request
from typing import Any

from .config import Settings
from . import cmis_spec

_SAFE_VALUE = re.compile(r"^[A-Za-z0-9_.:/@+-]*$")


class AdapterError(Exception):
    """Structured transport failure, converted to an HTTP error by the API."""

    def __init__(self, code: str, message: str, status: int = 502, details: Any = None):
        super().__init__(message)
        self.code = code
        self.message = message
        self.status = status
        self.details = details


def _validate_placeholder(name: str, value: Any) -> str:
    text = str(value)
    if not _SAFE_VALUE.fullmatch(text):
        raise AdapterError("UNSAFE_PARAM", f"Unsafe value for template placeholder {name!r}", 400)
    return text


def _render(template: str, values: dict[str, Any]) -> list[str]:
    """Render a command template into an argv list without invoking a shell."""
    try:
        rendered = template.format(**{k: _validate_placeholder(k, v) for k, v in values.items()})
    except KeyError as exc:
        raise AdapterError("BAD_TEMPLATE", f"Unknown placeholder in command template: {exc}", 500)
    except IndexError as exc:
        raise AdapterError("BAD_TEMPLATE", f"Malformed command template: {exc}", 500)
    try:
        return shlex.split(rendered, posix=(os.name != "nt"))
    except ValueError as exc:
        raise AdapterError("BAD_TEMPLATE", f"Cannot parse command template: {exc}", 500)


def _parse_hex_output(text: str, expected: int = 0) -> list[str]:
    """Extract byte values from typical i2cget / CLI output."""
    values: list[str] = []
    for line in text.splitlines():
        for match in re.finditer(r"0x([0-9a-fA-F]{2})\b", line):
            values.append(f"0x{match.group(1).upper()}")
    if not values:
        for token in re.findall(r"\b[0-9a-fA-F]{2}\b", text):
            values.append(f"0x{token.upper()}")
    return values[:expected] if expected else values


class AccessAdapter:
    """Common interface implemented by all three adapters."""

    mode = "mirror"

    def __init__(self, settings: Settings):
        self.settings = settings

    def capabilities(self) -> dict:
        mode = cmis_spec.ACCESS_MODE_BY_KEY[self.mode]
        return {
            "mode": self.mode,
            "label_zh": mode["zh"],
            "label_en": mode["en"],
            "topology": mode["topology"],
            "transport": mode["transport"],
            "reads": mode["reads"],
            "writes": mode["writes"],
            "risk": mode["risk"],
            "controls": mode.get("controls", []),
            "allow_hardware_write": self.settings.allow_hardware_write,
            "cdb_allow_firmware": self.settings.cdb_allow_firmware,
            "cdb_rest_allowed": self.settings.cdb_rest_allowed,
            "read_only": self.settings.read_only,
            "default_language": self.settings.default_language,
            "spec_releases": cmis_spec.SPEC_RELEASES,
        }

    def probe(self) -> dict:
        return {"ok": True, "mode": self.mode, "checked": False,
                "message": "No physical transport is configured in this mode"}

    def read_registers(self, device_id: str, module_id: str, page: str,
                       offset: int, length: int) -> dict:
        raise AdapterError("NOT_SUPPORTED", f"Register reads are unavailable in {self.mode} mode", 501)

    def write_register(self, device_id: str, module_id: str, page: str,
                       offset: int, data_hex: str) -> dict:
        raise AdapterError("NOT_SUPPORTED", f"Register writes are unavailable in {self.mode} mode", 501)

    def execute_cdb(self, device_id: str, module_id: str, frame_hex: str,
                    epl_hex: str, cmd_id: str) -> dict:
        raise AdapterError("NOT_SUPPORTED", f"CDB execution is unavailable in {self.mode} mode", 501)

    # ------------------------------------------------------------------
    def enforce_write_policy(self, page: str, offset: int) -> None:
        """Apply the page-level governance from the IETF CMIS YANG draft."""
        s = self.settings
        if s.read_only:
            raise AdapterError("SERVICE_READ_ONLY", "Service is in read-only mode", 409)
        if not s.allow_hardware_write:
            raise AdapterError("HARDWARE_WRITE_DISABLED",
                               "Hardware writes are disabled (allow_hardware_write=false)", 409)
        normalized = (page or "").strip().lower().replace(" ", "")
        is_lower = normalized.startswith("lower")
        is_cdb = normalized.startswith("9fh") or bool(re.fullmatch(r"a[0-9a-f]h", normalized))
        if is_lower and offset < 128:
            raise AdapterError("LOWER_MEMORY_PROTECTED",
                               "Writes to Lower Memory (0-127) MUST NOT be permitted "
                               "(IETF draft-hi-ccamp-cmis-control-yang-04 section 9.1)", 409)
        if is_cdb:
            raise AdapterError("CDB_PAGE_PROTECTED",
                               "CDB pages 9Fh-AFh MUST NOT be remotely writable "
                               "(IETF draft-hi-ccamp-cmis-control-yang-04 section 9.1)", 409)

    def enforce_cdb_policy(self, cmd_id: str, confirm: str) -> None:
        s = self.settings
        if s.read_only:
            raise AdapterError("SERVICE_READ_ONLY", "Service is in read-only mode", 409)
        if not s.allow_hardware_write:
            raise AdapterError("HARDWARE_WRITE_DISABLED",
                               "Hardware writes are disabled (allow_hardware_write=false)", 409)
        if confirm != s.cdb_confirm_token:
            raise AdapterError("CONFIRMATION_REQUIRED",
                               f"Set confirm to {s.cdb_confirm_token!r} before executing a CDB command", 409)
        if self.mode == "rest-api" and not s.cdb_rest_allowed:
            raise AdapterError("CDB_REST_FORBIDDEN",
                               "CDB commands are read-only over the REST path by default", 409)
        if cmis_spec.is_firmware_command(cmd_id) and not s.cdb_allow_firmware:
            raise AdapterError("FIRMWARE_COMMAND_FORBIDDEN",
                               "Firmware-management CDB commands require cdb_allow_firmware=true", 409)


class MirrorAdapter(AccessAdapter):
    """Offline adapter: all operations are simulated and never touch hardware."""

    mode = "mirror"

    def probe(self) -> dict:
        return {"ok": True, "mode": self.mode, "checked": True,
                "message": "SQLite mirror is ready; no physical device is contacted"}

    def read_registers(self, device_id, module_id, page, offset, length):
        return {"mode": self.mode, "device_id": device_id, "module_id": module_id,
                "page": page, "offset": offset, "length": length,
                "values": [], "source": "sqlite-mirror",
                "message": "Cached values are served by /api/config-items, not by a live I2C read"}

    def write_register(self, device_id, module_id, page, offset, data_hex):
        return {"mode": self.mode, "applied_to_hardware": False, "result": "staged",
                "message": "Write was staged in the local mirror only"}

    def execute_cdb(self, device_id, module_id, frame_hex, epl_hex, cmd_id):
        return {"mode": self.mode, "applied_to_hardware": False, "result": "staged",
                "cmd_id": cmd_id, "frame_bytes": len(frame_hex) // 2,
                "message": "CDB frame was validated and recorded; no command was sent to the module"}


class SshI2cAdapter(AccessAdapter):
    """Mode A: run switch-side I2C commands over a non-interactive SSH session."""

    mode = "ssh-i2c"

    def _argv(self, template: str, extra: dict[str, Any]) -> list[str]:
        s = self.settings
        values = {
            "host": s.ssh_host, "user": s.ssh_user, "port": s.ssh_port,
            "timeout": s.ssh_timeout, "bus": s.i2c_bus, "addr": s.i2c_addr,
            "page": 0, "offset": 0, "length": 1, "value": "00",
            "frame": "", "device": "unknown", "module": "unknown",
        }
        values.update(extra)
        return _render(template, values)

    def _run(self, argv: list[str]) -> str:
        if not argv:
            raise AdapterError("BAD_TEMPLATE", "Rendered command is empty", 500)
        try:
            proc = subprocess.run(argv, capture_output=True, text=True,
                                  timeout=self.settings.ssh_timeout, shell=False, check=False)
        except FileNotFoundError:
            raise AdapterError("SSH_UNAVAILABLE", "ssh executable was not found on this host", 502)
        except subprocess.TimeoutExpired:
            raise AdapterError("SSH_TIMEOUT", "SSH command timed out", 504)
        if proc.returncode != 0:
            raise AdapterError("SSH_COMMAND_FAILED",
                               f"Remote command exited with status {proc.returncode}",
                               502, {"stderr": (proc.stderr or "")[-500:]})
        return proc.stdout

    def probe(self) -> dict:
        if not self.settings.ssh_host:
            raise AdapterError("SSH_NOT_CONFIGURED", "ssh_host is not configured", 503)
        out = self._run(self._argv(self.settings.ssh_probe_cmd, {}))
        return {"ok": True, "mode": self.mode, "checked": True,
                "host": self.settings.ssh_host, "output": out.strip()[:300]}

    def read_registers(self, device_id, module_id, page, offset, length):
        out = self._run(self._argv(self.settings.ssh_read_cmd,
                                   {"device": device_id, "module": module_id,
                                    "page": page, "offset": offset, "length": length}))
        values = _parse_hex_output(out, length)
        return {"mode": self.mode, "device_id": device_id, "module_id": module_id,
                "page": page, "offset": offset, "length": length,
                "values": values, "raw_output": out.strip()[:500],
                "applied_to_hardware": True, "result": "read"}

    def write_register(self, device_id, module_id, page, offset, data_hex):
        self.enforce_write_policy(page, offset)
        out = self._run(self._argv(self.settings.ssh_write_cmd,
                                   {"device": device_id, "module": module_id,
                                    "page": page, "offset": offset, "value": data_hex}))
        return {"mode": self.mode, "applied_to_hardware": True, "result": "written",
                "page": page, "offset": offset, "data_hex": data_hex,
                "raw_output": out.strip()[:300]}

    def execute_cdb(self, device_id, module_id, frame_hex, epl_hex, cmd_id):
        return {"mode": self.mode, "applied_to_hardware": False, "result": "not_implemented",
                "cmd_id": cmd_id,
                "message": "CDB frame transport needs a switch-specific CLI mapping; "
                           "compose and validate frames offline with /api/cdb/compose, "
                           "then wire ssh_cdb_cmd to the vendor CLI"}


class RestApiAdapter(AccessAdapter):
    """Mode B: talk to the target device northbound REST API."""

    mode = "rest-api"

    def _token(self) -> str:
        return os.environ.get(self.settings.rest_token_env, "")

    def _url(self, path: str, params: dict[str, Any] | None = None) -> str:
        base = self.settings.rest_base_url.rstrip("/")
        url = base if path.startswith("http") else base + "/" + path.lstrip("/")
        if params:
            url += "?" + urllib.parse.urlencode(params)
        return url

    def _request(self, method: str, path: str, params=None, payload=None) -> dict:
        if not self.settings.rest_base_url:
            raise AdapterError("REST_NOT_CONFIGURED", "rest_base_url is not configured", 503)
        data = json.dumps(payload, ensure_ascii=False).encode("utf-8") if payload is not None else None
        headers = {"Accept": "application/json"}
        token = self._token()
        if token:
            headers["Authorization"] = f"Bearer {token}"
        if data is not None:
            headers["Content-Type"] = "application/json"
        req = urllib.request.Request(self._url(path, params), data=data, headers=headers, method=method)
        try:
            with urllib.request.urlopen(req, timeout=self.settings.rest_timeout) as resp:
                body = resp.read().decode("utf-8", "replace")
                status = resp.status
        except urllib.error.HTTPError as exc:
            raise AdapterError("REST_HTTP_ERROR", f"Device API returned HTTP {exc.code}",
                               502, {"body": exc.read().decode("utf-8", "replace")[:400]})
        except urllib.error.URLError as exc:
            raise AdapterError("REST_UNREACHABLE", f"Device API is unreachable: {exc.reason}", 502)
        except TimeoutError:
            raise AdapterError("REST_TIMEOUT", "Device API request timed out", 504)
        try:
            parsed = json.loads(body) if body.strip() else {}
        except json.JSONDecodeError:
            parsed = {"raw": body[:400]}
        return {"status": status, "body": parsed}

    def probe(self) -> dict:
        result = self._request("GET", self.settings.rest_probe_path, {"limit": 1})
        return {"ok": True, "mode": self.mode, "checked": True,
                "http_status": result["status"], "sample": str(result["body"])[:200]}

    def read_registers(self, device_id, module_id, page, offset, length):
        result = self._request("GET", self.settings.rest_read_path,
                               {"device": device_id, "module": module_id, "page": page,
                                "offset": offset, "length": length})
        return {"mode": self.mode, "device_id": device_id, "module_id": module_id,
                "page": page, "offset": offset, "length": length,
                "values": result["body"], "applied_to_hardware": False, "result": "read"}

    def write_register(self, device_id, module_id, page, offset, data_hex):
        self.enforce_write_policy(page, offset)
        result = self._request("PUT", self.settings.rest_write_path, None,
                               {"device": device_id, "module": module_id, "page": page,
                                "offset": offset, "data_hex": data_hex})
        return {"mode": self.mode, "applied_to_hardware": True, "result": "written",
                "http_status": result["status"], "response": result["body"]}

    def execute_cdb(self, device_id, module_id, frame_hex, epl_hex, cmd_id):
        result = self._request("POST", self.settings.rest_cdb_path, None,
                               {"device": device_id, "module": module_id, "cmd_id": cmd_id,
                                "frame_hex": frame_hex, "epl_hex": epl_hex})
        return {"mode": self.mode, "applied_to_hardware": True, "result": "executed",
                "cmd_id": cmd_id, "http_status": result["status"], "response": result["body"]}


_ADAPTERS = {"mirror": MirrorAdapter, "ssh-i2c": SshI2cAdapter, "rest-api": RestApiAdapter}


def get_adapter(settings: Settings) -> AccessAdapter:
    """Factory used by the API layer on every request (stateless, cheap)."""
    cls = _ADAPTERS.get(settings.access_mode)
    if cls is None:
        raise AdapterError("UNKNOWN_ACCESS_MODE", f"Unknown access mode: {settings.access_mode}", 500)
    return cls(settings)
