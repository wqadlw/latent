# 阶段 D 前端重构 · 借鉴评估与实施方案

> 参照对象：Vue 3 官方文档（组合式函数 / TypeScript 指南）、企业级 Vue3 中后台工程实践
> 评估日期：2026-10-11
> 上游路线：`A 工程加固 → B GEO 能力深化 → C 生产流水线智能化 → **D 前端重构**`
> 前置产出：`docs/GEOFlow-借鉴评估与阶段B实施方案.md`（阶段 B 的同类文档，本文件沿用其体例）

---

## 一、家底：前端现在是什么样

### 1.1 体量

| 指标 | 数值 |
|---|---|
| 视图（`src/views`） | 25 个 `.vue` + 8 个步骤子组件 |
| 共享组件（`src/components`） | 20 个 `.vue` |
| 视图总行数 | 15,565 行 |
| **千行巨石视图** | **5 个，合计 6,099 行** |
| 组合式函数 | **1 个**（`useFocusScroll.js`） |
| API 模块 | 31 个 |
| 设计令牌 | 54 个（`main.css`） |

### 1.2 五个巨石视图的解剖

| 视图 | 总行数 | template | script | style | 性质 |
|---|---:|---:|---:|---:|---|
| `BrowserStudio.vue` | 1417 | 691 | 475 | 249 | **模板巨石**（9 步流水线 + 4 个对话框） |
| `Knowledge.vue` | 1229 | 467 | 495 | 265 | 均衡 |
| `Production.vue` | 1210 | **252** | **810** | 146 | **逻辑巨石**（模板已拆，逻辑没拆） |
| `PromptLibrary.vue` | 1138 | 347 | 499 | 290 | 均衡 |
| `Keyword.vue` | 1105 | 425 | 451 | 227 | 均衡 |

**注意 `Production.vue`**：它的模板只有 252 行——因为 10 个步骤早已抽成子组件。但 script 有 **810 行**。
这说明「拆组件」不等于「拆逻辑」：把模板搬进子组件后，父组件的状态与编排逻辑一行没少，反而因为要传 props 更长。
**这是本次重构最重要的认知起点。**

### 1.3 已有的三个正面先例（要沿用，不要另起炉灶）

1. **纯逻辑/数据外提** —— `utils/clipboard.js`、`utils/markdown.js`、`utils/format.js`、`utils/download.js`、
   `utils/lookup.js`、`constants/platforms.js`、`constants/status.js`、`constants/modes.js`、`constants/browserStudio.js`
   （D1 收敛剪贴板，D2 收敛日期/下载/查名/状态映射）
2. **模板拆分 + 非 scoped 共享样式表** —— `views/production/steps/*` + `views/production/steps/step-shared.css`
   跨子组件复用的类写进一张**不带 scoped** 的共享样式表，这是本项目已验证可行的拆分手法
3. **组合式函数** —— `composables/useFocusScroll.js`（43 行，单职责、零依赖、被 5 个视图复用）

---

## 二、外部最佳实践调研结论

### 2.1 Vue 官方对「抽取组合式函数」的定性 —— 本次重构的官方依据

官方《组合式函数》指南有一节专门叫 **「通过抽取组合式函数改善代码结构」**，原文：

> 抽取组合式函数不仅是为了复用，**也是为了代码组织**。随着组件复杂度的增高，你可能会最终发现组件多得难以查询和理解。
> 组合式 API 会给予你足够的灵活性，让你可以基于逻辑问题将组件代码拆分成更小的函数。
> ……在某种程度上，你可以将这些提取出的组合式函数看作是可以**相互通信的组件范围内的服务**。

这句话直接回答了「巨石视图该怎么拆」：**先按逻辑问题拆 composable，再按展示职责拆组件**。
我们目前的 `Production.vue` 只做了后者（拆了 10 个 Step 组件），所以 script 反而更长。

### 2.2 官方约定的硬性规则（照做）

| 规则 | 内容 |
|---|---|
| 命名 | 驼峰 + `use` 前缀 |
| 返回值 | **始终返回一个普通对象，里面装 ref**——这样解构后仍保持响应性。返回 `reactive` 对象会在解构时丢响应性 |
| 输入参数 | 应能接受 ref / getter，用 `toValue()` 归一化；若据此建 effect，必须在 `watch`/`watchEffect` 内部调 `toValue()` 才能正确追踪 |
| 副作用 | 必须在 `onUnmounted()` 清理 |
| 调用位置 | 只能在 `<script setup>` / `setup()` 内，且**同步**调用（`<script setup>` 是唯一允许 `await` 之后再调的地方） |

### 2.3 TypeScript 渐进迁移（官方 + 社区共识）

| 结论 | 依据 |
|---|---|
| Vite 只做转译**不做类型检查**，所以引入 TS 不影响构建速度与产物 | Vue 官方 TS 指南 |
| 类型检查靠 `vue-tsc`（`tsc` 的 Vue SFC 包装），可 watch 模式并行跑 | 同上 |
| 存量迁移用 `allowJs: true` + **`checkJs: false`**，新代码写 `lang="ts"`，**不要一次性全量改写** | TS 官方迁移指南 + 社区实践 |
| `isolatedModules: true`（esbuild 单文件转译的限制） | Vue 官方推荐（`@vue/tsconfig` 用 `verbatimModuleSyntax`） |

### 2.4 ⚠️ 实测踩坑：TypeScript 7 会让 vue-tsc 直接崩

本机装到的最新版是 **TypeScript 7.0.2**（Go 原生编译器）。实测：

