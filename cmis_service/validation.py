"""Pre-save validation for CMIS configuration items.

Validation is always enforced on the server (browser checks are advisory only):
type -> value domain / enum / regex -> writable bit -> cross-field rules ->
unconfirmed-spec warnings. A structured report is returned for the UI and the
audit log.
"""

from __future__ import annotations

import json
import re
import sqlite3
from typing import Any

_HEX_RE = re.compile(r"^(?:0x)?([0-9a-fA-F]{1,4})$")
_PRINTABLE_RE = re.compile(r"^[\x20-\x7E]*$")


def _json_list(raw: Any) -> list:
    if not raw:
        return []
    if isinstance(raw, list):
        return raw
    try:
        parsed = json.loads(raw)
        return parsed if isinstance(parsed, list) else []
    except (TypeError, ValueError):
        return []


def _check(report: dict, rule: str, ok: bool, detail: str, code: str = "") -> bool:
    report["checks"].append({"rule": rule, "status": "pass" if ok else "fail", "detail": detail})
    if not ok:
        report["errors"].append({"code": code or rule.upper(), "field": "value", "message": detail})
    return ok


def _warn(report: dict, code: str, message: str) -> None:
    report["warnings"].append({"code": code, "message": message})


def _parse_value(item: sqlite3.Row, proposed: Any, report: dict) -> dict | None:
    """Parse and normalize the proposed value according to data_type."""
    dtype = (item["data_type"] or "text").lower()
    raw = proposed.strip() if isinstance(proposed, str) else proposed

    if dtype == "bool":
        if isinstance(raw, bool):
            val = int(raw)
        elif isinstance(raw, (int, float)) and raw in (0, 1):
            val = int(raw)
        elif isinstance(raw, str) and raw.lower() in ("0", "1", "true", "false", "on", "off"):
            val = 1 if raw.lower() in ("1", "true", "on") else 0
        else:
            _check(report, "type", False,
                   f"Boolean value must be 0/1/true/false, received {raw!r}", "INVALID_BOOL")
            return None
        return {"value": str(val), "raw_hex": f"0x{val:02X}"}

    if dtype == "enum":
        allowed = [str(x) for x in _json_list(item["allowed_values"])]
        text = str(raw)
        if not _check(report, "enum", (not allowed) or text in allowed,
                      f"Enum value {text!r} must be one of {allowed}" if allowed
                      else "Enum allowlist is empty, validation is impossible",
                      "VALUE_NOT_ALLOWED"):
            return None
        return {"value": text, "raw_hex": item["raw_hex"] if item["raw_hex"] else None}

    if dtype in ("int", "uint"):
        try:
            val = int(str(raw), 0) if isinstance(raw, str) and raw.lower().startswith("0x") else int(raw)
        except (TypeError, ValueError):
            _check(report, "type", False, f"Integer required, received {raw!r}", "INVALID_INT")
            return None
        lo, hi = item["min_value"], item["max_value"]
        if not _check(report, "range", (lo is None or val >= lo) and (hi is None or val <= hi),
                      f"Integer {val} must be within [{lo}, {hi}]", "OUT_OF_RANGE"):
            return None
        width = 2 if 0 <= val <= 0xFF else 4
        return {"value": str(val), "raw_hex": f"0x{val:0{width}X}"}

    if dtype == "float":
        try:
            val = float(raw)
        except (TypeError, ValueError):
            _check(report, "type", False, f"Number required, received {raw!r}", "INVALID_FLOAT")
            return None
        lo, hi = item["min_value"], item["max_value"]
        if not _check(report, "range", (lo is None or val >= lo) and (hi is None or val <= hi),
                      f"Number {val} must be within [{lo}, {hi}]", "OUT_OF_RANGE"):
            return None
        encoded = int(round(val * 256)) & 0xFFFF
        _warn(report, "RAW_ENCODING_UNCONFIRMED",
              "raw_hex is derived from a common 1/256-scaled 16-bit encoding; "
              "the real register encoding must be verified against the OIF spec")
        return {"value": f"{val:.4f}".rstrip("0").rstrip("."), "raw_hex": f"0x{encoded:04X}"}

    if dtype == "hex":
        m = _HEX_RE.match(str(raw))
        if not _check(report, "type", bool(m),
                      f"1-4 hexadecimal digits required (optional 0x prefix), received {raw!r}",
                      "INVALID_HEX"):
            return None
        val = int(m.group(1), 16)
        lo, hi = item["min_value"], item["max_value"]
        if not _check(report, "range", (lo is None or val >= lo) and (hi is None or val <= hi),
                      f"Hex value {val} must be within [{lo}, {hi}]", "OUT_OF_RANGE"):
            return None
        text = f"0x{val:02X}" if val <= 0xFF else f"0x{val:04X}"
        return {"value": text, "raw_hex": text}

    if dtype == "ascii":
        text = str(raw)
        if not _check(report, "format", bool(_PRINTABLE_RE.match(text)) and len(text) <= 16,
                      "ASCII string must contain printable characters and be at most 16 bytes",
                      "INVALID_ASCII"):
            return None
        return {"value": text, "raw_hex": "0x" + text.encode("ascii", "replace").hex().upper()}

    # text and unknown types: length constraint only
    text = str(raw)
    if not _check(report, "format", len(text) <= 128,
                  "Text must not exceed 128 characters", "TOO_LONG"):
        return None
    return {"value": text, "raw_hex": item["raw_hex"]}


