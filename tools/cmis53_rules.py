"""Normalization rules for the CMIS 5.3 field reference data.

Pure standard library. This module consolidates page / mask / value-type
normalization that was duplicated across four scripts in the upstream
``jimfred/CMIS`` project (``extract_memory_map.page_of``,
``normalize_memory_map.bank_scope``, ``rebuild_memory_map.page_cell/page_key``
and ``update_param_reference.masks_of/fmt_page``) into one testable place.

It also fixes the upstream weaknesses that matter for a portable runtime:
explicit UTF-8 handling belongs to the loader, paths are injected by the
caller, malformed values are reported instead of raising SystemExit, and the
section mapping is data (see SECTION_RULES) rather than scattered conditionals.

The lower half of this module refactors the spec-PDF row parsing and the
engineering-unit derivation from upstream ``extract_memory_map.page_of``,
``normalize_memory_map`` and ``conversions.py``.  Those rules live here so the
CSV importer, the PDF parser and their tests all share one implementation.

Derived from jimfred/CMIS, MIT, Copyright (c) 2026 Jim Frederick.
The field data itself is subject to the OIF / Apache-2.0 notices in NOTICE.
"""

from __future__ import annotations

import re

LOWER_PAGE = "Lwr"

# Column meanings from the upstream workbook (MIT original work).
FIELD_COLUMN_NOTES = {
    "Key ID": "Unique row key: CMIS Name, with .<page>, .<byte> and .<mask> suffixes on collisions",
    "CMIS Name": "Field name in OIF-CMIS-05.3 Section 8; 'Reserved' denotes a reserved region",
    "Page": "Upper memory page as 0xNN; blank means Lower Memory (bytes 0-127)",
    "Byte": "First byte address, decimal, as printed in the specification",
    "Byte Length": "Number of consecutive bytes occupied",
    "Mask Bytes": "One 0x mask per occupied byte, ascending address; blank means all bits",
    "Bank Scope": "Blank = unbanked; else Lane-banked / Application-banked / CDB-instance",
    "Value Type": "Normalized storage or decoding type; blank means a reserved region",
    "Unit": "Engineering unit after scaling (degC, uV, dBm, GHz, ...)",
    "Scale": "Engineering value = raw value x Scale",
    "Byte Order": "Big-endian (CMIS default) or Little-endian for multi-byte numbers",
    "Conversion Note": "Additional conversion rules, dependencies or formula hints",
    "Access": "RO / RW / WO / RWW as defined by Table 8-3",
    "Behavior": "Normal / ClearOnRead / SelfClearing / See reference",
    "Requirement": "Rqd / Opt / Cnd / Adv; blank when the specification does not state one",
    "Condition": "Conditional-field expression, e.g. DiagnosticsSelector=NNh",
    "Description": "Verbatim field description from the specification (OIF copyright)",
    "Reference Section": "Specification clause number, when available",
    "Reference Table": "Source table number, e.g. 8-62",
    "SONiC Cross-check": "Bit-level comparison with sonic-platform-common, bank 0, pinned commit",
    "SONiC Field": "Overlapping SONiC field names; aliases are separated by ' | '",
}

CDB_COLUMN_NOTES = {
    "CMD ID": "Command identifier, 4 hex digits",
    "Command Title": "Command name from the Section 9 overview tables",
    "Group": "Command group from Table 9-1 ID ranges",
    "Requirement": "Rqd / Opt / Cnd / Adv",
    "Section": "Specification clause 9.x.y",
    "Detail Table": "Table describing the CMD/REPLY payload layout",
    "Overview Table": "Group overview table, when the command is listed there",
    "Description": "Verbatim command description from the specification (OIF copyright)",
    "Note": "Provenance note for commands only present in a detail table",
}

FIELD_COLUMNS = {
    "Key ID": "key_id",
    "CMIS Name": "name",
    "Page": "page",
    "Byte": "byte",
    "Byte Length": "byte_length",
    "Mask Bytes": "mask_bytes",
    "Bank Scope": "bank_scope",
    "Value Type": "value_type",
    "Unit": "unit",
    "Scale": "scale",
    "Byte Order": "byte_order",
    "Conversion Note": "conversion_note",
    "Access": "access",
    "Behavior": "behavior",
    "Requirement": "requirement",
    "Condition": "condition",
    "Description": "description",
    "Reference Section": "ref_section",
    "Reference Table": "ref_table",
    "SONiC Cross-check": "sonic_cross_check",
    "SONiC Field": "sonic_field",
}

