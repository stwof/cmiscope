# 测试报告 — 源码清理、接入模式互斥与跨版本规范验证

本轮改动包含两部分：**(A)** 移除外部仓库引入的原始实现与残留引用，改为项目自有的规范化数据集与重构实现；**(B)** `ssh + i2c` 与 `restful API` 两种接入模式严格互斥（添加、显示、提交、生效全链路）。测试围绕这两条改动路径补齐了功能、异常、边界与回归覆盖，并下载 CMIS 5.1 / 5.2 手册完成跨版本验证。

全部测试纯标准库、离线执行、不触硬件、不写交付数据（`smoke_test.py` 使用临时库与临时端口）；数据库类用例均在临时目录建库。

## 1. 结果汇总

复跑命令见 [README.md](../README.md) 的「常用命令」；本次结果：

| 测试套件 | 项数 | 结果 | 覆盖重点 |
| --- | ---: | --- | --- |
| `tools/smoke_test.py` | 87 | 全绿 | 端到端 HTTP、分区视图、CDB 编排/审计/写保护（既有回归） |
| `tools/test_reference.py` | 20 | 全绿 | 只读参考层 DB 导入与 `/api/reference/*`（既有回归） |
| `tools/test_spec_pdf.py` | 38 | 全绿 | PDF 解析规则、索引、API 溯源；**新增 5 项线性化 PDF 回归** |
| `tools/test_spec_diff.py` | 22 | 全绿 | 5.3 → 5.4 版本差异报告（既有回归） |
| `tools/test_seed_verification.py` | 28 | 全绿 | 64 个演示字段校验（既有回归） |
| `tools/test_access_modes.py` | **99** | 全绿 | 源码清理 + 模式互斥：功能、异常、边界、API 端到端、前端一致性 |
| `tools/test_dataset_build.py` | **37** | 全绿 | 规范化数据集构建：功能路径、异常输入、边界、DB/API 回归 |
| `tools/test_legacy_specs.py` | **19** | 全绿 | CMIS 5.1 / 5.2 手册跨版本验证（需本地手册） |
| **合计** | **350** | **0 失败** | |

另通过：`py_compile`（全部 `cmis_service/*.py`、`tools/*.py`）、`node --check`（`app.js` / `i18n.js`）、`verify_seed_fields.py --strict`（退出码 0）、无 PDF 索引时的数据集重建、`config.ini.example` 的 configparser 解析。

## 2. 改动路径的覆盖明细

### A. 源码清理（数据集构建链路）

`tools/test_dataset_build.py`（37 项）覆盖 `tools/import_cmis53.py` 的完整链路：

- **功能路径**：2442 字段 / 48 命令构建、统计与行数一致、三份输入的 SHA-256、许可边界、PDF 溯源注入与表排序、与交付 `cmis53_reference.json` 的逐行一致性、重建确定性、纯数据集（无索引）构建。
- **异常**：数据集缺失、根非对象、分组缺失/空/非列表/含非对象行、字段缺列、JSON 损坏、`key_id` / `cmd_id` 重复 —— 全部要求显式 `SystemExit` 且带诊断信息，不接受静默产出半成品。
- **边界**：单行数据集、空索引 / 无 tables / 空 tables、`ref_table` 多表引用取首个可解析项、输入里残留的派生溯源键被剥离、缺失输入文件标记为 `missing`。
- **回归**：新鲜构建产物导入 SQLite 后 2442/48/7 行 + 238 张表，演示字段 64 / 配置项 512 不变，CDB 操作日志为空，`/api/reference/meta|fields|cdb-commands|spec-tables|verify` 均可用。
- `test_access_modes.py` 另扫描全仓库文本，确认外部仓库名、作者名、上游目录字样零残留。

### B. 两种接入模式严格互斥

`tools/test_access_modes.py`（99 项）逐层覆盖：

- **校验层**：三种模式各自的字段归属；混合字段提交被拒（含空值 / `null` 的异模式键）；大小写与空白归一化；未知模式、非法 `device_id`、重复 ID、凭据字面量、非对象条目、host 缺失与 shell 元字符、IPv6、端口 `0/1/65535/65536/-1/非整数`、`rest_scheme` 非法值与大写归一化、`module_ids` 类型、字符串布尔与超长备注、`active_target` 回退、全禁用、畸形 registry 根。
- **显示层**：`public_target` 不向非 REST 目标输出 token 元数据，REST 目标只报 `token_present` 布尔且不泄漏值；`public_settings` 只输出当前模式的连接块；`GET /api/targets` 的 `fields`/`mode_fields`/`note` 与后端一致；前端 `data-tg-modes` 分组、`TG_MODE_KEYS` 映射、CSS `[hidden]` 规则、中英文文案、HTML 分组与 `TARGET_FIELDS` 一致。
- **提交层**：`PUT /api/targets` 对混合配置返回 400 `TARGETS_VALIDATION_FAILED` 且带校验明细、被拒后磁盘无文件；合法保存后落盘文件与响应都只含单模式字段；非对象 body、只读模式分别返回 400 / 409。
- **生效层**：`load_settings` 在加载期清空未选中模式端点（含 ini 同时存在 `[ssh]` 与 `[rest]` 的三种模式组合、环境变量覆盖）；`resolve_settings` 先禁用两端再启用其一；REST URL 在默认端口省略/非默认端口/base_path 尾斜杠等组合下构造正确；disabled / 未知模式 / `None` 目标回退到原配置；探针经桩适配器验证传给适配器的配置严格单模式（不发起真实 SSH/REST 连接）。
- **配置模板回归**：`config/targets.example.json` 通过严格校验且每条目标单模式，`config.ini.example` 的 `[ssh]` / `[rest]` 均默认注释（不同时生效）。

