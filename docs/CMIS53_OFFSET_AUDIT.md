# CMIS 5.3 Offset 核对报告 — Low Page / Page 00h

> 核对日期：2026-11-11 ｜ 结论：**15 + 7 + 24 = 46 个展示/定义条目**中，数值正确的 27 项、错误或缺失 offset 的 17 项、版本差异保留 2 项。
> 约束：仅按规范修正 offset 并统一展示格式；字段含义、顺序、说明文字、默认值、访问属性、置信度、规范引用均保持不变。

## 1. 核对基准与统一规则

| 基准 | 内容 | 用途 |
|---|---|---|
| `data/cmis53_dataset.json` | 从 OIF-CMIS-05.3 PDF 表格解析的 2442 个字段，含 `page` / `byte` / `byte_length` / `ref_table` | 逐字节 offset 的唯一数值基准 |
| `data/spec_pdf_index.json` | 238 张规范表目录；Table 8-4 = Lower Memory Overview，Table 8-26 = Page 00h Overview | 分区边界、区块名与表号交叉校验 |
| `data/cmis53_reference.json` | 只读参考层（同一数据集派生） | 参考层一致性复核 |

关键规范锚点：

| 范围 | CMIS 5.3 依据 | 字节 |
|---|---|---|
| Lower | Table 8-5 / 8-6 | 0–3 ID、Revision、MemoryModel、ModuleState |
| Lower | Table 8-8 / 8-9 / 8-10 | 4–7 标志汇总、8–13 模块级标志、14–25 监测量 |
| Lower | Table 8-11 / 8-12 / 8-13 / 8-15 | 26–30 全局控制、31–36 掩码、37–38 CDB 状态、39–40 活动固件版本 |
| Lower | Table 8-16 / 8-17 / 8-18 | 41 故障信息、42–45 杂项状态、46–55 保留、56–63 扩展模块信息 |
| Lower | Table 8-4 / 8-21 / 8-23 | 64–84 保留、85 MediaType、86–117 八个应用描述符（85–117 统称 Applications Advertising） |
| Lower | Table 8-24 / 8-25 | 118–121 密码修改区、122–125 密码入口区、126 BankSelect、127 PageSelect |
| Upper 00h | Table 8-26 / 8-27 / 8-28 | 128 IdentifierCopy、129–189 厂商信息、190–199 CLEI、222 PageChecksum（CC_BASE）、223–254 保留 |
| Upper 01h | Table 8-43 | 128–129 非活动固件 Major/Minor |

**统一格式规则**（与项目既有 high page 数据 `01h:128 (0x80)`、`9Fh:130 (0x82)` 完全同构）：

1. 页前缀：`Lower` = 常驻低页 0–127；Upper 页用 `00h` / `01h` / `9Fh` 等，以 `:` 连接偏移。
2. 偏移用十进制字节，括号内为大写两位十六进制；连续范围用 `-`：`Lower:8-13 (0x08-0x0D)`；单字节 `00h:222 (0xDE)`；位级 `Lower:26 (0x1A) bit4`。
3. 字段标签沿用主字段表的 `名称 @ 页:偏移` 分隔风格，英文标签与中文标签只差名称部分。
4. 英文名称统一 Title Case，缩写全大写：`ID` / `OUI` / `PN` / `SN` / `CDB` / `VDM` / `CMIS` / `CC_BASE` / `CC_EXT` / `SFF-8024`；去掉冗余 `Byte` 后缀；中文名称不变。
5. 展示层：偏移用等宽字体、访问属性用徽标、字段名两行（中文主标题 + 英文副标题）、表格统一 `table-sm table-vcenter`、列顺序统一为 字段 / 页·偏移 / 字节数 / 访问属性 / 说明。

## 2. 逐字段核对结论

图例：✅ 数值与 5.3 一致 ｜ ❌ 数值或页归属错误，已修正 ｜ ⚠️ 版本/语义差异，按约束保留含义与范围 ｜ ⟳ 数值正确、仅格式统一。

### 2.1 `cmis_service/cmis_spec.py` → `LOWER_MEMORY_MAP`（15 项）

