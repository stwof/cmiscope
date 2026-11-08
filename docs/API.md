# CMIScope REST API 文档

基址：`http://127.0.0.1:8787`（可用 `config.ini` 的 `port`、`CMIS_PORT` 或 `--port` 修改）。
所有接口同源，本地部署默认无需认证；REST 接入的 token 只从环境变量读取，**不会**出现在任何响应中。
所有 SQL 使用参数绑定，用户输入在前端统一 HTML 转义，静态资源做目录穿越防护。

> 页面默认中文、可切英文；但**所有 API 错误消息与代码注释均为英文**（`Accept-Language` 不参与协商，
> 语言切换仅由前端 `js/i18n.js` 处理）。规范分区的 `zh` / `en` 文案由后端一并返回。

---

## 1. 统一响应

```jsonc
// 成功
{ "ok": true, "data": { ... } }
// 失败
{ "ok": false, "error": { "code": "VALIDATION_FAILED", "message": "...", "details": { ... } } }
```

| HTTP | `error.code` | 场景 |
| ---: | --- | --- |
| 400 | `MISSING_VALUE` / `BAD_PARAM` / `BAD_REQUEST` / `INVALID_JSON` / `MISSING_QUERY` / `MISSING_PARAM` / `VALIDATION_FAILED` / `CDB_VALIDATION_FAILED` / `UNSAFE_PARAM` | 参数缺失、JSON 非法、保存前校验失败、CDB 帧校验失败、SSH 模板参数不安全 |
| 403 | `FORBIDDEN` / `HARDWARE_WRITE_DISABLED` / `LOWER_MEMORY_PROTECTED` / `CDB_PAGE_PROTECTED` / `CDB_REST_FORBIDDEN` / `FIRMWARE_COMMAND_FORBIDDEN` | 目录穿越、硬件写开关未开、Lower Memory 写保护、CDB 页只读、固件命令未授权 |
| 404 | `NOT_FOUND` / `ENDPOINT_NOT_FOUND` / `DEVICE_NOT_FOUND` / `CONFIG_ITEM_NOT_FOUND` / `KG_ENTITY_NOT_FOUND` / `SECTION_NOT_FOUND` | 资源不存在 |
| 405 | `METHOD_NOT_ALLOWED` | 方法不支持 |
| 409 | `VERSION_CONFLICT` / `SERVICE_READ_ONLY` / `CONFIRMATION_REQUIRED` | 乐观锁冲突 / 服务只读 / CDB 缺少 `confirm=EXECUTE` |
| 413 | `PAYLOAD_TOO_LARGE` | 请求体超过 `max_body_bytes` |
| 500 | `DB_ERROR` / `INTERNAL_ERROR` / `IO_ERROR` / `BAD_TEMPLATE` / `UNKNOWN_ACCESS_MODE` | 服务端异常（堆栈只写日志，不返回客户端） |
| 501 | `NOT_SUPPORTED` | 当前接入模式不支持该操作（如 mirror 模式读真实寄存器） |
| 502/503/504 | `SSH_UNAVAILABLE` / `REST_UNREACHABLE` / `SSH_NOT_CONFIGURED` / `REST_NOT_CONFIGURED` / `SSH_TIMEOUT` / `REST_TIMEOUT` | 目标设备不可达或未配置 |

---

## 2. 端点总览

完整清单也可在运行时通过 `GET /api/meta -> data.endpoints` 获取。

### 2.1 服务与检索

| 方法 | 路径 | 参数 | 说明 |
| --- | --- | --- | --- |
| GET | `/api/health` | — | 存活探测；返回 `status / time / read_only / access_mode / project` |
| GET | `/api/meta` | — | 配置摘要、项目名称与默认语言、Tabler 框架信息、CMIS 规范版本、分区键、接入模式、端点列表 |
| GET | `/api/overview` | — | Dashboard 概览：设备/字段/配置项统计、状态分布、分区计数、最近变更、图谱统计 |
| GET | `/api/search` | `q`(必填), `scope=all\|device\|field\|config\|kg` | 跨设备/字段/配置项/图谱统一检索 |