## 3. CMIS 5.1 / 5.2 手册验证

手册为第三方版权文档且体积较大，**不随仓库分发**。下载到工作区外的 `spec_downloads/`，用 `CMIS_LEGACY_SPEC_DIR` 指向后复跑：

```bash
python tools/test_legacy_specs.py                  # 找不到手册时明确 SKIP，不判失败
CMIS_LEGACY_SPEC_DIR=/path/to/pdfs python tools/test_legacy_specs.py
CMIS_LEGACY_REPORT=/path/to/report.json ...       # 可选：输出 JSON 报告
```

| 版本 | 来源 | 大小 | SHA-256（前 16） | 页数 | Section 8 表数 |
| --- | --- | ---: | --- | ---: | ---: |
| 5.1 | OIF 托管的 QSFP-DD MSA 第三方规范 `CMIS5p1_Third_Party_Spec.pdf` | 9,339,898 | `c24cc897fccfea99` | 336 | 158 |
| 5.2 | `OIF-CMIS-05.2.pdf` | 11,974,505 | `69f0cc11676d8cc0` | 344 | 164 |
| 5.3 | 仓库内规范化数据集 / PDF 索引（对照） | — | — | 408 | 238 |

规范依据：CMIS 5.1 前言声明「同一主版本号的后续修订与 5.1 保持向后规范兼容」。验证内容：

- 两版手册均可被项目零依赖 `tools/spec_pdf.py` 打开，前置页为可读文本层（非扫描件），首页/目录明确标识修订号。
- 目录覆盖 10/10 项核心规范概念：`memory map`、`command data block`、`lower memory`、`upper memory`、`two-wire`、`module state machine`、`versatile diagnostic`、`page 00h`、`page 9fh`、`byte 128`。
- **表号兼容性**：5.1 的 158 个、5.2 的 164 个 `Table 8-N` 编号**全部**落在 5.3 的 238 张表索引内（无游离编号），且 158 → 164 → 238 单调增长，与「5.3 在 5.2 基础上增补、5.4 中段插入导致表号整体 +10」的既有差异报告一致。
- 解析器鲁棒性：跨全文抽样 11–12 页均可读出文本，无异常。

## 4. 发现的问题

| # | 问题 | 处理 |
| --- | --- | --- |
| 1 | **真实缺陷**：CMIS 5.1 是线性化（Fast Web View）PDF，唯一的 `/Root` 位于文件开头的首段 trailer；`spec_pdf.py` 原先只在文件尾 8192 字节找 `/Root`，回退到对象 1 后只读出 1 页、0 文本，导致 5.1 无法验证 | 已修复：`_read_xref` 遍历 trailer 时记录 `/Root` 到 `self._root_ref`，`_read_page_tree` 优先使用；新增 `test_spec_pdf.py` 的 5 项**合成线性化 PDF** 回归（不依赖手册）。修复后 5.1=336 页、5.2=344、5.3=408、5.4=456；重新生成 5.3 索引逐字段比对，除 `generated_at` 外完全一致，无回归 |
| 2 | 测试设计：直接用 `api.probe_target` 测 ssh 目标会真实执行 `ssh` 命令并 8 秒超时，污染 CI | 改为桩适配器记录传入的 `Settings`，既避免外部依赖又更直接地断言「只有一种模式生效」 |
| 3 | 环境：OIF 5.1 镜像的 HEAD 请求经会话代理持续超时（curl 单连接约 20 KB/s） | 改用单字节 Range GET 探测长度 + 10 段并发下载 + 备用镜像；两本手册均成功下载 |
| 4 | 低风险观察：`mirror` 目标在后端仍允许保存通用字段 `host`/`port`（前端分组隐藏、运行时端点被清空，不会生效） | 未改动：属于通用字段设计，不影响互斥语义；如需更严格可后续收紧 |
| 5 | 既有局限：PDF 表格坐标重建为尽力而为，5.3 相对规范化数据集匹配率 91.5% | 保留：索引只作溯源线索，字段值以规范化数据集 / OIF 原文为准 |

## 5. 未覆盖项

- **真实硬件路径**：未连接测试 Switch、I2C 设备或目标设备 REST 服务；SSH/REST 适配器只做了配置解析与桩验证，未做端到端连通性与故障注入。
- **浏览器交互**：无自动化浏览器；前端互斥靠静态一致性断言（HTML 分组、JS 映射与键、CSS、i18n）与后端 API 契约覆盖，未做真实点击/模式切换的 DOM 行为测试。
- **5.1 / 5.2 字段级逐条目比对**：本轮只验证到目录术语、表号集合、页数与解析器层，**未**把 2442 行字段的 Page/Byte/Access 逐条与两版手册核对；跨版本结论限于表号与章节的向后兼容。
- **手册依赖外置**：5.1/5.2 PDF 不入库，未配置目录时 `test_legacy_specs.py` 会 SKIP 8+ 项版本检查；CI 需自备手册才能跑满 350 项。
- **PDF 格式边界**：xref stream、`/ObjStm` 对象流、加密 PDF、旋转文本、Type3 字体、扫描件仍不在 `spec_pdf.py` 支持范围（当前四版手册均为 classic xref）。
- **并发与负载**：未覆盖多请求并发下目标配置热切换、注册表原子写入竞争、大分页压力测试。
- **平台**：全部验证在 Windows 环境完成；Linux/macOS 的路径、权限与 `ssh` 命令行为未实机验证。
