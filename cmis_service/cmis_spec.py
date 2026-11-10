"""CMIS register-map reference data for OIF-CMIS-05.3 / 05.4.

This module is the single source of truth for the dashboard partition layout,
the Lower Page register map and the Command Data Block (CDB) command catalog.

Sources (see docs/CMIS_SECTIONS.md and data/knowledge_graph.json):
  * OIF-CMIS-05.3, Common Management Interface Specification rev 5.3 (Sep 2024)
  * OIF-CMIS-05.4, Common Management Interface Specification rev 5.4 (May 2026)
  * OIF-CMIS-05-Errata-01.0, CMIS 5.x Errata and Corrigenda (Feb 2025)
  * IETF draft-hi-ccamp-cmis-control-yang-04, CMIS page classification
  * Linux kernel net/ethtool/cmis.h and net/ethtool/cmis_cdb.c (GPL-2.0)
  * Public CMIS module datasheets (lower-memory layout)

Confidence policy: page numbers and CDB command IDs are corroborated by at least
two independent public sources and are marked "confirmed"; exact byte offsets
that could not be checked against the OIF PDF text are marked "partial" and are
also listed in knowledge_graph.json -> pending_confirmations.
"""

from __future__ import annotations

from typing import Any

SPEC_RELEASES = [
    {"doc": "OIF-CMIS-05.2", "revision": "5.2", "date": "April 2022",
     "publisher": "OIF", "note": "Last QSFP-DD MSA-era revision adopted by OIF"},
    {"doc": "OIF-CMIS-05.3", "revision": "5.3", "date": "September 2024",
     "publisher": "OIF", "note": "First revision fully produced under OIF; CDB in section 9"},
    {"doc": "OIF-CMIS-05-Errata-01.0", "revision": "5.x", "date": "February 2025",
     "publisher": "OIF", "note": "Interoperability fixes for Application advertising"},
    {"doc": "OIF-CMIS-05.4", "revision": "5.4", "date": "May 2026",
     "publisher": "OIF", "note": "Latest published CMIS revision"},
    {"doc": "OIF-C-CMIS-01.5", "revision": "1.5", "date": "September 2026",
     "publisher": "OIF", "note": "Coherent CMIS extension, pages 30h-4Fh"},
]

SOURCE_IDS = {
    "oif_53": "S-OIF-053",
    "oif_54": "S-OIF-054",
    "oif_52": "S-OIF-052",
    "errata": "S-OIF-ERRATA",
    "yang": "S-IETF-CMIS-YANG",
    "kernel": "S-GH-ETHTOOL",
    "datasheet": "S-ART-MAPYOURTECH",
    "sff": "S-SFF-8024",
}

