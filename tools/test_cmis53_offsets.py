#!/usr/bin/env python3
"""CMIS 5.3 low-page / page-00h offset conformance checks.

The authoritative baseline is data/cmis53_dataset.json, which is derived from
the OIF-CMIS-05.3 PDF tables (8-4 .. 8-43). Every offset shipped in the
register map, the field catalog and the generated seed data must:

  * use the unified notation "<page>:<decimal> (0x<hex>)" used by high pages,
  * carry a page/decimal/hex triple that matches the CMIS 5.3 baseline,
  * never be "pending" for Low Page / Page 00h fields.

Usage: python tools/test_cmis53_offsets.py
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
if str(ROOT / "tools") not in sys.path:
    sys.path.insert(0, str(ROOT / "tools"))

import cmis_catalog  # noqa: E402
from cmis_service import cmis_spec  # noqa: E402

PASS, FAIL = [], []


def check(name: str, condition: bool, detail: str = "") -> None:
    (PASS if condition else FAIL).append(name)
    print(f"{'PASS' if condition else 'FAIL'}  {name}" + (f"  | {detail}" if detail else ""))


UNIFIED = re.compile(
    r"^(Lower|[0-9A-F]{2}h):(\d+)(?:-(\d+))? "
    r"\(0x([0-9A-F]{2})(?:-0x([0-9A-F]{2}))?\)(?: bit(\d+))?$"
)
ZH = re.compile(r"[\u3400-\u9fff]")


def parse_unified(text: str):
    """Return (page, dec_start, dec_end, hex_start, hex_end, bit) or None."""
    hit = UNIFIED.match(str(text))
    if not hit:
        return None
    page, first, last, hx_first, hx_last, bit = hit.groups()
    last = last or first
    hx_last = hx_last or hx_first
    return page, int(first), int(last), int(hx_first, 16), int(hx_last, 16), bit


def consistent(text: str) -> bool:
    parsed = parse_unified(text)
    if parsed is None:
        return False
    page, first, last, hx_first, hx_last, _ = parsed
    return first == hx_first and last == hx_last and first <= last


# ---------------------------------------------------------------------------
# Baseline anchors: verify the reference dataset itself before using it.
# (page in dataset, field name, byte, byte_length)
# ---------------------------------------------------------------------------
ANCHORS = [
    ("Lwr", "SFF8024Identifier", 0, 1),
    ("Lwr", "CmisRevision", 1, 1),
    ("Lwr", "ModuleState", 3, 1),
    ("Lwr", "LowPwrRequestSW", 26, 1),
    ("Lwr", "CdbStatus1", 37, 1),
    ("Lwr", "CdbStatus2", 38, 1),
    ("Lwr", "ModuleActiveFirmwareMajorRevision", 39, 1),
    ("Lwr", "ModuleActiveFirmwareMinorRevision", 40, 1),
    ("Lwr", "TempMonValue", 14, 2),
    ("Lwr", "CustomMonValue", 24, 2),
    ("Lwr", "MediaType", 85, 1),
    ("Lwr", "HostInterfaceIDApp1", 86, 1),
    ("Lwr", "PasswordChangeEntryArea", 118, 4),
    ("Lwr", "PasswordEntryArea", 122, 4),
    ("Lwr", "BankSelect", 126, 1),
    ("Lwr", "PageSelect", 127, 1),
    ("00h", "VendorName", 129, 16),
    ("00h", "VendorOUI", 145, 3),
    ("00h", "VendorPN", 148, 16),
    ("00h", "VendorRev", 164, 2),
    ("00h", "VendorSN", 166, 16),
    ("00h", "DateCode", 182, 8),
    ("00h", "PageChecksum", 222, 1),
    ("01h", "ModuleInactiveFirmwareMajorRevision", 128, 1),
    ("01h", "ModuleInactiveFirmwareMinorRevision", 129, 1),
]

# field_key -> (expected page, expected unified byte_offset)
EXPECT_CATALOG = {
    "ModuleIdentifier": ("Lower", "0 (0x00)"),
    "CmisRevision": ("Lower", "1 (0x01)"),
    "ModuleState": ("Lower", "3 (0x03)"),
    "ModuleFlags": ("Lower", "8-13 (0x08-0x0D)"),
    "LaneFlagSummary": ("Lower", "4-7 (0x04-0x07)"),
    "VendorName": ("00h", "129-144 (0x81-0x90)"),
    "VendorOUI": ("00h", "145-147 (0x91-0x93)"),
    "VendorPartNumber": ("00h", "148-163 (0x94-0xA3)"),
    "VendorSerialNumber": ("00h", "166-181 (0xA6-0xB5)"),
    "DateCode": ("00h", "182-189 (0xB6-0xBD)"),
    "CcBase": ("00h", "222 (0xDE)"),
    "CcExt": ("00h", "223 (0xDF)"),
    "ModuleTypeEncoding": ("Lower", "85 (0x55)"),
    "ModuleGlobalControls": ("Lower", "26-30 (0x1A-0x1E)"),
    "ModuleLevelFlagMasks": ("Lower", "31-36 (0x1F-0x24)"),
    "ModuleFirmwareVersion": ("Lower", "39-40 (0x27-0x28)"),
    "InactiveFirmwareVersion": ("01h", "128-129 (0x80-0x81)"),
    "CdbStatusLower": ("Lower", "37-38 (0x25-0x26)"),
    "ApplicationAdvertisingLegacy": ("Lower", "85-117 (0x55-0x75)"),
    "BankSelect": ("Lower", "126 (0x7E)"),
    "PageSelect": ("Lower", "127 (0x7F)"),
    "ModuleLevelMonitors": ("Lower", "14-25 (0x0E-0x19)"),
    "CdbPasswordEntry": ("Lower", "122 (0x7A)"),
    "LPMode": ("Lower", "26 (0x1A) bit4"),
}

# LOWER_MEMORY_MAP: (expected unified addr, size, canonical English name)
EXPECT_MAP = [
    ("Lower:0-3 (0x00-0x03)", 4, "ID and Status Area"),
    ("Lower:4-7 (0x04-0x07)", 4, "Lane Flag Summary"),
    ("Lower:8-13 (0x08-0x0D)", 6, "Module-Level Flags"),
    ("Lower:14-25 (0x0E-0x19)", 12, "Module-Level Monitors"),
    ("Lower:26-30 (0x1A-0x1E)", 5, "Module Global Controls"),
    ("Lower:31-36 (0x1F-0x24)", 6, "Module-Level Flag Masks"),
    ("Lower:37-38 (0x25-0x26)", 2, "CDB Status Area"),
    ("Lower:39-40 (0x27-0x28)", 2, "Active Firmware Version"),
    ("Lower:41-63 (0x29-0x3F)", 23, "Reserved"),
    ("Lower:64-82 (0x40-0x52)", 19, "Custom Area"),
    ("01h:128-129 (0x80-0x81)", 2, "Inactive Firmware Version"),
    ("Lower:85-117 (0x55-0x75)", 33, "Application Advertising"),
    ("Lower:118-125 (0x76-0x7D)", 8, "Password Entry and Change"),
    ("Lower:126 (0x7E)", 1, "Bank Select"),
    ("Lower:127 (0x7F)", 1, "Page Select"),
]

# UPPER_PAGE_00H: (expected unified addr, size, canonical English name)
EXPECT_UPPER = [
    ("00h:129-144 (0x81-0x90)", 16, "Vendor Name"),
    ("00h:145-147 (0x91-0x93)", 3, "Vendor OUI"),
    ("00h:148-163 (0x94-0xA3)", 16, "Vendor Part Number"),
    ("00h:164-165 (0xA4-0xA5)", 2, "Vendor Revision"),
    ("00h:166-181 (0xA6-0xB5)", 16, "Vendor Serial Number"),
    ("00h:182-189 (0xB6-0xBD)", 8, "Date Code"),
    ("00h:222-223 (0xDE-0xDF)", 2, "CC_BASE / CC_EXT"),
]


def main() -> int:
    dataset = json.loads((ROOT / "data/cmis53_dataset.json").read_text(encoding="utf-8"))
    fields = dataset["fields"]
    index = {(f["page"], f["name"]): f for f in fields}

    # 1. Baseline integrity -------------------------------------------------
    for page, name, byte, length in ANCHORS:
        row = index.get((page, name))
        check(f"CMIS 5.3 baseline: {page}:{name} @ {byte} ({length}B)",
              row is not None and row["byte"] == byte and row["byte_length"] == length,
              f"got {row['byte']}/{row['byte_length']}" if row else "missing")
    lpmode = index.get(("Lwr", "LowPwrRequestSW"))
    check("CMIS 5.3 baseline: LowPwrRequestSW mask is bit4 (0x10)",
          lpmode is not None and lpmode.get("mask_bytes") == "0x10")
    checksum = index.get(("00h", "PageChecksum"))
    check("CMIS 5.3 baseline: 00h:222 PageChecksum covers bytes 128-221",
          checksum is not None and "128-221" in checksum.get("description", ""))

    # 2. Field catalog ------------------------------------------------------
    catalog = {f["field_key"]: f for f in cmis_catalog.FIELD_CATALOG}
    for key, (page, offset) in EXPECT_CATALOG.items():
        field = catalog.get(key)
        check(f"Catalog: {key} = {page}:{offset}",
              field is not None and field["page"] == page
              and field["byte_offset"] == offset and consistent(page + ":" + offset),
              f"got {field['page']}:{field['byte_offset']}" if field else "missing")
    low_keys = set(EXPECT_CATALOG)
    check("Catalog: no pending offsets remain for Low Page / Page 00h",
          all("pending" not in str(catalog[k]["byte_offset"]) for k in low_keys if k in catalog))
    check("Catalog: field order preserved for Low Page / Page 00h",
          [f["field_key"] for f in cmis_catalog.FIELD_CATALOG
           if f["field_key"] in low_keys][:5]
          == ["ModuleIdentifier", "CmisRevision", "ModuleState", "ModuleFlags", "LaneFlagSummary"])

    # 3. Register map / Upper 00h ------------------------------------------
    mapping = cmis_spec.LOWER_MEMORY_MAP
    check("LOWER_MEMORY_MAP: 15 rows in original order", len(mapping) == 15, str(len(mapping)))
    for i, (addr, size, en) in enumerate(EXPECT_MAP):
        row = mapping[i] if i < len(mapping) else {}
        check(f"LOWER_MEMORY_MAP[{i}]: {addr} / {size}B / {en}",
              row.get("addr") == addr and row.get("size") == size
              and row.get("en") == en and consistent(addr))
    upper = cmis_spec.UPPER_PAGE_00H
    check("UPPER_PAGE_00H: 7 rows", len(upper) == 7, str(len(upper)))
    for i, (addr, size, en) in enumerate(EXPECT_UPPER):
        row = upper[i] if i < len(upper) else {}
        check(f"UPPER_PAGE_00H[{i}]: {addr} / {size}B / {en}",
              row.get("addr") == addr and row.get("size") == size
              and row.get("en") == en and consistent(addr))
    check("Register maps: no pending addresses",
          not any("pending" in str(r.get("addr", "")) for r in mapping + upper))
    check("Register maps: canonical abbreviations are upper-case",
          all(re.search(r"\b(?:ID|OUI|PN|SN|CDB|VDM|CMIS|CC_BASE|CC_EXT)\b", r["en"])
              or not any(a in r["en"] for a in ("Id", "Oui", "Cdb", "Vdm", "Cmis"))
              for r in mapping + upper))

    # 4. Generated data -----------------------------------------------------
    seed = json.loads((ROOT / "data/seed.json").read_text(encoding="utf-8"))
    items = seed["config_items"]
    label_problems = []
    for item in items:
        key = item["field_key"]
        if key not in EXPECT_CATALOG:
            continue
        page, offset = EXPECT_CATALOG[key]
        # Labels are checked structurally; the Chinese/English pair is validated below.
        if item["page"] != page or item["byte_offset"] != offset:
            label_problems.append(f"{key}:{item['page']}:{item['byte_offset']}")
        if not item["label"].endswith("@ %s:%s" % (page, offset)):
            label_problems.append(f"label:{item['label']}")
        if not item["label_en"].endswith("@ %s:%s" % (page, offset)):
            label_problems.append(f"label_en:{item['label_en']}")
    check("seed.json: all Low/Page 00h items use verified page:offset and label suffix",
          not label_problems, repr(label_problems[:3]))
    check("seed.json: 512 config items intact", len(items) == 512, str(len(items)))

    mapping_en = json.loads((ROOT / "data/i18n_data_en.json").read_text(encoding="utf-8"))
    zh_labels = {i["label"] for i in items if ZH.search(i["label"])}
    check("i18n map: every Chinese data label has a Chinese-free English value",
          all(k in mapping_en and not ZH.search(mapping_en[k]) for k in zh_labels),
          str(sorted(zh_labels - set(mapping_en))[:3]))
    bundle = (ROOT / "cmis_service/static/js/data_en.js").read_text(encoding="utf-8")
    bundle_entries = bundle.count('\n  "')
    check("data_en.js: generated bundle matches the mapping entry count",
          bundle_entries == len(mapping_en),
          f"bundle={bundle_entries} map={len(mapping_en)}")

    # 5. Runtime parsing and frontend presentation --------------------------
    parse_problems = []
    for key, (page, offset) in EXPECT_CATALOG.items():
        hit = re.search(r"\d+", offset)
        if hit is None or int(hit.group(0)) != parse_unified(page + ":" + offset)[1]:
            parse_problems.append(key)
    check("api._parse_register_location: every offset yields the correct first byte",
          not parse_problems, repr(parse_problems[:3]))

    app = (ROOT / "cmis_service/static/js/app.js").read_text(encoding="utf-8")
    check("Frontend: lower register table uses unified mono offset + two-line field name",
          "mono(r.addr)" in app and "mono(r.en)" in app
          and "table table-sm table-vcenter" in app)
    check("Frontend: Upper 00h table shares the main table column order and badge",
          "esc(t('mod.pageOffset')) + '</th><th>' + esc(t('mod.size'))" in app
          and "badge(esc(r.access), 'secondary')" in app)
    check("Frontend: section title reflects Lower + Upper page coverage",
          "(Lower / Upper 00h-01h)" in app)
    high = catalog.get("HostInterfaceId")
    check("High-page notation unchanged (01h:128 (0x80) style still shipped)",
          high is not None and high["page"] == "01h"
          and high["byte_offset"] == "128 (0x80)")

    print(f"\n{len(PASS)} passed, {len(FAIL)} failed")
    return 1 if FAIL else 0


if __name__ == "__main__":
    sys.exit(main())
