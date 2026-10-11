"""
FastAPI 主程序入口 —— 显影 Latent（企业级 GEO 运营系统）后端服务。

启动流程（``init_db``）：
1. **schema 迁移** —— Alembic ``upgrade head``（老库自动 stamp 基线）
2. **数据迁移** —— 存量敏感字段加密、历史业务数据归一
3. **种子数据** —— 默认管理员 / 默认行业 / GEO 预置 / 自动化提示词 / 平台合规策略

v3 相较 v2 的关键变化：
- 新增**全局鉴权**：除 ``/api/auth/*`` 与 ``/api/meta`` 外，所有路由都要求登录
- 用 **Alembic** 取代了原先塞在本文件 ``init_db()`` 里的约 400 行手写迁移
- **CORS 默认收紧**到本地开发端口，不再通配
"""
import os
import threading
import time
import webbrowser
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from .database import SessionLocal, engine
from .datamigrate import run_data_migrations
from .dbmigrate import upgrade_to_head
from .deps import get_current_user
from .models import Industry, IntentQuestion, SysUser, TargetPersona
from .routers import (
    auth,
    automation_prompts,
    background,
    brand_asset,
    browser_studio,
    content,
    crawler,
    effect,
    geo_canvas,
    geo_monitor,
    industry,
    intent,
    keyword,
    knowledge,
    llm,
    pipeline,
    platform,
    platform_preset,
    production,
    prompt_library,
    publish,
    quality,
    rule,
    search,
    site,
    visibility,
)
from .security import hash_password
from .version import APP_NAME, APP_TITLE, __version__

# 需要登录才能访问的业务路由（auth / site 不在此列）
# - auth 公开：否则无法登录
# - site 公开：/llms.txt /sitemap.xml /robots.txt 必须对**匿名 AI 爬虫**可达，
#   否则整个 GEO 抓取入口对外不可达，功能形同虚设。
_PROTECTED_ROUTERS = [
    industry, platform, knowledge, rule, keyword, content, effect,
    prompt_library, production, brand_asset, platform_preset, search, intent, geo_monitor, geo_canvas,
    llm, publish, browser_studio, automation_prompts, background, crawler, quality, visibility, pipeline,
]


def _seed_defaults() -> None:
    """播种首次运行所需的默认数据（全部幂等）。"""
    db = SessionLocal()
    try:
        if not db.query(SysUser).filter(SysUser.username == "admin").first():
            db.add(SysUser(
                username="admin",
                password=hash_password("admin123"),
                role="admin",
                industry_perms="all",
                status=1,
            ))
            db.commit()
            print("[初始化] 已创建默认管理员: admin / admin123 （请立即在「设置 → 账号安全」中修改）")

        ind = db.query(Industry).filter(Industry.is_deleted == 0).first()
        if not ind:
            ind = Industry(name="默认行业", description="系统默认创建的行业空间", sort=0)
            db.add(ind)
            db.commit()
            print("[初始化] 已创建默认行业空间")

        # GEO：为默认（首个）行业预置目标画像 + 意图问题。
        # 两者各自独立判空播种（幂等），避免一方已存在导致另一方不被播种。
        try:
            tp_count = db.query(TargetPersona).filter(
                TargetPersona.industry_id == ind.id, TargetPersona.is_deleted == 0
            ).count()
            if tp_count == 0:
                intent.seed_target_personas(ind.id, db)
                db.commit()
            iq_count = db.query(IntentQuestion).filter(
                IntentQuestion.industry_id == ind.id, IntentQuestion.is_deleted == 0
            ).count()
            if iq_count == 0:
                intent.seed_intent_questions(ind.id, db)
                db.commit()
            if tp_count == 0 or iq_count == 0:
                print("[初始化] 已预置 GEO 默认画像与意图问题")
        except Exception as exc:  # noqa: BLE001
            db.rollback()
            print(f"[初始化] GEO 预置跳过: {exc}")
    finally:
        db.close()

    # 自动化提示词（页面可编辑，覆盖代码里的默认常量）
    try:
        from .services.automation_prompts import seed_automation_prompts

        with SessionLocal() as session:
            seed_automation_prompts(session)
        print("[初始化] 自动化提示词默认种子已就绪")
    except Exception as exc:  # noqa: BLE001
        print(f"[初始化] automation_prompt 种子跳过: {exc}")

    # 平台合规策略（按平台 publish_mode 播种）
    try:
        from .services.publish_strategy import seed_publish_strategies

        with SessionLocal() as session:
            added = seed_publish_strategies(session)
        print(f"[初始化] 平台合规策略种子完成（新增 {added} 条）")
    except Exception as exc:  # noqa: BLE001
        print(f"[初始化] 平台合规策略种子跳过: {exc}")


def init_db() -> None:
    """初始化数据库：schema 迁移 → 数据迁移 → 种子数据。"""
    upgrade_to_head()
    run_data_migrations(engine)
    _seed_defaults()


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    # 生产队列调度线程：按有界并发执行排队中的作业。
    # 测试环境用 APP_PIPELINE_WORKER=0 关掉它（见 tests/conftest.py）——
    # 否则后台线程会与测试用例抢同一批作业，断言变得不确定。
    from .services.task_queue import dispatcher, worker_enabled

    if worker_enabled():
        reaped = dispatcher.start()
        print(f"[队列] 调度线程已启动（并发上限 {dispatcher.concurrency}）"
              + (f"；已回收 {dispatcher.status()['reaped_on_start']} 条上次中断的作业" if reaped else ""))
    else:
        print("[队列] 调度线程未启动（APP_PIPELINE_WORKER=0），作业需手动执行")
    yield
    try:
        dispatcher.stop()
    except Exception:  # noqa: BLE001
        pass


