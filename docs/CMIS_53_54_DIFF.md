# OIF CMIS 5.3 → 5.4 规范差异报告

> 由 `tools/diff_spec_versions.py` 自动生成于 `2026-11-09T16:01:58+00:00`。知识图谱待确认项 **P-02**（版本差异）的自动化依据。

## 1. 输入与结论

| 项 | CMIS 5.3 | CMIS 5.4 |
| --- | --- | --- |
| PDF | `knowledge/specs/OIF-CMIS-05.3.pdf` | `knowledge/specs/OIF-CMIS-05.4.pdf` |
| 页数 | 408 | 456 |
| SHA-256（前 12 位） | `631c76d0c829` | `cd57ebb1cfb8` |
| 索引来源 | cached index | parsed PDF |
| 表 / CDB 命令 | 238 / 48 | 258 / 51 |

**表目录（按标题序列对齐）**：5.4 真正新增 26 张、移除 6 张、实质改名 42 张、术语统一替换 5 张、仅标点/空格差异 1 张。**CDB 命令**：新增 5 条、移除 2 条、属性变化 42 条。

> ⚠️ **表号不能直接对比**：5.4 在 Section 8 中段插入了表格，185 张按标题成功配对的表中，有 **102 张的表号整体 +10**；页码位移 +0 ~ +44 页属排版效应。本报告用 `difflib.SequenceMatcher` 对齐标题序列后再比对，避免把重编号误报为改动。

## 2. 新增表（5.4 独有）

| 表号 | 标题 | PDF 页 | 字段行 |
| --- | --- | --- | --- |
| 8-23 | Format of Application Descriptor (Flat Memory Modules) | 183 | 0 |
| 8-57 | Host Lane Polarity Inversion Indication (Page 01h) | 206 | 2 |
| 8-58 | Supported Pages and Banks Advertisement (Page 01h) | 207 | 2 |
| 8-69 | Page 0Ch Overview | 218 | 0 |
| 8-70 | Supported Pages Map (Page 0Ch) | 218 | 1 |
| 8-71 | Generic FeatureAdvertisement Data Structure | 218 | 0 |
| 8-72 | Named Feature Advertisements (Page 0Ch) | 218 | 3 |
| 8-73 | Named Feature Details Advertisement (Page 0Ch) | 219 | 5 |
| 8-74 | Page 0Dh Overview | 220 | 0 |
| 8-75 | Firmware Load VersionDescriptor Data Structure | 220 | 0 |
| 8-76 | Firmware Management Registers (Page 0Dh) | 220 | 8 |
| 8-187 | Page 60h Overview | 313 | 0 |
| 8-188 | Host Lane Polarity Inversion Indication (Page 60h) | 313 | 3 |
| 8-189 | Reset Acquisition Counters (Page 60h) | 313 | 1 |
| 8-190 | Page 61h Overview | 315 | 0 |
| 8-191 | Acquisition Counters (Page 61h) | 316 | 4 |
| 8-192 | Page 62h Overview | 317 | 0 |
| 8-193 | Output Power Threshold Quad Data Structure | 317 | 0 |
| 8-194 | Output Power Thresholds (Page 62h) | 317 | 0 |
| 8-195 | Page 6Dh Overview | 318 | 0 |

_仅列出前 20 条，完整清单见 `data/spec_version_diff.json`。_

## 3. 移除表（仅 5.3）

| 表号 | 标题 | PDF 页 | 字段行 |
| --- | --- | --- | --- |
| 8-55 | Overview of CDB advertising combinations | 180 | 0 |
| 9-18 | CDB Firmware Download Commands Overview | 307 | 0 |
| 9-45 | CDB Command 0281h: Data Monitoring and Recording Advertisements | 339 | 0 |
| 9-49 | CDB Command 0380h: Loopbacks | 342 | 0 |
| 9-50 | CDB Diagnostics and Debug Commands Overview | 343 | 0 |
| 9-51 | Detailed Return Status Codes for Security Commands | 344 | 0 |


## 4. 表标题变化（实质，忽略大小写/标点/空格差异）

