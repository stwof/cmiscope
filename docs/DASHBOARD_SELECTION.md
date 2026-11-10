# Dashboard 框架选型说明（CMIScope）

**结论：选定 [tabler/tabler](https://github.com/tabler/tabler) v1.7.3（MIT），以 vendored 静态资源方式集成。**
本服务命名为 **CMIScope**（CMIS + scope，取「观测 / 测量 CMIS 的仪表」之意），代码与注释均为英文，
页面默认中文、可切换英文。

调研时间：2026-11-08。元数据通过 GitHub REST API `/repos/{owner}/{repo}` 实时读取，
版本通过 npm registry `@tabler/core/latest` 核对，许可证文本通过 jsDelivr GitHub 源获取。

---

## 1. 筛选口径

目标服务约束：**依赖少、启动快、资源占用低、本地部署、配置与环境解耦、便于迁移**。
据此设置筛选条件：

1. 开源许可清晰且对内部/商用无传染性顾虑（优先 MIT / Apache-2.0 / BSD）；
2. 维护活跃（最近提交在数周内、未归档、issue 有响应）；
3. 易集成：最好是纯静态 CSS/JS，不需要 Node 构建链、不需要额外常驻服务或数据库；
4. 组件足够覆盖表格、表单、弹窗、徽章、卡片、导航等数据型 Dashboard 需求；
5. 可离线 vendored、体积小、可随项目整目录迁移。

## 2. 候选对比（GitHub API 实时快照，2026-11-08）

| 仓库 | 许可 | Stars | Forks | 最近 push | Open issues | 技术栈 / 集成成本 | 结论 |
| --- | --- | ---: | ---: | --- | ---: | --- | --- |
| **tabler/tabler** | **MIT** | **42,021** | 4,433 | **2026-11-07** | 93 | Bootstrap 5 内置，**单 CSS + 单 JS**，纯静态、无构建 | ✅ **选定** |
| tabler/tabler-icons | MIT | 22,579 | 1,268 | 2026-11-07 | 96 | SVG/WebFont 图标包 | ✅ 配套引入 |
| ColorlibHQ/AdminLTE | MIT | 45,678 | 18,114 | 2026-11-04 | 12 | jQuery + Bootstrap 模板，页面模板化、依赖 jQuery/Bootstrap bundle | ❌ 未采用 |
| Lissy93/dashy | MIT | 26,940 | 1,969 | 2026-11-07 | 14 | Vue + Node/Yarn 构建链、PWA、导航型首页 | ❌ 未采用 |
| grafana/grafana | AGPL-3.0 | 77,759 | 14,941 | 2026-11-08 | 3,321 | Go 后端 + 数据库 + 插件体系，重量级 | ❌ 未采用 |

补充核对：`@tabler/core` npm latest = **1.7.3**（license=MIT），
下载到的 `tabler.min.css` 头部标注 `Tabler v1.7.3 · Copyright 2018-2026 The Tabler Authors · Licensed under MIT`；
仓库 `LICENSE` 为完整 MIT 文本。Tabler 仓库有 51+ releases、持续提交（2026-10 仍有依赖升级与功能提交），
未归档，维护活跃度满足要求。

## 3. 评估维度与打分

| 维度 | 权重 | Tabler | AdminLTE | Dashy | Grafana |
| --- | ---: | ---: | ---: | ---: | ---: |
| 许可清晰且无传染性 | 高 | 5 (MIT) | 5 (MIT) | 5 (MIT) | 2 (AGPL-3.0) |
| 维护活跃 | 高 | 5 | 5 | 5 | 5 |
| 零构建 / 零额外运行时 | 高 | 5 | 3（jQuery 依赖） | 1（Node/Vite） | 1（Go + DB） |
| 本地离线可移植 | 高 | 5（静态可拷贝） | 4 | 2 | 1 |
| 资源占用 | 中 | 5 | 4 | 2 | 1 |
| 数据型组件（表格/表单/弹窗） | 中 | 5 | 4 | 3（偏导航卡片） | 5 |
| 与 Python 标准库后端契合度 | 高 | 5（直接托管静态文件） | 4 | 2 | 1 |

**为何是 Tabler**

- 许可：MIT，允许内部使用、修改、分发，无 AGPL 类网络分发义务；LICENSE 原文随资源保留。
- 活跃：42k stars、4.4k forks、最近 push 2026-11-07、51+ releases、未归档。
- 易集成：Bootstrap 5 已打包进发行版，只需 `tabler.min.css` + `tabler.min.js` 两个文件；
  无需 npm、无需构建、无需后端模板引擎；直接由标准库 `http.server` 托管。
- 组件覆盖：`card` / `table` / `form-control` / `form-select` / `btn` / `badge` / `modal` /
  `alert` / `status-dot` 等，正好对应设备列表、字段表、编辑弹窗、校验报告与变更反馈。
- 可移植：全部资源本地化，断网可用；深色主题 `data-bs-theme="dark"` 开箱即用。

**未采用的原因**

- AdminLTE：同为 MIT 且 star 更多，但依赖 jQuery 与 Bootstrap bundle，模板结构偏「整页模板」，
  集成进自定义单页布局需要裁剪；Tabler 的组件粒度更细、依赖更少。
- Dashy：定位是自托管导航/起始页，数据表格与表单能力弱；Vue + Yarn/Vite 构建链、
  Node 运行时与我们的「零依赖、零构建」目标冲突。
- Grafana：能力最强但 AGPL-3.0 许可、Go 服务 + 数据库 + 插件体系，启动慢、内存占用高，
  完全不适合轻量本地部署；且本服务需要自定义配置编辑与图谱查询，并非时序面板场景。

## 4. 集成方式

资源全部 vendored 到 `cmis_service/static/vendor/tabler/`（随代码一起迁移）：

| 文件 | 大小 | 用途 |
| --- | ---: | --- |
| `tabler.min.css` | 686 KB | Tabler 1.7.3 主样式（含 Bootstrap 5） |
| `tabler.min.js` | 149 KB | 交互组件 bundle |
| `tabler-icons.min.css` | 217 KB | Tabler Icons WebFont 样式（v3.0.1，MIT） |
| `fonts/tabler-icons.woff2` | 805 KB | 图标字体，CSS 相对路径 `./fonts/` |
| `LICENSE` | 1 KB | Tabler 原始 MIT 许可文本 |

`index.html` 通过相对路径引用；`server.py::_static` 做 `resolve()` + `relative_to()` 校验防目录穿越，
vendor 资源设置 `Cache-Control: public, max-age=3600`。页面交互用原生 JS 调用同源 `/api/*`，
不引入任何 CDN、npm 包或框架运行时。

### 4.1 CMIScope 在 Tabler 之上的页面结构

| 视图 | Tabler 组件 | 数据来源 |
| --- | --- | --- |
| 总览 | `card` / `table` / `badge` / `status-dot` / 进度条 | `GET /api/overview` |
| 设备与配置项 | `table` / `form-control` / `form-select` | `GET /api/devices`、`/api/config-items` |
| **模块 CMIS（按规范分区）** | `card` / `accordion(details)` / `pill` / `table` | `GET /api/sections`、`/api/cmis/module` |
| **CDB 操作面板** | `form-select` / `input` / `btn` / `code` 块 / `alert` | `/api/cdb/commands`、`compose`、`execute`、`history`、`status` |
| 配置编辑弹窗 | `modal` / `form-control` / `alert` / 校验报告列表 | `validate` + `PUT /api/config-items/{id}` |
| 知识图谱 | `card` / `table` / 内联 SVG | `/api/kg/stats`、`entities`、`relations`、`graph` |
| 来源与待确认 | `card` / `table` / `badge` | `/api/kg/sources/coverage`、`/api/kg/pending` |
| 关于服务 / 接入方式 | `card` / `table` | `GET /api/access`、`/api/meta` |
| 统一检索 | `form-control` / 结果列表 | `GET /api/search?scope=all` |

本项目自有的静态文件（与 vendor 分离，便于独立升级）：
`index.html` 16 KB、`js/app.js` 46 KB、`js/i18n.js` 14 KB、`css/app.css` 9 KB。

**双语实现**：`js/i18n.js` 暴露 `CMIS_I18N`（`t()` / `getLang()` / `setLang()` / `applyStatic()`），
静态文案用 `data-i18n` / `data-i18n-ph` 标注，动态文案调用 `t()`；
语言存于 `localStorage['cmiscope.lang']`，默认 `zh`，切换后触发 `window.onLanguageChange` 重渲染。
Tabler 只提供样式骨架，不参与语言切换，这正是选择「纯 CSS/JS、无框架运行时」带来的好处：
后端仍是 Python 标准库，无需模板引擎。

**深色主题**：页面使用 `data-bs-theme="dark"`，`css/app.css` 为分区卡片、CDB 帧预览、校验报告
与图谱 SVG 补充了主题变量，避免自定义组件在暗色下出现黑字黑底。

升级方式：替换上述 vendor 文件并同步修改 `api.py /api/meta` 中的版本号即可，业务逻辑无需改动。

## 5. 风险与后续

- vendored 静态资源需手动跟踪官方版本；建议定期核对 npm `@tabler/core/latest` 与 GitHub release。
- Tabler 1.x 相对早期 1.4 有类名/主题变量变化，升级后应回归一次页面渲染；
  本项目已用 Edge 无头浏览器验证三个核心视图，升级后应重复该回归。
- 图标字体 805 KB 是体积大头；若需极致瘦身，可改为按需内联 SVG 图标并移除 webfont。
- 双语字典目前覆盖 `index.html` 与 `app.js` 的可见文案；后端规范数据自带 `zh`/`en` 字段，
  新增分区或 CDB 命令时需同步补 `i18n.js` 的键。
- GitHub star / pushed_at 为 2026-11-08 快照，选型说明中的数据会随时间变化（对应图谱待确认项 `P-13`）。
- 端到端回归 `python tools/smoke_test.py`（87 项）会检查 `/`、`app.css`、`app.js`、`i18n.js`
  与 vendor CSS 的可访问性及目录穿越防护，可作为升级后的最低验证门槛。
