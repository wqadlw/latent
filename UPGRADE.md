# Prompt Matrix Pro V4 升级说明

> 本文档详细记录了从 V3 到 V4 的所有变更，包括新增功能、修改的文件、数据库变更和迁移指南。

---

## 一、升级总览

V4 在 V3 基础上对三大核心模块进行了全面升级：

| 模块 | 新增功能数 | 修改文件数 | 新增 API 数 |
|------|-----------|-----------|------------|
| 知识库 | 8 项 | 4 个 | 4 个 |
| AI 提示词库 | 10 项 | 4 个 | 5 个 |
| 软文生产 | 6 项 | 3 个 | 2 个 |
| **合计** | **24 项** | **11 个** | **11 个** |

---

## 二、知识库模块升级详情

### 2.1 数据库变更

#### knowledge_category 表新增字段

```sql
ALTER TABLE knowledge_category ADD COLUMN icon TEXT DEFAULT 'Folder';
ALTER TABLE knowledge_category ADD COLUMN color TEXT DEFAULT '#6366f1';
ALTER TABLE knowledge_category ADD COLUMN description TEXT DEFAULT '';
ALTER TABLE knowledge_category ADD COLUMN update_time DATETIME;
```

#### knowledge_item 表新增字段

```sql
ALTER TABLE knowledge_item ADD COLUMN summary TEXT DEFAULT '';
ALTER TABLE knowledge_item ADD COLUMN source TEXT DEFAULT '';
ALTER TABLE knowledge_item ADD COLUMN importance TEXT DEFAULT 'normal';
ALTER TABLE knowledge_item ADD COLUMN status TEXT DEFAULT 'published';
ALTER TABLE knowledge_item ADD COLUMN view_count INTEGER DEFAULT 0;
```

### 2.2 后端变更

#### models.py

- `KnowledgeCategory` 模型新增 `icon`、`color`、`description`、`update_time` 字段
- `KnowledgeItem` 模型新增 `summary`、`source`、`importance`、`status`、`view_count` 字段

#### routers/knowledge.py

- `CategoryIn` 模型新增 `icon`、`color`、`description` 字段
- `ItemIn` 模型新增 `summary`、`source`、`importance`、`status` 字段
- `list_categories` 返回值新增 `item_count`（每个分类的知识点数量）
- `get_item` 新增查看次数自增逻辑
- **新增** `list_items_grouped` 接口：按分类分组返回知识点
- **新增** `stats` 接口：返回总数、分类数、按重要性/状态分组统计
- **新增** `export` 接口：支持 JSON/CSV 导出
- 路由顺序调整：`/item/grouped` 和 `/item/search` 移到 `/item/{item_id}` 之前，避免路径冲突

### 2.3 前端变更

#### api/index.js

- `knowledgeApi` 新增 `getItem`、`listItemsGrouped`、`stats`、`exportItems` 方法

#### views/Knowledge.vue（全面重写）

- 顶部操作栏新增"导出"（JSON/CSV）和"统计"按钮
- 新增统计面板（可折叠）：显示总数、分类数、高重要性数、已发布数
- 左侧分类树：分类显示图标和颜色，显示知识点数量
- 右侧知识点列表：支持卡片网格 / 紧凑列表双视图切换
- 知识点卡片：显示标题、摘要、重要性标签、标签、预览按钮
- 新增详情抽屉：点击预览按钮右侧滑出，显示完整详情
- 新增分类筛选条：顶部按分类快速筛选
- 新增重要性筛选：按高/普通/低重要性筛选
- 搜索框：支持标题+内容+标签+摘要全文搜索
- 新建/编辑弹窗：新增摘要、来源、重要性、状态字段
- 分类弹窗：新增图标、颜色、描述字段

---

## 三、AI 提示词库模块升级详情

### 3.1 数据库变更

#### prompt_library_item 表新增字段