# ---------------------------------------------------------------------------
# Dashboard partitions.  Each partition maps to a group of CMIS pages so the
# UI can present registers and configuration controls the way the spec does.
# ---------------------------------------------------------------------------
SECTIONS: list[dict[str, Any]] = [
    {
        "key": "LOW_PAGE",
        "zh": "低页 0x00（Lower + Upper Page 00h）",
        "en": "Low Page 0x00 (Lower + Upper 00h)",
        "pages": ["Lower 00h-7Fh", "Upper 00h 80h-FFh"],
        "spec_ref": "OIF-CMIS-05.3 8.2 / 8.4; 05.4 8.x",
        "source_ids": [SOURCE_IDS["oif_53"], SOURCE_IDS["oif_54"], SOURCE_IDS["datasheet"]],
        "confidence": "partial",
        "summary_zh": "常驻低 128 字节与 Upper Page 00h：模块标识、状态机、模块级标志、全局控制、CDB 状态、固件/应用通告、密码区、Bank/Page 选择；静态识别信息包含厂商、OUI、料号、序列号、日期码与 CC_BASE/CC_EXT 校验。",
        "summary_en": "Always-visible lower 128 bytes plus Upper Page 00h: module ID, state machine, module flags, global controls, CDB status, firmware/application advertising, password area, Bank/Page select; static identity holds vendor, OUI, part/serial number, date code and CC_BASE/CC_EXT checksums.",
        "write_policy": "read-mostly",
        "write_note_en": "Writes to Lower Memory are forbidden for remote access (IETF draft section 9.1). Only Bank/Page select and explicitly delegated controls are allowed in a lab setup.",
        "write_note_zh": "远程接入禁止写 Lower Memory（IETF 草案 9.1 节）；仅实验环境允许 Bank/Page 选择与被显式委派的控制位。",
    },
    {
        "key": "VDM",
        "zh": "VDM 诊断监控域",
        "en": "VDM (Versatile Diagnostic Monitoring)",
        "pages": ["Lower 14-25", "02h", "10h", "11h", "20h-2Fh"],
        "spec_ref": "OIF-CMIS-05.3 8.8 / 8.22; IETF YANG draft table 2",
        "source_ids": [SOURCE_IDS["oif_53"], SOURCE_IDS["yang"], SOURCE_IDS["kernel"]],
        "confidence": "partial",
        "summary_zh": "CMIS 称 Monitors：Lower 14-25 模块级监测量、Page 02h 告警/预警阈值、Page 10h/11h 通道状态与 Tx/Rx 光功率/偏置/温度监测量、Pages 20h-2Fh VDM；本项目统一以 VDM 命名该分区，并按规范页组织展示。",
        "summary_en": "CMIS calls these Monitors: Lower 14-25 module-level monitors, Page 02h alarm/warning thresholds, Page 10h/11h lane status and Tx/Rx power/bias/temperature monitors, Pages 20h-2Fh VDM; this service names the partition VDM throughout.",
        "write_policy": "thresholds-only",
        "write_note_en": "Thresholds and monitor configuration are page-delegated; raw monitor values are read-only.",
        "write_note_zh": "阈值与监控配置需按页委派；监测量本身只读。",
    },
    {
        "key": "CDB",
        "zh": "CDB 命令数据块与操作接口",
        "en": "CDB (Command Data Block) and operations",
        "pages": ["Lower 37-38", "Lower 118-125", "9Fh", "A0h-AFh"],
        "spec_ref": "OIF-CMIS-05.3 8.23 / 8.24 / 9; 05.4 9",
        "source_ids": [SOURCE_IDS["oif_53"], SOURCE_IDS["oif_54"], SOURCE_IDS["kernel"]],
        "confidence": "confirmed",
        "summary_zh": "Page 9Fh 承载 128 字节命令帧（CMDID / EPL 长度 / LPL 长度 / 校验码 / 120 字节 LPL），Pages A0h-AFh 承载最多 2048 字节 EPL；状态在 Lower 37-38，密码入口在 Lower 118-125。命令由写入结束于 9Fh:129 的操作触发。",
        "summary_en": "Page 9Fh holds the 128-byte command frame (CMDID / EPL length / LPL length / check code / 120-byte LPL); Pages A0h-AFh hold up to 2048 bytes of EPL. Status lives in Lower 37-38, password entry in Lower 118-125. A command is triggered by a write ending at or including 9Fh:129.",
        "write_policy": "gated",
        "write_note_en": "CDB pages MUST NOT appear in a remote-write allowlist (IETF draft section 9.1). Execution is gated by explicit confirmation, firmware commands by a separate flag.",
        "write_note_zh": "CDB 页禁止纳入远程写白名单（IETF 草案 9.1 节）；执行需显式确认，固件类命令另需单独开关。",
    },
    {
        "key": "CONTROL",
        "zh": "数据通路 / 诊断 / 相干控制",
        "en": "Datapath, diagnostics and coherent control",
        "pages": ["01h", "10h", "12h", "13h", "14h", "30h-4Fh"],
        "spec_ref": "OIF-CMIS-05.3 6.3 / 8.9 / 8.10 / 8.20; OIF-C-CMIS-01.5",
        "source_ids": [SOURCE_IDS["oif_53"], SOURCE_IDS["yang"], SOURCE_IDS["kernel"]],
        "confidence": "partial",
        "summary_zh": "Page 01h 应用描述符、Page 10h AppSel/DPSM/Staged Control Set、Pages 13h/14h PRBS 与环回、Page 12h 可调激光器、Pages 30h-4Fh C-CMIS 相干设置。",
        "summary_en": "Page 01h application descriptors, Page 10h AppSel/DPSM/Staged Control Set, Pages 13h/14h PRBS and loopbacks, Page 12h tunable laser, Pages 30h-4Fh C-CMIS coherent settings.",
        "write_policy": "delegated",
        "write_note_en": "Writable only when the page is explicitly delegated by the host NOS.",
        "write_note_zh": "仅在 Host NOS 显式委派该页后允许写入。",
    },
]