CDB_COLUMNS = {
    "CMD ID": "cmd_id",
    "Command Title": "title",
    "Group": "cmd_group",
    "Requirement": "requirement",
    "Section": "spec_section",
    "Detail Table": "detail_table",
    "Overview Table": "overview_table",
    "Description": "description",
    "Note": "note",
}

# Deterministic, auditable mapping from an Upper page to a CMIScope section.
# Lower Memory is handled separately because its byte ranges are split between
# LOW_PAGE, VDM (bytes 14-25) and CDB (bytes 37-38 and 118-125) in
# cmis_service/cmis_spec.py SECTIONS.
VDM_PAGES = {"02h", "10h", "11h"} | {f"{n:02X}h" for n in range(0x20, 0x30)}
CDB_PAGES = {"9Fh"} | {f"{n:02X}h" for n in range(0xA0, 0xB0)}

SECTION_RULES = {
    "LOW_PAGE": "Lower bytes 0-13, 26-36, 39-117, 126-127; Upper page 00h",
    "VDM": "Lower bytes 14-25; Upper pages 02h, 10h, 11h, 20h-2Fh",
    "CDB": "Lower bytes 37-38 and 118-125; Upper pages 9Fh, A0h-AFh",
    "CONTROL": "Remaining Upper pages (01h, 04h, 12h-1Dh, 30h-4Fh, ...)",
}

_NUMERIC_TYPES = {"u8", "s8", "u16", "s16", "u32", "s32", "u64", "s64", "f16"}


def parse_page(raw: str | None) -> str:
    """Return a canonical page token: 'Lwr' for Lower Memory, else 'NNh'."""
    text = (raw or "").strip()
    if not text or text.lower() in ("lwr", "lower", "lower memory"):
        return LOWER_PAGE
    match = re.fullmatch(r"0x([0-9a-fA-F]{1,2})", text)
    if match:
        return f"{int(match.group(1), 16):02X}h"
    match = re.fullmatch(r"([0-9a-fA-F]{1,2})h?", text)
    if match:
        return f"{int(match.group(1), 16):02X}h"
    return text


def parse_masks(raw: str | None, length: int) -> list[int]:
    """Parse '0x80 0x40' into byte masks, padding blank masks with 0xFF.

    The upstream code repeated this in four places and assumed well-formed
    input. Here an unparsable token is ignored (and the loader records it),
    so a single malformed cell cannot abort the whole import.
    """
    size = max(0, int(length or 0))
    text = (raw or "").strip()
    if not text:
        return [0xFF] * size
    values: list[int] = []
    for token in re.split(r"[\s_,;]+", text):
        if not token:
            continue
        try:
            values.append(int(token, 16) if token.lower().startswith("0x") else int(token, 0))
        except ValueError:
            continue
    if len(values) < size:
        values.extend([0xFF] * (size - len(values)))
    return values[:size] if size else values[:1]


def classify_section(page: str, byte: int | None = None) -> str:
    """Map a canonical page (and optional Lower byte) to a CMIScope section."""
    if page == LOWER_PAGE:
        offset = byte if isinstance(byte, int) else -1
        if 14 <= offset <= 25:
            return "VDM"
        if (37 <= offset <= 38) or (118 <= offset <= 125):
            return "CDB"
        return "LOW_PAGE"
    if page == "00h":
        return "LOW_PAGE"
    if page in CDB_PAGES:
        return "CDB"
    if page in VDM_PAGES:
        return "VDM"
    return "CONTROL"


def to_data_type(value_type: str | None) -> str:
    """Translate a spec value type into CMIScope's validation vocabulary."""
    text = (value_type or "").strip().lower()
    if not text or text == "unspecified":
        return "text"
    if text == "bool":
        return "bool"
    if text in _NUMERIC_TYPES:
        return "float" if text == "f16" else "int"
    if text.startswith("enum"):
        return "enum"
    if text.startswith("ascii"):
        return "ascii"
    if text.startswith(("bitfield", "bitmask", "bytes", "u", "s")):
        return "hex"
    return "text"


def parse_int(raw: str | None, default: int = 0) -> int:
    try:
        return int(str(raw).strip())
    except (TypeError, ValueError):
        return default


def parse_float(raw: str | None) -> float | None:
    text = (raw or "").strip()
    if not text:
        return None
    try:
        return float(text)
    except ValueError:
        return None