| # | 字段（中文 / 规范英文） | 原偏移 | CMIS 5.3 基准 | 结论 | 统一后偏移 |
|---|---|---|---|---|---|
| 1 | 标识与状态区 / ID and Status Area | `0-3` | Lower:0–3，Table 8-5/8-6 | ✅ | `Lower:0-3 (0x00-0x03)` |
| 2 | 通道标志汇总 / Lane Flag Summary | `4-7` | Lower:4–7，Table 8-8 | ✅ | `Lower:4-7 (0x04-0x07)` |
| 3 | 模块级标志 / Module-Level Flags | `8-13` | Lower:8–13，Table 8-9 | ✅ | `Lower:8-13 (0x08-0x0D)` |
| 4 | 模块级监测量 / Module-Level Monitors | `14-25` | Lower:14–25，Table 8-10 | ✅ | `Lower:14-25 (0x0E-0x19)` |
| 5 | 模块全局控制 / Module Global Controls | `26-30` | Lower:26–30，Table 8-11 | ✅ | `Lower:26-30 (0x1A-0x1E)` |
| 6 | 模块级标志掩码 / Module-Level Flag Masks | `31-36` | Lower:31–36，Table 8-12 | ✅ | `Lower:31-36 (0x1F-0x24)` |
| 7 | CDB 状态区 / CDB Status Area | `37-38` | Lower:37–38，Table 8-13 | ✅ | `Lower:37-38 (0x25-0x26)` |
| 8 | 模块固件版本 / Active Firmware Version | `39-40` | Lower:39–40，Table 8-15 | ✅ ＋名称统一（`Module Firmware Version`→`Active Firmware Version`） | `Lower:39-40 (0x27-0x28)` |
| 9 | 保留区 / Reserved | `41-63` | 41–63 为故障信息/杂项状态/保留/扩展信息混合区，Table 8-16～8-18 | ⚠️ 范围正确，语义为粗略合并；按要求不改含义 | `Lower:41-63 (0x29-0x3F)` |
| 10 | 厂商自定义区 / Custom Area | `64-82` | 5.3 中 64–84 为 Reserved（Table 8-4） | ⚠️ datasheet 遗留，按要求不改含义与范围 | `Lower:64-82 (0x40-0x52)` |
| 11 | 非活动固件版本 / Inactive Firmware Version | `83-84` | **Upper 01h:128–129**，Table 8-43；Lower 83–84 在 5.3 为保留 | ❌ 已修正 | `01h:128-129 (0x80-0x81)` |
| 12 | 应用通告 / Application Advertising | `85-117` | Lower:85–117，Table 8-4 / 8-21 / 8-23 | ✅ 范围正确（说明文字仍称 legacy，按要求保留） | `Lower:85-117 (0x55-0x75)` |
| 13 | 密码输入与修改 / Password Entry and Change | `118-125` | 118–121 Change + 122–125 Entry，Table 8-24 | ✅ | `Lower:118-125 (0x76-0x7D)` |
| 14 | Bank 选择字节 / Bank Select | `126` | Lower:126 BankSelect，Table 8-25 | ✅ ＋名称统一（去掉 `Byte`） | `Lower:126 (0x7E)` |
| 15 | Page 选择字节 / Page Select | `127` | Lower:127 PageSelect，Table 8-25 | ✅ ＋名称统一（去掉 `Byte`） | `Lower:127 (0x7F)` |

### 2.2 `cmis_service/cmis_spec.py` → `UPPER_PAGE_00H`（7 项）

| # | 字段 | 长度 | 原偏移 | CMIS 5.3 基准 | 结论 | 统一后偏移 |
|---|---|---|---|---|---|---|
| 1 | Vendor Name | 16 | `pending` | 00h:129–144，Table 8-28 | ❌ | `00h:129-144 (0x81-0x90)` |
| 2 | Vendor OUI | 3 | `pending` | 00h:145–147，Table 8-28 | ❌ | `00h:145-147 (0x91-0x93)` |
| 3 | Vendor Part Number | 16 | `pending` | 00h:148–163，Table 8-28 | ❌ | `00h:148-163 (0x94-0xA3)` |
| 4 | Vendor Revision | 2 | `pending` | 00h:164–165，Table 8-28 | ❌ | `00h:164-165 (0xA4-0xA5)` |
| 5 | Vendor Serial Number | 16 | `pending` | 00h:166–181，Table 8-28 | ❌ | `00h:166-181 (0xA6-0xB5)` |
| 6 | Date Code | 8 | `pending` | 00h:182–189，Table 8-28 | ❌ | `00h:182-189 (0xB6-0xBD)` |
| 7 | CC_BASE / CC_EXT | 2 | `pending` | 00h:222 = PageChecksum（CC_BASE），Table 8-26；00h:223 在 5.3 为保留区起点 | ❌（CC_EXT 说明见 §5） | `00h:222-223 (0xDE-0xDF)` |

