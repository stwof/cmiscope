# CMIS 规范分区与实现依据（5.3 / 5.4）

> 本文说明 Dashboard「模块 CMIS」视图为什么这样分区、每个分区对应哪些页/寄存器、依据哪些公开资料，以及哪些内容仍待确认。实现位于 `cmis_service/cmis_spec.py`（分区、寄存器布局、CDB 命令目录、帧编排）与 `tools/cmis_catalog.py`（字段目录）。

## 1. 规范版本

| 文档 | 版本 | 发布日期 | 用途 |
|---|---|---|---|
| OIF-CMIS-05.2 | 5.2 | 2022-04 | 早期基线；QSFP-DD MSA 移交 OIF 后的版本 |
| **OIF-CMIS-05.3** | **5.3** | **2024-09** | **本项目主要依据**；首个完全由 OIF 产出的修订版，CDB 命令集中在第 9 章 |
| OIF-CMIS-05-Errata-01.0 | 5.x | 2025-02 | 修复 Application advertising 互操作问题，须与 5.3 一起读 |
| **OIF-CMIS-05.4** | **5.4** | **2026-05** | 最新主规范，作为版本对齐目标 |
| OIF-C-CMIS-01.5 | 1.5 | 2026-09 | 相干模块扩展（Pages 30h–4Fh） |

来源：OIF 官方 Implementation Agreements 索引页（核对编号与日期）、OIF-CMIS-05.3 公开 PDF 目录。辅助交叉验证：Linux 内核 `net/ethtool/cmis.h` 与 `cmis_cdb.c`（GPL-2.0）、IETF `draft-hi-ccamp-cmis-control-yang-04`、公开 CMIS 模块 datasheet 与 Vitex EEPROM 指南。

> CMIS 采用「256 字节窗口」：低 128 字节（00h–7Fh）常驻，高 128 字节（80h–FFh）由 Page Select 切换成一页 Upper Memory。旧的 SFF-8472 / SFF-8636 是固定地址映射；QSFP-DD / OSFP / 800G 模块使用 CMIS。

## 2. 分区总览

| 分区 key | 页面 | 主要内容 | 写策略 |
|---|---|---|---|
| `LOW_PAGE` | Lower 00h–7Fh + Upper 00h | 识别、状态、标志、全局控制、固件版本、应用广告、口令区、Bank/Page 选择 | 只读为主；远程写 Lower Memory 被禁止 |
| `VDM` | Lower 14–25、02h、10h、11h、20h–2Fh | 监测量、阈值、通道状态、VDM | 阈值可委派；监测量只读 |
| `CDB` | Lower 37–38 / 118–125、9Fh、A0h–AFh | 命令帧、EPL、状态、口令、命令目录 | 门控；禁止远程写白名单委派 |
| `CONTROL` | 01h、10h、12h、13h、14h、30h–4Fh | AppSel / DPSM / Staged Control Set / PRBS / 环回 / 相干设置 | 需页级委派 |

分组依据：OIF-CMIS-05.3 §8（寄存器组织）、§9（CDB 命令）、IETF YANG 草案 §3 的 CMIS Page Classification 表（Lower Memory / 00h–01h / 02h / 10h–11h / 12h / 13h–14h / 20h–2Fh / 30h–3Fh / 40h–4Fh / 9Fh–AFh / B0h–FFh）。

## 3. 低页 0x00（Lower + Upper Page 00h）

### Lower Memory（常驻 00h–7Fh）

| 地址 | 字节数 | 区域 | 权限/注意 |
|---|---|---|---|
| 0–3 | 4 | ID and Status Area | RO；Identifier(SFF-8024)、Revision Compliance、FlatMem、Module State |
| 4–7 | 4 | Lane Flag Summary | RO / CoR；Pages 10h–1Fh 通道标志汇总 |
| 8–13 | 6 | Module-Level Flags | RO / CoR |
| 14–25 | 12 | Module-Level Monitors | RO；温度/电压/辅助监测量（VDM 分区） |
| 26–30 | 5 | Module Global Controls | RW；含 LowPwrRequestSW |
| 31–36 | 6 | Module-Level Flag Masks | RW |
| 37–38 | 2 | CDB Status Area | RO；最近一次 CDB 命令状态 |
| 39–40 | 2 | Module Firmware Version | RO |
| 41–63 | 23 | Reserved | — |
| 64–82 | 19 | Custom Area | 厂商自定义 |
| 83–84 | 2 | Inactive Firmware Version | RO；00h 表示单镜像 |
| 85–117 | 33 | Application Advertising | RO；**旧布局**，CMIS 5.3/5.4 主要使用 Upper Page 01h 描述符 |
| 118–125 | 8 | Password Entry and Change | WO；内核 ethtool 在 `0x7A`(122) 写 4 字节口令 |
| 126 | 1 | Bank Select | RW |
| 127 | 1 | Page Select | RW；切换后遵守 tBPC 保持时间 |

