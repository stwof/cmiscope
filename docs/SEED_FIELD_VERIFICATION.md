# 演示字段与 CMIS 5.3 权威表对照报告

> 由 `tools/verify_seed_fields.py` 自动生成于 `2026-11-10T12:55:20+00:00`。知识图谱待确认项 **P-01**（寄存器精确地址）的复核清单。

## 1. 结论

`data/seed.json` 的 **64** 个演示字段与 **2442** 行权威参考表对照结果：

| 状态 | 数量 | 含义 |
| --- | --- | --- |
| verified | 4 | 名称精确匹配且页/地址一致 |
| address_resolved | 3 | 名称精确匹配、演示 offset 为 pending，可参考表回填 |
| mismatch | 0 | 名称精确匹配但页/地址不一致，需修正 |
| candidate | 47 | 别名或地址推断，需人工对照 OIF 原文 |
| unresolved | 10 | 未匹配，多为演示合成字段 |


其中 27 个字段已有可解析地址、37 个仍为 `pending`/占位；**3 个精确名称字段可直接给出权威 byte**，另有 **10 个高置信度别名候选**可供 P-01 复核。候选置信度分布：{'high': 13, 'low': 12, 'medium': 22}（`low` 一律视为未解决）。

> ⚠️ 本报告只做只读对照，**不修改 `seed.json`**，也不参与任何硬件写入。字段名与地址属 OIF 版权事实标识，许可边界见 `NOTICE` 第 5–8 节；最终以 OIF 规范原文为准。

## 2. 可直接回填的地址（P-01 优先项）

| 演示字段 | demo 页 | demo offset | 参考页 | 参考 byte | 权威 key_id | 表号 | PDF 页 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| VendorName | 00h | pending | 00h | 129 | VendorName | 8-28 | 161 |
| VendorOUI | 00h | pending | 00h | 145 | VendorOUI | 8-28 | 161 |
| DateCode | 00h | pending | 00h | 182 | DateCode | 8-28 | 161 |

## 3. 已验证字段

| 演示字段 | demo 页 | demo offset | 参考页 | 参考 byte | 权威 key_id | 表号 | PDF 页 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| CmisRevision | Lower | 01h | Lwr | 1 | CmisRevision | 8-5 | 142 |
| ModuleState | Lower | 03h | Lwr | 3 | ModuleState | 8-6 | 144 |
| BankSelect | Lower | 126 (0x7E) | Lwr | 126 | BankSelect | 8-25 | 159 |
| PageSelect | Lower | 127 (0x7F) | Lwr | 127 | PageSelect | 8-25 | 159 |

## 4. 地址 / 页不一致（需修正）

_（无）_


## 5. 高置信度可回填候选（P-01 次优先项）

> 名称高度相似且同页，但演示 offset 为 `pending`；仍需对照 OIF 原文确认后使用。

| 演示字段 | demo 页 | demo offset | 参考页 | 参考 byte | 权威 key_id | 表号 | PDF 页 | 置信度 | 相似度 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| TempHighAlarmThreshold | 02h | pending | 02h | 128 | TempMonHighAlarmThreshold | 8-62 | 185 | high | 0.936 |
| TempHighWarningThreshold | 02h | pending | 02h | 132 | TempMonHighWarningThreshold | 8-62 | 185 | high | 0.941 |
| TempLowWarningThreshold | 02h | pending | 02h | 134 | TempMonLowWarningThreshold | 8-62 | 185 | high | 0.939 |
| VccHighAlarmThreshold | 02h | pending | 02h | 136 | VccMonHighAlarmThreshold | 8-62 | 185 | high | 0.933 |
| AppSelLane1 | 10h | pending | 10h | 145 | AppSelCodeLane1.10h.145 | 8-72 | 198 | high | 0.846 |
| AppSelLane2 | 10h | pending | 10h | 146 | AppSelCodeLane2.10h.146 | 8-72 | 198 | high | 0.846 |
| AppSelLane3 | 10h | pending | 10h | 147 | AppSelCodeLane3.10h.147 | 8-72 | 198 | high | 0.846 |
| AppSelLane4 | 10h | pending | 10h | 148 | AppSelCodeLane4.10h.148 | 8-72 | 198 | high | 0.846 |
| CdrEnableTx | 10h | pending | 10h | 160 | CDREnableTx8.10h.160 | 8-73 | 199 | high | 0.957 |
| CdrEnableRx | 10h | pending | 10h | 161 | CDREnableRx8.161 | 8-74 | 200 | high | 0.957 |