SECTION_BY_KEY = {s["key"]: s for s in SECTIONS}

# ---------------------------------------------------------------------------
# Lower Memory (Page 00h, always visible, address 0-127).
# Layout reproduced from a public CMIS module datasheet; CMIS 5.3/5.4 may move
# Application Advertising to Upper Page 01h. Offsets are therefore "partial".
# ---------------------------------------------------------------------------
LOWER_MEMORY_MAP: list[dict[str, Any]] = [
    {"addr": "0-3", "size": 4, "en": "ID and Status Area", "zh": "标识与状态区", "access": "RO",
     "note": "Module ID (SFF-8024), revision compliance, flat-memory indication, module state bits"},
    {"addr": "4-7", "size": 4, "en": "Lane Flag Summary", "zh": "通道标志汇总", "access": "RO/CoR",
     "note": "Summary of lane flags on pages 10h-1Fh; may be clear-on-read"},
    {"addr": "8-13", "size": 6, "en": "Module-Level Flags", "zh": "模块级标志", "access": "RO/CoR",
     "note": "Flags that are neither lane nor datapath specific"},
    {"addr": "14-25", "size": 12, "en": "Module-Level Monitors", "zh": "模块级监测量", "access": "RO",
     "note": "Temperature, supply voltage and auxiliary monitors (VDM partition)"},
    {"addr": "26-30", "size": 5, "en": "Module Global Controls", "zh": "模块全局控制", "access": "RW",
     "note": "LowPwrRequestSW, reset and module-wide controls"},
    {"addr": "31-36", "size": 6, "en": "Module-Level Flag Masks", "zh": "模块级标志掩码", "access": "RW",
     "note": "Masking bits for module-level flags"},
    {"addr": "37-38", "size": 2, "en": "CDB Status Area", "zh": "CDB 状态区", "access": "RO",
     "note": "Status of the most recently triggered CDB command"},
    {"addr": "39-40", "size": 2, "en": "Module Firmware Version", "zh": "模块固件版本", "access": "RO",
     "note": "Active firmware version"},
    {"addr": "41-63", "size": 23, "en": "Reserved", "zh": "保留区", "access": "RO", "note": "Reserved for future standardization"},
    {"addr": "64-82", "size": 19, "en": "Custom Area", "zh": "厂商自定义区", "access": "RW",
     "note": "Vendor or module-type specific use"},
    {"addr": "83-84", "size": 2, "en": "Inactive Firmware Version", "zh": "非活动固件版本", "access": "RO",
     "note": "00h indicates a single-image module"},
    {"addr": "85-117", "size": 33, "en": "Application Advertising", "zh": "应用通告", "access": "RO",
     "note": "Legacy layout; CMIS 5.3/5.4 uses Upper Page 01h application descriptors"},
    {"addr": "118-125", "size": 8, "en": "Password Entry and Change", "zh": "密码输入与修改", "access": "WO",
     "note": "Password entry at 0x7A (122) in the Linux ethtool implementation; 4-byte value"},
    {"addr": "126", "size": 1, "en": "Bank Select Byte", "zh": "Bank 选择字节", "access": "RW",
     "note": "Bank address of the currently visible upper page"},
    {"addr": "127", "size": 1, "en": "Page Select Byte", "zh": "Page 选择字节", "access": "RW",
     "note": "Page address of the currently visible upper page; observe tBPC hold time"},
]

UPPER_PAGE_00H: list[dict[str, Any]] = [
    {"en": "Vendor Name", "zh": "厂商名称", "size": 16, "access": "RO", "addr": "pending"},
    {"en": "Vendor OUI", "zh": "厂商 OUI", "size": 3, "access": "RO", "addr": "pending"},
    {"en": "Vendor Part Number", "zh": "厂商料号", "size": 16, "access": "RO", "addr": "pending"},
    {"en": "Vendor Revision", "zh": "厂商版本", "size": 2, "access": "RO", "addr": "pending"},
    {"en": "Vendor Serial Number", "zh": "序列号", "size": 16, "access": "RO", "addr": "pending"},
    {"en": "Date Code", "zh": "日期码", "size": 8, "access": "RO", "addr": "pending"},
    {"en": "CC_BASE / CC_EXT", "zh": "基础/扩展校验和", "size": 2, "access": "RO", "addr": "pending"},
]