| 5.3 表号 | 5.4 表号 | 5.3 标题 | 5.4 标题 |
| --- | --- | --- | --- |
| 8-1 | 8-1 | List of CMIS Pages | List of CMIS 128-Byte Pages and Banks |
| 8-13 | 8-13 | CdbStatus fields (paged memory modules only) (Lower Memory) | CdbStatus Registers (paged memory modules only) (Lower Memory) |
| 8-14 | 8-14 | Bit definitions within CdbStatus fields | Fields of a CdbStatus register |
| 8-20 | 8-20 | Media Type Encodings | Media Type Encodings (Table Selection) |
| 8-22 | 8-22 | Format of Application Descriptor Bytes 1-4 | Format of Application Descriptor Bytes 1-4 (Paged Memory Modules) |
| 8-25 | 8-26 | Page Mapping Register Components (Lower Memory) | Dynamic Page Mapping Register (Lower Memory) |
| 8-37 | 8-38 | Far End Configurations for Homogeneous Far End Breakout (Page 00h) | Far End Configurations for Uniform Far End Breakout (Page 00h) |
| 8-46 | 8-47 | Supported Pages Advertising (Page 01h) | Supported Pages and Banks Advertising (Page 01h) |
| 8-60 | 8-62 | Miscellaneous Advertisements (Page 01h) | Miscellaneous Feature Advertisements (Page 01h) |
| 8-62 | 8-64 | Module-Level Monitor Thresholds (Page 02h) | Module-Level Supervision Thresholds (Page 02h) |
| 8-71 | 8-81 | Data Path Configuration per Lane (DPConfigLane<i>) | Staged Data Path Configuration per Lane (DPConfigLane<i>) |
| 8-92 | 8-102 | Data Path Configuration per Lane (DPConfigLane<i> Field) | Provisioned Data Path Configuration per Lane (DPConfigLane<i> Field) |
| 8-168 | 8-178 | VDM Configuration (Page 20h-23h) | VDM Instance Descriptors (Page 20h-23h) |
| 8-171 | 8-181 | VDM Real-Time Values (Page 24h-27h) | VDM Real-Time or Statistics Values (Page 24h-27h) |
| 8-172 | 8-182 | VDM Alarm/Warning Thresholds (Page 28h-2Bh) | VDM Supervision Thresholds (Page 28h-2Bh) |
| 8-174 | 8-184 | VDM Alarm and Warning Configuration (Page 2Ch) | VDM Alarm/Warning Flags (Page 2Ch) |
| 8-175 | 8-185 | VDM ThresholdSet0 to 15 Alarm and Warning Configuration (Page 2Dh) | VDM Supervision Masks (Page 2Dh) |
| 8-176 | 8-186 | VDM Advertisement and Control Registers Summary (Page 2Fh) | VDM Advertisement and Control Registers (Page 2Fh) |
| 9-7 | 9-7 | CDB Feature and Capabilities Commands Overview | CDB Command 0005h: Get Module Time |
| 9-8 | 9-8 | CDB Command 0040h: Module Features | CDB Command 0006h: Set Module Time |

_仅列出前 20 条，共 42 条。_

## 4b. 术语统一替换（5.3 → 5.4 全局措辞变化）

> 5.4 以「not for static memory modules」替换 5.3 的 「paged memory modules only」，属于全局措辞调整，单列以免淹没实质改名。

| 5.3 表号 | 5.4 表号 | 5.3 标题 | 5.4 标题 |
| --- | --- | --- | --- |
| 8-9 | 8-9 | Module Flags (paged memory modules only) (Lower Memory) | Module Flags (not for static memory modules) (Lower Memory) |
| 8-10 | 8-10 | Module-Level Monitor Values (paged memory modules only) (Lower Memory) | Module-Level Monitor Values (not for static memory modules) (Lower Memory) |
| 8-11 | 8-11 | Module Global Controls (paged memory modules only) (Lower Memory) | Module Global Controls (not for static memory modules ) (Lower Memory) |
| 8-12 | 8-12 | Module Level Masks (paged memory modules only) (Lower Memory) | Module Level Masks (not for static memory modules) (Lower Memory) |
| 8-16 | 8-16 | Fault Information (paged memory modules only) (Lower Memory) | Fault Information (not for static memory modules) (Lower Memory) |


## 4c. 重编号与页码位移

| 指标 | 值 |
| --- | --- |
| 对齐方法 | difflib.SequenceMatcher on normalized table captions |
| 按标题配对的表 | 185 |
| 主流表号位移 | +10 (102 张表) |
| 页码位移范围 | +0 ~ +44 页 |
| 最常见页码位移 | +30 页 (44 张表) |


## 5. CDB 命令变化

**新增命令**

| CMD ID | 标题 | 条款 | 明细表 | PDF 页 |
| --- | --- | --- | --- | --- |
| 0005 | Get Module Time | 9.3.5 | 9-7 | 332 |
| 0006 | Set Module Time | 9.3.6 | 9-8 | 333 |
| 010B | Check Firmware Activation Options | 9.6.13 | 9-31 | 361 |
| 010C | Store Firmware Load Tag | 9.6.14 | 9-32 | 362 |
| 010D | Retrieve Firmware Load Tag | 9.6.15 | 9-33 | 363 |

**移除命令**

| CMD ID | 标题 | 条款 | 明细表 | PDF 页 |
| --- | --- | --- | --- | --- |
| 0281 | Data Monitoring and Recording Advertisements | 9.9.2 | 9-45 | 339 |
| 0380 | Loopbacks | 9.11.1 | 9-49 | 342 |

**属性变化**