def normalize_cmd_id(raw: str | None) -> str:
    """'0000h' -> '0000', matching cmis_spec.CDB_COMMANDS.cmd_id."""
    text = (raw or "").strip()
    match = re.fullmatch(r"([0-9a-fA-F]{4})h?", text)
    return match.group(1).upper() if match else text.upper()


def normalize_field(row: dict) -> dict:
    """Convert one upstream CSV row into the portable reference schema."""
    out = {target: (row.get(source) or "").strip() for source, target in FIELD_COLUMNS.items()}
    byte = parse_int(out["byte"])
    length = parse_int(out["byte_length"], 1)
    page_raw = out["page"]
    page = parse_page(page_raw)
    masks = parse_masks(out["mask_bytes"], length)
    value_type = out["value_type"]

    out.update({
        "page_raw": page_raw,
        "page": page,
        "byte": byte,
        "byte_length": length,
        "scale": parse_float(out["scale"]),
        "mask_values": masks,
        "section": classify_section(page, byte),
        "data_type": to_data_type(value_type),
        "is_reserved": 1 if out["name"] == "Reserved" else 0,
        "is_lower_memory": 1 if page == LOWER_PAGE else 0,
    })
    return out


def normalize_cdb(row: dict) -> dict:
    """Convert one upstream CDB CSV row into the portable reference schema."""
    out = {target: (row.get(source) or "").strip() for source, target in CDB_COLUMNS.items()}
    out["cmd_id"] = normalize_cmd_id(out["cmd_id"])
    return out


# ---------------------------------------------------------------------------
# Rules for rows extracted directly from the OIF specification PDF.
# Refactored from upstream extract_memory_map.page_of, normalize_memory_map
# (clean/parse_type/value_type/mask derivation) and conversions.derive.
# ---------------------------------------------------------------------------

TABLE_TITLE = re.compile(r"^\s*Table\s+([89])-(\d+)\s+(.+?)\s*$", re.I)
_PAGE_IN_TITLE = re.compile(r"Pages?\s+([0-9A-F]{2})h", re.I)
_PAGE_BYTE_TITLE = re.compile(r"Byte\s+([0-9A-F]{2})h\s*:", re.I)
CMD_TITLE_RE = re.compile(r"Table\s+9-\d+\s+CDB Command\s+([0-9A-Fh/]+)\s*:\s*([^\n]+)", re.I)
CMD_SECTION_RE = re.compile(r"\b(9\.\d+(?:\.\d+)?)\s+CMD\s+([0-9A-Fh/]+)", re.I)

# Refactored from upstream extract_memory_map.SKIP_TABLES and
# normalize_memory_map.OUT_OF_SCOPE. Overview tables duplicate the detail
# tables that follow them; template tables describe relative structures or
# page ranges instead of fixed addresses. Keeping these as data (rather than
# scattered conditionals) makes the extraction rules auditable and testable.
OVERVIEW_TABLES = frozenset({
    "8-4", "8-26", "8-42", "8-61", "8-64", "8-65", "8-67", "8-82",
    "8-98", "8-100", "8-125", "8-130", "8-132", "8-152", "8-155",
    "8-158", "8-162", "8-165", "8-177",
})
TEMPLATE_TABLES = {
    "8-22": "Application Descriptor format template",
    "8-163": "NAD structure template (relative offsets)",
    "8-169": "VDM instance descriptor format template",
    "8-173": "VDM TC flag byte format template",
    "8-168": "VDM configuration, page range 20h-23h",
    "8-171": "VDM real-time values, page range 24h-27h",
    "8-172": "VDM thresholds, page range 28h-2Bh",
    "8-180": "CDB message body, generic LPL",
    "8-181": "EPL segments, page range A0h-AFh",
}

# Longest-first aliases, used to locate logical columns in a header row.
HEADER_ALIASES: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("selector", ("Diag. Selector", "Diag Selector")),
    ("desc", ("Field/Register Description", "Diagnostics Data Description",
              "Field Description", "Register Description", "Description")),
    ("name", ("Subject Area or Field", "Diagnostics Field", "Field Name",
              "Register Name", "Subject Area", "Name")),
    ("byte", ("Bytes", "Byte", "Address")),
    ("bits", ("Bits", "Bit")),
    ("type", ("Type",)),
)

_ACCESS_TOKENS = ("RWW", "RW", "RO", "WO")
_REQUIREMENT_TOKENS = ("Rqd", "Opt", "Cnd", "Adv")
_TYPE_TOKEN = re.compile(r"^(U8|U16|S16|U32|S32|U64|F16|S8|ASCII\[\d+\])\b", re.I)
_NUMERIC_VALUE_TYPES = re.compile(r"^(u8|s8|u16|s16|u32|s32|u64|f16|unspecified|bitfield\d+)$")