```
Error [ERR_PACKAGE_PATH_NOT_EXPORTED]:
Package subpath './lib/tsc' is not defined by "exports" in typescript/package.json
```

TS 7 移除了 vue-tsc 依赖的内部子路径 `./lib/tsc`。
**必须钉到 `typescript@^5.9`**（实测 5.9.3 + vue-tsc 3.3.13 正常）。

> 这条写进文档，是因为它浪费的是**下一个人的一小时**——搜索引擎上还查不到，属于新版本刚出时的空窗期。

### 2.5 Scoped CSS 的跨组件共享（拆分的最大技术障碍）

`<style scoped>` 的作用域是**本组件模板 + 本组件根元素**，不会渗进子组件内部。因此把一个块抽成子组件后，
父组件里那些「原本同时管着这个块」的类名会立刻失效。业界三种解法：

| 方案 | 说明 | 本项目取舍 |
|---|---|---|
| `:deep()` / `::v-deep` | 父组件穿透改子组件样式 | ❌ 不用——它把父子样式重新耦合，是「假拆分」 |
| CSS Modules | 编译期哈希类名 | ❌ 不用——要改所有模板写法，收益不抵成本 |
| **非 scoped 共享样式表** | 按特性目录放一张全局样式表，跨子组件复用的类写在这里 | ✅ **用**——项目已有先例（`step-shared.css`），团队已熟悉 |

---

## 三、我们的 9 个洞（全部有实证）

### 洞 1：跨视图重复 —— 同一个 `copyText` 的故事还没讲完

D1 收掉了剪贴板（10 份实现 + 17 处内联）。但同一类重复还有 7 处：

| 重复物 | 涉及文件数 | 说明 |
|---|---:|---|
| 日期/时间格式化 | **8** | 至少 5 种不同实现（`slice(0,16)` / `toLocaleString` 三种参数组合 / 自写 `fmtTime`） |
| `getPlatformName` / `getPersonaName` | **5** | 各写各的查找 |
| 「Blob 下载」（`createObjectURL` + `<a download>`） | **7** | 完全逐字复制 |
| `modeLabel`（geo/platform/green/official → 中文） | **4** | 已在 D1 把其中 2 个搬进 constants，还剩 2 个 |
| 任务状态 `{draft/processing/done/archived}` → 标签+颜色 | **3** | `Dashboard` / `Production` / `ContentOpsPanel` |
| 虚拟表格 `.vtable` 结构 | 2 | `ContentAssetPanel` 与 `Keyword` 各写一套 |
| 各类 `el-tag type` 映射函数 | **≈13 个函数，散在 8+ 文件** | 无统一来源 |

**代价**：不是「改多处」，而是**改漏**。D1 就发现 10 份 `copyText` 演化出 3 个版本、其中 2 个缺关键分支。

### 洞 2：设计令牌有 7 个是坏的，且会静默失效

写了扫描脚本 `scripts/audit-css-tokens.mjs`（新增，可复用），实测：

```
已定义 token：54 个 ｜ 被引用 token：65 个 ｜ 未定义且非注入：14 个
```

**A 类：未定义且无 fallback —— 静默失效（7 个）**

| token | 无 fallback 引用 | 位置 |
|---|---:|---|
| `--bg-hover` | 5 处 | `GeoMonitor.vue`、`step-shared.css` |
| `--amber-500` | 3 处 | `BrowserStudio.vue` |
| `--red-500` | 3 处 | `BrowserStudio.vue` |
| `--red-300` | 2 处 | `StepLogPanel.vue`、`BrowserStudio.vue` |
| `--red-600` | 2 处 | `BrowserStudio.vue` |
| `--red-50` | 1 处 | `BrowserStudio.vue` |
| `--emerald-300` | 1 处 | `BrowserStudio.vue` |

写 `color: var(--red-500)` 而该变量不存在时，**整条声明被丢弃**，元素回退到继承色——
不报错、不警告，只是「颜色不太对」。这是最难发现的一类 bug。

**B 类：未定义但有 fallback（7 个）** —— `--font-mono`、`--bg-secondary`、`--bg-mute`、`--amber-400`、`--amber-600`、`--emerald-50`、`--font-sans`。
能显示，但语义已漂移（每处各写各的 fallback 值，同一语义在不同文件里是不同颜色）。

> 扫描器刻意排除了两类**误报**：运行时 `:style` 注入的局部变量（`--rc`/`--dc`/`--pc`/`--cat-color`，实测合法）
> 与 Element Plus 自有的 `--el-*`。不排除就会得到 13 个「假 bug」。

### 洞 3：API 响应信封不一致，调用方靠猜

`api/index.js` 的响应拦截器直接 `return response.data`（拆了 axios 外壳，但没拆业务信封）。于是调用方各读各的：

```js
res.code === 0            // BrowserStudio:941, Industry:129
res.data.ok               // BrowserStudio:941
res.data.msg              // BrowserStudio:1005, Knowledge:896
res.msg                   // GeoMonitor:305, IntentQuestion:420, Persona:340
res.data.data.id          // BrowserStudio:1029, Knowledge:954
```

**同一个后端，5 种读法。** 拆视图会把数据访问点从 5 个变成 25 个，而这个洞没有任何编译期保护。

### 洞 4：侧边栏菜单与路由 meta 是两份独立事实，已经漂移

| 来源 | `/publish` 的标题 |
|---|---|
| `router/index.js:99` `meta.title` | `发布自动化` |
| `Layout.vue:224` 菜单项 | `发布中心` |

`Layout.vue:171-230` 是**手工维护**的 `menuGroups`，不复用路由的 `meta.group`/`meta.icon`。
组顺序也不同。**同一个路由被两个来源描述**，改一处必漏另一处。