app = FastAPI(
    title=APP_TITLE,
    description="面向多行业、多平台、多账号矩阵的内容生产流水线与 AI 可见性闭环",
    version=__version__,
    lifespan=lifespan,
)

# CORS：默认只放行本地前端开发端口（vite dev server）。
# 生产为前后端同源单体部署，本不需要 CORS；显式收紧避免「任意网页直读本地 API」。
# 需要额外来源时设 BACKEND_CORS_ORIGINS=https://a,https://b（逗号分隔）。
_cors_origins = [o.strip() for o in os.environ.get("BACKEND_CORS_ORIGINS", "").split(",") if o.strip()]
if not _cors_origins:
    _cors_origins = [
        "http://127.0.0.1:5173", "http://localhost:5173",
        "http://127.0.0.1:8765", "http://localhost:8765",
    ]
# 爬虫流量日志：记录 AI / 搜索引擎爬虫的抓取行为，让「内容有没有被收录」可观测。
# Starlette 的中间件是「**后**注册者在外层」，所以这里先装日志、再装 CORS，
# 让 CORS 位于最外层 —— 预检请求由 CORS 直接短路，不会进入日志逻辑。
from .middleware.traffic_log import install_traffic_log  # noqa: E402

install_traffic_log(app)

app.add_middleware(
    CORSMiddleware,
    # 鉴权走 Authorization 头而非 Cookie，无需 credentials；保持 False 以配合白名单来源。
    allow_origins=_cors_origins,
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 注册路由：auth / site 公开，其余统一挂登录守卫。
# 用 include_router 的 dependencies 参数而不是中间件，是为了让「哪些接口需要登录」
# 在 OpenAPI 文档里可见，且 20 个业务路由模块一行都不用改。
app.include_router(auth.router)
app.include_router(site.router)
for _router in _PROTECTED_ROUTERS:
    app.include_router(_router.router, dependencies=[Depends(get_current_user)])


@app.get("/api/meta")
def api_meta():
    """公开的元信息接口（供前端展示版本号、探测后端可用性）。"""
    return {"code": 0, "data": {"name": APP_NAME, "title": APP_TITLE, "version": __version__}}


# ============================================================
#  静态文件 & SPA 回退
#  源码模式 = backend/static；打包 exe 模式 = PyInstaller 解压目录下的 static
# ============================================================
from .paths import resource_dir  # noqa: E402

STATIC_DIR = os.path.join(resource_dir(), "static")

if os.path.isdir(STATIC_DIR) and os.path.exists(os.path.join(STATIC_DIR, "index.html")):
    app.mount("/assets", StaticFiles(directory=os.path.join(STATIC_DIR, "assets")), name="assets")

    @app.get("/")
    def root():
        return FileResponse(os.path.join(STATIC_DIR, "index.html"))

    @app.get("/{full_path:path}")
    def spa_fallback(full_path: str):
        if full_path.startswith("api/"):
            return JSONResponse({"code": 404, "msg": "Not Found"}, status_code=404)
        candidate = os.path.join(STATIC_DIR, full_path)
        if os.path.isfile(candidate):
            return FileResponse(candidate)
        return FileResponse(os.path.join(STATIC_DIR, "index.html"))
else:
    @app.get("/")
    def root_not_built():
        return {"msg": "前端未构建，请先执行 npm run build", "docs": "/docs"}

    @app.get("/{full_path:path}")
    def spa_fallback_missing(full_path: str):
        # 前端未构建时，深链接也返回提示而非 404 JSON，避免刷新直接报错
        if full_path.startswith("api/"):
            return JSONResponse({"code": 404, "msg": "Not Found"}, status_code=404)
        return JSONResponse({"msg": "前端未构建，请先执行 npm run build", "docs": "/docs"}, status_code=200)


def open_browser(url: str, delay: float = 1.5) -> None:
    time.sleep(delay)
    try:
        webbrowser.open(url)
    except Exception:  # noqa: BLE001
        pass


def main() -> None:
    import uvicorn

    from .selfcheck import run_selfcheck

    host = os.environ.get("APP_HOST", "127.0.0.1")
    port = int(os.environ.get("APP_PORT", "8765"))
    url = f"http://{host}:{port}"
    print("=" * 60)
    print(f"  {APP_TITLE} v{__version__}")
    print("=" * 60)
    run_selfcheck(host, port)
    print(f"  服务地址: {url}")
    print(f"  API文档:  {url}/docs")
    print("  默认账号: admin / admin123（首次登录后请立即修改）")
    print("=" * 60)
    if os.environ.get("APP_NO_BROWSER", "") != "1":
        threading.Thread(target=open_browser, args=(url,), daemon=True).start()
    uvicorn.run(app, host=host, port=port, log_level="info")


if __name__ == "__main__":
    main()
