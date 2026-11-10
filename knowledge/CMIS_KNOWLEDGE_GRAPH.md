# CMIS 知识图谱数据与来源说明（CMIScope）

数据文件：**`data/knowledge_graph.json`**（约 206 KB，UTF-8）。
生成器：**`tools/build_kg.py`**（`python tools/build_kg.py` 可复现），字段/设备定义来自 `tools/cmis_catalog.py`，
规范分区与 CDB 定义来自 `cmis_service/cmis_spec.py`。
服务启动时由 `cmis_service/db.py` 导入 SQLite `kg_*` 表，因此图谱既是可直接消费的 JSON，
也是**可关联查询**的结构化数据。

---

## 1. 规模

| 项目 | 数量 |
| --- | ---: |
| 来源 `sources` | **38** |
| 实体 `entities` | **129** |
| 关系 `relations` | **257** |
| CMIS 关联映射 `links` | **268** |
| 待确认项 `pending_confirmations` | **19** |

实体类型（12 类，较初版新增 `SpecificationPartition`、`AccessPath`）：
`ConfigItem 31`、`SpecClause 20`、`Interface 14`、`Standard 13`、`OpenSourceProject 13`、
`Concept 9`、`Module 8`、`Device 8`、`Organization 5`、`SpecificationPartition 4`、
`AccessPath 3`、`Service 1`。

置信度分布：`confirmed 54` / `partial 74` / `pending 1`。

关系类型（11 类，覆盖题目要求的「包含、定义、约束、实现、引用」）：

| 关系 | 中文 | 数量 | 典型例子 |
| --- | --- | ---: | --- |
| `DEFINES` | 定义 | 90 | `OIF-CMIS-05.3` → `§9 CDB 命令`；`SEC-CDB` → `IF-CDB-FRAME` |
| `CONTAINS` | 包含 | 62 | `QSFP-DD 模块` → `TWI 管理接口`；`SEC-LOW-PAGE` → `CFG-IDENT` |
| `IMPLEMENTS` | 实现 | 24 | `libsffcmis` → `Page 10h/11h 数据路径控制`；Linux `cmis_cdb.c` → `CDB 命令帧` |
| `REFERENCES` | 引用 | 22 | `CMIS 5.3` → `SFF-8024`；`ethtool` → `CMIS 5.3` |
| `CONFIGURES` | 配置 | 22 | `AppSel` → `Data Path`；`BankSelect` → `Bank/Page` |
| `CONSTRAINS` | 约束 | 19 | `§6.2.1` → `AppSel 只能引用已广告 Application`；`CON-PAGE-GOVERNANCE` → `PageSelect` |
| `ADVERTISES` | 声明能力 | 5 | `OSFP 模块` → `Application Descriptor` |
| `MONITORS` | 监控 | 5 | `VDM 监控量` → `DDM/VDM 概念` |
| `DERIVES_FROM` | 派生自 | 4 | `CMIS 5.3` → `5.2`；`libsffcmis` → `ethtool` |
| `INSTANTIATES` | 实例化 | 2 | `相干 DCO` → `QSFP-DD / OSFP 封装` |
| `INTEGRATES` | 集成 | 2 | CMIScope → `Tabler 1.7.3` / `Tabler Icons` |

每条实体与关系都带 `source_ids`、`confidence`、`status`；每条来源带
`source_id / title / publisher / url / kind / license / retrieved_at / note`。

### 1.1 第二轮新增的实体族

| 实体族 | ID | 说明 |
| --- | --- | --- |
| 规范分区 `SpecificationPartition` | `SEC-LOW-PAGE`、`SEC-VDM`、`SEC-CDB`、`SEC-CONTROL` | 与 `cmis_spec.SECTIONS` 一一对应，字段通过 link 归属到分区 |
| 接入路径 `AccessPath` | `IF-SSH-I2C`、`IF-REST-API`、`IF-MIRROR` | 对应 `docs/USAGE_BACKGROUND.md` 的两种生产接入方式 + 离线镜像 |
| CDB 接口 | `IF-CDB-FRAME`（Page 9Fh 128B 帧）、`IF-CDB-EPL`（A0h–AFh）、`IF-CDB` | 命令帧与扩展载荷 |
| CDB/分区配置项 | `CFG-CDB`、`CFG-VDM`、`CFG-LOW-PAGE` | 让 CDB/VDM/Low Page 字段在图谱中有落点 |
| 页治理约束 | `CON-PAGE-GOVERNANCE` | 参照 IETF YANG 草案的 `remote-read-allowed-pages` / `remote-write-allowed-pages` |
| 服务实体 | `Service`：`CMIScope - Lightweight CMIS Dashboard` | 项目名称同步 |