# ---------------------------------------------------------------------------
# CDB command frame (Page 9Fh, bytes 128-255) and extended payload pages.
# Field widths are corroborated by net/ethtool/cmis.h in the Linux kernel:
#   __be16 id; __be16 epl_len; u8 lpl_len; u8 chk_code; u8 resv1; u8 resv2;
#   u8 payload[120];  -> 128 bytes, offsets 0x80..0xFF on page 9Fh.
# ---------------------------------------------------------------------------
CDB_PAGE = "9Fh"
CDB_EPL_PAGES = "A0h-AFh"
CDB_LPL_MAX = 120
CDB_EPL_MAX = 2048
CDB_I2C_ADDR = "0x50"

CDB_FRAME: list[dict[str, Any]] = [
    {"offset": "9Fh:128 (0x80)", "size": 2, "en": "CMDID", "zh": "命令 ID", "access": "WO",
     "note": "Big-endian command ID; writing the CMDID bytes triggers the command"},
    {"offset": "9Fh:130 (0x82)", "size": 2, "en": "EPL Length", "zh": "EPL 长度", "access": "WO",
     "note": "Big-endian length of the extended payload in pages A0h-AFh"},
    {"offset": "9Fh:132 (0x84)", "size": 1, "en": "LPL Length", "zh": "LPL 长度", "access": "WO",
     "note": "Number of valid bytes in the local payload, max 120"},
    {"offset": "9Fh:133 (0x85)", "size": 1, "en": "Check Code", "zh": "校验码", "access": "WO",
     "note": "Byte sum over EPL length, LPL length, reserved bytes and LPL must be zero modulo 256"},
    {"offset": "9Fh:134-135 (0x86-0x87)", "size": 2, "en": "Reserved", "zh": "保留", "access": "WO",
     "note": "Reserved, written as 00h"},
    {"offset": "9Fh:136-255 (0x88-0xFF)", "size": 120, "en": "Local Payload (LPL)",
     "zh": "本地载荷 LPL", "access": "RW", "note": "Command arguments and short replies"},
]

CDB_STATUS: list[dict[str, Any]] = [
    {"offset": "Lower 37-38 (0x25-0x26)", "en": "CDB Status Area", "zh": "CDB 状态区",
     "note": "Status of the most recent CDB command, including busy and failure bits"},
    {"offset": "Lower 122 (0x7A)", "en": "Password Entry", "zh": "密码入口",
     "note": "4-byte password; used by Linux ethtool before firmware commands"},
    {"offset": "Page 9Fh:136-255", "en": "CDB Reply (RPL)", "zh": "CDB 回复",
     "note": "Reply length, reply check code and up to 120 payload bytes"},
]