该表来自公开 CMIS 模块 datasheet（CMIS 4.x/5.x 混合资料），**精确偏移在 5.3/5.4 中可能变化**，已在图谱标为 `partial` / 待确认项 P-16。

### Upper Page 00h（静态识别）

Vendor Name(16B ASCII)、Vendor OUI(3B)、Part Number(16B)、Revision(2B)、Serial Number(16B)、Date Code(8B)、`CC_BASE` / `CC_EXT` 校验和。重编码 EEPROM 后若不重算校验和，模块可能无法识别。精确偏移待 OIF 原文核对（P-01）。

## 4. VDM（Versatile Diagnostic Monitoring）

> **术语说明**：本分区统一命名为 **VDM**（Versatile Diagnostic Monitoring），覆盖 CMIS 5.3 中的 Monitors、Thresholds 与 VDM 页；项目内变量、接口参数、配置项分组与文档术语全部使用 VDM，寄存器布局与读写策略保持不变。

| 位置 | 内容 | 依据 |
|---|---|---|
| Lower 14–25 | 模块级监测量（温度、供电电压、辅助量） | datasheet + OIF-CMIS-05.3 §8.8 |
| Page 02h | Alarm / Warning Thresholds | IETF YANG 草案 Table 2「Thresholds & Monitors」 |
| Page 10h / 11h | 通道状态、Tx/Rx 光功率、偏置、告警标志 | §8.8 / §8.9；公开 EEPROM 指南 |
| Pages 20h–2Fh | VDM（Versatile Diagnostics Monitor）配置与实时值 | §8.22 |

Dashboard 中该分区展示 `ModuleTemperature / ModuleVoltage / TxPowerDbm / RxPowerDbm / TxBiasLane1 / RxLosLane1`、高低温与电压阈值、`VdmFreeze`，并支持阈值编辑（含 `threshold_high_gt_warning` 跨字段校验）。监测量本身只读。

## 5. CDB（Command Data Block）

### 5.1 命令帧（Page 9Fh，字节 128–255，I2C 地址 0x50）

| 偏移 | 字节数 | 字段 | 说明 |
|---|---|---|---|
| 9Fh:128 (0x80) | 2 | CMDID | 大端命令 ID；写入结束于 9Fh:129 的操作触发命令（§8.23.1 / §8.23.2） |
| 9Fh:130 (0x82) | 2 | EPL Length | 大端扩展载荷长度，≤2048 字节 |
| 9Fh:132 (0x84) | 1 | LPL Length | 本地载荷有效字节数，≤120 |
| 9Fh:133 (0x85) | 1 | Check Code | 使 EPL 长度至 LPL 载荷的字节和对 256 取模为 0 |
| 9Fh:134–135 | 2 | Reserved | 00h |
| 9Fh:136–255 (0x88–0xFF) | 120 | LPL | 命令参数 / 短回复 |

字段宽度由 Linux 内核 `struct ethtool_cmis_cdb_request`（`__be16 id; __be16 epl_len; u8 lpl_len; u8 chk_code; u8 resv1; u8 resv2; u8 payload[120];`，共 128 字节）交叉印证；`ETHTOOL_CMIS_CDB_CMD_PAGE = 0x9F`、`I2C_ADDR = 0x50`。本项目按此实现离线帧编排：校验码取 `(-sum(body)) & 0xFF`，返回 128 字节十六进制帧预览。

### 5.2 扩展载荷与状态

