# 阶段 D · D7 三栏工作台 + 菜单单一来源 · 调研与实施方案

> 上游：`docs/PhaseD-前端重构-借鉴评估与实施方案.md`（本文件是其 D7 小节的展开）
> 前置：D1–D6 已完成（5 个巨石视图全部拆完）
> 调研日期：2026-10-11
> 状态：**实施中**

---

## 一、家底：D7 到底要动什么

### 1.1 计划里写的 D7

> **目标**：把前 4 包拆出的面板，装进统一的 `WorkbenchLayout`（左·中·右三槽 + 可折叠）。
> **同时修洞 4**：`Layout.vue` 的 `menuGroups` 改为从 `router.getRoutes()` 按 `meta.group` 派生。
> **验收**：三栏布局在各页视觉一致；改路由 meta 后菜单自动跟随；build + smoke 通过。

### 1.2 实证一：**「三栏」不存在，真实重复的是「两栏」**（5 处）

D4–D6 拆完之后，我逐文件量了每处工作台布局的**实际 CSS**：

| 视图 | 容器类 | 左栏宽度 | gap | `align-items` | 高度策略 |
|---|---|---:|---:|---|---|
| `Knowledge.vue` | `.kw-layout` | `220px` | 16 | `start` | 无 |
| `Keyword.vue` | `.kw-layout` | `232px` | 16 | 默认 | `min-height: 500px` |
| `IntentQuestion.vue` | `.iq-body` | `268px` | 16 | `stretch` | `min-height: 540px` |
| `Production.vue` | `.prod-layout` | `320px` | 20 | 默认 | `flex: 1; min-height: 0` |
| `BrowserStudio.vue` | `.studio__body` | 无（flex） | 16 | `stretch` | `height: 100%` |
| （另）`production/steps/step-shared.css` | `.two-col-layout` | `320px` | 18 | 默认 | `min-height: 520px` |

**结论：同一个「左栏 + 主区」结构被抄了 6 份，宽度有 5 个值、gap 有 4 个值、高度策略有 5 种。**
这就是真正的重复。计划里假设的「三栏」在代码里**一处都不存在**——所有页面的「详情」要么是 `el-drawer`
浮层（Knowledge / Keyword），要么本来就长在右栏里（BrowserStudio 的运行详情、Production 的工作区）。

> 这与 D5 的教训完全同构：**计划里的 `components/catalog/` 公共层最终没建，因为「两边差异大于共性」。**
> 所以 D7 也必须先证伪，再动手 —— 不能照着计划里的目录结构硬套。

### 1.3 实证二：**「同一份事实被抄了三遍」，已实测漂移**

| 来源 | 性质 | 现状 |
|---|---|---|
| `router/index.js` 的 `meta` | 路由真源 | 23 条业务路由，含 `title/subtitle/group/icon` |
| `Layout.vue` 的 `menuGroups` | **手工第二份** | 23 项，组顺序与路由**不同**，含 `badge` |
| `scripts/smoke.mjs` 的 `ROUTES` | **手工第三份** | **只有 19 条**，静默漏掉 4 条 |

实测证据（浏览器里读真实 DOM）：

```
侧边栏渲染：7 组 / 23 项
组顺序(菜单)：工作台 → 内容生产 → 品牌资产 → 基础配置 → AI配置 → GEO 作战 → 发布自动化
组顺序(路由)：工作台 → 内容生产 → 品牌资产 → 基础配置 → AI配置 → 发布自动化 → GEO 作战   ← 不同
标题漂移    ：/publish  meta.title='发布自动化'  vs  菜单='发布中心'
冒烟漏测    ：/prompt-center、/settings、/publish、/manual 从未被 smoke 访问过
```

`/publish` 的漂移还有个副作用：它的 `meta.group` 也叫「发布自动化」，于是顶栏会渲染成
**「发布自动化 / 发布自动化」**——组名和标题一模一样，用户看不出层级。

### 1.4 外部调研结论