# Command groups and IDs follow the OIF-CMIS-05.3 section 9 table of contents.
# Linux ethtool net/ethtool/cmis.h independently confirms 0000h, 0040h, 0041h,
# 0101h, 0103h, 0104h, 0107h, 0109h and 010Ah.
CDB_COMMANDS: list[dict[str, Any]] = [
    {"cmd_id": "0000", "en": "Query Status", "zh": "查询状态", "group": "module",
     "spec_ref": "OIF-CMIS-05.3 9.3.1", "risk": "read", "lpl_rule": "optional 2-byte response delay"},
    {"cmd_id": "0001", "en": "Enter Password", "zh": "输入密码", "group": "security",
     "spec_ref": "OIF-CMIS-05.3 9.3.2", "risk": "security", "lpl_rule": "4-byte password"},
    {"cmd_id": "0002", "en": "Change Password", "zh": "修改密码", "group": "security",
     "spec_ref": "OIF-CMIS-05.3 9.3.3", "risk": "security", "lpl_rule": "4-byte new password"},
    {"cmd_id": "0004", "en": "Abort Processing", "zh": "中止处理", "group": "module",
     "spec_ref": "OIF-CMIS-05.3 9.3.4", "risk": "control", "lpl_rule": "empty LPL"},
    {"cmd_id": "0040", "en": "Module Features", "zh": "模块能力查询", "group": "capability",
     "spec_ref": "OIF-CMIS-05.3 9.4.1", "risk": "read", "lpl_rule": "optional feature group"},
    {"cmd_id": "0041", "en": "Firmware Management Features", "zh": "固件管理能力", "group": "capability",
     "spec_ref": "OIF-CMIS-05.3 9.4.2", "risk": "read", "lpl_rule": "optional sub-feature"},
    {"cmd_id": "0042", "en": "Performance Monitoring Features", "zh": "性能监控能力", "group": "capability",
     "spec_ref": "OIF-CMIS-05.3 9.4.3", "risk": "read", "lpl_rule": "optional"},
    {"cmd_id": "0043", "en": "BERT and Diagnostics Features", "zh": "BERT 与诊断能力", "group": "capability",
     "spec_ref": "OIF-CMIS-05.3 9.4.4", "risk": "read", "lpl_rule": "optional"},
    {"cmd_id": "0044", "en": "Security Features and Capabilities", "zh": "安全能力", "group": "capability",
     "spec_ref": "OIF-CMIS-05.3 9.4.5", "risk": "read", "lpl_rule": "optional"},
    {"cmd_id": "0045", "en": "Externally Defined Features", "zh": "外部定义能力", "group": "capability",
     "spec_ref": "OIF-CMIS-05.3 9.4.6", "risk": "read", "lpl_rule": "optional"},
    {"cmd_id": "0050", "en": "Get Application Attributes", "zh": "获取应用属性", "group": "capability",
     "spec_ref": "OIF-CMIS-05.3 9.4.7", "risk": "read", "lpl_rule": "application selector"},
    {"cmd_id": "0051", "en": "Get Interface Code Description", "zh": "获取接口码描述", "group": "capability",
     "spec_ref": "OIF-CMIS-05.3 9.4.8", "risk": "read", "lpl_rule": "interface id"},
    {"cmd_id": "0100", "en": "Get Firmware Info", "zh": "获取固件信息", "group": "firmware",
     "spec_ref": "OIF-CMIS-05.3 9.7.1", "risk": "read", "lpl_rule": "optional"},
    {"cmd_id": "0101", "en": "Start Firmware Download", "zh": "开始固件下载", "group": "firmware",
     "spec_ref": "OIF-CMIS-05.3 9.7.2", "risk": "firmware", "lpl_rule": "image size and slot"},
    {"cmd_id": "0102", "en": "Abort Firmware Download", "zh": "中止固件下载", "group": "firmware",
     "spec_ref": "OIF-CMIS-05.3 9.7.3", "risk": "firmware", "lpl_rule": "empty LPL"},
    {"cmd_id": "0103", "en": "Write Firmware Block LPL", "zh": "写固件块 LPL", "group": "firmware",
     "spec_ref": "OIF-CMIS-05.3 9.7.4", "risk": "firmware", "lpl_rule": "up to 120 bytes"},
    {"cmd_id": "0104", "en": "Write Firmware Block EPL", "zh": "写固件块 EPL", "group": "firmware",
     "spec_ref": "OIF-CMIS-05.3 9.7.5", "risk": "firmware", "lpl_rule": "EPL up to 2048 bytes"},
    {"cmd_id": "0105", "en": "Read Firmware Block LPL", "zh": "读固件块 LPL", "group": "firmware",
     "spec_ref": "OIF-CMIS-05.3 9.7.6", "risk": "read", "lpl_rule": "block address"},
    {"cmd_id": "0106", "en": "Read Firmware Block EPL", "zh": "读固件块 EPL", "group": "firmware",
     "spec_ref": "OIF-CMIS-05.3 9.7.7", "risk": "read", "lpl_rule": "block address"},
    {"cmd_id": "0107", "en": "Complete Firmware Download", "zh": "完成固件下载", "group": "firmware",
     "spec_ref": "OIF-CMIS-05.3 9.7.8", "risk": "firmware", "lpl_rule": "checksum or flags"},
    {"cmd_id": "0108", "en": "Copy Firmware Image", "zh": "复制固件镜像", "group": "firmware",
     "spec_ref": "OIF-CMIS-05.3 9.7.9", "risk": "firmware", "lpl_rule": "image selector"},
    {"cmd_id": "0109", "en": "Run Firmware Image", "zh": "运行固件镜像", "group": "firmware",
     "spec_ref": "OIF-CMIS-05.3 9.7.10", "risk": "firmware", "lpl_rule": "image selector"},
    {"cmd_id": "010A", "en": "Commit Firmware Image", "zh": "提交固件镜像", "group": "firmware",
     "spec_ref": "OIF-CMIS-05.3 9.7.11", "risk": "firmware", "lpl_rule": "confirmation flag"},
    {"cmd_id": "0200", "en": "Control PM", "zh": "性能监控控制", "group": "pm",
     "spec_ref": "OIF-CMIS-05.3 9.8.1", "risk": "control", "lpl_rule": "PM parameters"},
    {"cmd_id": "0201", "en": "Get PM Feature Information", "zh": "获取 PM 能力信息", "group": "pm",
     "spec_ref": "OIF-CMIS-05.3 9.8.2", "risk": "read", "lpl_rule": "feature selector"},
    {"cmd_id": "0380", "en": "Loopbacks", "zh": "环回诊断", "group": "diagnostics",
     "spec_ref": "OIF-CMIS-05.3 9.10 / 9.11 (partial)", "risk": "control", "lpl_rule": "diagnostic selector"},
]