### 2.3 `tools/cmis_catalog.py` → Low / Page 00h 字段目录（24 项）

| # | Field Key | 原 页:偏移 | 基准 | 结论 | 统一后 页:偏移 |
|---|---|---|---|---|---|
| 1 | `ModuleIdentifier` | `Lower:00h` | Lower:0 | ⟳ | `Lower:0 (0x00)` |
| 2 | `CmisRevision` | `Lower:01h` | Lower:1 | ⟳ | `Lower:1 (0x01)` |
| 3 | `ModuleState` | `Lower:03h` | Lower:3 | ⟳ | `Lower:3 (0x03)` |
| 4 | `ModuleFlags` | `Lower:08-13` | Lower:8–13 | ⟳ | `Lower:8-13 (0x08-0x0D)` |
| 5 | `LaneFlagSummary` | `Lower:04-07` | Lower:4–7 | ⟳ | `Lower:4-7 (0x04-0x07)` |
| 6 | `VendorName` | `00h:pending` | 00h:129–144 | ❌ | `00h:129-144 (0x81-0x90)` |
| 7 | `VendorOUI` | `00h:pending` | 00h:145–147 | ❌ | `00h:145-147 (0x91-0x93)` |
| 8 | `VendorPartNumber` | `00h:pending` | 00h:148–163 | ❌ | `00h:148-163 (0x94-0xA3)` |
| 9 | `VendorSerialNumber` | `00h:pending` | 00h:166–181 | ❌ | `00h:166-181 (0xA6-0xB5)` |
| 10 | `DateCode` | `00h:pending` | 00h:182–189 | ❌ | `00h:182-189 (0xB6-0xBD)` |
| 11 | `CcBase` | `00h:pending` | 00h:222 | ❌ | `00h:222 (0xDE)` |
| 12 | `CcExt` | `00h:pending` | 00h:223（4.x 兼容位置） | ❌（见 §5） | `00h:223 (0xDF)` |
| 13 | `ModuleTypeEncoding` | `00h:85 (0x55)` | Lower:85 MediaType，Table 8-21 | ❌ 页归属错误 | `Lower:85 (0x55)` |
| 14 | `ModuleGlobalControls` | `Lower:26-30` | Lower:26–30 | ⟳ | `Lower:26-30 (0x1A-0x1E)` |
| 15 | `ModuleLevelFlagMasks` | `Lower:31-36` | Lower:31–36 | ⟳ | `Lower:31-36 (0x1F-0x24)` |
| 16 | `ModuleFirmwareVersion` | `Lower:39-40` | Lower:39–40 | ⟳ | `Lower:39-40 (0x27-0x28)` |
| 17 | `InactiveFirmwareVersion` | `Lower:83-84` | **01h:128–129**，Table 8-43 | ❌ 页与偏移均错 | `01h:128-129 (0x80-0x81)` |
| 18 | `CdbStatusLower` | `Lower:37-38 (0x25-0x26)` | Lower:37–38 | ✅ 已合规，未改动 | 同原值 |
| 19 | `ApplicationAdvertisingLegacy` | `Lower:85-117` | Lower:85–117 | ⟳（范围正确） | `Lower:85-117 (0x55-0x75)` |
| 20 | `BankSelect` | `Lower:126 (0x7E)` | Lower:126 | ✅ 已合规，未改动 | 同原值 |
| 21 | `PageSelect` | `Lower:127 (0x7F)` | Lower:127 | ✅ 已合规，未改动 | 同原值 |
| 22 | `ModuleLevelMonitors` | `Lower:14-25` | Lower:14–25 | ⟳ | `Lower:14-25 (0x0E-0x19)` |
| 23 | `CdbPasswordEntry` | `Lower:122 (0x7A)` | Lower:122 PasswordEntryArea | ✅ 已合规，未改动 | 同原值 |
| 24 | `LPMode` | `Lower:26 bit4` | Lower:26 bit4（mask 0x10） | ⟳ | `Lower:26 (0x1A) bit4` |