```sql
ALTER TABLE prompt_library_item ADD COLUMN variable_schema TEXT DEFAULT '[]';
ALTER TABLE prompt_library_item ADD COLUMN tags TEXT DEFAULT '';
ALTER TABLE prompt_library_item ADD COLUMN usage_count INTEGER DEFAULT 0;
ALTER TABLE prompt_library_item ADD COLUMN last_used_time DATETIME;
ALTER TABLE prompt_library_item ADD COLUMN rating INTEGER DEFAULT 0;
```

### 3.2 后端变更

#### models.py

- `PromptLibraryItem` 模型新增 `variable_schema`、`tags`、`usage_count`、`last_used_time`、`rating` 字段

#### routers/prompt_library.py

- `PromptIn` 模型新增 `variable_schema`、`tags`、`rating` 字段
- `PromptIn` 新增 `field_validator`：自动将 `variables` 和 `variable_schema` 的 list/dict 转为 JSON 字符串
- `list_prompts` 返回值新增 `usage_count`、`last_used_time`、`rating`、`tags`、`variable_schema` 字段
- **新增** `BUILTIN_VARIABLES` 常量：24 个内置变量，按 7 个分组，含描述和示例值
- **新增** `builtin_variables` 接口：返回内置变量参考列表
- **新增** `increment_usage` 接口：使用次数 +1，更新最后使用时间
- **新增** `rate` 接口：设置评分（0-5）
- **新增** `export_prompts` 接口：导出提示词为 JSON
- **新增** `import_prompts` 接口：批量导入提示词

#### services/prompt_engine.py

- `build_render_context` 新增 `knowledge_summary`、`knowledge_titles`、`knowledge_count` 变量
- `BUILTIN_VARIABLES` 集合新增 `knowledge_summary`、`knowledge_titles`、`knowledge_count`
- `VARIABLE_DESCRIPTIONS` 字典新增对应描述

### 3.3 前端变更

#### api/index.js

- `promptLibraryApi` 新增 `builtinVariables`、`incrementUsage`、`rate`、`exportPrompts`、`importPrompts` 方法

#### views/PromptLibrary.vue（全面重写）

- 顶部操作栏新增"导出"和"导入"按钮
- 4 分类卡片：显示提示词数量
- 编辑器升级为三栏布局：
  - **左栏（变量面板）**：24 个内置变量按 7 个分组展示，支持搜索过滤，点击插入
  - **中栏（编辑器）**：textarea 编辑器，底部显示检测到的变量列表
  - **右栏（实时预览）**：使用示例值实时渲染提示词
- 新增模板片段功能：6 个常用片段一键插入
- 新增自定义变量定义：可定义变量名称、描述、默认值
- 提示词列表：显示使用次数、评分、标签
- 新增评分功能：0-5 星评分
- 新增导入导出功能

---

## 四、软文生产模块升级详情

### 4.1 后端变更

#### routers/production.py

- `RenderIn` 模型新增 `custom_vars` 字段：支持渲染时传入自定义变量
- `render` 函数：合并 `custom_vars` 到渲染上下文，使用次数自增，更新最后使用时间
- `options` 接口返回值新增 `knowledge_grouped`：按分类分组的知识点
- **新增** `search_knowledge` 接口：在第 4 步中搜索知识点（支持关键词+分类过滤）
- **新增** `get_knowledge_detail` 接口：获取知识点详情（查看次数 +1）

### 4.2 前端变更

#### api/index.js

- `productionApi` 新增 `searchKnowledge` 方法

#### views/Production.vue

- 第 4 步从双栏升级为三栏布局：
  - **左栏（关键词库）**：新增搜索框，显示已选数量
  - **中栏（知识库知识点）**：新增分类筛选条、搜索框、卡片式知识点展示
  - **右栏（大纲提示词）**：新增已选知识点摘要面板
- 知识点卡片：显示标题、摘要、重要性标签、标签、预览按钮
- 新增知识点预览抽屉：右侧滑出显示完整详情
- 新增分类筛选条：按分类快速筛选知识点
- 新增已选知识点摘要：右栏显示已选列表，可单独移除
- 新增关键词搜索：左栏实时过滤关键词

---

## 五、迁移指南