| CMD ID | 变化字段 | 5.3 | 5.4 |
| --- | --- | --- | --- |
| 0040 | title | Module Features | Query Module Features |
| 0040 | detail_table | 9-8 | 9-10 |
| 0041 | title | Firmware Management Features | Query Firmware Management Features |
| 0041 | detail_table | 9-9 | 9-11 |
| 0042 | title | Performance Monitoring Features | Query Monitoring Features |
| 0042 | detail_table | 9-10 | 9-12 |
| 0043 | title | BERT and Diagnostics Features | Query Diagnostics Features |
| 0043 | detail_table | 9-11 | 9-13 |
| 0044 | title | Security Features and Capabilities | Query Security Features |
| 0044 | detail_table | 9-12 | 9-14 |
| 0045 | title | Externally Defined Features | Query Supplement Support |
| 0045 | detail_table | 9-13 | 9-15 |
| 0050 | spec_section | 9.4.7 | 9.5.1 |
| 0050 | detail_table | 9-14 | 9-16 |
| 0051 | spec_section | 9.4.8 | 9.5.2 |
| 0051 | detail_table | 9-15 | 9-17 |
| 0100 | spec_section | 9.7.1 | 9.6.2 |
| 0100 | detail_table | 9-19 | 9-20 |
| 0101 | title | Start Firmware Download | Start Firmware Transfer |
| 0101 | spec_section | 9.7.2 | 9.6.3 |
| 0101 | detail_table | 9-20 | 9-21 |
| 0102 | title | Abort Firmware Download | Abort Firmware Transfer |
| 0102 | spec_section | 9.7.3 | 9.6.4 |
| 0102 | detail_table | 9-21 | 9-22 |
| 0103 | spec_section | 9.7.4 | 9.6.5 |
| 0103 | detail_table | 9-22 | 9-23 |
| 0104 | spec_section | 9.7.5 | 9.6.6 |
| 0104 | detail_table | 9-23 | 9-24 |
| 0105 | spec_section | 9.7.6 | 9.6.7 |
| 0105 | detail_table | 9-24 | 9-25 |
| 0106 | spec_section | 9.7.7 | 9.6.8 |
| 0106 | detail_table | 9-25 | 9-26 |
| 0107 | title | Complete Firmware Download | Complete Firmware Transfer |
| 0107 | spec_section | 9.7.8 | 9.6.9 |
| 0107 | detail_table | 9-26 | 9-27 |
| 0108 | title | Copy Firmware Image | Copy Firmware Load |
| 0108 | spec_section | 9.7.9 | 9.6.10 |
| 0108 | detail_table | 9-27 | 9-28 |
| 0109 | title | Run Firmware Image | Run Firmware Load |
| 0109 | spec_section | 9.7.10 | 9.6.11 |
| 0109 | detail_table | 9-28 | 9-29 |
| 010A | title | Commit Image | Commit Firmware Load |
| 010A | spec_section | 9.7.11 | 9.6.12 |
| 010A | detail_table | 9-29 | 9-30 |
| 0200 | title | Control PM | Control PM Statistics |
| 0200 | spec_section | 9.8.1 | 9.7.1 |
| 0200 | detail_table | 9-32 | 9-36 |

_仅列出前 20 条。_

> `detail_table` 的变化大多来自上述表号重编号（5.4 中普遍 +2 / +10），不代表命令语义改变；`title` 与 `spec_section` 的变化才需要人工复核。

## 6. 字段级差异（指示性，需人工复核）

按 `(page, byte, name)` 对齐：5.3 抽取 719 行、5.4 抽取 745 行；新增 82、移除 56、属性变化 26。

> ⚠️ 字段行来自坐标重建，覆盖率不完整（5.3 相对规范化数据集约 91.5%），因此这些差异**只作为复核线索**，不能据此断言规范增删。逐条结论必须回到 OIF 原文；字段值以 `data/cmis53_reference.json`（本项目规范化数据集）为准。

| 页 | Byte | 字段 | 表号 | access | value_type |
| --- | --- | --- | --- | --- | --- |
| 01h | 171 | DefaultInputPolarityTx8 | 8-57 | RO | bool |
| 01h | 172 | DefaultOutputPolarityRx8 | 8-57 | RO | bool |
| 01h | 173 | PageChSupported | 8-58 | — | bool |
| 01h | 174 | Page60hSupported | 8-58 | RO | bool |
| 01h | 175 | NADBanksSupported | 8-59 | — | u8 |
| 04h | 166 | GridLowChannel300GHz | 8-68 | RO | s16 |
| 04h | 168 | GridHighChannel300GHz | 8-68 | RO | s16 |
| 04h | 170 | Reserved | 8-68 | RO | — |
| 0Ch | 128 | MapOfSupportedPages | 8-70 | RO | u8 |
| 0Ch | 161 | Reserved | 8-72 | — | — |

## 7. 复现与边界

```bash
python tools/parse_spec_pdf.py                 # 重建 5.3 索引（可选）
python tools/diff_spec_versions.py            # 生成本报告 + JSON 差异
python tools/test_spec_diff.py                # 报告回归测试
```

- 纯 Python 标准库，无 `pdfplumber` / `openpyxl`，无网络访问；5.3 索引仅在 PDF SHA-256 匹配时复用，否则自动重新解析。
- 只持久化事实标识（表号、短标题、页码、字段名、地址、access），**不写入 OIF 描述正文**。版权与许可边界见 `NOTICE` 第 8 节和 `knowledge/specs/README.md`。
- 页码为 PDF 物理页；5.4 表号与 5.3 相同不代表内容相同，请结合标题变化判断。