## 3. 修正项清单

| 类别 | 数量 | 明细 |
|---|---|---|
| 页归属 / 位置错误 | 3 | `InactiveFirmwareVersion`（Lower:83-84 → 01h:128-129，两处：`LOWER_MEMORY_MAP` + 字段目录）；`ModuleTypeEncoding`（00h → Lower:85） |
| `pending` 未核对 | 14 | 字段目录 7 项（VendorName / VendorOUI / VendorPartNumber / VendorSerialNumber / DateCode / CcBase / CcExt）＋ `UPPER_PAGE_00H` 7 项 |
| offset 表示方式统一（数值不变） | 26 | `LOWER_MEMORY_MAP` 15 行 ＋ 字段目录 11 项 |
| 字段名大小写/缩写统一 | 3 | `Bank Select Byte`→`Bank Select`、`Page Select Byte`→`Page Select`、`Module Firmware Version`→`Active Firmware Version` |
| 展示层统一 | 3 | `LOWER_MEMORY_MAP` 表头/偏移/双行字段名、`UPPER_PAGE_00H` 表列顺序与徽标、分区标题 `Lower 00h-7Fh` → `Lower / Upper 00h-01h` |
| 生成产物同步 | 4 | `data/seed.json`（512 条 label）、`data/knowledge_graph.json`、`data/i18n_data_en.json`（20 条标签映射替换）、`static/js/data_en.js` |

**修正后零 `pending`**：Low Page / Page 00h 范围内所有字段都有可解析的规范偏移；API 的寄存器写操作不再因这些字段触发 `REGISTER_OFFSET_PENDING`。

## 4. 统一后的字段定义与展示结果

### 4.1 统一后的 Low Page 字段定义（等宽对齐）

```
Field Key                       Page   Offset                          Len  Access  Canonical Name
------------------------------ ------ -------------------------------- ---- ------- --------------------------------
ModuleIdentifier                Lower  0 (0x00)                          1    RO      Module Identifier
CmisRevision                    Lower  1 (0x01)                          1    RO      CMIS Revision
ModuleState                     Lower  3 (0x03)                          1    RO      Module State
LaneFlagSummary                 Lower  4-7 (0x04-0x07)                   4    RO/CoR  Lane Flag Summary
ModuleFlags                     Lower  8-13 (0x08-0x0D)                  6    RO/CoR  Module-Level Flags
ModuleLevelMonitors             Lower  14-25 (0x0E-0x19)                12   RO      Module-Level Monitors
ModuleGlobalControls            Lower  26-30 (0x1A-0x1E)                 5    RW      Module Global Controls
LPMode                          Lower  26 (0x1A) bit4                    1    RW      Low Power Request
ModuleLevelFlagMasks            Lower  31-36 (0x1F-0x24)                 6    RW      Module-Level Flag Masks
CdbStatusLower                  Lower  37-38 (0x25-0x26)                 2    RO      CDB Status Area
ModuleFirmwareVersion           Lower  39-40 (0x27-0x28)                 2    RO      Active Firmware Version
ModuleTypeEncoding              Lower  85 (0x55)                          1    RO      Module Type Encoding
ApplicationAdvertisingLegacy    Lower  85-117 (0x55-0x75)               33   RO      Application Advertising (legacy)
CdbPasswordEntry                Lower  122 (0x7A)                         4    WO      CDB Password Entry
BankSelect                      Lower  126 (0x7E)                         1    RW      Bank Select
PageSelect                      Lower  127 (0x7F)                         1    RW      Page Select
```

### 4.2 统一后的 Page 00h 字段定义

