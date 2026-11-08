"""Build data/knowledge_graph.json, the linkable CMIS knowledge graph.

Entities: devices, modules, interfaces, config items, clauses, specification
documents, concepts, open-source projects, organizations and services.
Relations: CONTAINS, DEFINES, CONSTRAINS, IMPLEMENTS, REFERENCES, and more.
Every entity and relation carries source_ids / confidence / status; unverified
claims are listed in pending_confirmations.

Usage: python tools/build_kg.py
"""

from __future__ import annotations

import json
from collections import Counter
from pathlib import Path

from cmis_catalog import DEVICE_PROFILES, FIELD_CATALOG

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "data" / "knowledge_graph.json"
CHECKED_AT = "2026-11-08"
OIF = ["S-OIF-052", "S-OIF-INDEX"]


def S(source_id, title, publisher, url, kind, license_="", note="", confidence="confirmed"):
    return {"source_id": source_id, "title": title, "publisher": publisher, "url": url,
            "kind": kind, "license": license_, "retrieved_at": CHECKED_AT, "note": note,
            "confidence": confidence}


SOURCES = [
    S("S-OIF-INDEX", "OIF Implementation Agreements - Management Interface Specifications", "OIF",
      "https://www.oiforum.com/technical-work/implementation-agreements/", "oif_page",
      "公开 IA 索引（文档条款以各 PDF 为准）",
      "核对了 05.2/05.3/05.4、Errata、C-CMIS 01.1-01.5、VCS、FF、ELSFP-CMIS、LT 的编号与发布日期"),
    S("S-OIF-052", "OIF-CMIS-05.2 Common Management Interface Specification Rev 5.2 (April 2022)", "OIF",
      "https://www.oiforum.com/wp-content/uploads/OIF-CMIS-05.2.pdf", "oif_ia",
      "OIF IA（公开 PDF）", "首个由 OIF 完成接管后发布的 CMIS 版本"),
    S("S-OIF-053", "OIF-CMIS-05.3 CMIS Rev 5.3 (September 2024)", "OIF",
      "https://www.oiforum.com/wp-content/uploads/OIF-CMIS-05.3.pdf", "oif_ia", "OIF IA（公开 PDF）"),
    S("S-OIF-054", "OIF-CMIS-05.4 CMIS Rev 5.4 (May 2026)", "OIF",
      "https://www.oiforum.com/wp-content/uploads/OIF-CMIS-05.4.pdf", "oif_ia",
      "OIF IA（公开 PDF）", "本次整理时 OIF 官网列出的最新主规范"),
    S("S-OIF-ERRATA", "OIF-CMIS-05-Errata-01.0 Errata and Corrigenda for CMIS 5.x Rev 1.0 (February 2025)", "OIF",
      "https://www.oiforum.com/wp-content/uploads/OIF-CMIS-05-Errata-01.0.pdf", "oif_ia", "OIF IA（公开 PDF）"),
    S("S-IETF-CMIS-YANG", "draft-hi-ccamp-cmis-control-yang-04 - A YANG Data Model for CMIS Access and Control", "IETF",
      "https://datatracker.ietf.org/doc/html/draft-hi-ccamp-cmis-control-yang-04", "ietf_draft", "",
      "Section 3 page classification table and section 9.1 security rules: Lower Memory writes and CDB pages 9Fh-AFh MUST NOT be remotely writable", "partial"),
    S("S-GH-LINUX-CDB", "Linux kernel net/ethtool/cmis_cdb.c and cmis.h (GPL-2.0)", "Linux Foundation",
      "https://github.com/torvalds/linux/blob/master/net/ethtool/cmis_cdb.c", "github_repo", "GPL-2.0",
      "CDB request frame layout (CMDID / EPL len / LPL len / check code / 120-byte LPL), EPL pages A0h-AFh, password at 0x7A, command IDs 0000h-010Ah"),
    S("S-ART-VITEX", "AI Data Center Engineering Guide - CMIS 5.3 EEPROM map (Vitex)", "Vitex",
      "https://cdn.asp.events/CLIENT_Kisaco_R_E0D4AD69_B740_B124_D2ADF5A777880773/sites/AI-Infra-Summit-2026/media/libraries/sponsor-editorial/9781-vitex-eeprom-guide-2026.pdf", "vendor_guide", "",
      "Lower/Upper memory split, Page 00h identity fields, Page 01h Application Descriptors, Page 02h thresholds, 10h-11h lane monitoring, Page 9Fh CDB", "partial"),
    S("S-OIF-CCMIS-013", "OIF-C-CMIS-01.3 Implementation Agreement for Coherent CMIS (October 2023)", "OIF",
      "https://www.oiforum.com/wp-content/uploads/OIF-C-CMIS-01.3.pdf", "oif_ia", "OIF IA（公开 PDF）"),
    S("S-OIF-CCMIS-015", "OIF-C-CMIS-01.5 Implementation Agreement for Coherent CMIS (September 2026)", "OIF",
      "https://www.oiforum.com/wp-content/uploads/OIF-C-CMIS-01.5.pdf", "oif_ia", "OIF IA（公开 PDF）"),
    S("S-OIF-VCS-011", "OIF-CMIS-VCS-01.1 CMIS Versatile Control Set Rev 1.1 (July 2025)", "OIF",
      "https://www.oiforum.com/wp-content/uploads/OIF-CMIS-VCS-01.1.pdf", "oif_ia", "OIF IA（公开 PDF）"),
    S("S-OIF-FF-010", "OIF-CMIS-FF-01.0 Formfactor Specific Hardware Management CMIS-FF (September 2024)", "OIF",
      "https://www.oiforum.com/wp-content/uploads/OIF-CMIS-FF-01.0.pdf", "oif_ia", "OIF IA（公开 PDF）"),
    S("S-OIF-ELSFP-010", "OIF-ELSFP-CMIS-01.0 ELSFP CMIS (September 2024)", "OIF",
      "https://www.oiforum.com/wp-content/uploads/OIF-ELSFP-CMIS-01.0.pdf", "oif_ia", "OIF IA（公开 PDF）"),
    S("S-OIF-LT-010", "OIF-CMIS-LT-01.0 CMIS Out of Band Link Training (September 2026)", "OIF",
      "https://www.oiforum.com/wp-content/uploads/OIF-CMIS-LT-01.0.pdf", "oif_ia", "OIF IA（公开 PDF）"),
    S("S-SFF-8024", "SNIA SFF-8024 - SFF Module / Interface Identifier Codes", "SNIA SFF TWG",
      "https://www.snia.org/technology-communities/sff/specifications", "standard_index", "",
      "Host/Media Interface ID、Module Identifier 编码来源；具体 Revision 待确认", "partial"),
    S("S-SFF-8636", "SFF-8636 - QSFP+ / QSFP28 Management Interface (legacy)", "SNIA SFF TWG",
      "https://www.snia.org/technology-communities/sff/specifications", "standard_index", "",
      "CMIS 之前的 QSFP 管理接口，用于对比，非本次配置项来源"),
    S("S-QSFPDD-MSA", "QSFP-DD MSA CMIS 4.0 / 5.0（CMIS 前身）", "QSFP-DD MSA",
      "http://www.qsfp-dd.com/", "msa", "", "CMIS 2022 年移交 OIF 前的版本谱系；精确文档编号待确认", "partial"),
    S("S-GH-API-SNAPSHOT", "GitHub REST API /repos 元数据快照 (2026-11-08)", "GitHub",
      "https://api.github.com", "github_api", "API 数据",
      "star / license / pushed_at / archived 均为本次构建时实时读取"),
    S("S-GH-TABLER", "tabler/tabler - HTML Dashboard UI Kit (v1.7.3, MIT)", "Tabler Authors",
      "https://github.com/tabler/tabler", "github_repo", "MIT",
      "42021 stars / 4433 forks / pushed_at 2026-11-07；本项目选定并 vendored 的前端框架"),
    S("S-GH-TABLER-ICONS", "tabler/tabler-icons (MIT)", "Tabler Authors",
      "https://github.com/tabler/tabler-icons", "github_repo", "MIT",
      "22579 stars / pushed_at 2026-11-07；配套图标字体"),
    S("S-GH-ADMINLTE", "ColorlibHQ/AdminLTE (MIT)", "ColorlibHQ",
      "https://github.com/ColorlibHQ/AdminLTE", "github_repo", "MIT",
      "45678 stars / pushed_at 2026-11-04；选型候选"),
    S("S-GH-DASHY", "Lissy93/dashy (MIT)", "Lissy93",
      "https://github.com/Lissy93/dashy", "github_repo", "MIT",
      "26940 stars / pushed_at 2026-11-07；选型候选（Vue/Node 构建链）"),
    S("S-GH-GRAFANA", "grafana/grafana (AGPL-3.0)", "Grafana Labs",
      "https://github.com/grafana/grafana", "github_repo", "AGPL-3.0",
      "77759 stars / pushed_at 2026-11-08；选型候选（Go 服务 + 数据库，重量级）"),
    S("S-GH-SONIC-PC", "sonic-net/sonic-platform-common (CMIS API: sonic_xcvr/api/public/cmis.py)", "SONiC",
      "https://github.com/sonic-net/sonic-platform-common", "github_repo", "NOASSERTION (GitHub 未识别)",
      "61 stars / 255 forks / pushed_at 2026-11-04；CmisApi 实现字段解析、AppSel、SI staging；许可待法务确认", "partial"),
    S("S-GH-SONIC-PD", "sonic-net/sonic-platform-daemons (xcvrd CMIS 初始化状态机)", "SONiC",
      "https://github.com/sonic-net/sonic-platform-daemons", "github_repo", "待确认",
      "PR #217 引入 CMIS application initialization", "partial"),
    S("S-GH-SONIC-UTIL", "sonic-net/sonic-utilities (sfputil show eeprom)", "SONiC",
      "https://github.com/sonic-net/sonic-utilities", "github_repo", "待确认",
      "CMIS EEPROM/VDM 命令行展示", "partial"),
    S("S-GH-FBOSS", "facebook/fboss -> meta/fboss (qsfp_service, CmisModule)", "Meta",
      "https://github.com/facebook/fboss", "github_repo", "NOASSERTION (BSD-style + PATENTS 文件)",
      "1002 stars / pushed_at 2026-11-07；许可与专利授予条款待法务确认", "partial"),
    S("S-GH-LIBSFFCMIS", "vjardin/libsffcmis (C 库 + CLI, 支持 OIF-CMIS-05.3 / C-CMIS-01.3)", "vjardin",
      "https://github.com/vjardin/libsffcmis", "github_repo", "README 声明 GPLv2（GitHub 未识别 LICENSE）",
      "派生自 ethtool；按页拆分 cmis-datapath / cmis-vdm / cmis-cdb / cmis-diag / cmis-coherent；许可待确认", "partial"),
    S("S-GH-ETHTOOL", "ethtool (cmis.c / qsfp.c, GPL-2.0)", "kernel.org / GitHub mirrors",
      "https://github.com/kernelkit/ethtool", "github_repo", "GPL-2.0",
      "cmis.c 注释引用 CMIS Rev.5 §8.4.4 Table 8-40（最大 Bank 数、每 Bank 8 通道）"),
    S("S-GH-LINUX", "Linux kernel (I2C / SFP 与模块 EEPROM 访问)", "Linux Foundation",
      "https://github.com/torvalds/linux", "github_repo", "GPL-2.0",
      "底层 I2C 访问路径，作为 CMIS 实现的硬件通道背景", "partial"),
    S("S-ART-MAPYOURTECH", "CMIS for Pluggable Optics: Management Architecture, State Machines and Comparison", "MapYourTech",
      "https://mapyourtech.com/cmis-for-pluggable-optics-management-architecture-state-machines-and-comparison",
      "technical_article", "", "引用 OIF CMIS IA clause 5.2.1、Table 10-4；Lower/Upper Memory、Bank:Page:Byte 模型"),
    S("S-ART-W2W", "CMIS Transceiver Programming & Breakout Configuration Reference Guide v1.0", "Wave2Wave",
      "https://www.wave2wave.io/datasheets/resources/W2W_CMIS-Programming-Breakout-Guide_v1.0.pdf",
      "vendor_guide", "", "Page 00h/01h 寄存器地址、0xAD AppSel 编码、Lane Count Encoding（第三方解读）", "partial"),
    S("S-ART-LINKPP", "CMIS Explained - Common Management Interface", "LINK-PP",
      "https://resources.l-p.com/knowledge-center/cmis-common-management-interface-specification",
      "technical_article", "", "CMIS 背景、QSFP-DD/OSFP/COBO、应用化配置与 DDM"),
    S("S-ART-XRDOCS", "DCO configuration using CMIS AppSel (IOS-XR)", "Cisco / xrdocs",
      "https://xrdocs.io/design/blogs/2026-0610-dco-configuration-appsel", "technical_article", "",
      "400ZR / OpenZR+ / 800ZR 与 AppSel 的工程上下文"),
    S("S-ART-LIGHTWAVE", "OIF finishes one CMIS project, starts another (2022 Q2)", "Lightwave Online",
      "https://www.lightwaveonline.com/optical-tech/transmission/article/14277596/oif-finishes-one-cmis-project-starts-another",
      "news", "", "CMIS 5.2 作为首个 OIF IA、由 QSFP-DD MSA 移交 OIF 的背景"),
    S("S-ART-CSDN-52", "CMIS 5.2 深度解读：光模块 I2C 管理、LPO 配置与实战排查", "CSDN 社区",
      "https://blog.csdn.net/weixin_32642109/article/details/164407082", "technical_article", "",
      "I2C 0x50/0x51、Lower/Upper 分页、Module State 中文解读（社区资料，条款号需复核）", "partial"),
    S("S-ART-CSDN-53", "CMIS 5.3 vs 5.2：光模块管理接口差异与驱动迁移实践", "CSDN 社区",
      "https://blog.csdn.net/weixin_29193359/article/details/164416903", "technical_article", "",
      "IntL 中断、密码保护区、消息邮箱（社区资料，条款号需复核）", "partial"),
    S("S-INTERNAL", "本项目内部示例设备数据（合成）", "本项目", "data/seed.json", "internal_dataset", "",
      "设备/模块/配置项均为演示合成数据，不代表真实网元资产", "confirmed"),
]


