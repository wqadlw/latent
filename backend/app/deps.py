"""
请求级依赖：从 ``Authorization: Bearer <token>`` 解析当前登录用户。

用法（在 ``main.py`` 注册路由时统一挂载，业务路由无需逐个改）：

    app.include_router(industry.router, dependencies=[Depends(get_current_user)])

这样 20 个业务路由模块一行都不用动，鉴权就在入口处生效。
"""
from __future__ import annotations

from fastapi import Depends, HTTPException, Request
from sqlalchemy.orm import Session

from .database import get_db
from .models import OperationLog, SysUser
from .security import TokenError, decode_access_token

_UNAUTHORIZED_HEADERS = {"WWW-Authenticate": "Bearer"}


def extract_token(request: Request) -> str:
    """从请求中提取令牌。

    支持两种载体：
    1. ``Authorization: Bearer xxx``（常规）
    2. ``?access_token=xxx``（EventSource / 浏览器直接下载等无法自定义请求头的场景）
    """
    header = request.headers.get("authorization", "")
    if header.lower().startswith("bearer "):
        return header[7:].strip()
    return (request.query_params.get("access_token") or "").strip()


def get_current_user(request: Request, db: Session = Depends(get_db)) -> SysUser:
    """解析当前登录用户；未登录 / 令牌失效 / 账号停用一律 401。"""
    token = extract_token(request)
    if not token:
        raise HTTPException(401, "未登录或登录已过期", headers=_UNAUTHORIZED_HEADERS)
    try:
        payload = decode_access_token(token)
    except TokenError as exc:
        raise HTTPException(401, str(exc), headers=_UNAUTHORIZED_HEADERS) from exc

    user = (
        db.query(SysUser)
        .filter(SysUser.id == int(payload.get("uid", 0)), SysUser.status == 1)
        .first()
    )
    if not user:
        raise HTTPException(401, "用户不存在或已停用", headers=_UNAUTHORIZED_HEADERS)
    return user


def require_admin(user: SysUser = Depends(get_current_user)) -> SysUser:
    """管理员专用依赖：用户管理、系统级配置等接口使用。"""
    if user.role != "admin":
        raise HTTPException(403, "需要管理员权限")
    return user


def log_operation(
    db: Session,
    *,
    user_id: int = 0,
    module: str = "",
    action: str = "",
    detail: str = "",
    request: Request | None = None,
) -> None:
    """写一条操作日志（失败不阻断主流程 —— 日志永远不该让业务请求失败）。"""
    try:
        ip = ""
        if request is not None:
            # 兼容反向代理：优先取 X-Forwarded-For 的第一段
            forwarded = request.headers.get("x-forwarded-for", "")
            ip = forwarded.split(",")[0].strip() if forwarded else (request.client.host if request.client else "")
        db.add(OperationLog(user_id=user_id, module=module, action=action, detail=detail, ip=ip))
        db.commit()
    except Exception:  # noqa: BLE001 — 审计日志尽力而为
        db.rollback()