### 2.2 CMIS 查询展示

| 方法 | 路径 | 参数 | 说明 |
| --- | --- | --- | --- |
| GET | `/api/devices` | `q`, `status`, `access_mode`, `limit`, `offset` | 设备列表（含模块数/配置项数、中英文名称） |
| GET | `/api/devices/{id}` | — | 设备详情：模块、字段/配置项、图谱关联、最近变更 |
| GET | `/api/fields` | `q`, `page`, `access`, `section` | 字段字典（页、偏移、类型、权限、分区、规范引用、置信度、来源）；最多返回 300 条 |
| GET | `/api/config-items` | `q`, `device_id`, `field_key`, `section`, `writable`, `limit`, `offset` | 配置项实例检索；`section` 取 `LOW_PAGE\|DOM\|CDB\|CONTROL` |
| GET | `/api/config-items/{id}` | — | 配置项详情：字段定义、所属分区、校验规则、图谱关联、变更历史 |
| GET | `/api/changes` | `device_id`, `limit` | 配置项变更审计记录 |

### 2.3 按 CMIS 规范分区的模块视图

| 方法 | 路径 | 参数 | 说明 |
| --- | --- | --- | --- |
| GET | `/api/sections` | — | 四个分区定义（`LOW_PAGE / DOM / CDB / CONTROL`）及字段数，附 Lower Memory 布局、Upper Page 00h、CDB 帧、CDB 状态寄存器、规范版本、来源 ID |
| GET | `/api/sections/{key}` | — | 单分区详情 + 该分区下全部字段；未知 key → 404 `SECTION_NOT_FOUND` |
| GET | `/api/cmis/module` | `device_id`(可选，缺省取第一个设备), `section`(可选过滤) | **模块 CMIS 分区视图**：设备+模块信息，配置项按分区分组，每组带 `writable_count` 与对应寄存器映射；LOW_PAGE 返回 Lower Memory 表，CDB 返回命令帧表 |

分区键与页范围：

| key | 名称 | 主要页 | 写策略 |
| --- | --- | --- | --- |
| `LOW_PAGE` | 低页 0x00（Lower + Upper 00h） | Lower 00h–7Fh、Upper 00h 80h–FFh | `read-mostly`；远程接入禁止写 Lower Memory |
| `DOM` | DOM 数字诊断监测（CMIS 称 Monitors） | Lower 14–25、02h、10h、11h、20h–2Fh | `thresholds-only`；监测量只读 |
| `CDB` | CDB 命令数据块与操作接口 | Lower 37–38、118–125、9Fh、A0h–AFh | 命令帧专用接口；页级只读保护 |
| `CONTROL` | 控制/状态/应用与诊断 | 01h、10h、12h、13h、14h、30h–4Fh | 逐字段 `writable` 位控制 |

### 2.4 接入方式与寄存器

| 方法 | 路径 | 参数 / 请求体 | 说明 |
| --- | --- | --- | --- |
| GET | `/api/access` | — | 当前适配器能力（`capabilities()`）、三种接入模式拓扑/读写语义/风险/控制项、脱敏后的服务配置、规范版本 |
| POST | `/api/access/probe` | `{}` | 连通性探测；mirror 模式直接返回离线状态；SSH/REST 模式按配置发起真实探测 |
| GET | `/api/registers/read` | `device_id`(必填), `page`(默认 `00h`), `offset`(0–255), `length`(1–128) | 通过当前适配器读取页/偏移；mirror 返回本地镜像缓存值 |
| POST | `/api/registers/write` | `{"device_id":"...", "page":"10h", "offset":130, "data_hex":"0x21"}` | **先执行页级写保护**再下发；Lower Memory 与 CDB 页直接拒绝 |