def E(entity_id, type_, name, summary, sources=None, confidence="confirmed", status="active", **attrs):
    return {"entity_id": entity_id, "type": type_, "name": name, "summary": summary,
            "source_ids": sources or [], "confidence": confidence, "status": status, "attrs": attrs}


ENTITIES: list[dict] = []

# --- Organizations ---
ENTITIES += [
    E("ORG-OIF", "Organization", "OIF（光互联论坛）", "CMIS 及其扩展 IA 的维护组织，2022 年从 QSFP-DD MSA 接管 CMIS", ["S-OIF-INDEX", "S-ART-LIGHTWAVE"]),
    E("ORG-SNIA", "Organization", "SNIA SFF TWG", "SFF-8024 / SFF-8636 等模块编码与管理接口规范维护方", ["S-SFF-8024"]),
    E("ORG-QSFPDD", "Organization", "QSFP-DD MSA", "CMIS 4.0/5.0 的原始发起方", ["S-QSFPDD-MSA", "S-ART-LIGHTWAVE"], "partial"),
    E("ORG-SONIC", "Organization", "SONiC / Linux Foundation", "开源网络操作系统，含 CMIS 平台抽象与 xcvrd", ["S-GH-SONIC-PC"]),
    E("ORG-META", "Organization", "Meta (FBOSS)", "FBOSS qsfp_service 的维护方", ["S-GH-FBOSS"]),
]

# --- Specification documents ---
STANDARDS = [
    ("STD-CMIS-052", "OIF-CMIS-05.2 (Rev 5.2, 2022-04)", ["S-OIF-052", "S-OIF-INDEX"], "confirmed", "首个 OIF 发布版"),
    ("STD-CMIS-053", "OIF-CMIS-05.3 (Rev 5.3, 2024-09)", ["S-OIF-053", "S-OIF-INDEX"], "confirmed", ""),
    ("STD-CMIS-054", "OIF-CMIS-05.4 (Rev 5.4, 2026-05)", ["S-OIF-054", "S-OIF-INDEX"], "confirmed", "本次调研时最新主规范"),
    ("STD-CMIS-ERRATA", "OIF-CMIS-05-Errata-01.0 (2025-02)", ["S-OIF-ERRATA", "S-OIF-INDEX"], "confirmed", "CMIS 5.x 勘误"),
    ("STD-CCMIS-013", "OIF-C-CMIS-01.3 (2023-10)", ["S-OIF-CCMIS-013", "S-OIF-INDEX"], "confirmed", ""),
    ("STD-CCMIS-015", "OIF-C-CMIS-01.5 (2026-09)", ["S-OIF-CCMIS-015", "S-OIF-INDEX"], "confirmed", ""),
    ("STD-VCS-011", "OIF-CMIS-VCS-01.1 (2025-07)", ["S-OIF-VCS-011", "S-OIF-INDEX"], "confirmed", "Versatile Control Set"),
    ("STD-FF-010", "OIF-CMIS-FF-01.0 (2024-09)", ["S-OIF-FF-010", "S-OIF-INDEX"], "confirmed", "封装相关硬件管理"),
    ("STD-ELSFP-010", "OIF-ELSFP-CMIS-01.0 (2024-09)", ["S-OIF-ELSFP-010", "S-OIF-INDEX"], "confirmed", "外置激光器"),
    ("STD-LT-010", "OIF-CMIS-LT-01.0 (2026-09)", ["S-OIF-LT-010", "S-OIF-INDEX"], "confirmed", "带外链路训练"),
    ("STD-SFF-8024", "SFF-8024 模块/接口编码表", ["S-SFF-8024"], "partial", "版本待确认"),
    ("STD-SFF-8636", "SFF-8636（旧版 QSFP 管理接口）", ["S-SFF-8636"], "confirmed", "对比参照"),
    ("STD-QSFPDD-CMIS", "QSFP-DD MSA CMIS 4.0/5.0", ["S-QSFPDD-MSA", "S-ART-LIGHTWAVE"], "partial", "文档编号待确认"),
]
for sid, name, sources, conf, note in STANDARDS:
    ENTITIES.append(E(sid, "Standard", name, f"CMIS 规范体系文档：{name}", sources, conf, note=note))

# --- Specification clauses ---
CLAUSES = [
    ("CL-5-2-1", "§5.2.1 管理接口地址空间", "Lower 00h-7Fh 固定；Upper 80h-FFh 由 Bank/Page 选择映射", ["S-ART-MAPYOURTECH", "S-OIF-052"], "partial"),
    ("CL-6-2-1", "§6.2.1 Application / Application Advertising", "模块通过 Page 00h Application Descriptor 声明支持的 Host/Media 接口与 lane 组合", ["S-OIF-052", "S-ART-W2W"], "partial"),
    ("CL-6-2-2", "§6.2.2 Data Path 定义", "Data Path = 一组 Host 通道 + Media 通道 + 模块内部资源，实现某 Application", ["S-OIF-052", "S-ART-CSDN-52"], "partial"),
    ("CL-6-2-3", "§6.2.3 Control Set", "Staged / Active Control Set 与 VDM/VCS 控制集模型", ["S-OIF-052", "S-OIF-VCS-011"], "partial"),
    ("CL-6-3-2", "§6.3.2 Module State Machine", "ModuleReset / LowPwr / PwrUp / Ready / Fault 等状态与迁移条件", ["S-OIF-052", "S-ART-CSDN-52"], "partial"),
    ("CL-6-3-3", "§6.3.3 DPSM 数据路径状态机", "DPDeactivated -> DPInit -> DPActivated；每个 Data Path 一个 DPSM 实例", ["S-OIF-052", "S-ART-CSDN-52"], "partial"),
    ("CL-8-2", "§8.2 内存映射总览", "寄存器地址 = Bank:Page:Byte；Flat memory 模块仅 Lower + Page 00h", ["S-OIF-052", "S-ART-MAPYOURTECH"], "partial"),
    ("CL-8-4", "§8.4 Page 00h 管理与广告信息", "厂商信息、Module Type、Application Descriptor（86-... 起）", ["S-OIF-052", "S-ART-W2W"], "partial"),
    ("CL-8-4-4", "§8.4.4 / Table 8-40 Bank 与通道上限", "最大 4 个 Bank、每 Bank 8 通道（ethtool cmis.c 注释引用）", ["S-GH-ETHTOOL", "S-OIF-052"], "partial"),
    ("CL-8-9", "§8.9 Page 10h/11h 数据路径控制与状态", "TxDisable、DataPathInit、DPState、ConfigError、Staged Control Set", ["S-OIF-052", "S-GH-SONIC-PC", "S-GH-LIBSFFCMIS"], "partial"),
    ("CL-8-9-2", "§8.9.2 Output Status", "Tx/Rx 方向输出状态独立上报，不与 DPSM 状态混同", ["S-OIF-052", "S-ART-CSDN-52"], "partial"),
    ("CL-10-4", "Table 10-4 页切换保持时间 tBPC", "Bank/Page 切换后 ≤ 10 ms 访问保持时间", ["S-ART-MAPYOURTECH", "S-OIF-052"], "partial"),
    ("CL-APSEL", "§6.3 Application Select 激活", "AppSel 0xAD 编码，Page 01h 逐 lane 选择 Application 与 DataPath ID", ["S-ART-W2W", "S-OIF-052", "S-ART-XRDOCS"], "partial"),
    ("CL-THRESH", "Page 02h Alarm/Warning Thresholds", "温度/电压/功率告警与预警门限", ["S-OIF-052", "S-ART-MAPYOURTECH", "S-GH-LIBSFFCMIS"], "partial"),
    ("CL-CDB", "Page 9Fh / A0h-AFh CDB 命令与扩展载荷", "固件管理、结构化命令邮箱", ["S-OIF-052", "S-GH-LIBSFFCMIS"], "partial"),
    ("CL-VDM", "Pages 20h-2Fh VDM 可观测量", "VDM 监视、阈值与 Freeze 原子读取", ["S-OIF-052", "S-GH-LIBSFFCMIS"], "partial"),
    ("CL-DIAG", "Pages 13h/14h 诊断（PRBS / Loopback / BER）", "链路诊断能力", ["S-OIF-052", "S-GH-LIBSFFCMIS"], "partial"),
    ("CL-TUNABLE", "Pages 04h/12h 可调激光器能力", "DCO 频率/波长配置能力", ["S-OIF-052", "S-GH-LIBSFFCMIS", "S-OIF-CCMIS-013"], "partial"),
    ("CL-CCMIS-PM", "C-CMIS 性能监测（Pages 34h/35h、Flag 33h/3Bh）", "相干模块 PM / FEC / Flag 解码", ["S-OIF-CCMIS-013", "S-GH-LIBSFFCMIS"], "partial"),
    ("CL-PROTECTED", "受保护区与密码机制", "写保护控制字段需密码解锁（社区资料，条款待核）", ["S-ART-CSDN-53"], "pending"),
]
for cid, name, summary, sources, conf in CLAUSES:
    ENTITIES.append(E(cid, "SpecClause", name, summary, sources, conf,
                      status="needs_review" if conf != "confirmed" else "active"))

