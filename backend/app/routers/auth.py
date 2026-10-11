"""
认证与用户管理路由。

- 公开：``POST /api/auth/login``
- 需登录：``GET /api/auth/me``、``POST /api/auth/change-password``
- 需管理员：用户 CRUD、操作日志查询

设计取舍：令牌无状态（HS256），不引入 Redis/会话表；但登录失败做进程内限流，
防止本地端口被暴力撞库。用户停用后其存量 token 会因 ``get_current_user``
的 status 校验立即失效，无需维护吊销名单。
"""
from __future__ import annotations

import time
from collections import defaultdict, deque
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from ..database import get_db, now
from ..deps import get_current_user, log_operation, require_admin
from ..models import Industry, OperationLog, SysUser
from ..security import (
    TOKEN_TTL_SECONDS,
    create_access_token,
    hash_password,
    needs_rehash,
    verify_password,
)
from ..utils import to_dict

router = APIRouter(prefix="/api/auth", tags=["认证与用户"])

# ============================================================
#  登录失败限流（进程内，够用且零依赖）
# ============================================================
_LOGIN_WINDOW = 300          # 统计窗口：5 分钟
_LOGIN_MAX_FAILS = 10        # 窗口内允许的失败次数
_fail_log: dict[str, deque] = defaultdict(deque)


def _client_ip(request: Request) -> str:
    forwarded = request.headers.get("x-forwarded-for", "")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


def _check_rate_limit(ip: str) -> None:
    bucket = _fail_log[ip]
    cutoff = time.time() - _LOGIN_WINDOW
    while bucket and bucket[0] < cutoff:
        bucket.popleft()
    if len(bucket) >= _LOGIN_MAX_FAILS:
        wait = int(_LOGIN_WINDOW - (time.time() - bucket[0]))
        raise HTTPException(429, f"登录失败次数过多，请 {max(wait, 1)} 秒后重试")


def _record_fail(ip: str) -> None:
    _fail_log[ip].append(time.time())


def _clear_fail(ip: str) -> None:
    _fail_log.pop(ip, None)


# ============================================================
#  请求模型
# ============================================================
class LoginIn(BaseModel):
    username: str = Field(min_length=1, max_length=64)
    password: str = Field(min_length=1, max_length=256)


class ChangePasswordIn(BaseModel):
    old_password: str
    new_password: str = Field(min_length=8, max_length=256)


class UserIn(BaseModel):
    username: str = Field(min_length=1, max_length=64)
    password: str = Field(min_length=8, max_length=256)
    role: str = "admin"
    industry_perms: str = "all"
    status: int = 1


class UserUpdateIn(BaseModel):
    password: Optional[str] = Field(default=None, min_length=8, max_length=256)
    role: Optional[str] = None
    industry_perms: Optional[str] = None
    status: Optional[int] = None


def _user_payload(user: SysUser) -> dict:
    data = to_dict(user)
    data.pop("password", None)          # 绝不外泄密码哈希
    return data


# ============================================================
#  公开接口
# ============================================================
@router.post("/login")
def login(payload: LoginIn, request: Request, db: Session = Depends(get_db)):
    ip = _client_ip(request)
    _check_rate_limit(ip)

    user = db.query(SysUser).filter(SysUser.username == payload.username).first()
    if not user or not verify_password(payload.password, user.password):
        _record_fail(ip)
        log_operation(db, module="auth", action="login_failed",
                      detail=f"用户名={payload.username}", request=request)
        # 不区分「用户不存在」与「密码错误」，避免账号枚举
        raise HTTPException(401, "用户名或密码错误")
    if user.status != 1:
        _record_fail(ip)
        log_operation(db, user_id=user.id, module="auth", action="login_disabled",
                      detail=f"用户名={user.username}", request=request)
        raise HTTPException(403, "账号已停用，请联系管理员")

    # 存量裸 SHA-256 密码在首次成功登录时就地升级为 PBKDF2
    if needs_rehash(user.password):
        user.password = hash_password(payload.password)
        user.update_time = now()
        db.commit()

    _clear_fail(ip)
    token = create_access_token(user.username, user.id, user.role)
    log_operation(db, user_id=user.id, module="auth", action="login_success",
                  detail=f"用户名={user.username}", request=request)
    return {
        "code": 0,
        "data": {"token": token, "token_type": "Bearer", "expires_in": TOKEN_TTL_SECONDS,
                 "user": _user_payload(user)},
        "msg": "登录成功",
    }


# ============================================================
#  需登录
# ============================================================
@router.get("/me")
def me(user: SysUser = Depends(get_current_user)):
    """返回当前用户及其可访问的行业列表（前端据此初始化工作区）。"""
    return {"code": 0, "data": _user_payload(user)}