三种接入模式（`access_mode`）：

| key | 拓扑 | 说明 |
| --- | --- | --- |
| `mirror` | browser → 本地服务 → SQLite | 默认。离线演示，写只 staged，不接触硬件 |
| `ssh-i2c` | browser → 测试 Server 上的服务 → SSH → 测试 Switch → I2C `0x50` → 模块 EEPROM | 方式一；命令模板 + `subprocess`，高线程序列化、页选择需复原 |
| `rest-api` | browser → 服务 → 目标设备/NOS 北向 REST API → 设备内部 I2C | 方式二；token 走环境变量，页级 allowlist 参照 IETF YANG 草案 |

### 2.5 CDB 操作接口

| 方法 | 路径 | 参数 / 请求体 | 说明 |
| --- | --- | --- | --- |
| GET | `/api/cdb/commands` | — | 26 条命令目录（OIF-CMIS-05.3 §9），含 `cmd_id / en / zh / group / spec_ref / risk / lpl_rule`；另返回 9Fh 帧定义、状态寄存器、LPL/EPL 上限、I2C 地址 |
| POST | `/api/cdb/compose` | `{"cmd_id":"0040", "lpl_hex":"00 01", "epl_hex":""}` | **离线编排 + 校验**，返回 128 字节 `frame_hex`（256 个十六进制字符）、`check_code`、`lpl_len / epl_len`；校验失败不下发 |
| POST | `/api/cdb/execute` | `{"cmd_id":"0040", "lpl_hex":"00 01", "device_id":"SW-CORE-01", "confirm":"EXECUTE", "operator":"..."}` | 校验帧 → 检查设备 → 执行安全策略 → 写 `cdb_operations` 审计表；mirror 模式恒为 `staged` |
| GET | `/api/cdb/status` | `device_id`(可选) | 最近一次 CDB 操作、`CdbStatusLower` 配置项读数、CDB 状态寄存器定义 |
| GET | `/api/cdb/history` | `device_id`(可选), `limit` | CDB 操作审计历史（帧、校验码、结果、是否下发硬件、操作人、规范引用、来源 ID） |

CDB 帧（Page 9Fh，128 字节）：`CMDID(2B) / EPL Length(2B) / LPL Length(1B) / Check Code(1B) / Reserved(2B) / LPL(120B)`；
EPL 位于 A0h–AFh，最多 2048 字节。服务端计算 `check_code = (-sum(body)) & 0xFF`，使 EPL 长度至 LPL 载荷的字节和对 256 取模为 0。
`lpl_hex` 上限 120 字节、`epl_hex` 上限 2048 字节、CMDID 必须在命令目录中，否则 400 `CDB_VALIDATION_FAILED`。

CDB 下发安全策略（非 mirror 模式）：`confirm` 必须等于 `cdb_confirm_token`（默认 `EXECUTE`）→ 409 `CONFIRMATION_REQUIRED`；
固件类命令需 `cdb_allow_firmware=true` → 403 `FIRMWARE_COMMAND_FORBIDDEN`；REST 模式下发需 `cdb_rest_allowed=true` → 403 `CDB_REST_FORBIDDEN`；
所有硬件写还需 `allow_hardware_write=true` → 403 `HARDWARE_WRITE_DISABLED`。

### 2.6 配置管理

| 方法 | 路径 | 请求体 | 说明 |
| --- | --- | --- | --- |
| POST | `/api/config-items/{id}/validate` | `{"value": "..."}` | **保存前校验**（不写库），返回逐项检查、错误、告警、规范化值、当前 `access_mode` |
| PUT / POST | `/api/config-items/{id}` | `{"value":"...", "expected_version":1, "note":"...", "operator":"..."}` | 服务端二次校验 → 写本地镜像 →（可选）经适配器下发 → 记录审计 → 返回变更反馈 |

`PUT` 成功响应关键字段：