# --- Interfaces ---
INTERFACES = [
    ("IF-TWI", "TWI / I2C 两线管理接口 (0x50)", "Host 与模块之间的物理管理通道，256 字节可见窗口", ["S-ART-MAPYOURTECH", "S-ART-CSDN-52", "S-ART-LINKPP"], "partial"),
    ("IF-LOWER", "Lower Memory (00h-7Fh)", "固定映射：模块状态、Flag、中断掩码、CDB 状态、Bank/Page Select", ["S-ART-MAPYOURTECH", "S-OIF-052"], "confirmed"),
    ("IF-UPPER", "Upper Memory (80h-FFh)", "分页映射：一次只暴露一个 Bank:Page 的 128 字节", ["S-ART-MAPYOURTECH", "S-OIF-052"], "confirmed"),
    ("IF-BANKPAGE", "Bank/Page 选择寄存器 (7Eh / 7Fh)", "决定 Upper Memory 映射；切换需遵守 tBPC", ["S-ART-MAPYOURTECH", "S-OIF-052", "S-GH-ETHTOOL"], "confirmed"),
    ("IF-HOST-ELEC", "Host Electrical Interface", "主机侧电接口（如 100GAUI-1-S C2M / 400GAUI-8），编码见 SFF-8024", ["S-OIF-052", "S-SFF-8024", "S-ART-W2W"], "partial"),
    ("IF-MEDIA", "Media Interface", "线路侧光/铜接口（如 800GBASE-SR8 / 400G FR4 / 400ZR），编码见 SFF-8024", ["S-OIF-052", "S-SFF-8024", "S-ART-W2W"], "partial"),
    ("IF-DATAPATH", "Data Path", "由 Host/Media lane 与模块内部资源构成的双向数据通道", ["S-OIF-052", "S-ART-CSDN-52"], "partial"),
    ("IF-LANE", "Host / Media Lane", "按 lane 的通道控制与状态（8 lanes / Bank）", ["S-OIF-052", "S-GH-ETHTOOL", "S-ART-W2W"], "partial"),
    ("IF-CDB", "Command Data Block (CDB)", "结构化命令/固件管理消息接口，Page 9Fh + A0h-AFh", ["S-OIF-052", "S-GH-LIBSFFCMIS"], "partial"),
    ("IF-VDM", "VDM 观测接口 (Pages 20h-2Fh)", "Versatile Diagnostics Monitoring 可观测量", ["S-OIF-052", "S-GH-LIBSFFCMIS"], "partial"),
    ("IF-NETPATH", "Network Path (Pages 16h/17h)", "网络路径控制/状态（libsffcmis cmis-netpath.c）", ["S-GH-LIBSFFCMIS"], "partial"),
    ("IF-CONTROLSET", "Staged / Active Control Set", "先 stage 再 apply 的控制集模型（VCS 扩展）", ["S-OIF-052", "S-OIF-VCS-011", "S-GH-SONIC-PC"], "partial"),
]
for iid, name, summary, sources, conf in INTERFACES:
    ENTITIES.append(E(iid, "Interface", name, summary, sources, conf))

# --- Modules / form factors ---
MODULES = [
    ("MOD-QSFPDD", "QSFP-DD 光模块", "8 lane 可插拔封装，CMIS 主要承载对象；Identifier 编码 0x18 待复核", ["S-OIF-052", "S-ART-W2W", "S-ART-LINKPP"], "partial"),
    ("MOD-OSFP", "OSFP 光模块", "8 lane 可插拔封装，带散热鳍片；Identifier 0x19 待复核", ["S-OIF-052", "S-ART-W2W", "S-ART-LINKPP"], "partial"),
    ("MOD-QSFP112", "QSFP112 光模块", "4 lane 112G/lane 封装；Identifier 0x1E 待复核", ["S-ART-W2W"], "partial"),
    ("MOD-COBO", "COBO 板载光模块", "CMIS 支持板载形态", ["S-ART-LINKPP", "S-OIF-052"], "partial"),
    ("MOD-DCO", "相干 DCO (400ZR / 800ZR / OpenZR+)", "C-CMIS 扩展的相干可插拔模块，频率/PM 配置", ["S-OIF-CCMIS-013", "S-OIF-CCMIS-015", "S-ART-XRDOCS"], "confirmed"),
    ("MOD-ELSFP", "ELSFP 外置激光器模块", "OIF-ELSFP-CMIS-01.0 定义其 CMIS 扩展", ["S-OIF-ELSFP-010"], "confirmed"),
    ("MOD-FLAT", "Flat Memory 模块（无源铜缆等）", "仅 Lower + Page 00h，只读 EEPROM", ["S-ART-MAPYOURTECH", "S-OIF-052"], "confirmed"),
    ("MOD-CPO", "共封装光学 (CPO)", "OIF 后续 CMIS 项目方向之一", ["S-ART-LIGHTWAVE"], "partial"),
]
for mid, name, summary, sources, conf in MODULES:
    ENTITIES.append(E(mid, "Module", name, summary, sources, conf))

# --- Devices (synthetic internal data, one-to-one with seed.json) ---
FORM_TO_ENTITY = {"QSFP-DD": "MOD-QSFPDD", "OSFP": "MOD-OSFP", "QSFP112": "MOD-QSFP112"}
for p in DEVICE_PROFILES:
    ENTITIES.append(E(f"DEV-{p['device_id']}", "Device", p["name"],
                      f"{p['vendor']} {p['model']} @ {p['location']} | CMIS {p['cmis_revision']} | {p['status']}",
                      ["S-INTERNAL"], "confirmed", device_id=p["device_id"],
                      device_type=p["device_type"], form_factor=p["module"]["form_factor"],
                      status=p["status"], data_nature="synthetic"))

# --- Configuration items ---
CONFIG_ITEMS = [
    ("CFG-IDENT", "Module Identifier", "Lower 00h，SFF-8024 编码，RO", ["S-SFF-8024", "S-OIF-052", "S-ART-W2W"], "partial"),
    ("CFG-REV", "CMIS Revision", "Lower 01h，版本字节，RO", ["S-OIF-052", "S-ART-W2W"], "partial"),
    ("CFG-MSTATE", "Module State", "Lower 03h，模块状态机状态，RO", ["S-OIF-052", "S-GH-SONIC-PC"], "partial"),
    ("CFG-FLAGS", "Module Flags", "Lower Flag summary，RO", ["S-OIF-052"], "partial"),
    ("CFG-VENDOR", "Vendor Name / PN / SN / Date Code", "Page 00h ASCII 静态信息，RO，精确偏移待核对", ["S-OIF-052", "S-ART-W2W"], "partial"),
    ("CFG-PN", "Vendor Part Number", "Page 00h ASCII 料号，RO", ["S-OIF-052", "S-ART-W2W"], "partial"),
    ("CFG-SN", "Vendor Serial Number", "Page 00h ASCII 序列号，RO", ["S-OIF-052", "S-ART-W2W"], "partial"),
    ("CFG-MTYPE", "Module Type Encoding", "Page 00h byte 85，RO", ["S-ART-W2W"], "partial"),
    ("CFG-HOSTIF", "Host Electrical Interface ID", "Application Descriptor byte 0，RO", ["S-OIF-052", "S-SFF-8024", "S-ART-W2W"], "partial"),
    ("CFG-MEDIAIF", "Media Interface ID", "Application Descriptor byte 1，RO", ["S-OIF-052", "S-SFF-8024", "S-ART-W2W"], "partial"),
    ("CFG-LANECNT", "Host/Media Lane Count", "Application Descriptor byte 2（0x88 / 0x44 / 0x48 等），RO", ["S-ART-W2W", "S-OIF-052"], "partial"),
    ("CFG-LANEASSIGN", "Host/Media Lane Assignment Options", "Application Descriptor 中的 lane 分配位图，RO", ["S-OIF-052", "S-ART-W2W"], "partial"),
    ("CFG-DPSTATE", "DPState / ConfigError", "Page 11h 数据路径状态与配置错误码，RO", ["S-OIF-052", "S-GH-SONIC-PC"], "partial"),
    ("CFG-CFGERR", "Config Error Code", "Page 11h 配置错误枚举，RO", ["S-OIF-052", "S-GH-SONIC-PC"], "partial"),
    ("CFG-BANKSEL", "Bank Select (7Eh)", "Lower 7Eh，RW，最大 Bank 数见 Table 8-40", ["S-ART-MAPYOURTECH", "S-GH-ETHTOOL", "S-OIF-052"], "confirmed"),
    ("CFG-PAGESEL", "Page Select (7Fh)", "Lower 7Fh，RW，切换需等待 tBPC", ["S-ART-MAPYOURTECH", "S-OIF-052"], "confirmed"),
    ("CFG-APPSEL", "AppSel (Page 01h, 逐 lane)", "0xAD 编码，RW，必须引用模块已广告的 Application", ["S-ART-W2W", "S-OIF-052", "S-GH-SONIC-PC", "S-ART-XRDOCS"], "partial"),
    ("CFG-LPMODE", "LowPwrRequestSW (LPMode)", "模块级控制位，RW，受 MSM 时序约束", ["S-OIF-052", "S-GH-SONIC-PC"], "partial"),
    ("CFG-TXDIS", "TxDisable", "Page 10h 通道发射关闭，RW", ["S-OIF-052", "S-GH-LIBSFFCMIS"], "partial"),
    ("CFG-DPINIT", "DataPathInit", "Page 10h 触发 DPSM 初始化，RW", ["S-OIF-052", "S-GH-SONIC-PC"], "partial"),
    ("CFG-TXEQ", "Tx EQ / Amplitude (Staged Control Set)", "Page 10h SI 参数，RW，先 stage 后 apply", ["S-OIF-052", "S-GH-SONIC-PC", "S-OIF-VCS-011"], "partial"),
    ("CFG-CDR", "CDR Enable TX/RX", "Staged Control Set 位，RW", ["S-GH-SONIC-PC", "S-OIF-052"], "partial"),
    ("CFG-THRESH", "Alarm / Warning Thresholds (Page 02h)", "温度/电压/功率门限，RW，告警须高于预警", ["S-OIF-052", "S-ART-MAPYOURTECH", "S-GH-LIBSFFCMIS"], "partial"),
    ("CFG-VDMFREEZE", "VDM Freeze", "Pages 20h-2Fh 原子读取控制，RW", ["S-OIF-052", "S-GH-LIBSFFCMIS"], "partial"),
    ("CFG-LOOPBACK", "Loopback (Page 13h)", "诊断环回，RW，枚举待原文核对", ["S-OIF-052", "S-GH-LIBSFFCMIS"], "partial"),
    ("CFG-PRBS", "PRBS Generator / Checker (Pages 13h/14h)", "诊断码型与 BER，RW", ["S-OIF-052", "S-GH-LIBSFFCMIS"], "partial"),
    ("CFG-LASER", "Tunable Laser Frequency (C-CMIS)", "Page 04h/12h，DCO 专属，RW", ["S-OIF-052", "S-OIF-CCMIS-013", "S-GH-LIBSFFCMIS"], "partial"),
    ("CFG-DDM", "VDM / DDM 监测量", "温度、电压、Tx/Rx 光功率，RO", ["S-OIF-052", "S-GH-LIBSFFCMIS", "S-ART-LINKPP"], "partial"),
]
for cid, name, summary, sources, conf in CONFIG_ITEMS:
    ENTITIES.append(E(cid, "ConfigItem", name, summary, sources, conf))

