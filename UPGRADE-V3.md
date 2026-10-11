# v2 → v3 升级说明（阶段 A：工程加固）

> 本文档记录 v3.0.0 第一批改动：**不动业务功能，只修工程底座**。
> 目标是让后续的 GEO 能力深化、流水线智能化、前端重构有一个站得稳的地基。

---

## 一、为什么先做这一批

v2 功能面已经很厚（20 个路由模块约 206 个端点、22 个页面、40+ 张表），
但底座有三个必须先堵的洞，否则后面每加一个功能，债就翻一倍：

| 问题 | v2 现状 | 后果 |
| --- | --- | --- |
| 无鉴权 | 20 个业务路由全部只挂 `Depends(get_db)`，`sys_user` 表只在启动时播种 admin 后无人使用 | 任何能访问 8765 端口的人或网页都能读写全部数据 |
| 密钥明文 | `llm_config.api_key`、`platform_credential.cred_json` 明文落 SQLite | 拿到 `database.db` 文件即拿到全部供应商密钥与平台登录凭据 |
| 迁移散乱 | 约 400 行手写 `PRAGMA` / `ALTER TABLE` / `RENAME` / `INSERT SELECT` 全塞在 `main.py::init_db()`，外层一律 `except: pass` | 加字段要手写一段、失败静默、无法回滚、无法回答「当前库是哪个版本」 |

---

## 二、新增的鉴权体系

### 2.1 后端

| 文件 | 职责 |
| --- | --- |
| `backend/app/security.py` | 密码哈希（PBKDF2-HMAC-SHA256，26 万轮）+ 访问令牌（HS256 JWT） |
| `backend/app/deps.py` | `get_current_user` / `require_admin` / `log_operation` |
| `backend/app/routers/auth.py` | 登录、当前用户、改密、用户 CRUD、操作日志查询 |

**零新增依赖**：JWT 用标准库 `hmac` + `hashlib` + `base64` 手写（HS256 签名本身只有十几行），
不引入 `pyjwt` / `passlib` / `python-jose`。

**密码格式升级**：v2 用的是无盐单轮 SHA-256（`utils.encrypt_password`）。
v3 改为 `pbkdf2_sha256$迭代次数$盐$摘要`，且**兼容旧格式** ——
老用户首次登录成功后自动就地升级，不需要任何人改密码。

**挂载方式**：在 `main.py` 注册路由时统一挂守卫，而不是改 20 个路由文件：

```python
app.include_router(auth.router)                                   # 公开
for r in _PROTECTED_ROUTERS:
    app.include_router(r.router, dependencies=[Depends(get_current_user)])
```

好处是「哪些接口需要登录」在 `/docs` 的 OpenAPI 文档里直接可见。

### 2.2 接口清单

| 方法 | 路径 | 权限 |
| --- | --- | --- |
| POST | `/api/auth/login` | 公开 |
| GET | `/api/meta` | 公开 |
| GET | `/api/auth/me` | 登录 |
| POST | `/api/auth/change-password` | 登录 |
| GET/POST | `/api/auth/users` | 管理员 |
| PUT/DELETE | `/api/auth/users/{id}` | 管理员 |
| GET | `/api/auth/operation-logs` | 管理员 |

### 2.3 前端

- 新增 `views/Login.vue`（左品牌区 + 右表单区，窄屏自动隐藏品牌区）
- `router/index.js` 加 `beforeEach` 守卫：无令牌一律跳登录页并记录 `redirect`
- `api/authToken.js` 独立管理令牌存取，避免 `api ↔ store` 循环依赖
- `api/index.js` 请求拦截器注入 `Authorization: Bearer`，响应 401 统一清令牌 + 跳登录
- `Layout.vue` 顶栏用户区接真实登录态，下拉含「修改密码 / 系统设置 / 退出登录」

**守卫策略**：前端只做「有没有令牌」的粗判，令牌是否有效由后端裁决。
过期令牌会在首个接口 401 时被拦截器统一处理，避免守卫里同步请求后端拖慢首屏。

---

## 三、密钥加密存储

### 3.1 实现方式

新增 `backend/app/crypto.py`，用 **SQLAlchemy `TypeDecorator`** 做透明加解密：

```python
api_key = Column(EncryptedText, default="")   # 写库加密、读库解密
```