### 洞 5：`Production.vue` 的孤儿 CSS —— 不是「死代码」，是**活 bug**

`Production.vue:1192-1200`（`.version-*`）与 `:1203-1209`（`.gen-*`）写在**父组件的 scoped style** 里，
但它们对应的标记早已搬进 `VersionHistoryDialog.vue` / `OneClickGenerateResult.vue`——
**而这两个子组件根本没有 `<style>` 块**。

> ⚠️ 本文档初稿把这里判断为「18 条死规则，删掉即可」，**这个判断是错的**。
> scoped 样式够不到子组件内部（只能作用到子组件的**根元素**），而这两个子组件的根元素是 `<el-dialog>`，
> 所以规则从未生效。但它们描述的是**子组件真实需要的样式**——
> 正确处置是**把样式归还给子组件**，不是删除。若照初稿删掉，历史版本弹窗会永久停留在裸样式。
>
> 教训：判断一段 CSS 是否「死」之前，必须先确认它想作用的元素现在归谁管。

这是「拆分不做样式归属决策」的必然结果，也是本次必须先立规矩的原因。

### 洞 8：状态枚举只映射了一半，且同一列存在多份文案（**D2 实施中新发现**）

`production_task.status` 一列承载两套语义（见 `models.py:1045-1049`）：

| 模式 | 取值 | 写入口 |
|---|---|---|
| 手动（步骤式） | `draft / processing / done / archived` | `routers/production.py` |
| 自动（工作室·流水线·批量） | `created / running / await_confirm / confirmed / succeeded / partial / failed / published / cancelled` | `services/doubao_studio.py`、`services/task_queue.py` |

而前端只映射了**手动模式那 4 个**。后果是仪表盘、软文生产列表、内容日历上，
所有自动模式任务**直接显示英文原始码**（`await_confirm` / `running` / `failed`）。

同时，同一个列在三处各有一份文案，且已经互相漂移：

| 取值 | `constants/browserStudio.js` | `views/Pipeline.vue` |
|---|---|---|
| `created` | 已创建 | 待启动 |
| `running` | 运行中 | 执行中 |
| `await_confirm` | 待你确认 | 等待确认 |
| `confirmed` | 已确认 | 已入库 |

**同一批行、两个页面、两套词** —— 用户从流水线点进工作室会看到状态变了。
已统一到 `constants/status.js` 的 `TASK_STATUS_*`。

### 洞 9：`toISOString().slice(0, 10)` 取的是 **UTC** 日期（**D2 实施中新发现**）

`ContentOpsPanel.vue` 新建效果记录时，默认日期写的是
`new Date().toISOString().slice(0, 10)`。`toISOString()` 输出 UTC，
东八区**下午 4 点之后**拿到的就是「昨天」——默认记录日期整整差一天。
已改为 `toDateKey()`（按本地时区）。

---

### 洞 6：函数 props 爆炸 —— 现有拆分范式的天花板

`Production.vue` 给 `StepFinal` 传了 **约 30 个 props**，其中大量是函数（`copyText`、`runGeoFinalize`、`openPublishDialog`…）；
`StepSingleFlow` 17 个、`StepGeoGate` 15 个。这套做法如果复制到另外 4 个视图，会得到一堆
「改一个函数签名要同步改 6 处、且没有类型检查」的脆弱接口。

**这正是官方说的「抽取组合式函数，把它当作组件范围内的服务」要解决的问题。**

### 洞 7：两处「写进去但从没读出来」的状态

- `store/app.js:32-35`：`setIndustry()` 把 `currentIndustryId` 写进 `localStorage`，
  但 `initFromStorage()`（`:40-43`）只恢复 `sidebarCollapsed`，**从不读回 industry**。
  于是「上次选中的行业」永远丢失，每次启动都回落到 `industries[0]`。
- `Production.vue:871-872`：`cvarPendingCategory` / `cvarPendingAction` 是**模块级 `let`**，
  在组件外共享。多标签页或组件重挂载时会串状态。

---

## 四、借什么（最佳实践 → 落点）

| # | 借 | 来源 | 落点 |
|---|---|---|---|
| 借 1 | **按逻辑问题抽 composable，而不只是拆组件** | Vue 官方 | `composables/` 新增 `useIndustryReload` / `useEntityLookup` / `useBlobDownload` / `useRunPolling` 等 |
| 借 2 | **非 scoped 共享样式表**（按特性目录） | 项目既有先例 | `views/browser-studio/studio-shared.css` 等 |
| 借 3 | **composable 返回普通对象 + ref**，参数用 `toValue` 归一化 | Vue 官方约定 | 所有新 composable |
| 借 4 | **设计令牌单一来源**，补全缺失的语义色阶 | 设计系统通行做法 | `styles/main.css` 补 `--red-*` / `--amber-*` / `--emerald-*` / `--bg-hover` / `--font-mono` |
| 借 5 | **渐进式 TypeScript**（`allowJs` + `checkJs:false`，新代码 `lang="ts"`） | Vue 官方 + TS 官方 | `tsconfig.json` + `vue-tsc` 脚本 |
| 借 6 | **菜单由路由 meta 派生**，消灭第二份事实 | 中后台通行做法 | `Layout.vue` 的 `menuGroups` 改为从 `router.getRoutes()` 派生 |
| 借 7 | **扫描脚本化**（把「靠人肉 review」的检查变成可重复执行的工具） | 工程化 | `scripts/audit-css-tokens.mjs`（已完成）；后续可加 `audit-duplication.mjs` |

---

## 五、明确不借的（避免踩坑）