# --- Concepts ---
CONCEPTS = [
    ("CON-APP", "Application / Application Descriptor", "Page 00h 中 4 字节一组的接口能力声明（Host ID / Media ID / Lane Count / Lane Assignment）", ["S-OIF-052", "S-ART-W2W"]),
    ("CON-MSM", "Module State Machine", "模块上电/低功耗/就绪/故障的状态机", ["S-OIF-052", "S-ART-CSDN-52"]),
    ("CON-DPSM", "Data Path State Machine", "每个 Data Path 一个实例，表达配置/初始化状态", ["S-OIF-052", "S-ART-CSDN-52"]),
    ("CON-CDB", "Command Data Block", "消息邮箱与固件管理命令", ["S-OIF-052", "S-GH-LIBSFFCMIS"]),
    ("CON-VDM", "Versatile Diagnostics Monitoring", "可扩展的监测量集合与 Freeze 机制", ["S-OIF-052", "S-GH-LIBSFFCMIS"]),
    ("CON-DDM", "Digital Diagnostics Monitoring (DDM)", "实时温度/电压/光功率监视", ["S-ART-LINKPP", "S-OIF-052"]),
    ("CON-MEMMAP", "Bank:Page:Byte 地址空间", "CMIS 寄存器三元坐标", ["S-ART-MAPYOURTECH", "S-OIF-052"]),
    ("CON-MIRROR", "本地配置镜像（本项目）", "服务只写本地 SQLite 镜像，不下发硬件；真实下发需适配器", ["S-INTERNAL"]),
]
for cid, name, summary, sources in CONCEPTS:
    ENTITIES.append(E(cid, "Concept", name, summary, sources, "confirmed"))

# --- Open-source projects ---
PROJECTS = [
    ("OSS-TABLER", "tabler/tabler", "MIT / 42021 stars / pushed 2026-11-07 / Bootstrap 5 单 CSS+JS 仪表盘 UI Kit", ["S-GH-TABLER", "S-GH-API-SNAPSHOT"], "dashboard"),
    ("OSS-TABLER-ICONS", "tabler/tabler-icons", "MIT / 22579 stars / 6000+ SVG 图标", ["S-GH-TABLER-ICONS", "S-GH-API-SNAPSHOT"], "dashboard"),
    ("OSS-ADMINLTE", "ColorlibHQ/AdminLTE", "MIT / 45678 stars / pushed 2026-11-04，jQuery+Bootstrap 模板", ["S-GH-ADMINLTE", "S-GH-API-SNAPSHOT"], "dashboard-candidate"),
    ("OSS-DASHY", "Lissy93/dashy", "MIT / 26940 stars / pushed 2026-11-07，Vue+Node 导航型 dashboard", ["S-GH-DASHY", "S-GH-API-SNAPSHOT"], "dashboard-candidate"),
    ("OSS-GRAFANA", "grafana/grafana", "AGPL-3.0 / 77759 stars / pushed 2026-11-08，Go 服务 + 数据库", ["S-GH-GRAFANA", "S-GH-API-SNAPSHOT"], "dashboard-candidate"),
    ("OSS-SONIC-PC", "sonic-net/sonic-platform-common", "CmisApi：字段解析、AppSel、SI staging、CDB/VDM API", ["S-GH-SONIC-PC"], "cmis-implementation"),
    ("OSS-SONIC-PD", "sonic-net/sonic-platform-daemons", "xcvrd：CMIS application initialization 状态机", ["S-GH-SONIC-PD"], "cmis-implementation"),
    ("OSS-SONIC-UTIL", "sonic-net/sonic-utilities", "sfputil show eeprom：CMIS EEPROM/VDM CLI 展示", ["S-GH-SONIC-UTIL"], "cmis-implementation"),
    ("OSS-FBOSS", "meta/fboss (facebook/fboss)", "qsfp_service / CmisModule：字段解析与 transceiver 状态管理", ["S-GH-FBOSS"], "cmis-implementation"),
    ("OSS-LIBSFFCMIS", "vjardin/libsffcmis", "C 库 + CLI，按页实现 datapath / VDM / CDB / diag / coherent / tunable", ["S-GH-LIBSFFCMIS"], "cmis-implementation"),
    ("OSS-ETHTOOL", "ethtool (cmis.c / qsfp.c)", "用户态 CMIS EEPROM 解析与 JSON 输出，GPL-2.0", ["S-GH-ETHTOOL"], "cmis-implementation"),
    ("OSS-LINUX", "Linux kernel (I2C / SFP)", "底层两线访问与模块 EEPROM 框架", ["S-GH-LINUX"], "cmis-implementation"),
    ("OSS-THIS-SERVICE", "本项目 CMIS Dashboard Service", "Python 标准库 + SQLite + vendored Tabler 的轻量本地服务", ["S-INTERNAL"], "internal"),
]
for pid, name, summary, sources, category in PROJECTS:
    ENTITIES.append(E(pid, "OpenSourceProject", name, summary, sources,
                      "partial" if category == "cmis-implementation" else "confirmed",
                      category=category))

ENTITIES.append(E("SVC-CMIS-DASH", "Service", "CMIScope - Lightweight CMIS Dashboard",
                  "本地 dashboard：按 CMIS 分区查询/展示模块信息、配置项编辑校验、CDB 命令编排、知识图谱关联查询",
                  ["S-INTERNAL", "S-GH-TABLER"], "confirmed",
                  runtime="Python 3 stdlib + SQLite", frontend="Tabler 1.7.3 (MIT)",
                  access_modes="mirror / ssh-i2c / rest-api",
                  default_language="zh", optional_language="en"))

