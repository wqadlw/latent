# AI Content Matrix

> 面向品牌内容运营团队的 **AI 软文生产矩阵系统**：把「行业空间 → 平台/账号/人设 → 关键词 → 知识库 → 提示词 → 软文生产 → 多平台发布」串成一条可复用、可追溯的流水线。

[![License](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)
[![Python](https://img.shields.io/badge/python-3.9%2B-3776ab.svg)](https://www.python.org/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.115-009688.svg)](https://fastapi.tiangolo.com/)
[![Vue](https://img.shields.io/badge/Vue-3.5-42b883.svg)](https://vuejs.org/)

---

## 目录

- [它解决什么问题](#它解决什么问题)
- [核心特性](#核心特性)
- [技术栈](#技术栈)
- [快速开始](#快速开始)
- [配置 LLM](#配置-llm)
- [使用流程](#使用流程)
- [三种发布模式](#三种发布模式)
- [提示词变量体系](#提示词变量体系)
- [项目结构](#项目结构)
- [数据模型](#数据模型)
- [测试](#测试)
- [打包为可执行文件](#打包为可执行文件)
- [常见问题](#常见问题)
- [贡献](#贡献)
- [开源协议](#开源协议)

---

## 它解决什么问题

内容团队做「AI 批量写稿」时，通常会在三件事上翻车：

1. **资产散** — 关键词、知识库、品牌资料、提示词散落在各个文档和聊天记录里，换个账号就要重新找一遍。
2. **不可控** — 直接把提示词丢给大模型，产出忽好忽坏，品牌信息要么漏掉、要么硬植入到过不了平台审核。
3. **不可追溯** — 一篇文章从大纲到终稿改了哪几步、用了哪版提示词，事后完全说不清。

本系统把这三件事收敛进一个**按行业隔离**的工作台：所有内容资产结构化沉淀，提示词用变量占位符与业务数据解耦，生产流程拆成 7 个可回填、可回看的步骤。

---

## 核心特性

### 内容资产

| 模块 | 能力 |
| --- | --- |
| **行业空间** | 顶层隔离实体，所有业务数据挂靠行业，互不干扰 |
| **平台 / 账号 / 人设** | 平台字数与合规等级、账号定位、人设身份与语气规则 |
| **关键词** | 关键词与关键词组管理，供生产时勾选 |
| **知识库** | 分类（图标/颜色/描述）+ 知识点（摘要/来源/重要性/状态/标签）、统计面板、JSON/CSV 导出、批量导入、按分类分组浏览、全文搜索、详情抽屉 |
| **AI 提示词库** | 4 分类（大纲/初稿/洗稿/安全）、三栏编辑器（变量面板 + 编辑器 + 实时预览）、自定义变量、使用次数追踪、0-5 星评分、JSON 导入导出 |
| **规则库** | 去 AI 味规则 / 合规规则 / AI SEO 规则三大类，可组合挂载到任务 |
| **品牌资产** | 品牌名、官网、联系方式、口号、核心产品、卖点、品牌故事 |
| **客户画像 / 意图问题** | GEO 作战用：目标客户角色、痛点、关注点，以及「目标客户会问 AI 的问题」 |

### 生产与发布

| 模块 | 能力 |
| --- | --- |
| **软文生产** | 7 步标准化流程（见下），每步可回填、可回看 |
| **内容中心** | 成稿归档、版本管理与内容资产沉淀 |
| **发布管理** | 发布任务与发布策略编排 |
| **浏览器工作室** | 浏览器自动化流水线：豆包 Web 对话创作 → 回传存档 → 搜狐号自动发布（无官方 API 时最稳的路径） |
| **GEO 监控** | 追踪品牌在 AI 回答中的收录与提及情况 |
| **自动化提示词** | 可复用的提示词编排单元 |

---

## 技术栈

| 层 | 选型 |
| --- | --- |
| 后端 | FastAPI 0.115 · SQLAlchemy 2.0 · Pydantic 2.9 · Uvicorn |
| 数据库 | SQLite（单文件，零安装零服务） |
| 前端 | Vue 3.5 · Vite 5 · Element Plus 2.8 · Pinia · Vue Router |
| 浏览器自动化 | Playwright |
| 打包 | PyInstaller（后端）、Vite build（前端） |

---

## 快速开始

### 环境要求

- Python **3.9+**（开发环境为 3.11）
- Node.js **18+**
- npm 或 pnpm

### 方式一：一键启动（推荐）

```bash
# Linux / macOS
bash start.sh

# Windows
start.bat
```

### 方式二：手动启动

```bash
# 终端 1 —— 后端
cd backend
python -m venv venv
venv/Scripts/activate        # Linux/macOS: source venv/bin/activate
pip install -r requirements.txt
python run.py                # http://127.0.0.1:8765

# 终端 2 —— 前端
cd frontend
npm install
npm run dev                  # http://localhost:5173
```

打开 `http://localhost:5173`，默认账号 **admin / admin123**。

> ⚠️ 首次登录后请立即在「设置」中修改默认密码。

### 首次使用

1. 在左侧创建或选择一个**行业空间**
2. 依次配置：平台 → 账号 → 人设 → 关键词 → 知识库 → 提示词库
3. 进入**软文生产**，新建任务并按 7 步流程操作

> 本仓库**不包含数据库文件**。首次启动时后端会自动建表并创建一个空库，无需手动初始化。

---

## 配置 LLM

系统通过 OpenAI 兼容接口调用大模型，需在界面中自行配置密钥：

1. 进入「设置 → LLM 配置」
2. 新增配置，填写 `provider` / `api_key` / `base_url` / `model`
3. 可配置多条并分配不同 `role`（如 `research` 用于选题调研、`writing` 用于正文撰写、`review` 用于审核整改）

密钥仅保存在本地 SQLite 中，不会外传。**请勿将带有真实密钥的 `backend/data/` 目录提交到版本库**（已在 `.gitignore` 中排除）。

---

## 使用流程

**软文生产 7 步工作流**：

| 步骤 | 内容 |
| --- | --- |
| 1 | **基础设置** — 选择平台、账号、人设 |
| 2 | **品牌资产** — 选择品牌资产 |
| 3 | **规则配置** — 选择规则库 |
| 4 | **关键词 & 知识点 & 大纲** — 三栏布局：左栏选关键词、中栏选知识点、右栏生成大纲 |
| 5 | **初稿写作** — 选择初稿提示词，生成初稿 |
| 6 | **洗稿精修** — 选择洗稿提示词，去 AI 味精修 |
| 7 | **安全筛选** — 选择安全提示词，做合规检测 |

每步生成结果后回填系统，下一轮渲染会把上一步产物作为变量注入（如 `{outline_content}` → `{draft_content}` → `{rewrite_content}`）。

---

## 三种发布模式

生产任务可指定发布模式，不同模式会注入不同的品牌策略与文章目标：

| 模式 | 适用阵地 | 品牌策略 |
| --- | --- | --- |
| **`geo`** | 自建站 / 官网 | 强品牌。以公司为主体，品牌名全文至少出现 3 次，追求被 AI 检索与推荐引用 |
| **`platform`** | 内容平台（搜狐号、知乎等） | 中立合规。第三方视角，品牌自然提及 ≤ 2 次，标题不含品牌名，文末标注 AIGC 声明 |
| **`green`** | 自媒体账号 | 纯干货涨粉。不带软文营销，品牌仅「彩蛋式」轻提 ≤ 2 次 |

当平台 `output_format = "mdx"`（如官网/自建站）时，系统按 MDX 模板产出可直接粘贴的文章代码：固定 frontmatter + 六段结构 + 4 列数据对比表 + 引用块，禁止 `<Image />` 组件与 emoji。

---

## 提示词变量体系

提示词模板中用 `{variable_name}` 引用业务数据，避免硬编码。系统提供 **64 个内置变量**（前端面板展示），渲染引擎支持 **74 个变量键**。

| 分组 | 变量示例 | 说明 |
| --- | --- | --- |
| 行业与平台 | `{industry_name}` `{platform_name}` `{compliance_level}` `{current_date}` | 行业与平台上下文 |
| 账号与人设 | `{account_name}` `{persona_identity}` `{persona_tone}` | 账号定位与人设语气 |
| 品牌信息 | `{brand_name}` `{brand_official_url}` `{core_products}` `{selling_points}` `{brand_story}` | 品牌资产全量字段 |
| 关键词与知识 | `{keywords}` `{keyword_list}` `{knowledge_content}` `{knowledge_items}` `{knowledge_count}` | 关键词与知识库内容 |
| 生产内容 | `{outline_content}` `{draft_content}` `{rewrite_content}` `{final_content}` `{task_title}` | 工作流各步产物 |
| 配图专用 | `{section_title}` `{section_content}` `{aspect_ratio}` `{image_size}` `{style_label}` | 按章节拆分配图 |
| 规则约束 | `{anti_ai_rules}` `{compliance_rules}` `{ai_seo_rules}` `{creation_rules}` | 规则库注入 |
| 字数要求 | `{word_min}` `{word_max}` `{platform_word_min}` `{platform_word_max}` | 字数约束 |
| GEO 作战 | `{target_persona_name}` `{target_persona_pain_points}` `{intent_question}` `{geo_signals}` | 目标客户画像与 AI 意图问题 |

除内置变量外，提示词还可定义**自定义变量**（名称 / 描述 / 默认值 / 是否必填），渲染时用 `custom_vars` 覆盖。

> 提示词编写规范详见 [`docs/提示词编写规范与优化清单.md`](docs/提示词编写规范与优化清单.md)。

---

## 项目结构

```
.
├── backend/                    # FastAPI 后端
│   ├── app/
│   │   ├── main.py             # 应用入口、建表与迁移
│   │   ├── models.py           # SQLAlchemy 模型 + 平台预设
│   │   ├── database.py         # SQLite 连接与会话
│   │   ├── constants.py        # 内置变量单一事实来源
│   │   ├── paths.py            # 源码/打包双模式路径解析
│   │   ├── routers/            # 20 个路由模块，约 206 个端点
│   │   └── services/           # 提示词渲染、编排、LLM、发布、合规检测等
│   ├── tests/                  # pytest 测试
│   ├── migrations/             # 一次性数据迁移脚本
│   ├── run.py                  # 启动入口（兼 PyInstaller 打包入口）
│   └── requirements.txt
├── frontend/                   # Vue 3 前端
│   ├── src/
│   │   ├── views/              # 22 个页面视图
│   │   ├── components/         # 通用组件（内容 / 知识库 / 生产）
│   │   ├── api/                # 接口封装
│   │   ├── store/              # Pinia 状态
│   │   ├── router/             # 路由与导航分组
│   │   └── styles/
│   ├── scripts/                # 冒烟与端到端验证脚本
│   └── tests/
├── docs/                       # 设计与规范文档
├── start.sh / start.bat        # 一键启动
├── init_env.sh / init_env.bat  # 环境初始化
└── build_exe.bat               # 打包脚本
```

---

## 数据模型

核心表（SQLite）：

| 表 | 说明 |
| --- | --- |
| `industry` | 行业空间（顶层隔离实体） |
| `platform` / `account` / `persona` | 平台、账号、人设 |
| `keyword` / `keyword_group` | 关键词与关键词组 |
| `knowledge_category` / `knowledge_item` | 知识库分类与知识点 |
| `prompt_library_item` | AI 提示词库 |
| `rule_library` | 三大规则库 |
| `brand_asset` | 品牌资产 |
| `target_persona` / `intent_question` | GEO 目标客户画像与意图问题 |
| `production_task` / `content_asset` / `content_version` | 生产任务、内容资产与版本 |
| `publish_job` / `publish_strategy` / `platform_credential` | 发布任务、策略与平台凭据 |
| `browser_studio_run` / `browser_studio_step` | 浏览器工作室流水线与步骤状态机 |
| `geo_monitor` / `geo_monitor_reply` | GEO 收录监控 |
| `llm_config` / `llm_call_log` | LLM 配置与调用日志 |
| `sys_user` | 系统用户 |

建表由 `backend/app/main.py` 的 `init_db()` 在启动时自动完成（`Base.metadata.create_all`），无需手动执行 SQL。

---

## 测试

```bash
cd backend
./venv/Scripts/python.exe -m pytest tests/ -q     # Linux/macOS: ./venv/bin/python -m pytest
```

前端验证脚本：

```bash
cd frontend
npm run smoke             # 冒烟
npm run test:backend      # 后端接口连通性
npm run test:frontend     # 组件测试
npm run build:check       # 后端测试 + 构建 + 冒烟 全链路
```

---

## 打包为可执行文件

```bash
# Windows
build_exe.bat
```

使用 PyInstaller 将后端打包为单文件可执行程序，前端构建产物由后端托管。打包后运行时数据存放在可执行文件同级的 `data/` 目录，不随临时目录丢失。

---

## 常见问题

**Q：启动后页面空白 / 接口 404？**
确认后端已在 `8765` 端口运行。前端开发模式通过 Vite 代理转发 `/api`，两个服务需同时启动。

**Q：需要联网吗？**
系统本身完全离线可用。只有在调用大模型 API 与执行浏览器自动化发布时需要网络。

**Q：数据库在哪？可以迁移吗？**
源码模式为 `backend/data/database.db`；打包模式为可执行文件同级的 `data/database.db`。直接拷贝该文件即可迁移全部数据。

**Q：为什么仓库里没有数据？**
`backend/data/` 被 `.gitignore` 排除，因为它会包含真实业务数据与 API 密钥。首次启动会自动创建空库。

**Q：默认密码是什么？**
`admin / admin123`，请在首次登录后修改。

---

## 贡献

欢迎提交 Issue 与 Pull Request。

- 提交前请确保 `pytest tests/` 全部通过
- 新增内置变量时，需同步维护 `backend/app/constants.py` 中的 `BUILTIN_VARIABLES` 与 `SUPPORTED_RENDER_VARIABLES`（面板键集合必须是渲染白名单的子集，该不变量由 `tests/test_constants.py` 守护）
- 请勿提交任何真实业务数据、API 密钥或平台登录凭据

---

## 开源协议

[MIT](LICENSE) © 2026 wqadlw