UNIT_ALIASES = {
    "degree celsius": "degC", "deg c": "degC", "°c": "degC", "degc": "degC",
    "µv": "uV", "uv": "uV", "mv": "mV", "v": "V", "µa": "uA", "ua": "uA",
    "ma": "mA", "µw": "uW", "uw": "uW", "mw": "mW", "w": "W", "dbm": "dBm",
    "db": "dB", "ghz": "GHz", "mhz": "MHz", "thz": "THz", "nm": "nm",
    "ns": "ns", "µs": "us", "μs": "us", "us": "us", "ms": "ms", "s": "s",
    "km": "km", "m": "m", "%": "%",
}
_UNIT_PATTERN = (
    r"(degree Celsius|deg C|°C|µV|uV|mV|V|µA|uA|mA|µW|uW|mW|W|dBm|dB|"
    r"GHz|MHz|THz|nm|ns|µs|μs|us|ms|s|km|m|%)"
)
_NUM_PATTERN = r"(\d+(?:\.\d+)?(?:\s*/\s*\d+)?)"
CONVERSION_PATTERNS = (
    re.compile(r"(?:units? of|increments of|multiples of|resolution of)\s*"
               + _NUM_PATTERN + r"\s*" + _UNIT_PATTERN + r"(?![A-Za-z])", re.I),
    re.compile(r"(?:in\s+)?" + _NUM_PATTERN + r"\s*" + _UNIT_PATTERN
               + r"(?![A-Za-z])\s*increments", re.I),
    re.compile(r"\bin\s+" + _NUM_PATTERN + r"\s*" + _UNIT_PATTERN + r"(?![A-Za-z])", re.I),
    re.compile(r"\bin\s+" + _UNIT_PATTERN + r"(?![A-Za-z])(?!\s*\d)", re.I),
)
# (name regex, unit, scale, note) - fields whose conversion depends on another register.
FAMILY_RULES = (
    (r"^Aux1Mon", None, None, "Depends on 01h:145.0 (custom / TEC current)"),
    (r"^Aux2Mon", None, None, "Depends on 01h:145.1 (laser temperature / TEC current)"),
    (r"^Aux3Mon", None, None, "Depends on 01h:145.2 (laser temperature / supply voltage)"),
    (r"^CustomMon", None, None, "Vendor-defined monitor"),
    (r"^LaserBias", "uA", 2.0, "Also multiply by TxBiasCurrentScalingFactor (01h:160.4-3)"),
    (r"^BaseLength$", "m", 1.0, "Also multiply by LengthMultiplier (00h:202.7-6)"),
    (r"^BaseLengthSMF$", "km", 1.0, "Also multiply by LengthMultiplierSMF (01h:132.7-6)"),
    (r"^ModSelWaitTime(Mantissa|Exponent)$", "us", None,
     "ModSelWaitTime = Mantissa x 2^Exponent us (01h:143)"),
)


def page_from_title(title: str | None) -> str | None:
    """Derive the memory page from a Section 8 table caption.

    Upstream hardcoded this as ``page_of()`` and returned a bare hex token;
    here the result is the canonical CMIScope page token (``Lwr`` / ``NNh``).
    """
    text = title or ""
    if "lower memory" in text.lower():
        return LOWER_PAGE
    match = _PAGE_IN_TITLE.search(text) or _PAGE_BYTE_TITLE.search(text)
    return parse_page(match.group(1) + "h") if match else None


def clean_cell(value: str | None) -> str | None:
    """Collapse PDF line breaks without losing the distinction None vs ''."""
    if value is None:
        return None
    return re.sub(r"[ \t]*\n[ \t]*", " ", value).strip()


def parse_byte_range(text: str | None) -> tuple[int, int] | None:
    """'129-130' -> (129, 2); '14' -> (14, 1). Handles wrapped PDF ranges."""
    match = re.fullmatch(r"(\d+)(?:-(\d+))?", re.sub(r"\s+", "", text or ""))
    if not match:
        return None
    start, end = int(match.group(1)), int(match.group(2) or match.group(1))
    if end < start:
        start, end = end, start
    return start, end - start + 1