| 来源 | 结论 | 我们的取舍 |
|---|---|---|
| **Vue Router 官方**《Route Meta Fields》 | `route.meta` 是**父→子非递归合并**；可用 `declare module 'vue-router'` 扩展 `RouteMeta` 获得类型 | 用 `meta` 承载菜单元数据；D3 已开 TS，可在 `src/types/router.d.ts` 扩展（本轮先不引入，避免与 `allowJs` 渐进策略打架） |
| **vue-element-admin**《路由和侧边栏》 | 侧边栏**完全由路由派生**；`hidden: true` 排除（login/404/编辑页）；`meta.activeMenu` 让 `/article/1` 高亮 `/article/list`；**404 必须声明在最后** | 采纳「由路由派生」与 `hidden`；`activeMenu` 本轮不需要（我们的详情是浮层，`route.path` 不变）；404 我们已经放在最后 |
| **Forge Admin** `MasterDetailWorkspace` | 主从布局容器：左母版 / 右工作区，支持**折叠、分离、自适应堆叠** | 采纳其 API 形状：`aside/main` 两槽 + 宽度与折叠可配 + 窄屏堆叠 |
| **Vue 官方**《组合式函数》 | 抽 composable 是「为了代码组织」，不只是复用 | `buildMenuGroups()` 做成**纯函数**放 `constants/`，可被任何地方复用，且能被断言 |

---

## 二、决策：借什么、不借什么

### 借

| # | 借 | 落点 |
|---|---|---|
| 借 1 | **菜单由 `router.getRoutes()` 派生**，删掉手工 `menuGroups` | `src/constants/menu.js` + `Layout.vue` |
| 借 2 | **菜单独有元数据补进 `meta`**（`badge` / `hidden`），而不是另起一份 | `router/index.js` |
| 借 3 | **组顺序 = 路由声明顺序**（把路由重排成菜单该有的顺序，而不是再写一份排序表） | `router/index.js` |
| 借 4 | **`WorkbenchLayout` 三槽容器**，宽度/间距/对齐/高度由 props → CSS 变量驱动 | `components/layout/WorkbenchLayout.vue` |
| 借 5 | **验收脚本自证**：新增 `shot-menu.mjs` / `shot-workbench.mjs`，用计算样式与真实 DOM 断言 | `scripts/` |

### 不借（写清楚，避免下一个人"补全"）

| 不借 | 原因 |
|---|---|
| **把 `el-drawer` 详情改成内联第三列** | 那是**交互变更**（浮层 → 常驻列），不是重构。`WorkbenchLayout` 保留 `detail` 槽备用，但**当前无调用方**，不为了"凑三栏"去改 UX |
| **递归多级菜单组件** | 本项目只有「组 → 项」两级，没有嵌套子菜单。递归组件是纯负债 |
| **把布局状态塞进 Pinia** | 布局是**视图局部**的。跨视图的只有侧边栏折叠，那已经在 `store/app.js` 里 |
| **追求"零 props 的万能布局"** | 5 处的宽度/对齐/高度策略**确实不同**。用 5 个 props 显式表达，好过 5 份复制粘贴——这与 D5「拒绝靠 6 个 props 切换形态」不矛盾：**D5 拒绝的是把两个不同实体硬塞进一个组件，这里面对的是同一个实体** |
| **`::v-deep` 穿透统一卡片样式** | 会把父子重新耦合（假拆分） |
| **容器查询（`@container`）做自适应** | 项目现有断点是全局 `@media (max-width: 1024px)`，换成容器查询会让同一页面在不同父容器下行为不一致，反而更难排查 |

### ⚠️ 与计划的偏离（需要知会）

计划写的是「左·中·右**三**槽」。实证结果是**两**槽 + 一个备用槽。本方案按实证执行：
`WorkbenchLayout` 提供 `aside` / `main` / `detail` 三个插槽，但**只接两槽**；`detail` 槽留空位，
在组件注释里写明「当前无调用方，不要为了用它而改 UX」。**这是刻意的**，理由见上表第 1 行。

---

## 三、实施步骤

### D7-1 菜单单一来源（低风险，先做）

1. `src/constants/menu.js`
   - `buildMenuGroups(routes)` —— 纯函数：过滤 `meta.group` 为空的记录（含 `NotFound` 的 `hidden`），
     按**首次出现**分组，组顺序 = 声明顺序，项顺序 = 声明顺序。
   - 返回 `[{ title, items: [{ path, title, icon, badge }] }]`