| 不借 | 原因 |
|---|---|
| **一次性全量 TS 改写** | 5 个巨石视图 + 25 个组件一次性加类型，diff 巨大且无法逐块验证。用 `allowJs` 渐进，新代码才上 TS |
| **`reactive()` 作为 composable 返回值** | 官方明确：解构会丢响应性。一律返回「装 ref 的普通对象」 |
| **`::v-deep` 穿透解决拆分后的样式** | 那是把父子样式重新绑死，属于「假拆分」，下一个人改不动 |
| **CSS Modules / Tailwind** | 要改所有模板写法；本项目已有令牌体系 + Element Plus，收益不抵成本 |
| **引入 Pinia 全局 store 来「解决」传参** | 视图内的状态是**视图局部**的，塞进全局 store 会制造隐式耦合。局部用 composable，跨视图才用 store |
| **一次性把 5 个视图全拆完再验证** | 无法定位回归来源。每个视图独立拆、独立 build + smoke |
| **引入 ESLint / Prettier 全量格式化** | 会产生淹没真实改动的巨型 diff。本次只用 `vue-tsc` 做类型检查，不动风格 |
| **为拆而拆地追求「每个文件 < 300 行」** | 行数是症状不是目标。目标是**职责单一**；`Production.vue` 拆完 script 仍可能偏长，那是业务复杂度决定的 |

---

## 六、实施方案（7 个包，每包独立可验证）

### D1｜前端公共层抽取 ✅ 已完成（2026-10-11）

`utils/clipboard.js`（两层 API）+ `utils/markdown.js` + `constants/browserStudio.js`；
全站 17 文件收敛到一份剪贴板实现；`BrowserStudio.vue` 1552 → 1417。

---

### D2｜地基修复 ✅ 已完成（2026-10-11）

**目标**：在拆任何视图之前，把「会被复制的东西」先修对、先集中。

**实际改动**

| 项 | 内容 |
|---|---|
| 补设计令牌 | `main.css` 补 26 个语义色阶（`--red-*` / `--amber-*` / `--emerald-*` 各 7 档）+ `--bg-hover/--bg-mute/--bg-secondary` + `--font-sans/--font-mono`；token 总数 54 → 80 |
| 新增 `constants/status.js` | 生产任务、选题、内容资产发布、内容审核、流水线步骤五套枚举的 `_LABEL` / `_TYPE` + 取值函数 |
| 新增 `constants/modes.js` | 生成模式文案 + 徽标样式类，`browserStudio.js` 的 `modeOptionText` 改为委托 |
| 新增 `utils/format.js` | 日期时间 6 个函数（字符串解析，不走 `new Date()` 以免时区漂移） |
| 新增 `utils/download.js` | Blob 下载 5 个函数（含 CSV 的 BOM 处理） |
| 新增 `utils/lookup.js` | `nameById` / `nameBy`：列表按 id 找名称（原先 10 份实现、3 种回退行为） |
| 新增回归脚本 | `scripts/audit-css-tokens.mjs` → `npm run audit:tokens`；`scripts/shot-d2.mjs` 视觉验收 |
| 清理洞 5 | `VersionHistoryDialog.vue` / `OneClickGenerateResult.vue` 补回缺失的 `<style>`，`Production.vue` 删除够不到子组件的孤儿规则 |
| 修复洞 7 | `store/app.js` 的 `currentIndustryId` 只写不读 |

**收编的重复实现**：日期 10 处（8 份函数 + 2 处内联切片）、Blob 下载 8 处、
`modeLabel` 4 处、`modeTagClass` 2 处、状态映射 6 处、id→名称 10 处。

**过程中发现的、原计划没写的 4 个真缺陷**

1. **生产任务状态映射漏了一半枚举** —— `production_task.status` 同时承载
   手动模式（`draft/processing/done/archived`）和自动模式
   （`created/running/await_confirm/confirmed/succeeded/partial/failed/published/cancelled`），
   而前端只映射了手动模式那 4 个。后果：仪表盘、软文生产列表、内容日历上，
   **所有自动模式任务直接显示英文原始码**（`await_confirm`、`running`、`failed`）。
   证据见本地验收截图 `docs/screenshots/D2-仪表盘-任务状态与时间.png`（修复前；该类阶段证据图不入库）。
2. **同一个 DB 列存在三份文案** —— 浏览器工作室写「已创建/运行中/待你确认/已确认」，
   流水线写「待启动/执行中/等待确认/已入库」。**同一批行、两个页面、两套词**，
   用户从流水线点进工作室会看到状态变了。已统一。
3. **`new Date().toISOString().slice(0, 10)` 取到的是 UTC 日期** ——
   东八区下午 4 点后「默认记录日期」会比本地日期早一天。改用 `toDateKey()`。
4. **`statusMeta[x].color` 是死数据** —— 四个十六进制值和 `.st-*` 的 CSS 完全重复，
   且从未被读取。颜色归 CSS，已从 JS 侧删除。

**验收结果**

| 项 | 结果 |
|---|---|
| `audit:tokens` A 类（静默失效） | **0**（修复前 7） |
| `audit:tokens` 运行时注入误报 | 0（已排除 `--rc/--dc/--pc/--p/--cat` 与 `--el-*`） |
| `vite build` | ✓ |
| `smoke.mjs` 19 条路由 | ✓ 全绿，无运行时错误 |
| 后端 `pytest` | ✓ 398 通过（未受影响） |

---

### D3｜TypeScript 基础设施 ✅ 已完成（2026-10-11）

**目标**：装好车道，不强制所有车都上路。

**新增**