选 `TypeDecorator` 而不是在路由里手动加解密的原因：
`api_key` 在 **12 处**被直接读成 `c.api_key`（`routers/llm.py`、
`services/llm_scheduler.py`、`services/doubao_studio.py` 等）。
逐个改调用点既容易漏改，又会把加密逻辑散进业务代码。
`TypeDecorator` 只在 bind/result 两个边界转换，**20 个路由、4 个 service 一行未改**。

### 3.2 兼容与迁移

- 密文带 `enc:v1:` 前缀；不带前缀的值视为历史明文，读取时原样返回 → **老库不停机可用**
- 启动时 `datamigrate.encrypt_legacy_secrets()` 幂等把存量明文刷成密文
- 密钥存 `backend/data/.fernet_key`（0600），可用环境变量 `APP_FERNET_KEY` 覆盖
- 密钥被更换后旧密文解不开时返回空串而非抛异常，避免整个列表接口 500

---

## 四、Alembic 迁移体系

### 4.1 目录结构

```
backend/
├── alembic.ini
└── alembic/
    ├── env.py                    # 连接串从 app.database.DB_PATH 动态注入
    ├── script.py.mako
    └── versions/
        └── 0001_baseline.py      # v3 全量 schema 基线
```

### 4.2 启动时的三种路径

`app/dbmigrate.py::upgrade_to_head()` 自动判断：

1. **全新库**（无业务表）→ `alembic upgrade head`，由基线建全部表
2. **v2 老库**（有业务表但无 `alembic_version`）→ `alembic stamp head`，只打标记不重放
3. **v3 库**（已有 `alembic_version`）→ `alembic upgrade head`，执行增量

老用户把 v3 代码覆盖上去直接启动即可，无需手工执行 SQL。

### 4.3 常用命令

```bash
cd backend
venv/Scripts/python.exe -m alembic revision --autogenerate -m "加字段说明"
venv/Scripts/python.exe -m alembic upgrade head
venv/Scripts/python.exe -m alembic downgrade -1
venv/Scripts/python.exe -m alembic current
```

### 4.4 顺带解决的遗留问题

原先塞在 `init_db()` 里的三类**非 schema** 逻辑被拆到 `app/datamigrate.py`：
`safety→geo` 类目合并、默认提示词追加 GEO 需求块、孤儿表清理、敏感字段加密。
现在「建表」与「刷数据」职责分离，且都能单独测试。

保留的一处例外：`browser_studio_run` 表仍不创建 —— P2 并表后数据已并入
`production_task`，原表改名归档但索引名仍占用，重建会因索引重名导致启动失败。

---

## 五、其他工程改动

| 项 | v2 | v3 |
| --- | --- | --- |
| 版本号 | `main.py` 写 2.0.0、`package.json` 写 2.0.0、README 叫 V4 | 单一来源 `app/version.py`，前端经 `/api/meta` 读取 |
| CORS | 未设环境变量时 `allow_origins=["*"]` | 默认收紧到本地开发端口，需额外来源显式配置 |
| 依赖声明 | `requirements.txt` 仅 5 项 | 拆成核心 / 可选 / 开发三份，并说明版本策略 |
| 启动自检 | 无 | `app/selfcheck.py` 检查依赖、数据目录、端口占用、前端产物 |
| 代码检查 | 无 | `pyproject.toml` 配 ruff（E/W/F/I/B/C4/UP） |
| CI | 无 | `.github/workflows/ci.yml`（后端 ruff + pytest，前端 build） |
| 前端依赖归位 | `playwright-core` 挂在 `dependencies` | 移到 `devDependencies`（仅验证脚本使用） |

---

## 六、升级步骤（v2 → v3）

```bash
# 1. 备份数据（重要）
cp backend/data/database.db backend/data/database.db.bak

# 2. 更新依赖
cd backend
pip install -r requirements.txt -r requirements-dev.txt

# 3. 直接启动 —— schema 迁移与数据加密会自动完成
python run.py
# 启动日志中应出现：
#   [迁移] 检测到 v2 老库，已标记为 v3 基线（不重放建表）
#   [数据迁移] 已加密存量敏感字段：LLM 密钥 N 条、平台凭据 M 条

# 4. 前端
cd ../frontend && npm install && npm run build
```

启动后访问会跳转登录页，用 `admin / admin123` 登录，**并立即修改密码**。

---

## 七、本次新增/修改文件清单