## 6. 别名 / 地址推断候选（需人工确认）

> `low` 置信度多为「地址碰巧相同、名称无关」，不要当作字段别名。

| 演示字段 | demo 页 | demo offset | 参考页 | 参考 byte | 权威 key_id | 表号 | PDF 页 | 置信度 | 相似度 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| ModuleIdentifier | Lower | 00h | Lwr | 0 | SFF8024Identifier.Lwr | 8-5 | 142 | medium | 0.606 |
| ModuleFlags | Lower | 08-13 | Lwr | 8 | ModuleStateChangedFlag | 8-9 | 146 | medium | 0.606 |
| LaneFlagSummary | Lower | 04-07 | Lwr | 4 | FlagsSummaryBank0Page2Ch | 8-8 | 145 | low | 0.564 |
| VendorPartNumber | 00h | pending | 00h | 129 | VendorName | 8-28 | 161 | medium | 0.692 |
| VendorSerialNumber | 00h | pending | 00h | 129 | VendorName | 8-28 | 161 | low | 0.5 |
| ModuleTypeEncoding | 00h | 85 (0x55) | 01h | 147 | ModuleTempMin | 8-49 | 173 | medium | 0.645 |
| HostInterfaceId | 01h | 128 (0x80) | 01h | 128 | ModuleInactiveFirmwareMajorRevision | 8-43 | 169 | low | 0.16 |
| MediaInterfaceId | 01h | 129 (0x81) | 01h | 129 | ModuleInactiveFirmwareMinorRevision | 8-43 | 169 | low | 0.314 |
| HostMediaLaneCount | 01h | 130 (0x82) | 01h | 130 | ModuleHardwareMajorRevision | 8-43 | 169 | low | 0.222 |
| HostLaneAssignmentOptions | 01h | 131 (0x83) | 01h | 131 | ModuleHardwareMinorRevision | 8-43 | 169 | low | 0.231 |
| ModuleGlobalControls | Lower | 26-30 | Lwr | 26 | SquelchMethodSelect | 8-11 | 148 | low | 0.359 |
| ModuleLevelFlagMasks | Lower | 31-36 | Lwr | 31 | ModuleStateChangedMask | 8-12 | 150 | low | 0.571 |
| ModuleFirmwareVersion | Lower | 39-40 | Lwr | 39 | ModuleActiveFirmwareMajorRevision | 8-15 | 153 | medium | 0.704 |
| InactiveFirmwareVersion | Lower | 83-84 | Lwr | 40 | ModuleActiveFirmwareMinorRevision | 8-15 | 153 | medium | 0.679 |
| CdbStatusLower | Lower | 37-38 (0x25-0x26) | Lwr | 37 | CdbStatus1 | 8-13 | 151 | medium | 0.75 |
| ApplicationAdvertisingLegacy | Lower | 85-117 | Lwr | 85 | MediaType | 8-21 | 157 | low | 0.216 |
| ModuleLevelMonitors | Lower | 14-25 | Lwr | 14 | TempMonValue | 8-10 | 147 | low | 0.258 |
| ModuleTemperature | Lower/11h | pending | Lwr | 3 | ModuleState | 8-6 | 144 | low | 0.571 |
| ModuleVoltage | Lower/11h | pending | Lwr | 3 | ModuleState | 8-6 | 144 | medium | 0.75 |
| TxPowerDbm | 11h | pending | 00h | 201 | MaxPower | 8-31 | 163 | medium | 0.667 |
| RxPowerDbm | 11h | pending | 00h | 201 | MaxPower | 8-31 | 163 | medium | 0.667 |
| RxLosLane1 | 11h | pending | 01h | 151 | RxLOSType | 8-49 | 173 | medium | 0.632 |
| TempHighAlarmThreshold | 02h | pending | 02h | 128 | TempMonHighAlarmThreshold | 8-62 | 185 | high | 0.936 |
| TempHighWarningThreshold | 02h | pending | 02h | 132 | TempMonHighWarningThreshold | 8-62 | 185 | high | 0.941 |
| TempLowWarningThreshold | 02h | pending | 02h | 134 | TempMonLowWarningThreshold | 8-62 | 185 | high | 0.939 |
| VccHighAlarmThreshold | 02h | pending | 02h | 136 | VccMonHighAlarmThreshold | 8-62 | 185 | high | 0.933 |
| VdmFreeze | 2Fh | pending | 2Fh | 145 | FreezeDone | 8-176 | 280 | medium | 0.632 |
| CdbCmdId | 9Fh | 128 (0x80) | 9Fh | 128 | CMDID | 8-178 | 282 | medium | 0.769 |
| CdbEplLength | 9Fh | 130 (0x82) | 9Fh | 130 | EPLLength | 8-178 | 282 | high | 0.857 |
| CdbLplLength | 9Fh | 132 (0x84) | 9Fh | 132 | LPLLength | 8-178 | 282 | high | 0.857 |
| CdbCheckCode | 9Fh | 133 (0x85) | 9Fh | 133 | CdbChkCode | 8-178 | 282 | high | 0.909 |
| CdbPasswordEntry | Lower | 122 (0x7A) | Lwr | 122 | PasswordEntryArea | 8-24 | 159 | medium | 0.788 |
| CdbInstance | 9Fh | banked | 01h | 163 | CdbInstancesSupported | 8-54 | 178 | medium | 0.688 |
| DpState | 11h | pending | Lwr | 3 | ModuleState | 8-6 | 144 | medium | 0.667 |
| AppSelLane1 | 10h | pending | 10h | 145 | AppSelCodeLane1.10h.145 | 8-72 | 198 | high | 0.846 |
| AppSelLane2 | 10h | pending | 10h | 146 | AppSelCodeLane2.10h.146 | 8-72 | 198 | high | 0.846 |
| AppSelLane3 | 10h | pending | 10h | 147 | AppSelCodeLane3.10h.147 | 8-72 | 198 | high | 0.846 |
| AppSelLane4 | 10h | pending | 10h | 148 | AppSelCodeLane4.10h.148 | 8-72 | 198 | high | 0.846 |
| LPMode | Lower | 26 bit4 | Lwr | 26 | SquelchMethodSelect | 8-11 | 148 | low | 0.4 |
| TxDisable | 10h | pending | 10h | 130 | OutputDisableTx8 | 8-69 | 194 | medium | 0.64 |

_仅列前 40 条，共 47 条，完整清单见 JSON。_

## 7. 未匹配字段（演示合成）

`CcBase`, `CcExt`, `TxBiasLane1`, `CdbLocalPayload`, `CdbExtendedPayload`, `CdbMaxCompletionTime`, `ConfigErrorCode`, `TxAmplitude`, `Loopback`, `PrbsChecker`

## 8. 复现与边界

```bash
python tools/import_cmis53.py          # 重建权威参考数据
python tools/verify_seed_fields.py     # 生成本报告
python tools/verify_seed_fields.py --strict   # CI：存在地址不一致时返回 1
python tools/test_seed_verification.py        # 回归测试
```

- 匹配顺序：精确字段名 → 精确 `(page, byte)` 地址 → 模糊字段名（`difflib`，阈值 0.62）。模糊结果一律标记为 `candidate`。
- 演示模型的 `field_key` 多为自造别名（如 `ModuleIdentifier` 对应 `SFF8024Identifier`），`data_type` 也是展示用途的粗粒度类型，因此类型/access 差异只记录、不判定失败。
- `Lower/11h`、`A0h-AFh` 等复合页标签会展开；`pending`、`banked`、`Staged Control Set` 等占位不计为可解析地址。