@router.post("/change-password")
def change_password(
    payload: ChangePasswordIn,
    request: Request,
    user: SysUser = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    if not verify_password(payload.old_password, user.password):
        raise HTTPException(400, "原密码不正确")
    if payload.old_password == payload.new_password:
        raise HTTPException(400, "新密码不能与原密码相同")
    user.password = hash_password(payload.new_password)
    user.update_time = now()
    db.commit()
    log_operation(db, user_id=user.id, module="auth", action="change_password",
                  detail=f"用户名={user.username}", request=request)
    return {"code": 0, "msg": "密码已修改，请重新登录"}


# ============================================================
#  需管理员
# ============================================================
@router.get("/users")
def list_users(_: SysUser = Depends(require_admin), db: Session = Depends(get_db)):
    users = db.query(SysUser).order_by(SysUser.id.asc()).all()
    return {"code": 0, "data": [_user_payload(u) for u in users]}


@router.post("/users")
def create_user(
    payload: UserIn,
    request: Request,
    admin: SysUser = Depends(require_admin),
    db: Session = Depends(get_db),
):
    if db.query(SysUser).filter(SysUser.username == payload.username).first():
        raise HTTPException(400, "用户名已存在")
    if payload.role not in ("admin", "editor"):
        raise HTTPException(400, "角色只能是 admin 或 editor")
    user = SysUser(
        username=payload.username,
        password=hash_password(payload.password),
        role=payload.role,
        industry_perms=payload.industry_perms,
        status=payload.status,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    log_operation(db, user_id=admin.id, module="auth", action="create_user",
                  detail=f"新用户={user.username} 角色={user.role}", request=request)
    return {"code": 0, "data": _user_payload(user), "msg": "创建成功"}


@router.put("/users/{uid}")
def update_user(
    uid: int,
    payload: UserUpdateIn,
    request: Request,
    admin: SysUser = Depends(require_admin),
    db: Session = Depends(get_db),
):
    user = db.query(SysUser).filter(SysUser.id == uid).first()
    if not user:
        raise HTTPException(404, "用户不存在")
    data = payload.model_dump(exclude_unset=True)

    if data.get("role") is not None and data["role"] not in ("admin", "editor"):
        raise HTTPException(400, "角色只能是 admin 或 editor")

    # 保护措施：不允许把最后一个可用管理员降级或停用，否则系统会被锁死
    demoting = data.get("role") == "editor" or data.get("status") == 0
    if user.role == "admin" and demoting:
        remaining = (
            db.query(SysUser)
            .filter(SysUser.role == "admin", SysUser.status == 1, SysUser.id != uid)
            .count()
        )
        if remaining == 0:
            raise HTTPException(400, "系统必须保留至少一个启用的管理员")

    if data.get("password"):
        user.password = hash_password(data.pop("password"))
    data.pop("password", None)
    for key, value in data.items():
        if value is not None:
            setattr(user, key, value)
    user.update_time = now()
    db.commit()
    log_operation(db, user_id=admin.id, module="auth", action="update_user",
                  detail=f"目标用户={user.username}", request=request)
    return {"code": 0, "data": _user_payload(user), "msg": "更新成功"}


@router.delete("/users/{uid}")
def delete_user(
    uid: int,
    request: Request,
    admin: SysUser = Depends(require_admin),
    db: Session = Depends(get_db),
):
    user = db.query(SysUser).filter(SysUser.id == uid).first()
    if not user:
        raise HTTPException(404, "用户不存在")
    if user.id == admin.id:
        raise HTTPException(400, "不能删除当前登录账号")
    if user.role == "admin":
        remaining = db.query(SysUser).filter(SysUser.role == "admin", SysUser.status == 1, SysUser.id != uid).count()
        if remaining == 0:
            raise HTTPException(400, "系统必须保留至少一个启用的管理员")
    username = user.username
    db.delete(user)
    db.commit()
    log_operation(db, user_id=admin.id, module="auth", action="delete_user",
                  detail=f"已删除用户={username}", request=request)
    return {"code": 0, "msg": "已删除"}


@router.get("/operation-logs")
def list_operation_logs(
    module: Optional[str] = None,
    action: Optional[str] = None,
    user_id: int = 0,
    limit: int = 100,
    _: SysUser = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """操作日志查询（此前 operation_log 表只写不读，这里补上出口）。"""
    query = db.query(OperationLog)
    if module:
        query = query.filter(OperationLog.module == module)
    if action:
        query = query.filter(OperationLog.action == action)
    if user_id:
        query = query.filter(OperationLog.user_id == user_id)
    total = query.count()
    rows = query.order_by(OperationLog.id.desc()).limit(min(max(limit, 1), 500)).all()
    return {"code": 0, "data": {"total": total, "items": [to_dict(r) for r in rows]}}


@router.get("/industries")
def my_industries(user: SysUser = Depends(get_current_user), db: Session = Depends(get_db)):
    """当前用户可访问的行业空间。admin 看全部，editor 按 industry_perms 过滤。"""
    query = db.query(Industry).filter(Industry.is_deleted == 0)
    if user.role != "admin" and user.industry_perms not in ("all", "", None):
        ids = [int(x) for x in str(user.industry_perms).split(",") if x.strip().isdigit()]
        query = query.filter(Industry.id.in_(ids or [-1]))
    rows = query.order_by(Industry.sort.asc(), Industry.id.asc()).all()
    return {"code": 0, "data": [to_dict(r) for r in rows]}