```jsonc
{
  "ok": true,
  "data": {
    "result": "staged",               // 或 "applied"（真实下发成功）
    "applied_to_hardware": false,
    "message": "Saved to the local mirror (staged, no hardware write): AppSelLane1 0x11 -> 0x21",
    "diff": { "before": {"value":"0x11","raw_hex":"0x11","version":1},
              "after":  {"value":"0x21","raw_hex":"0x21","version":2} },
    "validation": { "valid": true, "checks": [...], "errors": [], "warnings": [...] },
    "transport": {},                 // 非 mirror 且已下发时带 adapter/page/offset
    "change": { "id": 1, "result": "staged", "created_at": "...", "operator": "local-admin" },
    "item": { ... }
  }
}
```

> `access_mode=mirror`（默认）：写入仅落本地 SQLite，**不向硬件下发**；`applied_to_hardware` 恒为 `false`。
> `expected_version` 省略时不做并发检查，建议始终携带。服务端写保护在所有模式下都生效。

### 2.7 知识图谱

| 方法 | 路径 | 参数 | 说明 |
| --- | --- | --- | --- |
| GET | `/api/kg/stats` | — | 实体/关系/来源/关联/待确认数量与类型分布 |
| GET | `/api/kg/entities` | `type`, `q`, `confidence`, `limit`, `offset` | 实体检索（12 类，含 `SpecificationPartition`、`AccessPath`） |
| GET | `/api/kg/entity/{id}` | `depth=1\|2` | 实体属性、解析后的来源、入/出边、二跳邻居 |
| GET | `/api/kg/relations` | `type`, `src`, `dst`, `q`, `limit` | 关系过滤（11 类） |
| GET | `/api/kg/link` | `cmis=字段key/设备id` 或 `entity=图谱实体id` | 双向关联查询 |
| GET | `/api/kg/graph` | `type`, `limit` | 可视化节点/边 |
| GET | `/api/kg/sources` | — | 38 条来源清单 |
| GET | `/api/kg/sources/coverage` | — | 每条来源支撑的实体/关系数 |
| GET | `/api/kg/pending` | — | 19 条待确认项清单 |

### 2.8 静态资源

| 路径 | 说明 |
| --- | --- |
| `/` `/index.html` | Dashboard 单页（默认中文，右上可切英文） |
| `/css/app.css`、`/js/app.js`、`/js/i18n.js` | 布局、交互与双语字典 |
| `/vendor/tabler/*` | Tabler 1.7.3 + Icons + LICENSE |

---

## 3. 校验规则

服务端在 `validate` 与 `PUT` 中执行同一套规则（前端校验仅为提示）：

1. **只读位**：`writable=0` → `READ_ONLY_FIELD`（字段字典中的 RO 项）。
2. **类型解析**：`bool` / `enum` / `int|uint` / `float` / `hex` / `ascii` / `text`；
   `hex` 支持 `0x` 前缀，输出统一大写 `0xNN`；`float` 会按常见 1/256 缩放推导 raw_hex 并给出 `RAW_ENCODING_UNCONFIRMED` 告警。
3. **取值域**：`min_value` / `max_value` → `OUT_OF_RANGE`；`allowed_values` → `VALUE_NOT_ALLOWED`；`regex` → `REGEX_MISMATCH`。
4. **跨字段约束**：
   - `appsel_in_advertised`：`0xAD` 编码（A=1..8、D=0..8），且 A 必须在模块 `advertised_apps` 内 → `INVALID_APPSEL` / `APP_NOT_ADVERTISED`；
   - `tx_disable_vs_datapath_init`：`TxDisable` 与 `DataPathInit` 不可同时置位 → `CROSS_FIELD_CONFLICT`；
   - `threshold_high_gt_warning`：高温告警阈值必须大于预警阈值 → `THRESHOLD_ORDER`；
   - `low_power_vs_datapath_init`：DP 初始化期间切 LowPwr 给出 `LOW_POWER_DURING_INIT` 告警。