```
Field Key                       Page   Offset                          Len  Access  Canonical Name
------------------------------ ------ -------------------------------- ---- ------- --------------------------------
VendorName                      00h    129-144 (0x81-0x90)              16   RO      Vendor Name
VendorOUI                       00h    145-147 (0x91-0x93)               3   RO      Vendor OUI
VendorPartNumber                00h    148-163 (0x94-0xA3)              16   RO      Vendor Part Number
VendorRevision                  00h    164-165 (0xA4-0xA5)               2   RO      Vendor Revision
VendorSerialNumber              00h    166-181 (0xA6-0xB5)              16   RO      Vendor Serial Number
DateCode                        00h    182-189 (0xB6-0xBD)               8   RO      Date Code
CcBase                          00h    222 (0xDE)                         1   RO      CC_BASE Checksum
CcExt                           00h    223 (0xDF)                         1   RO      CC_EXT Checksum
InactiveFirmwareVersion         01h    128-129 (0x80-0x81)               2   RO      Inactive Firmware Version
```

### 4.3 前端展示结果

- 「寄存器布局」表：`Lower:0-3 (0x00-0x03)` 等与 high page 的 `01h:128 (0x80)`、`9Fh:130 (0x82)` 同构；字段名两行（中文 + 英文副标题）、偏移等宽、访问属性徽标、说明 muted，列顺序与 CDB 帧表一致。
- 「Upper Page 00h 静态识别」表：从「字段 / 字节数 / 页·偏移」改为「字段 / 页·偏移 / 字节数 / 访问属性」，与主字段表前四列同序，补齐访问属性徽标与 `table-vcenter`。
- 主字段表（截图 2）原来的 `00h:pending`、`Lower:01h`、`Lower:08-13` 等混排已全部统一，例如 `CC_BASE 校验和 @ 00h:222 (0xDE)`、`CMIS 版本 @ Lower:1 (0x01)`、`模块级标志汇总 @ Lower:8-13 (0x08-0x0D)`；英文模式对应 `CC_BASE Checksum @ 00h:222 (0xDE)` 等，中文残留 0。

## 5. 说明与未修正项

| 项 | 说明 |
|---|---|
| `CC_EXT` | CMIS 5.3 的 Page 00h 仅定义 00h:222 PageChecksum（覆盖 128–221）；00h:223–254 为 Reserved。填充的 `00h:223 (0xDF)` 是 CMIS 4.x 的 CC_EXT 兼容位置，**不是 5.3 定义**；字段含义按约束保留，报告中显式标注。 |
| 41–63 / 64–82 | 5.3 中 41–63 为多类字段混合区、64–84 为 Reserved；项目沿用 datasheet 的「保留区 / 厂商自定义区」命名与范围。数值范围无误，按约束不改含义，故仅统一表示格式。 |
| 说明文字仍含「待核对」 | `cmis_catalog.py` 中 VendorName 等的 description、`LOWER_MEMORY_MAP` 中 Application Advertising 的 note 仍写「偏移待核对 / legacy layout」。按「其他数据内容不变」的约束保留原文，未同步改写；此处记录为已发现的文案滞后项。 |
| P-16 待确认项 | 知识图谱中「Low Page 应用通告位置版本差异」仍保留；本次核对确认 5.3 的 Lower:85–117 就是 Applications Advertising（85 MediaType + 86–117 描述符），但按约束未改动待确认条目。 |
| 未覆盖 | 未逐位核对 41–63 内部位定义；未覆盖 Page 02h 及以上页；`data_en.js` 只覆盖项目现有中文数据，运维自填内容不翻译。 |

## 6. 验证

- 新增 `tools/test_cmis53_offsets.py`：以 `data/cmis53_dataset.json` 为基准校验 46 个条目的页/偏移、统一格式正则、零 `pending`、缩写规则、seed / i18n 映射一致性与前端渲染统一。
- 全量回归：smoke 87、reference 20、spec_pdf 38、spec_diff 22、seed_verification 28、access_modes 99、dataset_build 37、legacy_specs 19、i18n 19、cmis53_offsets 88，**合计 457 项全绿**（详见 `docs/TEST_REPORT.md`）。
- `py_compile`、3 个 JS 的 `node --check`、`build_i18n_data.py --check`（648 条 / 0 未覆盖）、`verify_seed_fields.py --strict` 均通过。
- 正向状态迁移：`seed_field_verification.json` 的 `verified` 4 → 7、`address_resolved` 3 → 0、`pending_offsets` 37 → 30、`mismatches` 保持 0；`test_seed_verification.py` 的 P-01 断言已按「verified 或 address_resolved」的新语义更新。