CDB_COMMAND_BY_ID = {c["cmd_id"].upper(): c for c in CDB_COMMANDS}
FIRMWARE_PREFIXES = ("0101", "0102", "0103", "0104", "0107", "0108", "0109", "010A")


def is_firmware_command(cmd_id: str) -> bool:
    return cmd_id.upper() in FIRMWARE_PREFIXES


def parse_hex_bytes(text: str, max_len: int, field: str) -> tuple[bytes, list[dict]]:
    """Parse a whitespace/0x separated hex string into bytes, returning errors."""
    errors: list[dict] = []
    cleaned = (text or "").replace("0x", " ").replace(",", " ").replace(":", " ").strip()
    tokens = cleaned.split()
    if not tokens:
        return b"", errors
    raw = "".join(tokens)
    if len(raw) % 2:
        errors.append({"code": "ODD_HEX_LENGTH", "field": field,
                       "message": f"{field} must contain an even number of hex digits"})
        return b"", errors
    if any(ch not in "0123456789abcdefABCDEF" for ch in raw):
        errors.append({"code": "INVALID_HEX", "field": field,
                       "message": f"{field} contains non-hexadecimal characters"})
        return b"", errors
    data = bytes.fromhex(raw)
    if len(data) > max_len:
        errors.append({"code": "PAYLOAD_TOO_LARGE", "field": field,
                       "message": f"{field} is {len(data)} bytes, maximum is {max_len}"})
        return b"", errors
    return data, errors