2. `router/index.js`
   - 把 `发布自动化` 组的路由块**移到 `GEO 作战` 之后**，使声明顺序 = 期望菜单顺序
   - 补 `meta.badge`（`content: 'NEW'`、`brand-asset: 'NEW'`、`prompt-library: '4类'`、
     `prompt-center: '收口'`、`settings: 'NEW'`、`geo-canvas: 'NEW'`、`geo-visibility: 'NEW'`、
     `geo-loop: 'NEW'`、`pipeline: 'NEW'`、`publish: 'NEW'`、`browser-studio: 'NEW'`、
     `automation-studio: 'NEW'`）
   - 给 `NotFound` 加 `meta.hidden = true`
   - **修标题漂移**：`/publish` 的 `meta.title` 由 `发布自动化` 改为 `发布中心`（与菜单一致，
     同时消掉顶栏「发布自动化 / 发布自动化」）
3. `Layout.vue`：删除手工 `menuGroups`，改 `buildMenuGroups(router.getRoutes())`

### D7-2 WorkbenchLayout（中风险，后做）

1. `components/layout/WorkbenchLayout.vue`
   ```
   props:  asideWidth('280px') / gap('16px') / align('stretch') / fill(false) / minHeight('') / collapsed(false)
   slots:  aside / main / detail(备用)
   ```
   - root 元素**就是** grid 容器（不额外包一层），保证 `class="prod-layout"` 之类的
     **验收钩子类名可以透传**（Vue 3 attrs fallthrough）
   - `≤1024px` 自动单列（沿用现有 `.kw-layout` 的断点）
   - `collapsed` 把左栏宽度归零（不内置按钮，由使用方接自己的折叠按钮）
2. 接入 5 处：`Knowledge`(220/start) → `Keyword`(232) → `IntentQuestion`(268) → `Production`(320/fill)
   → `BrowserStudio`(fill)，删掉各自重复的 grid 规则
   - **保留** `.kw-layout` / `.prod-layout` / `.task-panel` / `.iq-body` 等类名（它们是验收脚本的钩子）
   - `gap` 统一为 16px（Production 的 20px 一并归一）——这正是「视觉一致」的验收点

---

## 四、验收标准

| 项 | 标准 |
|---|---|
| 菜单跟随 | 只改 `router/index.js` 的 `meta`，侧边栏标题/顺序/徽标自动跟随（由 `shot-menu.mjs` 断言） |
| 无第二份事实 | `Layout.vue` 里不再出现任何 `title: '…'` 的菜单字面量 |
| 冒烟无漏测 | `smoke.mjs` 的清单必须覆盖侧边栏全部链接（新守卫，缺一条即红） |
| 布局一致 | 5 处工作台走同一组件；`getComputedStyle().gridTemplateColumns` 逐页断言 |
| 窄屏 | ≤1024px 全部退化为单列 |
| 护栏有牙齿 | `shot-menu.mjs` / `shot-workbench.mjs` **各用故意注入的缺陷证明会红** |
| 回归 | build + typecheck + audit:tokens(A 类=0) + smoke + 全部 `shot-*` + 孤儿扫描 0 + 后端 pytest/ruff |

---

## 五、实施记录与验收（2026-10-11 完成）

### 5.1 D7-1 菜单单一来源

| 改动 | 文件 |
|---|---|
| 新增纯函数 `buildMenuGroups(routes)` | `frontend/src/constants/menu.js`（新） |
| 子路由按菜单顺序重排 + 补 `meta.badge` + `NotFound` 加 `hidden` + `/publish` 标题修正 | `frontend/src/router/index.js` |
| 删除手工 `menuGroups`（46 行），改为 `buildMenuGroups(router.getRoutes())` | `frontend/src/components/Layout.vue` |
| 补齐 4 条漏测路由 + 新增「冒烟清单必须覆盖侧边栏」守卫 | `frontend/scripts/smoke.mjs` |
| 新增菜单结构验收 | `frontend/scripts/shot-menu.mjs`（新） |

**实测修复的漂移**：

- 组顺序：`发布自动化` 由「GEO 作战」之前移到之后（与菜单一致）
- `/publish` 标题：`发布自动化` → `发布中心`，顶栏不再出现「发布自动化 / 发布自动化」
- 冒烟覆盖：19 → **23** 条（此前 `/prompt-center`、`/settings`、`/publish`、`/manual` 从未被访问）