# --- CMIS specification partitions (OIF-CMIS-05.3 / 05.4) ---
ENTITIES += [
    E("SEC-LOW-PAGE", "SpecificationPartition", "Low Page 0x00 (Lower + Upper 00h)",
      "常驻低 128 字节与 Upper Page 00h：ID/状态、模块级标志、全局控制、CDB 状态、固件版本、应用广告、口令区、Bank/Page 选择",
      ["S-OIF-053", "S-OIF-054", "S-ART-MAPYOURTECH", "S-ART-VITEX"], "partial",
      pages="Lower 00h-7Fh, Upper 00h 80h-FFh", spec_ref="OIF-CMIS-05.3 8.2 / 8.4"),
    E("SEC-VDM", "SpecificationPartition", "VDM / CMIS Monitors",
      "CMIS 称 Monitors：Lower 14-25 模块级监测量、Page 02h 阈值、Page 10h/11h 通道状态与光功率监测量、Pages 20h-2Fh VDM",
      ["S-OIF-053", "S-IETF-CMIS-YANG", "S-ART-VITEX"], "partial",
      pages="Lower 14-25, 02h, 10h, 11h, 20h-2Fh", spec_ref="OIF-CMIS-05.3 8.8 / 8.22"),
    E("SEC-CDB", "SpecificationPartition", "CDB (Command Data Block)",
      "Page 9Fh 命令帧与 120 字节 LPL、Pages A0h-AFh 最多 2048 字节 EPL、Lower 37-38 状态、Lower 122 口令入口；命令参考见 05.3 第 9 章",
      ["S-OIF-053", "S-OIF-054", "S-GH-LINUX-CDB"], "confirmed",
      pages="9Fh, A0h-AFh, Lower 37-38, Lower 118-125", spec_ref="OIF-CMIS-05.3 8.23 / 8.24 / 9"),
    E("SEC-CONTROL", "SpecificationPartition", "Datapath / Diagnostics / Coherent Control",
      "Page 01h 应用描述符、Page 10h AppSel/DPSM/Staged Control Set、Pages 13h/14h PRBS 与环回、Page 12h 可调激光器、Pages 30h-4Fh C-CMIS",
      ["S-OIF-053", "S-IETF-CMIS-YANG", "S-OIF-CCMIS-015"], "partial",
      pages="01h, 10h, 12h, 13h, 14h, 30h-4Fh", spec_ref="OIF-CMIS-05.3 6.3 / 8.9 / 8.10"),
    E("IF-CDB-FRAME", "Interface", "CDB Command Frame (Page 9Fh)",
      "128 字节命令帧：CMDID(2) / EPL 长度(2) / LPL 长度(1) / 校验码(1) / 保留(2) / LPL(120)；写入结束于 9Fh:129 触发命令",
      ["S-OIF-053", "S-GH-LINUX-CDB"], "confirmed",
      i2c_address="0x50", lpl_max_bytes=120, epl_max_bytes=2048),
    E("IF-CDB-EPL", "Interface", "CDB Extended Payload Pages (A0h-AFh)",
      "16 页 x 128 字节 = 最多 2048 字节扩展载荷，用于固件块等大数据传输",
      ["S-OIF-053", "S-GH-LINUX-CDB"], "confirmed"),
    E("IF-SSH-I2C", "AccessPath", "Mode A: Test Server -> SSH -> Test Switch -> I2C",
      "服务运行在测试 Server，经 SSH 登录测试 Switch 执行 i2cget/i2cset 或厂商 CLI，由交换机完成对模块 EEPROM (0x50) 的两线读写",
      ["S-INTERNAL", "S-GH-LINUX", "S-OIF-053"], "confirmed",
      transport="ssh + subprocess + i2c-tools", target="0x50", safety="Lower Memory writes blocked"),
    E("IF-REST-API", "AccessPath", "Mode B: Target Device RESTful API",
      "服务调用目标设备/NOS 的北向 REST API，由设备侧完成 I2C 事务；读写按页级 allowlist 委派",
      ["S-INTERNAL", "S-IETF-CMIS-YANG"], "confirmed",
      transport="HTTPS + JSON", token_env="CMIS_REST_TOKEN",
      safety="CDB pages are read-only over REST by default"),
    E("IF-MIRROR", "AccessPath", "Offline SQLite Mirror",
      "默认离线模式：读数来自本地 SQLite，配置写入仅 staged 并记入审计日志，从不访问硬件",
      ["S-INTERNAL"], "confirmed", transport="sqlite"),
    E("CON-PAGE-GOVERNANCE", "Concept", "Page-level Access Governance",
      "IETF YANG 草案：remote-read-allowed-pages / remote-write-allowed-pages / default-policy；Lower Memory 与 CDB 页不可委派远程写",
      ["S-IETF-CMIS-YANG"], "confirmed"),
    E("CFG-CDB", "ConfigItem", "CDB registers and command parameters",
      "Page 9Fh/A0h-AFh 与 Lower 37-38/122 的 CDB 相关寄存器：CMDID、EPL/LPL 长度、校验码、载荷、状态、口令、实例",
      ["S-OIF-053", "S-GH-LINUX-CDB"], "confirmed", spec_ref="OIF-CMIS-05.3 8.23 / 8.24 / 9"),
    E("CFG-VDM", "ConfigItem", "VDM threshold and monitor registers",
      "Page 02h 阈值、Lower 14-25 与 Page 10h/11h 监测量、Pages 20h-2Fh VDM 控制",
      ["S-OIF-053", "S-IETF-CMIS-YANG"], "partial"),
    E("CFG-LOW-PAGE", "ConfigItem", "Low Page 0x00 identity and status registers",
      "Lower 0-127 与 Upper Page 00h 静态识别字段（厂商、OUI、料号、序列号、日期码、校验和、Bank/Page 选择）",
      ["S-OIF-053", "S-ART-VITEX"], "partial"),
]

# --------------------------------------------------------------------------- Relations
_rel_counter = [0]


def R(src, dst, type_, label, sources=None, confidence="confirmed", **attrs):
    _rel_counter[0] += 1
    return {"relation_id": f"REL-{_rel_counter[0]:03d}", "src": src, "dst": dst,
            "type": type_, "label": label, "source_ids": sources or [],
            "confidence": confidence, "status": "active", "attrs": attrs}


RELATIONS: list[dict] = []

# Organizations -> specifications (define / publish)
for std in ("STD-CMIS-052", "STD-CMIS-053", "STD-CMIS-054", "STD-CMIS-ERRATA",
            "STD-CCMIS-013", "STD-CCMIS-015", "STD-VCS-011", "STD-FF-010",
            "STD-ELSFP-010", "STD-LT-010"):
    RELATIONS.append(R("ORG-OIF", std, "DEFINES", "OIF 发布/维护该实现协议", ["S-OIF-INDEX"]))
RELATIONS += [
    R("ORG-SNIA", "STD-SFF-8024", "DEFINES", "SFF TWG 维护编码表", ["S-SFF-8024"]),
    R("ORG-SNIA", "STD-SFF-8636", "DEFINES", "SFF TWG 维护旧版管理接口", ["S-SFF-8636"]),
    R("ORG-QSFPDD", "STD-QSFPDD-CMIS", "DEFINES", "MSA 发布 CMIS 前身", ["S-QSFPDD-MSA", "S-ART-LIGHTWAVE"], "partial"),
    R("STD-CMIS-052", "STD-QSFPDD-CMIS", "DERIVES_FROM", "CMIS 由 QSFP-DD MSA 移交 OIF 后延续", ["S-ART-LIGHTWAVE", "S-OIF-INDEX"], "partial"),
    R("STD-CMIS-053", "STD-CMIS-052", "DERIVES_FROM", "5.3 继承并扩展 5.2", ["S-OIF-INDEX"]),
    R("STD-CMIS-054", "STD-CMIS-053", "DERIVES_FROM", "5.4 继承并扩展 5.3", ["S-OIF-INDEX"]),
    R("STD-CMIS-ERRATA", "STD-CMIS-052", "CONSTRAINS", "勘误适用于 CMIS 5.x 系列", ["S-OIF-INDEX"]),
    R("STD-CMIS-052", "STD-SFF-8024", "REFERENCES", "Interface ID / Identifier 编码引用 SFF-8024", ["S-SFF-8024", "S-OIF-052"], "partial"),
    R("STD-SFF-8636", "STD-CMIS-052", "REFERENCES", "旧版 QSFP 管理接口作为对照", ["S-SFF-8636", "S-ART-LINKPP"]),
    R("STD-CCMIS-013", "STD-CMIS-052", "REFERENCES", "C-CMIS 基于 CMIS 主规范扩展相干能力", ["S-OIF-CCMIS-013"], "partial"),
    R("STD-VCS-011", "STD-CMIS-053", "REFERENCES", "VCS 扩展 Control Set 模型", ["S-OIF-VCS-011"], "partial"),
    R("STD-ELSFP-010", "STD-CMIS-053", "REFERENCES", "ELSFP 的 CMIS 扩展", ["S-OIF-ELSFP-010"], "partial"),
    R("STD-LT-010", "STD-CMIS-054", "REFERENCES", "带外链路训练 CMIS 扩展", ["S-OIF-LT-010"], "partial"),
    R("STD-FF-010", "STD-CMIS-053", "REFERENCES", "封装相关硬件管理扩展", ["S-OIF-FF-010"], "partial"),
]

# Specifications -> clauses (define)
CLAUSE_TO_STD = {
    "CL-5-2-1": "STD-CMIS-052", "CL-6-2-1": "STD-CMIS-052", "CL-6-2-2": "STD-CMIS-052",
    "CL-6-2-3": "STD-CMIS-052", "CL-6-3-2": "STD-CMIS-052", "CL-6-3-3": "STD-CMIS-052",
    "CL-8-2": "STD-CMIS-052", "CL-8-4": "STD-CMIS-052", "CL-8-4-4": "STD-CMIS-052",
    "CL-8-9": "STD-CMIS-052", "CL-8-9-2": "STD-CMIS-052", "CL-10-4": "STD-CMIS-052",
    "CL-APSEL": "STD-CMIS-052", "CL-THRESH": "STD-CMIS-052", "CL-CDB": "STD-CMIS-052",
    "CL-VDM": "STD-CMIS-052", "CL-DIAG": "STD-CMIS-052", "CL-TUNABLE": "STD-CMIS-052",
    "CL-CCMIS-PM": "STD-CCMIS-013", "CL-PROTECTED": "STD-CMIS-053",
}
for clause, std in CLAUSE_TO_STD.items():
    conf = "pending" if clause == "CL-PROTECTED" else "partial"
    RELATIONS.append(R(std, clause, "DEFINES", "规范定义该条款/章节", ["S-OIF-INDEX", "S-OIF-052"], conf))

# Clauses -> interfaces / concepts / config items (define and constrain)
DEFINES_MAP = [
    ("CL-5-2-1", "IF-LOWER"), ("CL-5-2-1", "IF-UPPER"), ("CL-8-2", "CON-MEMMAP"),
    ("CL-8-4-4", "IF-BANKPAGE"), ("CL-10-4", "IF-BANKPAGE"),
    ("CL-6-2-1", "CON-APP"), ("CL-6-2-1", "IF-HOST-ELEC"), ("CL-6-2-1", "IF-MEDIA"),
    ("CL-6-2-2", "IF-DATAPATH"), ("CL-6-2-3", "IF-CONTROLSET"),
    ("CL-6-3-2", "CON-MSM"), ("CL-6-3-3", "CON-DPSM"),
    ("CL-CDB", "IF-CDB"), ("CL-CDB", "CON-CDB"), ("CL-VDM", "IF-VDM"), ("CL-VDM", "CON-VDM"),
    ("CL-8-9", "IF-LANE"), ("CL-THRESH", "CON-DDM"),
    ("CL-APSEL", "CFG-APPSEL"), ("CL-8-9", "CFG-DPSTATE"), ("CL-8-9", "CFG-TXDIS"),
    ("CL-8-9", "CFG-DPINIT"), ("CL-8-9", "CFG-TXEQ"), ("CL-8-9", "CFG-CDR"),
    ("CL-6-3-2", "CFG-LPMODE"), ("CL-THRESH", "CFG-THRESH"),
    ("CL-8-4", "CFG-VENDOR"), ("CL-8-4", "CFG-HOSTIF"), ("CL-8-4", "CFG-MEDIAIF"),
    ("CL-8-4", "CFG-LANECNT"), ("CL-8-4", "CFG-LANEASSIGN"), ("CL-8-4", "CFG-MTYPE"),
    ("CL-8-4-4", "CFG-BANKSEL"), ("CL-5-2-1", "CFG-PAGESEL"),
    ("CL-VDM", "CFG-VDMFREEZE"), ("CL-DIAG", "CFG-LOOPBACK"), ("CL-DIAG", "CFG-PRBS"),
    ("CL-TUNABLE", "CFG-LASER"), ("CL-CCMIS-PM", "CFG-LASER"),
    ("CL-8-9-2", "CFG-DDM"), ("CL-8-2", "CFG-IDENT"), ("CL-8-2", "CFG-REV"),
    ("CL-6-3-2", "CFG-MSTATE"), ("CL-5-2-1", "CFG-FLAGS"),
    ("CL-8-4", "CFG-PN"), ("CL-8-4", "CFG-SN"), ("CL-8-9", "CFG-CFGERR"),
]
for clause, target in DEFINES_MAP:
    RELATIONS.append(R(clause, target, "DEFINES", "条款定义该实体", ["S-OIF-052"], "partial"))