| 文件 | 说明 |
|---|---|
| `frontend/tsconfig.json` | `allowJs:true` + **`checkJs:false`**（存量 JS 不参与检查）+ `strict:true` + `isolatedModules:true` + `noEmit:true`；`paths` 的 `@/*` 与 `vite.config.js` 的 alias 对齐 |
| `frontend/src/env.d.ts` | 只放 `/// <reference types="vite/client" />` |

**`env.d.ts` 故意不写 `declare module '*.vue'` 兜底**。那种写法会把每个 .vue 导入都退化成
`DefineComponent<{},{},any>`，props 全变 `any`、传错 prop 不再报错——正好抵消「新组件有类型」这个全部收益。
该声明只对纯 `tsc` 有意义；vue-tsc 原生解析 .vue，不需要也不应该加。

**改造**
- `package.json` 加 `"typecheck": "vue-tsc --noEmit"`（**不进 build 链路**）
- `typescript` 钉在 `^5.9`（TS 7 的 Go 编译器删掉了 vue-tsc 依赖的 `./lib/tsc` 子路径，会直接崩）
- `scripts/audit-css-tokens.mjs` 补上**退出码**：A 类 > 0 时 `exit 1`
- CI 前端 job 加 `npm run typecheck` 与 `npm run audit:tokens`

**验证（含「假绿」自检）**

| 项 | 结果 |
|---|---|
| `npm run typecheck`（空跑） | ✓ exit 0 |
| 故意放一个 `.ts` 类型错误 | ✓ 报 `TS2322`，exit 2 —— 证明**真的在检查** |
| 故意放一个 `lang="ts"` 的 `.vue` 类型错误 | ✓ 同样被捕获 —— 证明 .vue 链路通 |
| 故意引一个不存在的 CSS 变量 | ✓ `audit:tokens` exit 1 —— 证明**门禁真的会拦** |
| `vite build` | ✓ 不受影响 |
| `smoke.mjs` 19 条路由 | ✓ 全绿 |

**顺带完成第一例真实迁移**：`utils/lookup.js` → `utils/lookup.ts`（带 `NamedRow` 接口与泛型），
11 个调用点无需改动（Vite 按扩展名解析）。
同时删掉了 D2 里我顺手加的 `nameBy()`——它**没有任何调用方**，
正是 D2 自己批评过的「投机性死代码」，不该留着。

---

### D4｜拆分 `BrowserStudio.vue`（1417）—— 建立拆分范式 ✅ 已完成（2026-10-11）

**目标**：确立「**组件管展示 + 共享样式表管跨组件样式 + 壳只管取数/轮询/动作编排**」的范式。

**实际落地结构**（`BrowserStudio.vue` 1412 → **265 行**）
```
views/browser-studio/
  RunListPanel.vue          # 84  左：运行列表（纯展示 + select/create/refresh 三个上抛）
  RunDetailPanel.vue        # 595 右：详情（9 步流水线 + 逐轮产出 + 过审评分卡 + 终稿 + 背景资料）
                            #      空状态也在它内部（右栏本来就是「要么详情，要么提示去选」）
  CreateRunDialog.vue       # 383 新建向导（5 步），自取内容库/凭证数据
  PrecheckDialog.vue        # 157 发布前预检，自取预检结果
  RewriteDialog.vue         # 211 文章改写
  studio-shared.css         # 33  跨子组件复用的类（.mode-chip 配色 / .pc-tip）
views/BrowserStudio.vue     # 265 壳：横幅 + 空状态 + 两栏容器 + 5 个组件装配 + 取数/轮询/动作
```

**与原计划的偏差（有意为之，不是缩水）**
- 计划里 `RunDetailPanel` 下面还要再切 `StepPipeline` / `AiRoundsPanel` / `ReviewScoreCard` / `FinalDraftPanel`
  四块。**实际没切**：这四块共享同一份派生计算（`review` / `geoDims` / `reviseList` / `mdx*`），
  拆开后要么把 15 个 computed 逐层透传（props 爆炸，正是洞 6 描述的天花板），
  要么每块各自重算一遍（重复实现）。**595 行是一个连贯单元，不是巨石**——它的每一段都只服务「渲染一条运行」。
- 计划里的 `composables/useBrowserStudioRuns.js` 等三个 composable **没建**：壳现在只有
  ~110 行脚本（取数 + 轮询 + 6 个动作），已经没有值得再抽的逻辑。**先有重复，再抽 composable**；
  没有重复就抽，只是把「一处代码」拆成「两个文件」。
- `studio-shared.css` 的门槛执行得更严：只放了 `.mode-chip`（被运行列表 + 向导平台卡片共用）
  和 `.pc-tip`（被预检 + 改写弹窗共用）。计划里提到的 `.agent-*` / `.round-text` / `.issue-chip` /
  `.copy-row` **全部只被 RunDetailPanel 一个组件用**，所以留在它的 scoped style 里——共享表不是杂物间。

**D4 期间抓到并修掉的 4 个真缺陷**（都是「拆分必先修地基」的实证）
1. **壳的 `onMounted` 仍调用 `loadOptions()`**，而该函数已随向导搬走 → `ReferenceError`，
   导致后面的 `loadRuns()` 永不执行，**运行列表恒为空**。
2. **`<CreateRunDialog>` 在模板里用了却没 import** → 组件解析失败。
3. **壳渲染 `class="tag-mode mode-chip"` 却没 import `studio-shared.css`** → 模式徽标退化成
   没有底色/颜色的裸文字。**截图里肉眼几乎看不出来**，是靠 `getComputedStyle` 量 `backgroundColor`
   才确认的（量到 `rgb(224,242,254)` 才算真生效）。