def _cross_field_checks(conn: sqlite3.Connection, item: sqlite3.Row, normalized: dict,
                        report: dict) -> None:
    rule = item["cross_rule"]
    if not rule:
        return
    device_id = item["device_id"]

    def sibling(field_key: str) -> sqlite3.Row | None:
        return conn.execute(
            "SELECT * FROM config_items WHERE device_id = ? AND field_key = ?",
            (device_id, field_key),
        ).fetchone()

    if rule == "appsel_in_advertised":
        text = str(normalized["value"])
        val = int(text, 16) if text.lower().startswith("0x") else int(text)
        app_code, dp_id = (val >> 4) & 0xF, val & 0xF
        ok = val == 0 or (1 <= app_code <= 8 and 0 <= dp_id <= 8)
        _check(report, "appsel_encoding", ok,
               "AppSel must be 0xAD: A = Application number (1-8), D = DataPath ID (0-8); "
               "0x00 means unconfigured", "INVALID_APPSEL")
        if ok and val != 0:
            mod = conn.execute(
                "SELECT advertised_apps FROM modules WHERE module_id = ?", (item["module_id"],)
            ).fetchone()
            apps = _json_list(mod["advertised_apps"]) if mod else []
            if apps:
                _check(report, "appsel_advertised", app_code in apps,
                       f"Application {app_code} is not in the module's advertised list {apps} "
                       "(Page 01h Application Descriptor)", "APP_NOT_ADVERTISED")
            else:
                _warn(report, "ADVERTISED_APPS_UNKNOWN",
                      "Module has no advertised Application list; capability check skipped")

    elif rule == "tx_disable_vs_datapath_init":
        target = "DataPathInit" if item["field_key"] != "DataPathInit" else "TxDisable"
        other = sibling(target)
        if other:
            other_on = str(other["value"]) in ("1", "true", "0x01")
            new_on = str(normalized["value"]) in ("1", "true", "0x01")
            _check(report, "cross_field", not (other_on and new_on),
                   f"{item['field_key']} and {target} must not both be set: "
                   "the transmitter cannot be disabled during datapath initialization",
                   "CROSS_FIELD_CONFLICT")

    elif rule == "threshold_high_gt_warning":
        other = sibling("TempHighWarningThreshold")
        if other and other["value"] is not None:
            try:
                hi, warn = float(normalized["value"]), float(other["value"])
                _check(report, "cross_field", hi > warn,
                       f"High alarm threshold {hi} must exceed high warning threshold {warn}",
                       "THRESHOLD_ORDER")
            except (TypeError, ValueError):
                _warn(report, "SIBLING_UNCOMPARABLE",
                      "Related threshold is not numeric; ordering check skipped")

    elif rule == "low_power_vs_datapath_init":
        other = sibling("DataPathInit")
        if (other and str(other["value"]) in ("1", "true", "0x01")
                and str(normalized["value"]) in ("1", "true", "0x01")):
            _warn(report, "LOW_POWER_DURING_INIT",
                  "Switching to LowPwr while DataPathInit is set may abort datapath "
                  "initialization; verify the change order")


def validate(conn: sqlite3.Connection, item: sqlite3.Row, proposed: Any) -> dict:
    """Return a full validation report without writing anything."""
    report: dict[str, Any] = {
        "valid": False,
        "field_key": item["field_key"],
        "device_id": item["device_id"],
        "proposed": proposed,
        "normalized": None,
        "checks": [],
        "errors": [],
        "warnings": [],
        "rules": {
            "data_type": item["data_type"],
            "allowed_values": _json_list(item["allowed_values"]),
            "min_value": item["min_value"],
            "max_value": item["max_value"],
            "regex": item["regex"],
            "writable": bool(item["writable"]),
            "cross_rule": item["cross_rule"],
            "spec_ref": item["spec_ref"],
        },
    }

    if not _check(report, "writable", bool(item["writable"]),
                  "This field is read-only (RO) or write-only and cannot be saved here",
                  "READ_ONLY_FIELD"):
        return report

    normalized = _parse_value(item, proposed, report)
    if normalized is None:
        return report

    if item["regex"]:
        try:
            matched = re.fullmatch(item["regex"], normalized["value"]) is not None
        except re.error:
            matched = False
            _warn(report, "REGEX_INVALID", f"Configured regex does not compile: {item['regex']}")
        _check(report, "regex", matched,
               f"Value {normalized['value']!r} does not match regex {item['regex']}",
               "REGEX_MISMATCH")

    _cross_field_checks(conn, item, normalized, report)

    confidence = conn.execute(
        "SELECT confidence FROM fields WHERE field_key = ?", (item["field_key"],)
    ).fetchone()
    if confidence and confidence["confidence"] != "confirmed":
        _warn(report, "SPEC_UNCONFIRMED",
              "Register address or clause number is marked as pending; "
              "verify the source before applying to hardware")

    report["normalized"] = normalized
    report["valid"] = not report["errors"]
    return report