CONSTRAINS_MAP = [
    ("CL-APSEL", "CFG-APPSEL", "Application 编号必须落在模块已广告列表中"),
    ("CL-6-2-1", "CFG-APPSEL", "AppSel 只能引用 Application Descriptor 声明的能力"),
    ("CL-6-3-3", "CFG-DPINIT", "DPSM 状态迁移决定 DataPathInit 生效时机"),
    ("CL-6-3-2", "CFG-LPMODE", "MSM 状态约束低功耗切换时序"),
    ("CL-10-4", "CFG-PAGESEL", "页切换后需等待 tBPC ≤ 10 ms"),
    ("CL-8-4-4", "CFG-BANKSEL", "Bank 取值上限（最大 4 Bank）"),
    ("CL-THRESH", "CFG-THRESH", "告警阈值应高于预警阈值，且落在规范量纲/范围内"),
    ("CL-8-9", "CFG-TXDIS", "TxDisable 与 DPInit 不应同时置位（本服务实现为校验规则）"),
    ("CL-8-9", "CFG-TXEQ", "SI 参数取值受模块广告能力上限约束"),
    ("CL-PROTECTED", "CFG-APPSEL", "受保护区写入可能需密码解锁（待确认）"),
    ("CL-8-9-2", "CFG-DPSTATE", "Output Status 与 DPSM 状态需分别判读"),
]
for clause, target, note in CONSTRAINS_MAP:
    RELATIONS.append(R(clause, target, "CONSTRAINS", note, ["S-OIF-052"], "partial",
                       rule_note=note))

# Modules -> interfaces (contain); modules -> Applications (advertise)
for mid in ("MOD-QSFPDD", "MOD-OSFP", "MOD-QSFP112", "MOD-DCO"):
    for iid in ("IF-TWI", "IF-LOWER", "IF-BANKPAGE", "IF-HOST-ELEC", "IF-MEDIA",
                "IF-DATAPATH", "IF-LANE", "IF-CONTROLSET"):
        RELATIONS.append(R(mid, iid, "CONTAINS", "模块包含该接口/通道", ["S-OIF-052", "S-ART-LINKPP"], "partial"))
for mid in ("MOD-QSFPDD", "MOD-OSFP", "MOD-QSFP112", "MOD-DCO", "MOD-COBO"):
    RELATIONS.append(R(mid, "CON-APP", "ADVERTISES", "模块广告其 Application 能力", ["S-OIF-052", "S-ART-W2W"], "partial"))
for mid in ("MOD-QSFPDD", "MOD-OSFP", "MOD-DCO"):
    RELATIONS.append(R(mid, "IF-UPPER", "CONTAINS", "分页 Upper Memory", ["S-ART-MAPYOURTECH"], "confirmed"))
    RELATIONS.append(R(mid, "IF-CDB", "CONTAINS", "支持 CDB 命令接口", ["S-GH-LIBSFFCMIS"], "partial"))
    RELATIONS.append(R(mid, "IF-VDM", "CONTAINS", "支持 VDM 观测", ["S-GH-LIBSFFCMIS"], "partial"))
RELATIONS += [
    R("MOD-DCO", "MOD-QSFPDD", "INSTANTIATES", "相干模块常采用 QSFP-DD 封装", ["S-ART-XRDOCS"], "partial"),
    R("MOD-DCO", "MOD-OSFP", "INSTANTIATES", "800ZR 相干模块采用 OSFP 封装", ["S-ART-XRDOCS"], "partial"),
    R("MOD-DCO", "IF-NETPATH", "CONTAINS", "相干模块网络路径相关页", ["S-GH-LIBSFFCMIS"], "partial"),
    R("MOD-FLAT", "IF-LOWER", "CONTAINS", "Flat memory 仅固定 Lower 区", ["S-ART-MAPYOURTECH"], "confirmed"),
    R("MOD-ELSFP", "IF-CDB", "CONTAINS", "ELSFP CMIS 扩展管理", ["S-OIF-ELSFP-010"], "partial"),
    R("STD-CMIS-052", "MOD-QSFPDD", "CONSTRAINS", "规范约束模块管理行为", ["S-OIF-052"]),
    R("STD-CCMIS-013", "MOD-DCO", "CONSTRAINS", "C-CMIS 约束相干模块扩展", ["S-OIF-CCMIS-013"]),
    R("STD-ELSFP-010", "MOD-ELSFP", "CONSTRAINS", "ELSFP-CMIS 约束外置激光器模块", ["S-OIF-ELSFP-010"]),
    R("STD-CMIS-052", "MOD-CPO", "REFERENCES", "OIF 后续项目面向共封装光学", ["S-ART-LIGHTWAVE"], "partial"),
]

# Devices -> modules (contain); config items -> interfaces (configure / monitor)
for p in DEVICE_PROFILES:
    dev = f"DEV-{p['device_id']}"
    mod_entity = FORM_TO_ENTITY.get(p["module"]["form_factor"], "MOD-QSFPDD")
    RELATIONS.append(R(dev, mod_entity, "CONTAINS", "该设备端口上的模块封装类型", ["S-INTERNAL"]))
    RELATIONS.append(R(dev, "CFG-APPSEL", "CONFIGURES", "设备端口的 Application 选择", ["S-INTERNAL"]))
    if p.get("dco"):
        RELATIONS.append(R(dev, "MOD-DCO", "CONTAINS", "相干 DCO 模块", ["S-INTERNAL", "S-ART-XRDOCS"]))

CONFIG_TARGETS = {
    "CFG-APPSEL": ("IF-DATAPATH", "CONFIGURES"), "CFG-DPINIT": ("IF-DATAPATH", "CONFIGURES"),
    "CFG-TXDIS": ("IF-LANE", "CONFIGURES"), "CFG-TXEQ": ("IF-CONTROLSET", "CONFIGURES"),
    "CFG-CDR": ("IF-CONTROLSET", "CONFIGURES"), "CFG-LPMODE": ("IF-TWI", "CONFIGURES"),
    "CFG-BANKSEL": ("IF-BANKPAGE", "CONFIGURES"), "CFG-PAGESEL": ("IF-BANKPAGE", "CONFIGURES"),
    "CFG-THRESH": ("CON-DDM", "CONSTRAINS"), "CFG-VDMFREEZE": ("IF-VDM", "CONFIGURES"),
    "CFG-LOOPBACK": ("IF-LANE", "CONFIGURES"), "CFG-PRBS": ("IF-LANE", "CONFIGURES"),
    "CFG-LASER": ("IF-MEDIA", "CONFIGURES"), "CFG-DDM": ("CON-DDM", "MONITORS"),
    "CFG-MSTATE": ("CON-MSM", "MONITORS"), "CFG-DPSTATE": ("CON-DPSM", "MONITORS"),
    "CFG-CFGERR": ("CON-DPSM", "MONITORS"),
}
for cfg, (target, rel) in CONFIG_TARGETS.items():
    RELATIONS.append(R(cfg, target, rel, f"配置项{rel.lower()}目标", ["S-OIF-052", "S-INTERNAL"], "partial"))

# Open-source projects -> specifications / clauses / config items (implement / reference)
IMPLEMENTS = [
    ("OSS-SONIC-PC", "CL-APSEL", "CmisApi.set_application / get_application"),
    ("OSS-SONIC-PC", "CL-6-3-3", "CMIS application initialization 与 DPState 轮询"),
    ("OSS-SONIC-PC", "CL-8-9", "SI 参数 stage_* / CDR / TX-RX 控制"),
    ("OSS-SONIC-PC", "CL-8-4", "XCVR_INFO 字段解析与 Application Descriptor"),
    ("OSS-SONIC-PD", "CL-6-3-3", "xcvrd CMIS 初始化状态机"),
    ("OSS-SONIC-UTIL", "CL-8-4", "sfputil show eeprom"),
    ("OSS-FBOSS", "CL-8-4", "qsfp_service 解析 CMIS EEPROM"),
    ("OSS-LIBSFFCMIS", "CL-8-9", "cmis-datapath.c：Page 10h/11h 控制与状态"),
    ("OSS-LIBSFFCMIS", "CL-VDM", "cmis-vdm.c：Pages 20h-2Fh 监视/阈值/Freeze"),
    ("OSS-LIBSFFCMIS", "CL-CDB", "cmis-cdb.c：Page 9Fh 命令与固件管理"),
    ("OSS-LIBSFFCMIS", "CL-DIAG", "cmis-diag.c：PRBS / Loopback / BER"),
    ("OSS-LIBSFFCMIS", "CL-CCMIS-PM", "cmis-coherent.c：Pages 34h/35h 与 FEC/Flag"),
    ("OSS-LIBSFFCMIS", "CL-TUNABLE", "cmis-tunable.c：Pages 04h/12h"),
    ("OSS-ETHTOOL", "CL-8-4", "cmis.c / qsfp.c EEPROM 解析"),
    ("OSS-ETHTOOL", "CL-8-4-4", "CMIS_MAX_BANKS 定义与 Table 8-40 引用"),
    ("OSS-LINUX", "IF-TWI", "I2C 设备层访问"),
]
for project, clause, note in IMPLEMENTS:
    RELATIONS.append(R(project, clause, "IMPLEMENTS", note, ["S-GH-SONIC-PC", "S-GH-LIBSFFCMIS",
                                                             "S-GH-ETHTOOL", "S-GH-FBOSS"], "partial"))
for project in ("OSS-SONIC-PC", "OSS-FBOSS", "OSS-LIBSFFCMIS", "OSS-ETHTOOL"):
    RELATIONS.append(R(project, "STD-CMIS-052", "REFERENCES", "实现引用 CMIS 主规范", ["S-OIF-052"], "partial"))
RELATIONS.append(R("OSS-LIBSFFCMIS", "STD-CMIS-053", "REFERENCES", "声明支持 OIF-CMIS-05.3", ["S-GH-LIBSFFCMIS"]))
RELATIONS.append(R("OSS-LIBSFFCMIS", "STD-CCMIS-013", "REFERENCES", "声明支持 C-CMIS-01.3", ["S-GH-LIBSFFCMIS"]))
RELATIONS.append(R("OSS-LIBSFFCMIS", "OSS-ETHTOOL", "DERIVES_FROM", "由 ethtool cmis.c 引导派生", ["S-GH-LIBSFFCMIS"]))
RELATIONS.append(R("ORG-SONIC", "OSS-SONIC-PC", "DEFINES", "SONiC 社区维护平台公共库", ["S-GH-SONIC-PC"]))
RELATIONS.append(R("ORG-META", "OSS-FBOSS", "DEFINES", "Meta 维护 FBOSS", ["S-GH-FBOSS"]))