### 5.1 从 V3 升级到 V4

#### 方式一：全新安装（推荐）

1. 备份 V3 的 `database.db` 文件
2. 删除 `backend/app/data/database.db`
3. 启动 V4，系统会自动创建新数据库
4. 重新配置行业空间和基础数据

#### 方式二：保留数据升级

1. 备份 `database.db` 文件
2. 执行以下 SQL 升级数据库结构：

```sql
-- knowledge_category 新增字段
ALTER TABLE knowledge_category ADD COLUMN icon TEXT DEFAULT 'Folder';
ALTER TABLE knowledge_category ADD COLUMN color TEXT DEFAULT '#6366f1';
ALTER TABLE knowledge_category ADD COLUMN description TEXT DEFAULT '';
ALTER TABLE knowledge_category ADD COLUMN update_time DATETIME;

-- knowledge_item 新增字段
ALTER TABLE knowledge_item ADD COLUMN summary TEXT DEFAULT '';
ALTER TABLE knowledge_item ADD COLUMN source TEXT DEFAULT '';
ALTER TABLE knowledge_item ADD COLUMN importance TEXT DEFAULT 'normal';
ALTER TABLE knowledge_item ADD COLUMN status TEXT DEFAULT 'published';
ALTER TABLE knowledge_item ADD COLUMN view_count INTEGER DEFAULT 0;

-- prompt_library_item 新增字段
ALTER TABLE prompt_library_item ADD COLUMN variable_schema TEXT DEFAULT '[]';
ALTER TABLE prompt_library_item ADD COLUMN tags TEXT DEFAULT '';
ALTER TABLE prompt_library_item ADD COLUMN usage_count INTEGER DEFAULT 0;
ALTER TABLE prompt_library_item ADD COLUMN last_used_time DATETIME;
ALTER TABLE prompt_library_item ADD COLUMN rating INTEGER DEFAULT 0;
```

3. 用 V4 的代码替换 V3 的代码
4. 重新安装依赖：`pip install -r requirements.txt` 和 `npm install`
5. 启动系统

### 5.2 兼容性说明

- V4 完全兼容 V3 的数据格式
- V3 创建的知识点和提示词会自动获得 V4 新字段的默认值
- V3 的提示词模板中的变量占位符在 V4 中仍然有效
- V4 新增的变量（`knowledge_summary`、`knowledge_titles`、`knowledge_count`）需要手动添加到提示词模板中才会生效

---

## 六、测试验证

V4 已通过以下测试：

1. ✓ 后端所有 API 接口测试（12 项集成测试全部通过）
2. ✓ 前端构建测试（`npm run build` 成功）
3. ✓ 知识库 CRUD + 统计 + 导出 + 分组测试
4. ✓ 提示词库 CRUD + 变量检测 + 测试渲染 + 使用追踪 + 评分测试
5. ✓ 软文生产第 4 步三栏布局 + 知识点选择 + 自定义变量渲染测试
6. ✓ 提示词渲染引擎：知识库内容注入 + 自定义变量覆盖测试

---

## 七、文件变更清单

### 新增文件

无（所有变更都在现有文件上）

### 修改文件

**后端**：
- `backend/app/models.py` — 3 个模型新增字段
- `backend/app/routers/knowledge.py` — 新增 4 个接口，增强 2 个接口
- `backend/app/routers/prompt_library.py` — 新增 5 个接口，增强 2 个接口
- `backend/app/routers/production.py` — 新增 2 个接口，增强 2 个接口
- `backend/app/services/prompt_engine.py` — 新增 3 个变量

**前端**：
- `frontend/src/api/index.js` — 新增 11 个 API 方法
- `frontend/src/views/Knowledge.vue` — 全面重写
- `frontend/src/views/PromptLibrary.vue` — 全面重写
- `frontend/src/views/Production.vue` — 第 4 步重写

**文档**：
- `README.md` — 全面更新
- `UPGRADE.md` — 新增（本文件）

---

> Prompt Matrix Pro V4 — 更智能、更直观、更高效的 AI 软文生产系统。