- **EPL**：Pages A0h–AFh，16 页 × 128 字节 = **最多 2048 字节**（内核 `CMIS_CDB_EPL_PAGE_START/END`、偏移 128–255）。
- **CDB 状态**：Lower 37–38；**口令入口**：Lower 122 (0x7A)，内核在固件命令前写入 4 字节口令。服务不持久化口令。
- **回复区**：RPL length + RPL check code + 最多 120 字节回复（精确偏移待原文核对，P-14）。
- **多实例**：CMIS 支持多个 CDB 实例，Bank 选择决定当前实例（§9.2.2）。

### 5.3 命令目录（OIF-CMIS-05.3 第 9 章）

| CMDID | 命令 | 条款 | 风险 |
|---|---|---|---|
| 0000h | Query Status | §9.3.1 | read |
| 0001h / 0002h | Enter / Change Password | §9.3.2 / §9.3.3 | security |
| 0004h | Abort Processing | §9.3.4 | control |
| 0040h–0045h | Module Features / FW Mgmt Features / PM Features / BERT & Diag Features / Security Features / Externally Defined Features | §9.4.1–9.4.6 | read |
| 0050h / 0051h | Get Application Attributes / Get Interface Code Description | §9.4.7 / §9.4.8 | read |
| 0100h | Get Firmware Info | §9.7.1 | read |
| 0101h / 0102h | Start / Abort Firmware Download | §9.7.2 / §9.7.3 | firmware |
| 0103h / 0104h | Write Firmware Block LPL / EPL | §9.7.4 / §9.7.5 | firmware |
| 0105h / 0106h | Read Firmware Block LPL / EPL | §9.7.6 / §9.7.7 | read |
| 0107h–010Ah | Complete FW Download / Copy Image / Run Image / Commit Image | §9.7.8–9.7.11 | firmware |
| 0200h / 0201h | Control PM / Get PM Feature Information | §9.8.1 / §9.8.2 | control / read |
| 0380h | Loopbacks | §9.10 / §9.11 | control（标注 partial） |

> ⚠️ **来源冲突（待确认 P-15）**：部分中文技术文章把 0100h 写作 Start Firmware Download、0103h 写作 Complete Firmware Download；本项目以 **OIF-CMIS-05.3 第 9 章官方目录 + Linux 内核命令枚举**为准（0101h Start / 0107h Complete），两者互相印证。

### 5.4 操作接口与安全

`POST /api/cdb/compose` 只做离线编排（不碰硬件），`POST /api/cdb/execute` 经当前接入适配器执行并记入 `cdb_operations` 审计。执行约束：

1. `mirror` 模式恒为 `staged`，`applied_to_hardware=false`；
2. 非镜像模式需 `confirm=EXECUTE` 且 `allow_hardware_write=true`；
3. 固件类命令需 `cdb_allow_firmware=true`；
4. REST 路径执行 CDB 需 `cdb_rest_allowed=true`（默认禁止）；
5. 依据 IETF YANG 草案 §9.1，**CDB 页 9Fh–AFh 不得纳入远程写白名单**，Lower Memory 写一律拒绝。

## 6. 控制与诊断分区

Page 01h Application Descriptors（Host/Media Interface ID、Lane Count、Lane Assignment）、Page 10h AppSel(0xAD 编码)/DPSM/Staged Control Set（Tx 均衡、CDR）、Pages 13h/14h PRBS 与环回、Page 12h 可调激光器、Pages 30h–4Fh C-CMIS 相干设置。该分区字段多数为 `partial`，精确偏移与枚举需按 OIF 原文复核。

## 7. 待确认项与来源标注

所有分区与字段均标注 `source_ids` 与 `confidence`：

- `confirmed`：官方 IA 编号/目录、GitHub API 快照、内核结构体等可直接核实；
- `partial`：第三方解读、厂商 datasheet、开源实现引用，条款号或地址需复核；
- `pending`：推断或社区资料。

与本分区直接相关的待确认项：P-01（精确地址）、P-02（5.3/5.4 差异）、P-03（AppSel 编码）、P-04（数值编码）、P-14（CDB 帧位定义/校验码/回复区）、P-15（CMDID 冲突）、P-16（应用广告位置版本差异）、P-17（VDM 页归属与阈值可写性）、P-18（IETF 草案状态）、P-19（设备侧适配）。完整清单见 `data/knowledge_graph.json -> pending_confirmations` 与 [`knowledge/CMIS_KNOWLEDGE_GRAPH.md`](../knowledge/CMIS_KNOWLEDGE_GRAPH.md)。