# This service -> framework / graph / config items
RELATIONS += [
    R("SVC-CMIS-DASH", "OSS-TABLER", "INTEGRATES", "使用 vendored Tabler 1.7.3 (MIT) 作为 dashboard 框架", ["S-GH-TABLER", "S-INTERNAL"]),
    R("SVC-CMIS-DASH", "OSS-TABLER-ICONS", "INTEGRATES", "使用 Tabler Icons 图标字体", ["S-GH-TABLER-ICONS"]),
    R("SVC-CMIS-DASH", "STD-CMIS-052", "REFERENCES", "字段/条款/来源说明引用 OIF CMIS 5.2", ["S-OIF-052"]),
    R("SVC-CMIS-DASH", "CON-MIRROR", "IMPLEMENTS", "配置写入采用本地镜像模式", ["S-INTERNAL"]),
    R("SVC-CMIS-DASH", "CFG-APPSEL", "CONFIGURES", "提供 AppSel 查看/编辑/校验", ["S-INTERNAL"]),
    R("SVC-CMIS-DASH", "CFG-THRESH", "CONFIGURES", "提供阈值查看/编辑/校验", ["S-INTERNAL"]),
    R("SVC-CMIS-DASH", "CON-DDM", "MONITORS", "展示 DDM 监测量", ["S-INTERNAL"]),
    R("SVC-CMIS-DASH", "STD-CMIS-053", "REFERENCES", "CMIS 分区与 CDB 命令目录依据 OIF-CMIS-05.3", ["S-OIF-053"]),
    R("SVC-CMIS-DASH", "STD-CMIS-054", "REFERENCES", "最新 CMIS 5.4 作为版本对齐目标", ["S-OIF-054"]),
    R("SVC-CMIS-DASH", "IF-SSH-I2C", "IMPLEMENTS", "实现测试 Server -> SSH -> Switch -> I2C 接入适配器", ["S-INTERNAL"]),
    R("SVC-CMIS-DASH", "IF-REST-API", "IMPLEMENTS", "实现目标设备 RESTful API 接入适配器", ["S-INTERNAL"]),
    R("SVC-CMIS-DASH", "IF-MIRROR", "IMPLEMENTS", "默认离线 SQLite 镜像适配器", ["S-INTERNAL"]),
    R("SVC-CMIS-DASH", "CON-PAGE-GOVERNANCE", "IMPLEMENTS", "按页级委派规则阻止 Lower Memory 与 CDB 页的远程写", ["S-IETF-CMIS-YANG"]),
]
# Specification partitions and their register areas
for std in ("STD-CMIS-053", "STD-CMIS-054"):
    for sec in ("SEC-LOW-PAGE", "SEC-VDM", "SEC-CDB", "SEC-CONTROL"):
        RELATIONS.append(R(std, sec, "DEFINES", "规范定义该分区及其寄存器组织", ["S-OIF-053", "S-OIF-054"], "partial"))
RELATIONS += [
    R("SEC-LOW-PAGE", "IF-LOWER", "CONTAINS", "低页包含常驻 Lower Memory", ["S-OIF-053", "S-ART-VITEX"]),
    R("SEC-LOW-PAGE", "IF-UPPER", "CONTAINS", "低页包含 Upper Page 00h 静态识别区", ["S-OIF-053", "S-ART-VITEX"]),
    R("SEC-LOW-PAGE", "IF-BANKPAGE", "CONTAINS", "Bank/Page 选择字节位于 Lower 126/127", ["S-ART-MAPYOURTECH"]),
    R("SEC-VDM", "CON-DDM", "CONTAINS", "VDM 分区承载监测量与阈值", ["S-OIF-053", "S-IETF-CMIS-YANG"]),
    R("SEC-VDM", "IF-VDM", "CONTAINS", "VDM 页 20h-2Fh 属于监测分区", ["S-OIF-053"]),
    R("SEC-CDB", "IF-CDB-FRAME", "CONTAINS", "Page 9Fh 命令帧", ["S-OIF-053", "S-GH-LINUX-CDB"]),
    R("SEC-CDB", "IF-CDB-EPL", "CONTAINS", "Pages A0h-AFh 扩展载荷", ["S-OIF-053", "S-GH-LINUX-CDB"]),
    R("SEC-CDB", "IF-CDB", "CONTAINS", "CDB 消息接口", ["S-OIF-053"]),
    R("SEC-CONTROL", "IF-DATAPATH", "CONTAINS", "Page 10h 数据通路控制", ["S-OIF-053"]),
    R("SEC-CONTROL", "IF-LANE", "CONTAINS", "诊断与通道控制", ["S-OIF-053"]),
    R("CON-PAGE-GOVERNANCE", "SEC-LOW-PAGE", "CONSTRAINS", "Lower Memory 远程写 MUST NOT permitted", ["S-IETF-CMIS-YANG"]),
    R("CON-PAGE-GOVERNANCE", "SEC-CDB", "CONSTRAINS", "CDB 页 9Fh-AFh MUST NOT be in remote-write-allowed-pages", ["S-IETF-CMIS-YANG"]),
    R("IF-SSH-I2C", "IF-TWI", "IMPLEMENTS", "Mode A 经交换机 I2C 总线访问模块 EEPROM", ["S-GH-LINUX"]),
    R("IF-SSH-I2C", "MOD-QSFPDD", "REFERENCES", "目标为 CMIS 可插拔光模块", ["S-OIF-053"]),
    R("IF-REST-API", "CON-PAGE-GOVERNANCE", "CONSTRAINS", "Mode B 遵循页级读写委派", ["S-IETF-CMIS-YANG"]),
    R("IF-REST-API", "IF-CDB", "REFERENCES", "REST 模式默认将 CDB 视为只读", ["S-IETF-CMIS-YANG"]),
    R("OSS-LIBSFFCMIS", "SEC-CDB", "IMPLEMENTS", "cmis-cdb.c 实现 Page 9Fh 命令", ["S-GH-LIBSFFCMIS"]),
    R("OSS-LINUX", "IF-CDB-FRAME", "IMPLEMENTS", "内核 net/ethtool/cmis_cdb.c 结构体印证命令帧字段宽度", ["S-GH-LINUX-CDB"], "partial"),
]
# Alternative dashboard frameworks (comparison only)
for candidate in ("OSS-ADMINLTE", "OSS-DASHY", "OSS-GRAFANA"):
    RELATIONS.append(R(candidate, "OSS-TABLER", "REFERENCES", "选型对比候选（未采用）", ["S-GH-API-SNAPSHOT"]))

# --------------------------------------------------------------------------- CMIS -> graph link mapping
LINKS: list[dict] = []
seen_links: set[tuple] = set()


def L(cmis_ref, entity_id, relation, note=""):
    key = (cmis_ref, entity_id, relation)
    if key in seen_links:
        return
    seen_links.add(key)
    LINKS.append({"cmis_ref": cmis_ref, "entity_id": entity_id, "relation": relation, "note": note})


SECTION_ENTITY = {"LOW_PAGE": "SEC-LOW-PAGE", "VDM": "SEC-VDM",
                  "CDB": "SEC-CDB", "CONTROL": "SEC-CONTROL"}
ACCESS_ENTITY = {"ssh-i2c": "IF-SSH-I2C", "rest-api": "IF-REST-API", "mirror": "IF-MIRROR"}

for field in FIELD_CATALOG:
    key = field["field_key"]
    if field["kg_entity_id"]:
        L(key, field["kg_entity_id"], "config_item", "字段对应的图谱配置项实体")
    section_entity = SECTION_ENTITY.get(field.get("section", "LOW_PAGE"))
    if section_entity:
        L(key, section_entity, "belongs_to_section", "字段归属的 CMIS 规范分区")
    # Coarse clause linkage derived from spec_ref keywords (explicit and auditable)
    ref = field["spec_ref"]
    clause_hint = None
    for candidate, needle in (("CL-APSEL", "§6.3"), ("CL-8-9", "§8.9"), ("CL-8-4", "§8.4"),
                              ("CL-8-2", "§8.2"), ("CL-5-2-1", "§5.2.1"),
                              ("CL-6-3-3", "§6.3.3"), ("CL-6-3-2", "§6.3.2"),
                              ("CL-6-2-1", "§6.2.1"), ("CL-8-4-4", "§8.4.4"),
                              ("CL-10-4", "Table 10-4"), ("CL-THRESH", "Thresholds"),
                              ("CL-CDB", "CDB"), ("CL-VDM", "VDM"),
                              ("CL-DIAG", "Diagnostics"), ("CL-TUNABLE", "Tunable"),
                              ("CL-CCMIS-PM", "C-CMIS")):
        if needle in ref:
            clause_hint = candidate
            break
    if clause_hint:
        L(key, clause_hint, "defined_by", "字段关联的规范条款（依据 spec_ref 推断，条款号待复核）")
    L(key, "STD-CMIS-052", "referenced_spec", "字段定义引用 CMIS 主规范")
    if field["source_ids"] and any(s.startswith("S-GH-") for s in field["source_ids"]):
        for sid in field["source_ids"]:
            proj = {"S-GH-SONIC-PC": "OSS-SONIC-PC", "S-GH-LIBSFFCMIS": "OSS-LIBSFFCMIS",
                    "S-GH-ETHTOOL": "OSS-ETHTOOL", "S-GH-FBOSS": "OSS-FBOSS"}.get(sid)
            if proj:
                L(key, proj, "implemented_by", "该字段有对应开源实现")

for p in DEVICE_PROFILES:
    did = p["device_id"]
    L(did, f"DEV-{did}", "device_entity", "设备实体（内部合成数据）")
    L(did, FORM_TO_ENTITY.get(p["module"]["form_factor"], "MOD-QSFPDD"), "module_type", "端口模块封装类型")
    L(did, "STD-CMIS-052", "referenced_spec", "设备管理接口遵循 CMIS")
    access_entity = ACCESS_ENTITY.get(p.get("access_mode", "mirror"))
    if access_entity:
        L(did, access_entity, "accessed_via", "该设备演示数据所标注的接入方式")
    if p.get("dco"):
        L(did, "MOD-DCO", "module_type", "相干 DCO 模块")
        L(did, "STD-CCMIS-013", "referenced_spec", "C-CMIS 扩展")