`links` 从 168 增至 268，主要是**字段 → 规范分区**与**设备 → 接入路径**两类关联，
使「模块 CMIS 分区视图」与「接入方式」都能在图谱里反向检索。

---

## 2. 置信度与标注规则

| 取值 | 含义 | 典型场景 |
| --- | --- | --- |
| `confirmed` | 可由 OIF 官方 IA 索引、文档编号/日期、IETF 草案、GitHub API / README 或内核源码直接核实 | 规范版本与发布日期、Lower/Upper 地址空间、CDB 命令 ID、仓库许可/star/push 时间 |
| `partial` | 来自第三方解读或开源实现引用，条款号/字节地址/枚举需与 OIF 原文复核 | Page 00h/01h 寄存器偏移、`§6.3.3` 具体条款号、SI 参数范围、CDB 帧位定义 |
| `pending` | 推断或社区资料，明确待确认 | 受保护区密码机制 `CL-PROTECTED` |

`status`：规范条款中 `confidence != confirmed` 的标为 `needs_review`，其余 `active`。
字段字典 `data/seed.json -> fields[*].confidence` 与图谱一致，服务在保存配置项时
若字段为 `partial/pending`，校验报告会追加 `SPEC_UNCONFIRMED` 告警。

> 注意：本项目**未拷贝**任何开源项目的源代码，仅引用其 README / 文档、内核函数名与仓库元数据作为知识来源。

---

## 3. 来源清单（按类别）

来源明细见 `data/knowledge_graph.json -> sources` 与页面「来源与待确认」视图
（`GET /api/kg/sources/coverage` 返回每条来源支撑的实体/关系数量）。