def masks_from_bits(bits: str | None, nbytes: int) -> tuple[list[int], int, str | None]:
    """Return (mask per byte, field width in bits, optional parsing issue)."""
    text = re.sub(r"\s+", "", bits or "")
    match = re.fullmatch(r"(\d+)(?:-(\d+))?", text)
    if match and int(match.group(1)) < 8:
        hi, lo = int(match.group(1)), int(match.group(2) or match.group(1))
        if hi < lo:
            hi, lo = lo, hi
        mask = sum(1 << i for i in range(lo, hi + 1))
        return [mask] * nbytes, hi - lo + 1, None
    issue = None
    if text and not match and text not in ("All", "7-43-0"):
        issue = f"bits '{text}' treated as whole bytes"
    return [0xFF] * nbytes, 8 * nbytes, issue


def parse_access_type(text: str | None) -> tuple[str | None, str | None, str | None]:
    """'RO/COR Rqd.' -> ('RO', 'ClearOnRead', 'Rqd')."""
    flat = re.sub(r"\s+", "", text or "")
    access = next((token for token in _ACCESS_TOKENS if flat.startswith(token)), None)
    if "COR" in flat:
        behavior = "ClearOnRead"
    elif "/SC" in flat or "SC" in flat.split("/")[1:2]:
        behavior = "SelfClearing"
    else:
        behavior = "Normal" if access else None
    requirement = next((token for token in _REQUIREMENT_TOKENS if token in flat), None)
    return access, behavior, requirement


def value_type_from_text(description: str | None, width_bits: int, nbytes: int) -> str:
    """Infer a storage/decoding type from the spec description and geometry."""
    text = description or ""
    match = _TYPE_TOKEN.match(text) or re.search(r"\b(U8|U16|S16|U32|S32|U64|F16|S8)\b", text)
    if match:
        return match.group(1).lower()
    if re.search(r"\bASCII\b", text) and nbytes > 1:
        return f"ascii[{nbytes}]"
    if nbytes == 1 and width_bits == 1:
        return "bool"
    if nbytes == 1 and width_bits < 8:
        return f"bitfield{width_bits}"
    if nbytes == 1:
        return "u8"
    return "unspecified"


def _scale_number(text: str) -> float:
    compact = text.replace(" ", "")
    if "/" in compact:
        left, right = compact.split("/", 1)
        return float(left) / float(right)
    return float(compact)


def derive_conversion(description: str | None, value_type: str | None,
                      nbytes: int, name: str | None = None) -> dict:
    """Derive engineering unit/scale/byte-order from spec text.

    Refactored from upstream ``conversions.derive`` into a single rule set that
    is also used to cross-check the Unit/Scale columns of the published CSV.
    """
    text = (description or "").replace("\u00a0", " ")
    out: dict = {"unit": None, "scale": None, "byte_order": None, "conversion_note": None}
    if not value_type or not _NUMERIC_VALUE_TYPES.match(value_type):
        return out
    if nbytes > 1 and value_type != "unspecified" and not value_type.startswith("bitfield"):
        out["byte_order"] = ("Little-endian" if re.search(r"little.endian|LSB first", text, re.I)
                             else "Big-endian")
    if value_type == "f16":
        out["conversion_note"] = "F16 floating-point encoding (CMIS F16 format)"
        return out
    for family, unit, scale, note in FAMILY_RULES:
        if name and re.search(family, name):
            out.update(unit=unit, scale=scale, conversion_note=note)
            return out
    if re.search(r"100\s*%\s*/\s*32767|100\s*/\s*32767\s*%", text, re.I):
        out.update(unit="%", scale=100 / 32767,
                   conversion_note="Percent of maximum TEC current (01h:145)")
        return out
    for index, pattern in enumerate(CONVERSION_PATTERNS):
        match = pattern.search(text)
        if not match:
            continue
        if index == 3:
            unit, scale = match.group(1), 1.0
        else:
            scale, unit = _scale_number(match.group(1)), match.group(2)
        out["unit"] = UNIT_ALIASES.get(unit.lower(), unit)
        out["scale"] = scale
        break
    multiplier = re.search(
        r"(times the multiplier.*?|[Mm]ust be multiplied by.*?|use multiplier.*?)"
        r"(?=\s*\(|\.\s|;|$)", text)
    if multiplier:
        out["conversion_note"] = multiplier.group(1).strip()
    return out


def cmd_ids_in(text: str) -> list[str]:
    """'0210h/0211h' -> ['0210h', '0211h'] (Section 9 command titles)."""
    return [normalize_cmd_id(part) for part in
            re.findall(r"([0-9A-F]{4})h?", text.upper(), re.I)]