# --------------------------------------------------------------------------- Pending confirmations
PENDING = [
    {"pending_id": "P-01", "topic": "寄存器精确地址",
     "question": "Page 00h/01h/10h/11h/02h 各字段精确 byte offset 与 bit 位置需按模块实际 CMIS Revision 与 OIF 原文 Table 逐条核对；当前多处标为「待确认」",
     "source_ids": ["S-OIF-052", "S-ART-W2W", "S-ART-MAPYOURTECH"], "impact": "影响字段检索与配置项写入的准确性", "status": "open"},
    {"pending_id": "P-02", "topic": "版本差异",
     "question": "OIF-CMIS-05.3 / 05.4 相对 05.2 的条款增删未逐条比对，本次仅核对官方 IA 编号与发布日期",
     "source_ids": ["S-OIF-INDEX", "S-OIF-053", "S-OIF-054"], "impact": "5.4 模块可能包含本图谱未覆盖的新字段", "status": "open"},
    {"pending_id": "P-03", "topic": "AppSel 编码来源",
     "question": "0xAD 编码与 Page 01h byte 128-135 的地址来自第三方编程指南，需与 OIF-CMIS-05.2 §6.3/§8 原文核对",
     "source_ids": ["S-ART-W2W", "S-OIF-052"], "impact": "影响 appsel_in_advertised 跨字段校验规则", "status": "open"},
    {"pending_id": "P-04", "topic": "数值编码",
     "question": "float 型阈值按 1/256 缩放 16-bit 编码推导 raw_hex，属常见实现而非逐条规范核对",
     "source_ids": ["S-GH-LIBSFFCMIS", "S-GH-ETHTOOL"], "impact": "raw_hex 仅供参考，不应直接用于硬件写入", "status": "open"},
    {"pending_id": "P-05", "topic": "开源许可：SONiC",
     "question": "sonic-net/sonic-platform-common 的 GitHub license 返回 NOASSERTION（仓库内混合许可），集成其代码前需法务确认具体文件许可",
     "source_ids": ["S-GH-API-SNAPSHOT", "S-GH-SONIC-PC"], "impact": "合规风险；当前仅作资料引用，未拷贝代码", "status": "open"},
    {"pending_id": "P-06", "topic": "开源许可：libsffcmis",
     "question": "README 声明 GPLv2，但 GitHub 未识别 LICENSE 文件，需确认实际授权",
     "source_ids": ["S-GH-LIBSFFCMIS", "S-GH-API-SNAPSHOT"], "impact": "合规风险；当前仅作资料引用", "status": "open"},
    {"pending_id": "P-07", "topic": "开源许可：FBOSS",
     "question": "meta/fboss GitHub license 为 NOASSERTION，含 BSD-style LICENSE 与 PATENTS 专利授予文件，需评估",
     "source_ids": ["S-GH-FBOSS", "S-GH-API-SNAPSHOT"], "impact": "合规风险；当前仅作资料引用", "status": "open"},
    {"pending_id": "P-08", "topic": "SFF-8024 版本",
     "question": "Host/Media Interface ID 编码表版本未确认（libsffcmis 提到 SFF-8024 Rev 4.13）",
     "source_ids": ["S-SFF-8024", "S-GH-LIBSFFCMIS"], "impact": "接口编码解释可能随版本变化", "status": "open"},
    {"pending_id": "P-09", "topic": "内部设备数据",
     "question": "seed.json 中设备/模块/DDM 读数均为合成演示数据，非真实网元资产",
     "source_ids": ["S-INTERNAL"], "impact": "接入生产前需替换数据源并做字段映射", "status": "open"},
    {"pending_id": "P-10", "topic": "配置下发路径",
     "question": "本服务写入本地 SQLite 镜像（staged），未实现向硬件下发；真实下发需接入 I2C / ethtool / SONiC xcvrd 适配器",
     "source_ids": ["S-INTERNAL", "S-GH-ETHTOOL", "S-GH-SONIC-PD"], "impact": "变更结果反馈中的 applied_to_hardware 恒为 false", "status": "open"},
    {"pending_id": "P-11", "topic": "密码保护/消息邮箱",
     "question": "受保护区密码机制、CDB 邮箱细节来自社区技术文章，条款编号与适用版本未核实",
     "source_ids": ["S-ART-CSDN-53"], "impact": "CL-PROTECTED 条款实体置信度为 pending", "status": "open"},
    {"pending_id": "P-12", "topic": "扩展 IA 条款",
     "question": "CMIS-VCS-01.1 / CMIS-FF-01.0 / ELSFP-CMIS-01.0 / CMIS-LT-01.0 与主规范的条款级引用关系未逐条展开",
     "source_ids": ["S-OIF-INDEX"], "impact": "扩展规范仅建立文档级关系", "status": "open"},
    {"pending_id": "P-13", "topic": "元数据时效",
     "question": "GitHub star / license / pushed_at 为 2026-11-08 API 快照，需定期刷新",
     "source_ids": ["S-GH-API-SNAPSHOT"], "impact": "选型说明中的活跃度数据会随时间变化", "status": "open"},
    {"pending_id": "P-14", "topic": "CDB 命令帧精确位定义",
     "question": "Page 9Fh 帧字段宽度由 Linux 内核 ethtool_cmis_cdb_request 结构体反推（CMDID 2B / EPL 2B / LPL 1B / 校验码 1B / 保留 2B / LPL 120B）；校验码算法、回复区偏移及触发时序需按 OIF-CMIS-05.3 §8.23 / §9.2 原文逐条核对",
     "source_ids": ["S-OIF-053", "S-GH-LINUX-CDB"], "impact": "影响 CDB 命令编排结果的硬件可用性；当前仅用于离线编排与演示", "status": "open"},
    {"pending_id": "P-15", "topic": "CDB 命令 ID 第三方冲突",
     "question": "部分中文技术文章把 0100h 写作 Start Firmware Download、0103h 写作 Complete Firmware Download；OIF-CMIS-05.3 第 9 章目录与 Linux 内核枚举一致为 0101h Start / 0107h Complete，本图谱以官方目录+内核为准，仍需原文复核",
     "source_ids": ["S-OIF-053", "S-GH-LINUX-CDB"], "impact": "命令目录若与实际模块固件不一致会导致命令被拒绝", "status": "open"},
    {"pending_id": "P-16", "topic": "Low Page 应用广告位置版本差异",
     "question": "公开模块 datasheet 将 Application Advertising 列在 Lower 85-117，而 CMIS 5.3/5.4 主要使用 Upper Page 01h 的 Application Descriptors；该偏移随版本变化",
     "source_ids": ["S-ART-MAPYOURTECH", "S-ART-VITEX", "S-OIF-053"], "impact": "旧布局字段在 5.3/5.4 模块上可能不适用", "status": "open"},
    {"pending_id": "P-17", "topic": "VDM 页归属与阈值可写性",
     "question": "Lower 14-25、Page 02h、10h/11h、20h-2Fh 在 Monitors / Thresholds / VDM 之间的精确分工需按原文确认",
     "source_ids": ["S-OIF-053", "S-IETF-CMIS-YANG"], "impact": "影响 VDM 分区字段分组与阈值可写性判断", "status": "open"},
    {"pending_id": "P-18", "topic": "IETF CMIS YANG 草案状态",
     "question": "draft-hi-ccamp-cmis-control-yang-04 为 Internet-Draft，非 RFC；其页级委派与 9.1 节禁止条款被本项目用作安全策略参考，需跟踪最终 RFC 或厂商实现差异",
     "source_ids": ["S-IETF-CMIS-YANG"], "impact": "安全策略表述可能随草案版本变化", "status": "open"},
    {"pending_id": "P-19", "topic": "两种接入方式的设备侧映射",
     "question": "SSH+I2C 命令模板（i2cdump/i2cset）与 REST 路径（/api/cmis/registers、/api/cmis/cdb）为通用占位实现，真实交换机 CLI、端口到 I2C bus/mux 的映射、REST 认证与字段模型需按目标设备适配",
     "source_ids": ["S-INTERNAL", "S-OIF-053"], "impact": "未适配前不得开启 allow_hardware_write", "status": "open"},
]


def main() -> None:
    # Consistency check: both endpoints of every relation must exist
    ids = {e["entity_id"] for e in ENTITIES}
    src_ids = {s["source_id"] for s in SOURCES}
    problems = []
    for r in RELATIONS:
        if r["src"] not in ids or r["dst"] not in ids:
            problems.append(f"relation endpoint missing: {r['relation_id']} {r['src']}->{r['dst']}")
    for item in ENTITIES + RELATIONS:
        for sid in item["source_ids"]:
            if sid not in src_ids:
                problems.append(f"unknown source: {sid} in {item.get('entity_id') or item.get('relation_id')}")
    for link in LINKS:
        if link["entity_id"] not in ids:
            problems.append(f"link target missing: {link}")
    if problems:
        raise SystemExit("Knowledge graph consistency check failed://n" + "\n".join(problems[:30]))

    types = Counter(e["type"] for e in ENTITIES)
    rel_types = Counter(r["type"] for r in RELATIONS)
    data = {
        "meta": {
            "name": "CMIS Knowledge Graph",
            "version": "1.0.0",
            "generated_at": CHECKED_AT,
            "generator": "tools/build_kg.py",
            "description": "覆盖设备、模块、接口、配置项、规范条款/文档、概念、开源项目、组织与服务；每条实体/关系标注来源与置信度。",
            "entity_types": dict(types),
            "relation_types": dict(rel_types),
            "counts": {"sources": len(SOURCES), "entities": len(ENTITIES),
                       "relations": len(RELATIONS), "links": len(LINKS),
                       "pending_confirmations": len(PENDING)},
            "confidence_legend": {
                "confirmed": "可由官方页面 / GitHub API / 文档编号直接核实",
                "partial": "来自第三方解读或开源实现引用，条款号/地址需复核",
                "pending": "推断或社区资料，明确待确认",
            },
            "relation_legend": {
                "CONTAINS": "包含", "DEFINES": "定义", "CONSTRAINS": "约束",
                "IMPLEMENTS": "实现", "REFERENCES": "引用", "ADVERTISES": "声明能力",
                "CONFIGURES": "配置", "MONITORS": "监控", "INTEGRATES": "集成",
                "DERIVES_FROM": "派生自", "INSTANTIATES": "实例化",
            },
        },
        "sources": SOURCES,
        "entities": ENTITIES,
        "relations": RELATIONS,
        "links": LINKS,
        "pending_confirmations": PENDING,
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    # write_bytes keeps LF on every platform (write_text would emit CRLF on Windows).
    OUT.write_bytes((json.dumps(data, ensure_ascii=False, indent=2) + "\n").encode("utf-8"))
    print(f"wrote {OUT} | {data['meta']['counts']}")
    print("entity types:", dict(types))
    print("relation types:", dict(rel_types))


if __name__ == "__main__":
    main()
