# CMIScope

> Lightweight CMIS dashboard for optical modules — 一个零第三方依赖、可整体拷贝迁移的本地 Web 服务。

**CMIScope** = **CMIS** + **scope**（观测/测量仪器）。名字表达本项目的定位：像一台仪表一样**观察**光模块的 CMIS 寄存器，并在受控条件下**配置**它们；短小、易记，适合作为仓库名 `cmiscope`。

- 后端：Python 3 标准库 `http.server` + SQLite 单文件，**无需 pip 安装**
- 前端：GitHub 选型确定的 [Tabler 1.7.3](https://github.com/tabler/tabler)（MIT），静态资源已本地化，离线可用
- 代码、注释、API 错误消息：**英文**；页面默认**中文**，右上角可切 **English**
- 规范依据：**OIF-CMIS-05.3 / 05.4**、OIF 5.x Errata、IETF CMIS YANG 草案、Linux 内核 `cmis_cdb.c`
- 详细使用背景与两种接入方式见 [`docs/USAGE_BACKGROUND.md`](docs/USAGE_BACKGROUND.md)

---

## 1. 使用背景（简述）

实验室与生产网络中，光模块的 CMIS 信息散落在交换机 CLI、I2C 寄存器和厂商北向接口里。工程师需要一处统一的地方**按设备 / 字段 / 配置项检索**、查看列表与详情、修改配置并在保存前得到校验反馈，同时把「某字段属于哪条规范条款、哪个开源项目实现、来源是否可靠」关联起来。CMIScope 就是这层轻量工作台，并附带一份可关联查询的 CMIS 知识图谱。

服务刻意不绑定硬件：默认 `mirror` 模式下所有读数来自本地 SQLite 镜像，配置写入为 `staged` 并写审计日志，**不会向硬件下发**。接真实设备时按下面两种方式之一切换。

## 2. 两种接入方式（明确区分）

| | 方式一：SSH + I2C | 方式二：RESTful API |
|---|---|---|
| 配置值 | `access_mode = ssh-i2c` | `access_mode = rest-api` |
| 代码运行位置 | **测试 Server**（本机服务） | 本机服务或运维节点 |
| 链路 | 浏览器 → 服务 → **SSH 登录测试 Switch** → 交换机侧 `i2cget/i2cset`/厂商 CLI → **I2C (0x50)** → 模块 EEPROM | 浏览器 → 服务 → **目标设备/NOS 的北向 REST API** → 设备内部完成 I2C 事务 |
| 谁执行 I2C | 测试 Switch | 目标设备自己 |
| 典型场景 | 台架调测、模块表征、CDB/固件实验 | 多设备运维、自动化、生产集成 |
| 凭据 | 复用 ssh-agent 密钥（`BatchMode=yes`），配置里不存密码 | Token 从环境变量 `CMIS_REST_TOKEN` 读取，配置里不存 |
| 写策略 | 按页级白名单；Lower Memory 写被禁止 | 按 IETF YANG 草案的 `remote-write-allowed-pages`；CDB 页默认只读 |

两种方式是**并列的物理接入路径**，共用同一套 dashboard、字段目录、校验规则、审计与知识图谱。完整拓扑、职责边界、安全约束与配置示例见 [`docs/USAGE_BACKGROUND.md`](docs/USAGE_BACKGROUND.md)。

## 3. 快速启动

```bash
python run.py                       # 默认 http://127.0.0.1:8787/
python run.py --port 9000
python run.py --config config.ini   # 自定义配置
python tools/smoke_test.py          # 端到端回归（临时库 + 临时端口，不污染交付数据）
python tools/fetch_specs.py --check  # 校验随附的 OIF 5.3/5.4 PDF 副本
```

配置三层覆盖，环境与代码解耦：**默认值 → `config.ini` → `CMIS_*` 环境变量**。所有相对路径以 `base_dir` 为锚点，整目录复制即可迁移；数据库是单文件 `data/cmis.db`。

```bash
# 常用环境变量
CMIS_ACCESS_MODE=rest-api CMIS_REST_BASE_URL=https://device/api CMIS_REST_TOKEN=xxx python run.py
CMIS_ALLOW_HARDWARE_WRITE=true CMIS_ACCESS_MODE=ssh-i2c CMIS_SSH_HOST=10.0.0.2 python run.py
CMIS_DATA_DIR=/path/to/data python run.py
```

> ⚠️ `allow_hardware_write`、`cdb_allow_firmware`、`cdb_rest_allowed` 默认全部为 `false`。未与目标设备完成字段映射前不要开启。

## 4. Dashboard 功能

| 视图 | 内容 |
|---|---|
| 概览 | 设备/模块/字段/配置项/CDB 操作数、状态分布、最近变更、知识图谱构成、CMIS 分区字段数 |
| 内部设备 | 按名称/厂商/位置/状态/接入方式检索，设备详情（模块、分区字段、配置项） |
| **模块 CMIS** | **按 CMIS 规范分区组织**：低页 0x00、VDM、CDB、控制与诊断；含寄存器布局表、字段列表、就地编辑 |
| 配置项管理 | 全量 512 条实例，按设备/分区/权限/关键词过滤，编辑、保存前校验、变更 diff 与审计 |
| 知识图谱 | 实体检索、邻居遍历、关系过滤、SVG 概览、双向关联查询 |
| 来源与待确认 | 38 条来源及覆盖度、19 条待确认项 |
| **接入配置** | **可编辑、可切换的测试接口**：选择 `mirror` / `ssh + i2c` / `restful API`，编辑 IP、端口、SSH/I2C/REST 参数，新增设备保存后即时接入，支持探测 |
| 关于服务 | 项目说明、两种接入方式、API 端点清单 |

### 按规范分区的模块 CMIS 视图

| 分区 | 规范依据 | 主要页/地址 |
|---|---|---|
| 低页 0x00 | OIF-CMIS-05.3 §8.2 / §8.4 | Lower 00h–7Fh + Upper Page 00h（ID、状态、模块级标志、全局控制、CDB 状态、固件版本、口令区、Bank/Page 选择、厂商/OUI/料号/序列号/校验和） |
| VDM | §8.8 / §8.22；IETF YANG 草案 Table 2 | Lower 14–25 模块级监测量、Page 02h 阈值、10h/11h 通道状态与光功率、20h–2Fh VDM |
| CDB | §8.23 / §8.24 / §9 | Page 9Fh 命令帧、A0h–AFh EPL、Lower 37–38 状态、Lower 122 口令入口 |
| 控制与诊断 | §6.3 / §8.9 / §8.10 / C-CMIS | Page 01h 应用描述符、10h AppSel/DPSM/Staged Control Set、13h/14h PRBS、12h 可调激光器、30h–4Fh 相干设置 |

详见 [`docs/CMIS_SECTIONS.md`](docs/CMIS_SECTIONS.md)。

### CDB 操作接口

- 命令目录：26 条 CMDID（`0000h` Query Status、`0040h` Module Features、`0100h–010Ah` 固件管理、`0200h/0201h` PM、`0380h` 环回等），每条标注 OIF 5.3 条款、风险级别与载荷规则。
- 命令编排：选择 CMDID、输入 LPL（≤120 字节）/ EPL（≤2048 字节）十六进制，服务端离线计算 128 字节命令帧与校验码，返回帧预览；**校验不通过不产生任何下发**。
- 执行：通过当前接入适配器执行，记录 `cdb_operations` 审计；`mirror` 模式恒为 `staged`，`applied_to_hardware=false`。
- 安全：固件类命令需 `cdb_allow_firmware=true`；REST 路径需 `cdb_rest_allowed=true`；执行需 `confirm=EXECUTE`；Lower Memory 与 CDB 页的远程写被 IETF 草案 §9.1 规则禁止。

## 5. 配置项管理

保存前校验覆盖：类型（hex/int/float/bool/enum/ascii/text）、枚举白名单、数值范围、正则、只读位、跨字段约束（`appsel_in_advertised`、`threshold_high_gt_warning`、`tx_disable_vs_datapath_init`、`low_power_vs_datapath_init`）、待确认字段告警。写入使用乐观锁 `expected_version` 防并发，返回 `diff`、校验报告、审计记录与结构化错误（400/404/405/409/413/500/502）。

## 6. 知识图谱

`data/knowledge_graph.json`：**38 来源 / 129 实体 / 257 关系 / 268 关联 / 19 待确认项**。覆盖设备、模块、接口、配置项、规范条款/文档、概念、开源项目、组织、服务、**CMIS 分区**、**接入方式**等实体，含 `CONTAINS / DEFINES / CONSTRAINS / IMPLEMENTS / REFERENCES` 等关系。每条标注 `source_ids` 与 `confidence`（confirmed / partial / pending），启动时导入 SQLite 支持关联查询。图谱文档、JSON schema、38 条来源链接清单与 OIF CMIS 5.3/5.4 PDF 副本集中存放于 [`knowledge/`](knowledge/README.md)。

## 7. 目录结构

```
run.py                         服务入口
config.ini.example             配置模板（默认值 / ini / 环境变量三层覆盖）
config/
  targets.example.json        可编辑目标设备清单模板（IP、端口、接入方式）
  targets.json                运行时的设备清单（gitignore，用户编辑）
cmis_service/
  config.py db.py api.py       配置 / 数据层 / REST API
  adapters.py                  mirror | ssh-i2c | rest-api 三种传输适配器
  targets.py                   设备清单加载 / 校验 / 原子保存 / 按设备解析传输配置
  cmis_spec.py                 CMIS 5.3/5.4 分区、寄存器布局、CDB 命令目录、帧编排
  validation.py kg.py server.py
  static/                     index.html + i18n.js + app.js + app.css + vendored Tabler
tools/                         seed / 图谱 / 文档生成器、规格书下载、冒烟测试
data/                          seed.json、knowledge_graph.json、cmis.db
knowledge/                     图谱文档、SCHEMA、SOURCES、links.json 与 OIF 5.3/5.4 PDF 副本
docs/                          使用背景、分区说明、选型、API、部署与操作指导
NOTICE LICENSE                 第三方资产声明与 MIT 许可
```

## 8. 选型说明

从 GitHub 筛选并选定 **Tabler 1.7.3（MIT）**：实时 API 快照显示 MIT / 约 42k stars / 2026-11-07 仍有提交；单 CSS + 单 JS、无构建链、可本地 vendored，许可与活跃度均优于需 jQuery 的 AdminLTE、需 Vue/Node 构建链的 Dashy、AGPL-3.0 且重量级的 Grafana。详见 [`docs/DASHBOARD_SELECTION.md`](docs/DASHBOARD_SELECTION.md)。

## 9. 已知限制

- 设备、模块与读数为**合成演示数据**；接入生产前需替换 `data/seed.json` 或改写生成器。
- `mirror` 模式下配置只写本地镜像（`staged`），**不下发硬件**；`ssh-i2c` 的命令模板与 `rest-api` 的路径/字段模型为通用占位，需按目标交换机 CLI / 北向 API 适配。
- 部分 byte offset、CDB 校验码/回复区偏移、CMDID 第三方冲突、VDM 页归属与阈值可写性、IETF 草案状态等列入 19 条待确认项，需按 OIF 原文与法务复核后再用于硬件。
- Tabler 资源为 vendored 第三方文件，保留其 `LICENSE`；本项目代码为 MIT（见仓库 `LICENSE`）。

## 10. 文档索引

| 文档 | 内容 |
| --- | --- |
| [`docs/USAGE_BACKGROUND.md`](docs/USAGE_BACKGROUND.md) | 使用背景、两种接入方式的拓扑与职责边界、安全策略、上线检查清单 |
| [`docs/CMIS_SECTIONS.md`](docs/CMIS_SECTIONS.md) | CMIS 5.3/5.4 分区依据、Lower Memory 布局、Upper Page 00h、CDB 帧与命令目录 |
| [`docs/API.md`](docs/API.md) | 全部 REST 端点、错误码、校验规则、curl 示例 |
| [`knowledge/CMIS_KNOWLEDGE_GRAPH.md`](knowledge/CMIS_KNOWLEDGE_GRAPH.md) | 图谱规模、置信度规则、38 条来源、19 条待确认项、关联查询方式 |
| [`docs/DASHBOARD_SELECTION.md`](docs/DASHBOARD_SELECTION.md) | Tabler 1.7.3 选型依据、候选对比、集成方式与双语 UI 说明 |
| [`docs/DEPLOYMENT.md`](docs/DEPLOYMENT.md) | 英文部署指南：环境要求、配置优先级、接入模式、安全、跨平台迁移与升级 |
| [`docs/OPERATIONS.md`](docs/OPERATIONS.md) | 英文操作指导：视图、设备接入、CDB、配置编辑、图谱查询与故障排查 |
| [`knowledge/README.md`](knowledge/README.md) | 知识图谱独立目录：文档、schema、来源链接与规格书副本 |
| `NOTICE` | 第三方资产与 OIF 规格书版权声明 |