4. **壳里有一份 `platformLabel` 的重复实现**——`constants/platforms.js` 里早就有同名函数。
   这正是洞 1「同一个东西存两份」的漏网之鱼，已改为导入既有实现。

外加清理了一批**死导入**：`Plus` / `Refresh` / `Delete` / `DocumentDelete` / `DocumentCopy` 图标、
`StepLogPanel` / `ConversationPanel`、`copyText` / `markdownToPlain` / `formatDateTime`、
以及整套 `constants/browserStudio` 标签函数——它们都随各自的面板搬走了。
（本项目已两次因「拆完不清理」留下孤儿，故每次都跑一遍孤儿扫描。）

**验收**
- `BrowserStudio.vue` 265 行 < 300 ✅
- `npm run build` / `npm run typecheck` / `npm run audit:tokens` / `node scripts/smoke.mjs` 全绿 ✅
- `node scripts/shot-studio.mjs` 对 `/browser-studio` 逐项截图：主视图 / 新建向导 / 改写弹窗 /
  运行详情 / 预检弹窗 / 创作对话 ✅
- **关键：截图脚本现在带断言**，不只是截图。它断言「详情面板真的渲染了内容」——
  `非空详情容器=1、空状态容器=0、流水线步骤数=10、tabs=true`。
  这条断言已用**故意的错误**验证过会红（把 `:run="selected"` 改成 `:run="null"` → 脚本 exit 1）。
  理由：`RunDetailPanel` 拆出去后若 `run` 没传进来，页面会**静默**显示空状态——那也是一张「正常」的截图。
  只截图不断言 = 又一次「假绿」。

---

### D5｜拆分 `Knowledge.vue`（1230）+ `Keyword.vue`（1101） ✅ 已完成

**结果：`Knowledge.vue` 1230 → 338 行；`Keyword.vue` 1101 → 249 行。**

#### 实际产物（与计划的偏差见下）

```
constants/icons.js            # 图标单一真源（ICON_MAP / ICON_OPTIONS / iconOf）
constants/status.js           # +KEYWORD_TYPE_*（关键词类型标签/配色/下拉选项）、+TOPIC_STATUS_SHORT
views/knowledge/
  shared.js                   # parseTags / categoryNameOf / categoryColorOf
  knowledge-shared.css        # .kb-panel / .kb-panel-head / .kb-panel-title
  CategoryPanel.vue  ItemPanel.vue
  CategoryDialog.vue KnowledgeItemDialog.vue
  KnowledgeDetailDrawer.vue  BatchImportDialog.vue
views/keyword/
  keyword-shared.css          # .kw-panel / .kw-panel-head / .kw-panel-title
  GroupPanel.vue  KeywordItemPanel.vue
  ImportPromptBanner.vue  TopicPool.vue  MatrixView.vue
  KeywordDialog.vue  GroupDialog.vue  TopicDialog.vue  BatchImportDialog.vue
```

#### 与计划的 3 处**刻意偏离**（都按 D4 的教训「先有重复，再抽公共层」判断）

1. **没建 `components/catalog/` 这个跨视图公共层。** 计划想让 Knowledge / Keyword 共用
   `CategoryPanel` / `CatalogToolbar` / `BatchActionBar`。实际读过两边模板后发现：
   分组面板的差异不止样式 —— 关键词侧多了**拖拽排序**、多了「未分组」虚拟项、
   多了图标/颜色渲染；两边的批量条操作项也不同（知识库按分类/重要性/状态，关键词按分组）。
   强行合一会得到一个「靠 6 个 props 开关切换形态」的组件，比两份各自 100 行的实现更难改。
   → 两边各留一份，**共享的只有 CSS 与常量**。
2. **没建 `useCatalogGroups.js` / `useBatchImport.js`。** 同上：分组的 API 与状态形状两边不同；
   批量导入解析器只有关键词一处用（知识库走的是另一套 AI 抽取流程）。
   **没有第二个调用方，就不抽 composable。**
3. **没抽 `components/VirtualTable.vue`。** 知识库是卡片/行两种视图 + 拖拽排序，
   关键词是 `VirtualList` 虚拟滚动表格（8 列网格）。两者只有 `<div class="vtable">` 这个外壳名相同。
   → 只把 `.vtable` 的**基础样式**留在各自组件里，不做组件级复用。

#### 顺带收口 / 顺带修掉的

- **图标真源漂移**（计划里已点到，比预期更严重）：`Knowledge.iconOptions` 有 8 项、
  `Keyword.iconOptions` 有 9 项，**两边不一致**，且都没列 `Files`（可两边都渲染它）→ `constants/icons.js`。
- **关键词类型被抄了 4 遍**：类型筛选下拉、新建/编辑弹窗下拉、批量导入弹窗下拉，
  外加 `typeLabel()`/`typeColor()` 两个函数。拆分会把这份重复复制进 3 个新组件
  → 先收敛到 `constants/status.js` 的 `KEYWORD_TYPE_LABEL/TAG/OPTIONS`。
- **选题状态下拉**手抄了一遍「待处理/进行中/已完成」→ 改为从 `TOPIC_STATUS_LABEL` 派生。
- **`seedDefaults()` 调用了从未定义的 `loadData()`**（Knowledge）：接口成功之后抛
  ReferenceError，被外层 catch 当成失败 —— 用户看到「灌入失败」，**但数据其实已经写进去了**，
  列表还不刷新。现在 `loadData()` 有正经定义，并作为「重新拉一遍」的统一入口。