5. **字段置信度**：字段 `confidence != confirmed` 时追加 `SPEC_UNCONFIRMED` 告警。
6. **并发**：`expected_version` 与当前 `version` 不符 → 409 `VERSION_CONFLICT`。
7. **只读服务**：`read_only=true` 时所有写入 → 409 `SERVICE_READ_ONLY`。
8. **页级写保护**（真实下发时）：Lower Memory（页 00h 且 offset<128）与 CDB 页（9Fh、A0h–AFh）一律拒绝。

---

## 4. curl 示例

```bash
# 服务与概览
curl http://127.0.0.1:8787/api/meta
curl http://127.0.0.1:8787/api/overview

# 分区与模块 CMIS 视图
curl http://127.0.0.1:8787/api/sections
curl http://127.0.0.1:8787/api/sections/CDB
curl "http://127.0.0.1:8787/api/cmis/module?device_id=SW-CORE-01&section=DOM"

# 接入方式
curl http://127.0.0.1:8787/api/access
curl -X POST http://127.0.0.1:8787/api/access/probe -H "Content-Type: application/json" -d '{}'
curl "http://127.0.0.1:8787/api/registers/read?device_id=SW-CORE-01&page=00h&offset=0&length=16"

# CDB 命令编排 / 执行 / 审计
curl http://127.0.0.1:8787/api/cdb/commands
curl -X POST http://127.0.0.1:8787/api/cdb/compose \
  -H "Content-Type: application/json" -d '{"cmd_id":"0040","lpl_hex":"00 01"}'
curl -X POST http://127.0.0.1:8787/api/cdb/execute \
  -H "Content-Type: application/json" \
  -d '{"cmd_id":"0040","lpl_hex":"00 01","device_id":"SW-CORE-01","confirm":"EXECUTE"}'
curl "http://127.0.0.1:8787/api/cdb/history?device_id=SW-CORE-01"
curl "http://127.0.0.1:8787/api/cdb/status?device_id=SW-CORE-01"

# 按分区检索配置项
curl "http://127.0.0.1:8787/api/config-items?q=AppSelLane1&writable=1"
curl "http://127.0.0.1:8787/api/config-items?section=CDB"

# 保存前校验（合法 / 非法）与保存
curl -X POST http://127.0.0.1:8787/api/config-items/17/validate \
  -H "Content-Type: application/json" -d '{"value":"0x21"}'
curl -X POST http://127.0.0.1:8787/api/config-items/17/validate \
  -H "Content-Type: application/json" -d '{"value":"0xF1"}'
curl -X PUT http://127.0.0.1:8787/api/config-items/17 \
  -H "Content-Type: application/json" \
  -d '{"value":"0x21","expected_version":1,"note":"switch to Application 2"}'

# 图谱关联查询
curl "http://127.0.0.1:8787/api/kg/link?cmis=AppSelLane1"
curl "http://127.0.0.1:8787/api/kg/link?entity=CFG-APPSEL"
curl "http://127.0.0.1:8787/api/kg/entity/CFG-APPSEL?depth=2"
curl "http://127.0.0.1:8787/api/kg/relations?type=CONSTRAINS"
curl "http://127.0.0.1:8787/api/kg/link?cmis=CdbCmdId"
```

> 配置项 `id` 由种子数据顺序生成，可用 `/api/config-items?q=...` 查询实际 ID。
> `device_id` 可用 `/api/devices` 查询；示例值 `SW-CORE-01` 来自内置合成种子数据。

---

## 5. 回归验证

`python tools/smoke_test.py` 会启动临时端口 + 临时数据库，端到端验证 **60 项**：健康检查、分区视图、
CDB 编排/校验/审计/写保护、配置保存与乐观锁、图谱双向关联、静态资源与目录穿越防护。
当前结果：`60 passed / 0 failed`。