def compose_frame(cmd_id: str, lpl_hex: str = "", epl_hex: str = "") -> dict:
    """Build a 128-byte CDB command frame without touching any hardware.

    The check code is the 8-bit two's complement of the sum of all bytes from
    EPL length through the LPL payload (Linux ethtool uses the same convention
    over struct ethtool_cmis_cdb_request.body).
    """
    errors: list[dict] = []
    cid = (cmd_id or "").strip().upper().replace("0X", "")
    if len(cid) != 4 or any(ch not in "0123456789ABCDEF" for ch in cid):
        errors.append({"code": "INVALID_CMD_ID", "field": "cmd_id",
                       "message": "cmd_id must be a 4-digit hexadecimal value, e.g. 0040"})
    lpl, err_l = parse_hex_bytes(lpl_hex, CDB_LPL_MAX, "lpl_hex")
    epl, err_e = parse_hex_bytes(epl_hex, CDB_EPL_MAX, "epl_hex")
    errors.extend(err_l)
    errors.extend(err_e)
    if not errors and not epl and "0104" == cid:
        errors.append({"code": "EPL_REQUIRED", "field": "epl_hex",
                       "message": "CMD 0104h requires an extended payload"})
    if errors:
        return {"valid": False, "errors": errors, "frame_hex": "", "check_code": None}

    body = bytearray()
    body += len(epl).to_bytes(2, "big")
    body += bytes([len(lpl), 0x00, 0x00, 0x00])
    body += lpl + b"\x00" * (CDB_LPL_MAX - len(lpl))
    body[3] = (-sum(body)) & 0xFF  # check code at frame byte 5 (9Fh:133)
    frame = bytes.fromhex(cid) + bytes(body)
    return {
        "valid": True,
        "errors": [],
        "cmd_id": cid,
        "command": CDB_COMMAND_BY_ID.get(cid, {}).get("en", "Vendor or undefined command"),
        "risk": CDB_COMMAND_BY_ID.get(cid, {}).get("risk", "unknown"),
        "spec_ref": CDB_COMMAND_BY_ID.get(cid, {}).get("spec_ref", "OIF-CMIS-05.3 9 (command ID not in catalog)"),
        "lpl_len": len(lpl),
        "epl_len": len(epl),
        "check_code": f"0x{body[3]:02X}",
        "frame_hex": frame.hex().upper(),
        "epl_hex": epl.hex().upper(),
        "page": CDB_PAGE,
        "epl_pages": CDB_EPL_PAGES,
        "trigger": "Write ending at or including 9Fh:129 (OIF-CMIS-05.3 8.23.1 / 8.23.2)",
        "warnings": [
            {"code": "OFFSETS_PARTIAL",
             "message": "Exact bit assignments and reply offsets must be checked against the OIF-CMIS-05.3/05.4 PDF before hardware use."},
            {"code": "NO_HARDWARE_IO",
             "message": "Frame composition is offline only; execution is controlled by the active access adapter and safety flags."},
        ],
    }


# ---------------------------------------------------------------------------
# Access-path descriptions.  The two production paths are deliberately kept
# separate from the offline mirror used by the demo dataset.
# ---------------------------------------------------------------------------
ACCESS_MODES: list[dict[str, Any]] = [
    {
        "key": "mirror",
        "zh": "本地镜像（离线演示）",
        "en": "Local mirror (offline demo)",
        "transport": "sqlite",
        "topology": "browser -> local HTTP service -> SQLite mirror",
        "reads": "Cached values from the local mirror database",
        "writes": "Staged in SQLite and written to the audit log; never sent to hardware",
        "when": "Development, training, offline review and CI",
        "risk": "none",
    },
    {
        "key": "ssh-i2c",
        "zh": "方式一：测试 Server 经 SSH 到测试 Switch 走 I2C",
        "en": "Mode A: test server -> SSH -> test switch -> I2C",
        "transport": "ssh+subprocess+i2c",
        "topology": "browser -> service on TEST SERVER -> SSH session -> switch CLI / i2c-tools on TEST SWITCH -> module EEPROM at 0x50",
        "reads": "Raw page/byte reads over the two-wire interface; page select at Lower 127",
        "writes": "Direct register writes; must be enabled explicitly and confined to lab hardware",
        "when": "Lab bring-up, module characterization, CDB firmware work on a bench",
        "risk": "high",
        "controls": ["Page/bank select must be restored after every multi-page read",
                     "Lower Memory writes are blocked by the safety policy",
                     "CDB firmware commands require explicit confirmation"],
    },
    {
        "key": "rest-api",
        "zh": "方式二：经目标设备 RESTful API",
        "en": "Mode B: target device RESTful API",
        "transport": "https+json",
        "topology": "browser -> service -> northbound REST API of the target device / NOS -> module CMIS registers",
        "reads": "GET of normalized CMIS resources; the device owns the I2C transaction",
        "writes": "PUT/POST of delegated pages; governed by read/write allowlists",
        "when": "Production or integration environments, multi-device operations, automation",
        "risk": "medium",
        "controls": ["Token is read from an environment variable and never exposed by the API",
                     "Page-level allowlists follow IETF draft-hi-ccamp-cmis-control-yang-04",
                     "CDB pages are read-only over REST by default"],
    },
]

ACCESS_MODE_BY_KEY = {m["key"]: m for m in ACCESS_MODES}