- **⚠️ 发现并修掉一个后端真缺陷**：`POST /api/account` 在**不选人设时必然 500**
  （`FOREIGN KEY constraint failed`）。原因：`models.py:104-105` 把
  `platform_id` / `persona_id` 的列默认值写成 `0`，而 `database.py:43` 开着
  `PRAGMA foreign_keys=ON`，`persona` 表里根本没有 id=0 → 插 `persona_id=0` 触发外键失败。
  `Platform.vue:302` 的 `accountForm` 初始 `persona_id: null` 且下拉可清空，所以**极易触发**；
  本机库里 `account` 表是**空的**（即该功能从未成功过）。
  **修法**：两处改成 `default=None`（同文件 `:162` / `:200` 本来就是这么写的 —— 属漏改，
  且不需要 Alembic 迁移，列本来就是 nullable）。
  **补测试**：`backend/tests/test_account_api.py`（4 条）—— 三条覆盖
  「不传人设 / 人设与平台都不传 / 传了人设」，外加一条**结构守卫**
  `test_no_foreign_key_column_has_scalar_default`，遍历 `Base.metadata` 断言
  「外键列不得有标量默认值」，拦住同一类缺陷在别的表上重演。
  后端测试 398 → **402 项**。
  **已用故意的错误验证过**：把 `persona_id` 改回 `default=0` → 3 条红
  （两条功能 + 结构守卫，守卫精确指出 `account.persona_id = 0`），改回即绿。

#### 验收（全部绿）

`npm run build` / `npm run typecheck` / `npm run audit:tokens`（A 类 = 0）/
`node scripts/smoke.mjs`（19 路由）/ `node scripts/shot-knowledge.mjs` / 孤儿扫描 0 项 /
后端 `pytest`（402 项）+ `ruff check .` 0 告警。

`shot-knowledge.mjs` 本轮被**大幅加强**，因为原有断言只在**空库**上验证，
等于「断言在空数据上假过」：

- 造数扩到 **平台 / 账号 / 选题**（原先只造知识库+关键词），
  否则 `TopicPool` 与 `MatrixView` 这两个新组件**只在空状态下被验证**；
  账号**故意不传 `persona_id`** —— 正好端到端回归上面那个 500 缺陷；
- 断言从「渲染出卡片**或**空状态」收紧为「**必须**渲染出卡片且空状态为 0」；
- 矩阵额外断言三层都透传：平台卡 → 账号行 → 选题行，且**账号名正确**（证明数据真的流下去了）；
- 修掉脚本自身的泄漏缺陷：`seed()` 原先在 `try` **外面**，造数中途失败时
  `finally` 里的 `cleanup` 不会执行，标记数据永久残留（修 account 500 时实际漏了三张表）。

**两类新检查都用故意的错误证明过会红**：
- 孤儿扫描器注入「未使用 import + 未导入组件 + 嵌套模板 + 多行 import」→ exit 1；
- `shot-knowledge.mjs` 把 `:matrix="matrix"` 改成 `:matrix="[]"` → 4 条断言红，改回即绿。

---

### D6｜拆分 `Production.vue`（1210）+ `PromptLibrary.vue`（1138）

**`Production.vue` 是逻辑巨石**（script 810 行），本包的重点是**用 composable 拆逻辑，不是拆模板**（模板早就拆完了）。

**新增**
```
views/production/
  production-shared.css     # 已有 step-shared.css 的归并
composables/
  useProductionTasks.js     # 任务列表 + 草稿保存 + 行业联动
  useStepSelections.js      # 关键词/知识点/规则 的选中集合
  usePromptRender.js        # 渲染 + 自定义变量（收掉模块级 let）
  useGeoFinalize.js         # GEO 闸门 + 定稿
  useOneClickGenerate.js    # 一键生成
```
- 把给 `StepFinal` 的 ~30 个函数 props 改为**注入 composable 返回值**或 `provide/inject` 一个「工作台服务」对象
- 孤儿 CSS 已在 D2 归还给 `VersionHistoryDialog.vue` / `OneClickGenerateResult.vue`（见洞 5），此处无需再处理

**`PromptLibrary.vue`**：拆 `PromptEditorDialog`（三栏：变量面板 / 编辑器 / 预览）+ 变量检测 composable；
`META_PROMPT`（50 行字面量）搬进 `constants/prompts.js`。

**验收**：`Production.vue` script < 300 行；build + smoke 通过。

---

### D7｜统一三栏工作台 + 菜单单一来源

**目标**：把前 4 包拆出的面板，装进统一的 `WorkbenchLayout`（左·中·右三槽 + 可折叠）。

```
components/layout/WorkbenchLayout.vue
  <slot name="aside">   左：分组 / 导航
  <slot name="main">    中：列表 / 主工作区
  <slot name="detail">  右：详情 / 编辑（可折叠、可空）
```

- `Knowledge` / `Keyword` → `aside=分组, main=列表, detail=详情抽屉`
- `BrowserStudio` → `aside=运行列表, main=详情`（右栏暂空，留扩展位）
- `Production` → `aside=任务列表, main=工作区`

**同时修洞 4**：`Layout.vue` 的 `menuGroups` 改为从 `router.getRoutes()` 按 `meta.group` 派生，
删掉手工维护的第二份事实。`badge` 这类菜单独有的元数据补进路由 `meta`。

**验收**：三栏布局在各页视觉一致；改路由 meta 后菜单自动跟随；build + smoke 通过。

---

## 七、优先级与执行顺序