**OIF 官方 IA（11 条，编号与发布日期核对自 [OIF IA 索引](https://www.oiforum.com/technical-work/implementation-agreements/)）**

| 编号 | 版本 / 日期 |
| --- | --- |
| `OIF-CMIS-05.4` | Rev 5.4，2026-05（本次调研时最新主规范） |
| `OIF-CMIS-05.3` | Rev 5.3，2024-09（CDB / 分区实现的主要依据） |
| `OIF-CMIS-05.2` | Rev 5.2，2022-04（首个由 OIF 完成的 CMIS IA） |
| `OIF-CMIS-05-Errata-01.0` | CMIS 5.x 勘误，2025-02 |
| `OIF-C-CMIS-01.3 / 01.5` | 相干 CMIS，2023-10 / 2026-09 |
| `OIF-CMIS-VCS-01.1` | Versatile Control Set，2025-07 |
| `OIF-CMIS-FF-01.0` | 封装相关硬件管理，2024-09 |
| `OIF-ELSFP-CMIS-01.0` | 外置激光器 CMIS，2024-09 |
| `OIF-CMIS-LT-01.0` | 带外链路训练，2026-09 |

**第二轮新增的 3 条关键来源**

| ID | 来源 | 作用 |
| --- | --- | --- |
| `S-IETF-CMIS-YANG` | `draft-hi-ccamp-cmis-control-yang-04` — A YANG Data Model for CMIS Access and Control | 页级读写 allowlist、`default-policy`、§9.1 禁止 Lower Memory 远程写与 CDB 页写；支撑两种接入方式的安全模型 |
| `S-GH-LINUX-CDB` | Linux kernel `net/ethtool/cmis_cdb.c` / `cmis.h`（GPL-2.0） | 交叉印证 CDB 帧结构、LPL/EPL 常量、CMDID 目录与 Page 9Fh/A0h–AFh 用法 |
| `S-ART-VITEX` | AI Data Center Engineering Guide — CMIS 5.3 EEPROM map (Vitex) | Low Page / Upper Page 00h 地址映射的第三方交叉参考 |

**标准/组织（3 条）**：`SFF-8024`（Host/Media Interface ID 编码）、`SFF-8636`（旧版 QSFP 管理接口）、
`QSFP-DD MSA CMIS 4.0/5.0`（CMIS 前身，2022 年移交 OIF，见 Lightwave 报道）。

**GitHub 开源资料与框架候选（13 条）**

| 项目 | 许可（GitHub API 快照） | 在本图谱中的作用 |
| --- | --- | --- |
| `sonic-net/sonic-platform-common` | NOASSERTION（混合许可，待确认） | `CmisApi` 字段解析、AppSel、SI staging、CMIS 初始化 |
| `sonic-net/sonic-platform-daemons` | 待确认 | `xcvrd` CMIS application initialization 状态机 |
| `sonic-net/sonic-utilities` | 待确认 | `sfputil show eeprom` |
| `meta/fboss` | NOASSERTION（BSD-style + PATENTS） | `qsfp_service` / CmisModule |
| `vjardin/libsffcmis` | README 声明 GPLv2（GitHub 未识别 LICENSE） | 按页实现 datapath / VDM / CDB / diag / coherent / tunable |
| `ethtool` (`cmis.c`) | GPL-2.0 | CMIS EEPROM 解析；注释引用 `§8.4.4 Table 8-40` |
| `torvalds/linux` | GPL-2.0 | I2C / SFP 底层访问 + `cmis_cdb.c` CDB 实现 |
| `tabler/tabler`、`tabler/tabler-icons` | MIT | 选定/配套 Dashboard 框架 |
| `AdminLTE`、`dashy`、`grafana` | MIT / MIT / AGPL-3.0 | 选型对比候选 |

**第三方技术资料（9 条）**：
[MapYourTech CMIS 管理架构](https://mapyourtech.com/cmis-for-pluggable-optics-management-architecture-state-machines-and-comparison)
（Lower/Upper、Bank:Page:Byte、Table 10-4）、
[Wave2Wave CMIS 编程与 Breakout 指南](https://www.wave2wave.io/datasheets/resources/W2W_CMIS-Programming-Breakout-Guide_v1.0.pdf)
（Page 00h/01h 地址、0xAD AppSel）、
[LINK-PP CMIS Explained](https://resources.l-p.com/knowledge-center/cmis-common-management-interface-specification)、
[Cisco xrdocs DCO AppSel](https://xrdocs.io/design/blogs/2026-0610-dco-configuration-appsel)、
[Lightwave OIF CMIS 5.2 报道](https://www.lightwaveonline.com/optical-tech/transmission/article/14277596/oif-finishes-one-cmis-project-starts-another)、
Vitex CMIS 5.3 EEPROM map、CSDN CMIS 5.2/5.3 中文解读（社区资料，条款号待复核）。

**内部数据（1 条）**：`S-INTERNAL` —— `data/seed.json` 合成演示数据，不代表真实网元资产。

> OIF-CMIS-05.3 的 PDF 为二进制资源，无法直接抓取正文；本次通过 OIF IA 官方索引页、
> IETF YANG 草案、Linux 内核 `cmis_cdb.c` 索引结果及第三方编程指南**交叉印证**条款号与命令 ID，
> 因此相关条目统一标为 `partial` 并列入待确认项。

---

## 4. 待确认项（19 条）

完整文本见 `data/knowledge_graph.json -> pending_confirmations` 或 `GET /api/kg/pending`；
每条含 `pending_id / topic / question / source_ids / impact / status`（当前全部 `open`）。

| ID | 主题 | 要点 |
| --- | --- | --- |
| P-01 | 寄存器精确地址 | Page 00h/01h/10h/11h/02h 的 byte offset 与 bit 位置需按模块实际 CMIS Revision 与 OIF 原文逐条核对 |
| P-02 | 版本差异 | 05.3 / 05.4 相对 05.2 的条款增删未逐条比对，仅核对官方编号与日期 |
| P-03 | AppSel 编码来源 | 0xAD 与 Page 01h byte 128-135 来自第三方编程指南，需与 OIF 原文核对 |
| P-04 | 数值编码 | float 型阈值按 1/256 缩放 16-bit 推导 raw_hex，非逐条规范核对 |
| P-05 | 开源许可：SONiC | `sonic-platform-common` GitHub license 为 NOASSERTION，集成前需法务确认 |
| P-06 | 开源许可：libsffcmis | README 声明 GPLv2，GitHub 未识别 LICENSE 文件 |
| P-07 | 开源许可：FBOSS | NOASSERTION + PATENTS 专利授予文件，需评估 |
| P-08 | SFF-8024 版本 | 接口编码表版本未确认（libsffcmis 提到 Rev 4.13） |
| P-09 | 内部设备数据 | seed 中设备/模块/DDM 读数均为合成演示数据 |
| P-10 | 配置下发路径 | 默认 mirror 仅 staged；真实下发需 `ssh-i2c` / `rest-api` 适配器实测 |
| P-11 | 密码保护/消息邮箱 | 来自社区文章，条款编号与适用版本未核实 |
| P-12 | 扩展 IA 条款 | VCS / FF / ELSFP-CMIS / LT 与主规范仅建立文档级引用 |
| P-13 | 元数据时效 | GitHub star / license / pushed_at 为 2026-11-08 快照 |
| **P-14** | **CDB 命令帧精确位定义** | 9Fh 帧的字节序、Check Code 覆盖范围、保留字节需按 OIF-CMIS-05.3 §9 原文复核；当前实现以内核 `cmis_cdb.c` 与规范目录交叉推导 |
| **P-15** | **CDB 命令 ID 第三方冲突** | 命令目录中部分 CMDID 来自开源实现/社区资料，若与厂商自定义命令冲突需按模块实际能力裁剪 |
| **P-16** | **Low Page 应用通告位置版本差异** | Upper Page 00h/01h 的 Application 广告字节在 5.2/5.3/5.4 间可能有调整 |
| **P-17** | **VDM 页归属与阈值可写性** | Lower 14-25、Page 02h、10h/11h、20h-2Fh 在 Monitors / Thresholds / VDM 之间的精确分工需按 OIF 原文与真实模块确认 |
| **P-18** | **IETF CMIS YANG 草案状态** | `draft-hi-ccamp-cmis-control-yang-04` 为 Internet-Draft，页级 allowlist 尚未成为正式标准 |
| **P-19** | **两种接入方式的设备侧映射** | SSH+I2C 命令模板与 REST 资源路径因 NOS/厂商而异，需在真实设备上联调并填充 |

---

## 5. 可关联查询

图谱 JSON 导入 SQLite 后提供以下关联查询能力（`cmis_service/kg.py`）：

| 端点 | 能力 |
| --- | --- |
| `GET /api/kg/stats` | 实体/关系/来源/关联/待确认数量与类型分布 |
| `GET /api/kg/entities?type=&q=&confidence=` | 实体检索与过滤（含 `SpecificationPartition` / `AccessPath`） |
| `GET /api/kg/entity/{id}?depth=1\|2` | 实体属性、来源解析、入边/出边、二跳邻居 |
| `GET /api/kg/relations?type=&src=&dst=&q=` | 按关系类型/端点过滤 |
| `GET /api/kg/link?cmis=AppSelLane1` | **CMIS 字段 → 配置项实体 / 规范分区 / 规范条款 / 主规范 / 开源实现** |
| `GET /api/kg/link?entity=CFG-APPSEL` | **图谱实体 → 引用它的 CMIS 字段与设备** |
| `GET /api/kg/link?cmis=CdbCmdId` | CDB 字段 → `CFG-CDB` / `SEC-CDB` / 主规范 / `OSS-ETHTOOL` |
| `GET /api/kg/graph?limit=200` | 可视化用节点/边子集 |
| `GET /api/kg/sources/coverage` | 每条来源支撑的实体数/关系数 |
| `GET /api/kg/pending` | 19 条待确认项清单 |

示例：

```bash
curl "http://127.0.0.1:8787/api/kg/link?cmis=AppSelLane1"
curl "http://127.0.0.1:8787/api/kg/link?cmis=CdbCmdId"
curl "http://127.0.0.1:8787/api/kg/entity/SEC-CDB?depth=2"
curl "http://127.0.0.1:8787/api/kg/entities?type=AccessPath"
curl "http://127.0.0.1:8787/api/kg/relations?type=CONSTRAINS"
```

`kg_links` 的 `cmis_ref` 取值为字段 key（如 `AppSelLane1`、`CdbCmdId`）或设备 ID（如 `SW-CORE-01`），
因此配置项详情、设备详情、分区视图与图谱实体详情四处可以互相跳转，
形成「**配置项 ↔ 规范分区 ↔ 规范条款 ↔ 开源实现 ↔ 设备 ↔ 接入路径**」的闭环。

---

## 6. 数据维护

1. 修改 `tools/cmis_catalog.py`（字段/设备）、`cmis_service/cmis_spec.py`（分区/CDB 命令）
   或 `tools/build_kg.py`（实体/关系/来源/待确认项）。
2. 运行 `python tools/build_seed.py` 与 `python tools/build_kg.py`；生成器内置一致性自检
   （关系两端实体存在、`source_ids` 均已定义、link 目标存在）。
3. 运行 `python tools/smoke_test.py`（87 项端到端回归）。
4. 重启服务：图谱表自动以新 JSON 重建；设备数据以 `INSERT OR IGNORE` 幂等同步且**不覆盖用户已编辑的配置值**，
   如需完全重置，删除 `data/cmis.db` 后重启（或指向新的 `CMIS_DB_FILE`）。

接入真实数据时：替换 `seed.json` 生成逻辑接入 CMDB/NMS，并把字段地址、条款号与
`confidence` 按 OIF 原文逐条校准，逐步关闭 `pending_confirmations`。