**新增**
```
backend/app/security.py              密码哈希 + JWT
backend/app/deps.py                  请求级鉴权依赖
backend/app/crypto.py                字段级加密（TypeDecorator）
backend/app/datamigrate.py           数据级迁移
backend/app/dbmigrate.py             Alembic 编程式驱动
backend/app/selfcheck.py             启动自检
backend/app/version.py               版本单一来源
backend/app/routers/auth.py          认证与用户管理路由
backend/alembic.ini / alembic/       Alembic 配置与基线迁移
backend/tests/conftest.py            测试隔离夹具
backend/tests/test_security.py       密码与令牌单元测试
backend/tests/test_crypto.py         加密往返测试
backend/tests/test_auth_api.py       鉴权集成测试
frontend/src/views/Login.vue         登录页
frontend/src/api/authToken.js        令牌存取
frontend/src/store/auth.js           登录态 store
pyproject.toml / .env.example / .github/workflows/ci.yml
```

**修改**
```
backend/app/main.py                  鉴权挂载 + 精简 init_db（-400 行）
backend/app/models.py                两个敏感字段改用 EncryptedText
backend/app/database.py              支持 APP_DB_PATH 环境变量
backend/requirements*.txt            依赖拆分与版本策略
frontend/src/api/index.js            令牌注入 + 401 处理 + authApi
frontend/src/router/index.js         登录路由与守卫
frontend/src/components/Layout.vue   真实用户态 + 改密 + 退出登录
frontend/package.json                更名、升版本、依赖归位
frontend/index.html                  标题更新
.gitignore                           排除 .env
```

---

## 八、过程中发现并修复的潜伏缺陷

引入 ruff 全仓检查（424 项告警）后，除了风格问题，还暴露出几个**真实缺陷**。
它们此前都被 `from __future__ import annotations` 静默掩盖，属于「不报错但已经坏了」。

| 缺陷 | 位置 | 为什么以前没暴露 | 影响 |
| --- | --- | --- | --- |
| `Any` 未导入 | `routers/publish.py` 的 `CapturePaste.cookies: Any` | PEP 563 把注解变成字符串延迟求值 | pydantic 2.14 在生成 OpenAPI schema 时抛 `PydanticUserError`，**`/docs` 页面直接 500** |
| `Dict` 未导入 | 同文件 `_capture_sessions: Dict[str, ...]` | 同上 | 同上（同类问题，同一文件） |
| `category_id == None` | `routers/knowledge.py` | SQLAlchemy 会把 `== None` 翻译成 `IS NULL`，侥幸能跑 | 语义依赖 ORM 实现细节，一旦换表达式构造方式就会静默查不到数据 |
| `alembic.ini` 含中文注释 | `backend/alembic.ini` | 新增文件，首次运行即报错 | Windows（GBK 区域）下 configparser 读取崩溃，**服务无法启动** |
| 5 处未使用局部变量 | `background.py` / `knowledge.py` / `browser_studio.py` / `doubao_studio.py` / `publisher.py` | 无 linter | 死代码，误导后续维护者 |
| 19 处异常链丢失 | 10 个文件 | 无 linter | `raise HTTPException(...)` 丢掉原始异常，线上排查时看不到根因 |

**其中 `alembic.ini` 那条是本次改动自己引入的**，已改为纯 ASCII 配置并在文件头注明原因 ——
这类「在英文环境正常、在中文 Windows 上炸」的问题，只有真跑一遍才会发现。

修完后 `ruff check .` 为 **0 告警**（从 424 降到 0），`pytest` 全绿。

### 关于规则集的取舍

没有把 ruff 的所有规则都打开，而是**只开能真实抓到缺陷的规则**：

- **开**：`F`（未使用导入/变量、未定义名称）、`E4/E7/E9`、`W`、`B`、`C4`、`I`
- **不开 `UP`**（pyupgrade）：历史代码大量使用 `typing.Dict` / `typing.List`，
  但项目要求兼容 **Python 3.9**，而 `dict[str, X]` 作为运行时注解需要
  `from __future__ import annotations` 或 3.10+。开 `UP` 会强迫全仓改成
  3.10+ 语法，**反而破坏兼容性**。
- **忽略 `E702` / `E401`**：遗留代码的单行多语句/多导入，为它翻动全仓不值得。

配置在 `pyproject.toml` 的 `[tool.ruff.lint]`，取舍理由写在注释里。

---

## 九、后续阶段（尚未实施）

- **阶段 B** GEO 能力深化：多引擎并发巡检、提及率趋势、竞品对比、发布→收录→回流归因闭环
- **阶段 C** 生产流水线智能化：可编排 Pipeline、断点续跑、批量生产、并发队列
- **阶段 D** 前端重构：拆分 5 个千行巨石视图、引入 TypeScript、统一三栏工作台