| 包 | 收益 | 风险 | 依赖 | 建议 |
|---|---|---|---|---|
| **D2 地基修复** | 高（修 7 个静默失效 + 消灭重复源头） | 低 | 无 | ✅ 已完成 |
| **D3 TS 基础设施** | 中（后续新组件直接用类型） | 低 | 无 | ✅ 已完成 |
| **D4 拆 BrowserStudio** | 高（确立范式） | 中 | D2 D3 | ✅ 已完成 |
| **D5 拆 Knowledge/Keyword** | 高 | 中 | D4 | ✅ 已完成 |
| **D6 拆 Production/PromptLibrary** | 高（逻辑巨石最难） | 中高 | D4 D5 | **下一个** |
| **D7 三栏工作台 + 菜单单一来源** | 中高 | 中 | D4–D6 | 最后 |

**执行顺序：`D2 → D3 → D4 → D5 → D6 → D7`**

理由：**D2 必须最先**——如果先拆视图，那 7 个失效的 CSS 变量、8 份日期实现、5 种信封读法
会被**复制进每一个新文件**，之后再修要改 N 倍的地方。
D3 紧随其后，是为了让 D4 起的新组件一开始就带类型，避免二次返工。

---

## 八、回归保障（每一步都要能证明「没坏」）

| 手段 | 命令 | 覆盖 |
|---|---|---|
| 后端全量测试 | `pytest`（当前 **402** 项） | 后端零回归 |
| 前端构建 | `npm run build` | 编译期错误 |
| **真实渲染冒烟** | `node scripts/smoke.mjs`（19 路由，已修为登录后真实渲染） | 运行时错误 |
| CSS 令牌审计 | `npm run audit:tokens`（**A 类 > 0 即 exit 1**，已是 CI 门禁） | 设计令牌完整性 |
| 类型检查（D3 起） | `npm run typecheck`（CI 门禁） | 新代码类型 |
| 视觉验收 | `node scripts/shot-d2.mjs` 等 | 改动的视图实际长什么样 |
| **视觉 + 结构断言**（D4 起） | `node scripts/shot-studio.mjs`（**断言失败即 exit 1**） | 「拆出去的组件真的渲染了内容」而非静默退化成空状态 |
| **孤儿扫描**（D5 起） | `python scripts/_orphan-scan.py <*.vue>` | import 了没用到的绑定 / 模板里用了但没 import 的组件 |
| **视觉 + 结构断言**（D5） | `node scripts/shot-knowledge.mjs`（**先造幂等标记数据 → 断言 → finally 清理**） | 知识库 / 关键词 / 选题池 / 矩阵 四条链路真的渲染出内容 |

**每个包收尾必须全绿**，并在 `.workbuddy-ai/memory/YYYY-MM-DD.md` 记录「做了什么 / 踩了什么坑 / 验收结果」。

> ⚠️ **验收手段本身也要被验收**。本项目已经吃过两次「假绿」的亏：
> `smoke.mjs` 不登录 → 19 条「✓」其实是登录页渲染了 19 次；
> `audit-css-tokens.mjs` 只打印不 exit → 永远拦不住任何东西。
> 新增任何检查项时，**必须先用一个故意的错误证明它会红**，再相信它的绿。
>
> D4 新增的两类检查也都按这条规矩验过：
> - `shot-studio.mjs` 的详情断言 —— 把 `:run="selected"` 改成 `:run="null"`，确认脚本 exit 1；
> - 「模式徽标有底色」—— 用 `getComputedStyle` 量 `backgroundColor` 是否为透明，
>   而不是靠肉眼看截图（裸文字和有色徽标在缩略图里几乎分不出来）。
>
> D5 又添了第三次「假绿」教训，而且这次是**我自己刚写的工具**：
> `_orphan-scan.py` 第一版有两个 bug，**都能让它永远报不出问题** ——
> ① 边界正则写成 `[\s:@{(\[,]|^name`，`|` 的优先级让字符类变成独立分支，
> 于是任意空白都算命中，每个名字都被判成「用过」；
> ② 用 `<template>(.*?)</template>` 抽模板，遇到根模板里的 `<template #dropdown>`
> 会在第一个内层 `</template>` 处截断，后半段组件全被判成没用过。
> 另外还漏了「Element Plus 图标在 `main.js` 里全量全局注册」这一事实，会把 `<Memo>` 误报。
> **这三个 bug 只有靠「故意注入错误文件」才能发现 —— 直接跑在真实文件上时它是一路「ok」的。**
>
> 还有一个**数据层面的假绿**：`shot-knowledge.mjs` 原先只在**空开发库**上断言，
> 「列表有内容」这类断言要么恒失败、要么放宽成「不报错」而等于没断言。
> 现在改为**先造幂等标记数据 → 断言 → finally 清理**，
> 并且把 `seed()` 放进 `try` 内（否则造数中途失败时 `cleanup` 不执行，标记数据永久残留）。

---

## 九、一句话总结

**巨石视图的病因不是「行数多」，是「职责混在一起」——`Production.vue` 拆了 10 个子组件，script 反而涨到 810 行，就是最好的证明。**

最该借的三样：
1. **官方那句「抽取组合式函数也是为了代码组织」**——先按逻辑问题拆 composable，再按展示职责拆组件
2. **非 scoped 共享样式表**——项目已有的 `step-shared.css` 先例，是拆 scoped CSS 的现成解法
3. **渐进式 TypeScript（`allowJs` + 新代码 `lang="ts"`）**——不搞一次性全量改写

最不该做的：**跳过地基直接拆视图**。那 7 个静默失效的 CSS 变量和 5 种 API 信封读法，
会被忠实地复制进每一个新文件——拆分本该是降低复杂度，跳过地基就会变成放大缺陷。