**护栏变红证据**（注入 → 构建 → 跑 → 还原）：

| 注入 | 变红的断言 |
|---|---|
| `/publish` 标题改回 `发布自动化` | 逐项一致 / `/publish` 标题 / 顶栏同名 → 3 条 |
| 去掉 `/content` 的 `meta.badge` | 逐项一致（`/content 徽标：期望「NEW」，实际「」`） |
| 把「发布自动化」整组挪回 GEO 之前 | 分组顺序 / 逐项一致（路径整体错位）→ 2 条 |
| 冒烟清单删掉 `/manual` | 覆盖守卫：`以下侧边栏页面从未被测试：/manual` |

合计 **4 项失败**，逐条对得上注入的缺陷。

### 5.2 D7-2 WorkbenchLayout

| 改动 | 文件 |
|---|---|
| 新增两栏工作台容器 | `frontend/src/components/layout/WorkbenchLayout.vue`（新） |
| 接入（220px / align=start） | `frontend/src/views/Knowledge.vue` |
| 接入（232px / min-height 500px） | `frontend/src/views/Keyword.vue` |
| 接入（268px / min-height 540px） | `frontend/src/views/IntentQuestion.vue` |
| 接入（320px / fill） | `frontend/src/views/Production.vue` |
| 接入（300px / fill）+ `.studio` 改 flex 列 | `frontend/src/views/BrowserStudio.vue` |
| 栏宽上交给布局容器（删 `width:300px`） | `frontend/src/views/browser-studio/RunListPanel.vue` |
| 新增布局验收 | `frontend/scripts/shot-workbench.mjs`（新） |

**关键设计：槽位包裹元素用 `display: contents`。**
它不产生盒子，使用方传进来的元素因此**仍然是 `.wb` 的直接网格项** —— 与 D7 之前「子元素就是网格项」的写法逐字等价。
若换成普通块级盒子，会多出一层，`.task-panel` / `.iq-side` 这类没写 `height:100%` 的子元素会**静默塌成内容高度**。
`shot-workbench.mjs` 用「左栏子元素高度 === 容器高度」+「包裹元素 display 值」两条断言把这条约束钉住。

**顺带归一**：Production 的栏间距 20px → 16px（各页统一，这是「视觉一致」的验收点）。

**护栏变红证据**：

| 注入 | 变红的断言 |
|---|---|
| 槽位包裹元素 `display:contents` → `block` | 5 页的「包裹元素 display」+ 4 页的「左栏等高」→ 9 条 |
| Production `aside-width` 320px → 280px | 列轨道 + 左栏宽度 → 2 条 |
| 单列断点 1024px → 320px | 5 页的「≤1024px 退化为单列」→ 5 条 |

合计 **16 项失败**。
⚠️ 值得记一笔：注入 `display:block` 时，**「左栏子元素实际宽度 = 栏宽」这条断言依然全绿**
（块级包裹层仍会把栏宽传给子元素）—— 只靠宽度断言根本发现不了这个缺陷。
这正是必须补「等高」与「包裹元素 display」两条断言的原因。

### 5.3 与计划的偏离（两处，均已在此说明）

1. **「三栏」→「两栏 + 预留槽」**：实证是没有任何页面是三栏（详见 1.2）。`detail` 槽保留但无调用方。
2. **`collapsed` 折叠能力未接入任何页面**：组件的 `collapsed` prop 已实现并可用于窄屏，
   但当前**没有页面接折叠按钮** —— 接它属于功能变更（要加按钮、要定交互），不该混在重构里。
   等真有页面需要时再单独走一次验收。

### 5.4 全量回归（全部绿）

```
build ✅            typecheck ✅          audit:tokens A 类 = 0 ✅
smoke 23 路由 ✅     shot-menu ✅          shot-workbench ✅
shot-studio ✅       shot-knowledge ✅     shot-production ✅
shot-prompt-library ✅  shot-pipeline ✅  shot-brand ✅  shot-d2 ✅
孤儿扫描 0 项 ✅     后端 402 项 + ruff 0 告警 ✅
```

顺带修掉 `IntentQuestion.vue` 两个**历史遗留**的孤儿 import（`Rank` / `Download`，参照副本里也没有用到）——
D4–D6 没碰过这个文件，所以一直留着；本轮既然动了它就一并清理。
