"""管理后台 · 用户管理（前缀 /api/v1/admin）。

约定：
- 只有管理员能访问：在 get_current_user 之上再加一层 require_admin；
- 返回的用户信息**永远不含密码哈希**；
- 写操作都带「不能把自己锁在门外」的保护（不能取消自己的管理员、不能删掉最后一个管理员）；
- 删除用户会连带删除他的会话与对话状态，接口会把删掉的数量如实返回。
"""
from __future__ import annotations

import secrets

from fastapi import APIRouter, Depends, HTTPException, Query, Request

from app.api.deps import get_current_user
from app.common.admin import count_admins, is_admin_user, record_admin_action
from app.common.quota import QUOTA_TIMEZONE, resolve_quota, week_usage
from app.common.security import hash_password
from app.models.schemas import AdminUserUpdate

router = APIRouter()

# 生成给人念的初始密码：去掉容易看错的字符（0/O、1/l/I）
_PASSWORD_ALPHABET = "abcdefghijkmnpqrstuvwxyz23456789"


def _generate_password() -> str:
    raw = "".join(secrets.choice(_PASSWORD_ALPHABET) for _ in range(12))
    return f"{raw[:4]}-{raw[4:8]}-{raw[8:]}"


async def require_admin(request: Request, user: dict = Depends(get_current_user)) -> dict:
    """管理员校验（放在 get_current_user 之后，未登录仍是 401）。"""
    if not await is_admin_user(request.app.state.pool, user["id"]):
        raise HTTPException(status_code=403, detail="需要管理员权限")
    return user


async def _log(
    request: Request,
    admin: dict,
    action: str,
    *,
    target: dict | None = None,
    detail: dict | None = None,
    result: str = "ok",
    message: str | None = None,
) -> None:
    """写一条审计日志。被拒绝的尝试也记（result="denied"），这样"谁想干什么"也留痕。"""
    await record_admin_action(
        request.app.state.pool,
        admin_id=admin["id"],
        admin_username=admin["username"],
        action=action,
        target_user_id=(target or {}).get("id"),
        target_username=(target or {}).get("username"),
        detail=detail,
        result=result,
        message=message,
        ip=request.client.host if request.client else None,
    )


# 列表与详情共用的列（刻意不查 password_hash）
_USER_COLUMNS = """
    u.id, u.username, u.display_name, u.created_at, u.is_admin, u.weekly_token_quota,
    u.taste, u.spicy_level, u.diet_goal, u.avoid_ingredients, u.preferred_cuisines, u.notes
"""

# 本周用量（按自然周汇总，和配额判断用的是同一套口径）
_WEEK_USAGE_JOIN = """
    left join (
        select user_id,
               sum(requests)                     as week_requests,
               sum(input_tokens + output_tokens) as week_tokens
        from app_usage_daily
        where day >= date_trunc('week', (now() at time zone %(tz)s)::date)::date
          and day <  date_trunc('week', (now() at time zone %(tz)s)::date)::date + 7
        group by user_id
    ) d on d.user_id = u.id
"""


def _iso(value) -> str | None:
    return value.isoformat() if value is not None else None


def _serialize_user(row: dict, week_requests: int = 0, week_tokens: int = 0) -> dict:
    quota = resolve_quota(row.get("weekly_token_quota"))
    used = int(week_tokens or 0)
    return {
        "id": row["id"],
        "username": row["username"],
        "display_name": row.get("display_name") or "",
        "created_at": _iso(row.get("created_at")),
        "is_admin": bool(row.get("is_admin")),
        "weekly_token_quota": row.get("weekly_token_quota"),
        "effective_quota": quota,
        "used_this_week": used,
        "remaining": None if quota <= 0 else max(quota - used, 0),
        "requests_this_week": int(week_requests or 0),
    }


async def _fetch_user(pool, user_id: int) -> dict | None:
    async with pool.connection() as conn:
        cur = await conn.execute(
            f"select {_USER_COLUMNS} from app_users u where u.id = %s", (user_id,)
        )
        return await cur.fetchone()


@router.get("/admin/users")
async def list_users(
    request: Request,
    admin: dict = Depends(require_admin),
    q: str | None = Query(default=None, description="按用户名 / 昵称模糊搜索"),
    page: int = Query(default=1, ge=1),
    size: int = Query(default=20, ge=1, le=100),
):
    """用户列表：管理员排前面，带上会话数、登录设备数和本周用量。"""
    pool = request.app.state.pool

    filters = ""
    filter_params: dict = {}
    if q:
        filters = "where (u.username ilike %(q)s or coalesce(u.display_name, '') ilike %(q)s)"
        filter_params["q"] = f"%{q}%"

    async with pool.connection() as conn:
        cur = await conn.execute(
            f"select count(*) as total from app_users u {filters}", filter_params
        )
        total = (await cur.fetchone())["total"]

        cur = await conn.execute(
            f"""
            select {_USER_COLUMNS},
                   coalesce(d.week_requests, 0) as week_requests,
                   coalesce(d.week_tokens, 0)   as week_tokens,
                   (select count(*) from app_threads t where t.user_id = u.id)  as threads,
                   (select count(*) from app_sessions s where s.user_id = u.id) as sessions
            from app_users u
            {_WEEK_USAGE_JOIN}
            {filters}
            order by u.is_admin desc, u.id
            limit %(limit)s offset %(offset)s
            """,
            {
                **filter_params,
                "tz": QUOTA_TIMEZONE,
                "limit": size,
                "offset": (page - 1) * size,
            },
        )
        rows = await cur.fetchall()

    return {
        "total": total,
        "page": page,
        "size": size,
        "items": [
            {
                **_serialize_user(row, row["week_requests"], row["week_tokens"]),
                "threads": row["threads"],
                "sessions": row["sessions"],
            }
            for row in rows
        ],
    }


@router.get("/admin/users/{user_id}")
async def get_user(user_id: int, request: Request, admin: dict = Depends(require_admin)):
    """单个用户详情：资料、口味偏好、本周额度与用量、会话与登录设备数。"""
    pool = request.app.state.pool
    row = await _fetch_user(pool, user_id)
    if row is None:
        raise HTTPException(status_code=404, detail="用户不存在")

    usage = await week_usage(pool, user_id)
    week_tokens = int(usage["input_tokens"] or 0) + int(usage["output_tokens"] or 0)

    async with pool.connection() as conn:
        cur = await conn.execute(
            """
            select (select count(*) from app_threads t where t.user_id = %(id)s)  as threads,
                   (select count(*) from app_sessions s where s.user_id = %(id)s) as sessions,
                   (select max(c.checkpoint->>'ts') from checkpoints c
                      join app_threads t on t.thread_id = c.thread_id
                     where t.user_id = %(id)s)                                    as last_active
            """,
            {"id": user_id},
        )
        stats = await cur.fetchone()

    cuisines = (row.get("preferred_cuisines") or "").split(",")
    return {
        **_serialize_user(row, usage["requests"], week_tokens),
        "threads": stats["threads"],
        "sessions": stats["sessions"],
        "last_active": stats["last_active"],
        "week": {
            "start": usage["week_start"].isoformat(),
            "end": usage["week_end"].isoformat(),
            "resets_at": usage["resets_at"].isoformat(),
        },
        "preferences": {
            "taste": row.get("taste") or "",
            "spicy_level": row.get("spicy_level") or "",
            "diet_goal": row.get("diet_goal") or "",
            "avoid_ingredients": row.get("avoid_ingredients") or "",
            "preferred_cuisines": [c for c in cuisines if c],
            "notes": row.get("notes") or "",
        },
    }


@router.patch("/admin/users/{user_id}")
async def update_user(
    user_id: int,
    payload: AdminUserUpdate,
    request: Request,
    admin: dict = Depends(require_admin),
):
    """改权限或额度覆盖。`weekly_token_quota` 传 null = 恢复用全局默认额度。"""
    data = payload.model_dump(exclude_unset=True)
    if not data:
        raise HTTPException(status_code=400, detail="没有要更新的字段")

    pool = request.app.state.pool
    target = await _fetch_user(pool, user_id)
    if target is None:
        raise HTTPException(status_code=404, detail="用户不存在")

    updates: dict = {}

    if "is_admin" in data:
        value = bool(data["is_admin"])
        if not value:
            if user_id == admin["id"]:
                await _log(
                    request, admin, "update_user", target=target,
                    detail={"is_admin": False},
                    result="denied", message="不能取消自己的管理员权限",
                )
                raise HTTPException(status_code=400, detail="不能取消自己的管理员权限")
            if target["is_admin"] and await count_admins(pool) <= 1:
                await _log(
                    request, admin, "update_user", target=target,
                    detail={"is_admin": False},
                    result="denied", message="至少要保留一个管理员",
                )
                raise HTTPException(status_code=400, detail="至少要保留一个管理员")
        updates["is_admin"] = value

    if "weekly_token_quota" in data:
        raw = data["weekly_token_quota"]
        if raw is None:
            updates["weekly_token_quota"] = None
        else:
            if raw < 0:
                await _log(
                    request, admin, "update_user", target=target,
                    detail={"weekly_token_quota": raw},
                    result="denied", message="额度不能是负数",
                )
                raise HTTPException(status_code=400, detail="额度不能是负数")
            updates["weekly_token_quota"] = int(raw)

    if not updates:
        raise HTTPException(status_code=400, detail="没有要更新的字段")

    assignments = ", ".join(f"{column} = %({column})s" for column in updates)
    async with pool.connection() as conn:
        await conn.execute(
            f"update app_users set {assignments} where id = %(user_id)s",
            {**updates, "user_id": user_id},
        )

    updated = await _fetch_user(pool, user_id)
    await _log(request, admin, "update_user", target=updated, detail=updates)
    return _serialize_user(updated)


@router.post("/admin/users/{user_id}/logout-all")
async def logout_all(user_id: int, request: Request, admin: dict = Depends(require_admin)):
    """强制下线：删掉这个用户的所有登录令牌（他需要重新登录）。

    不允许对自己执行：那等于把自己踢出去，想退出请用右上角的退出。
    """
    if user_id == admin["id"]:
        await _log(
            request, admin, "logout_all", target={"id": user_id, "username": None},
            result="denied", message="不能对自己强制下线",
        )
        raise HTTPException(
            status_code=400, detail="不能对自己强制下线，要退出请点右上角的「退出」"
        )
    pool = request.app.state.pool
    target = await _fetch_user(pool, user_id)
    if target is None:
        raise HTTPException(status_code=404, detail="用户不存在")
    async with pool.connection() as conn:
        cur = await conn.execute(
            "delete from app_sessions where user_id = %s", (user_id,)
        )
        removed = cur.rowcount
    await _log(
        request, admin, "logout_all", target=target,
        detail={"removed_sessions": removed},
    )
    return {"removed_sessions": removed}


@router.post("/admin/users/{user_id}/reset-password")
async def reset_password(user_id: int, request: Request, admin: dict = Depends(require_admin)):
    """重置密码：生成一个临时密码返回给管理员，同时踢掉该用户所有登录态。

    不允许重置自己的密码：这个操作会清掉目标用户的全部登录令牌，
    对自己执行会当场把自己踢回登录页，而且旧密码立刻失效（真实踩过这个坑）。
    要改自己的密码，用客户端个人中心里的「修改密码」。
    """
    if user_id == admin["id"]:
        await _log(
            request, admin, "reset_password", target={"id": user_id, "username": admin["username"]},
            result="denied", message="不能重置自己的密码",
        )
        raise HTTPException(
            status_code=400,
            detail="不能在这里重置自己的密码，请在客户端个人中心里修改",
        )
    pool = request.app.state.pool
    target = await _fetch_user(pool, user_id)
    if target is None:
        raise HTTPException(status_code=404, detail="用户不存在")

    password = _generate_password()
    async with pool.connection() as conn:
        await conn.execute(
            "update app_users set password_hash = %s where id = %s",
            (hash_password(password), user_id),
        )
        cur = await conn.execute("delete from app_sessions where user_id = %s", (user_id,))
        cleared = cur.rowcount
    # 只记"清掉了几个登录态"，临时密码本身绝不入库
    await _log(
        request, admin, "reset_password", target=target,
        detail={"cleared_sessions": cleared},
    )
    return {"username": target["username"], "password": password}


@router.delete("/admin/users/{user_id}")
async def delete_user(user_id: int, request: Request, admin: dict = Depends(require_admin)):
    """删除用户：连带删掉他的会话、对话状态、登录令牌和用量记录。"""
    pool = request.app.state.pool
    if user_id == admin["id"]:
        await _log(
            request, admin, "delete_user", target={"id": user_id, "username": admin["username"]},
            result="denied", message="不能删除自己的账号",
        )
        raise HTTPException(status_code=400, detail="不能删除自己的账号")

    target = await _fetch_user(pool, user_id)
    if target is None:
        raise HTTPException(status_code=404, detail="用户不存在")
    if target["is_admin"] and await count_admins(pool) <= 1:
        await _log(
            request, admin, "delete_user", target=target,
            result="denied", message="至少要保留一个管理员",
        )
        raise HTTPException(status_code=400, detail="至少要保留一个管理员")

    async with pool.connection() as conn:
        cur = await conn.execute(
            "select thread_id from app_threads where user_id = %s", (user_id,)
        )
        thread_ids = [row["thread_id"] for row in await cur.fetchall()]

    # 对话状态由 LangGraph 管，必须走 checkpointer 删，不能直接删表
    checkpointer = request.app.state.checkpointer
    for thread_id in thread_ids:
        await checkpointer.adelete_thread(thread_id)

    async with pool.connection() as conn:
        # app_sessions / app_threads / app_usage_daily 都是 on delete cascade
        await conn.execute("delete from app_users where id = %s", (user_id,))

    await _log(
        request, admin, "delete_user", target=target,
        detail={"threads": len(thread_ids)},
    )
    return {"deleted": {"user_id": user_id, "username": target["username"], "threads": len(thread_ids)}}


@router.get("/admin/logs")
async def list_logs(
    request: Request,
    admin: dict = Depends(require_admin),
    page: int = Query(default=1, ge=1),
    size: int = Query(default=20, ge=1, le=100),
    action: str | None = Query(default=None, description="按操作类型过滤"),
    result: str | None = Query(default=None, description="ok / denied"),
    admin_username: str | None = Query(default=None, description="按操作人过滤"),
    target_user_id: int | None = Query(default=None, description="按被操作用户过滤"),
):
    """管理操作日志：谁、什么时候、对谁、做了什么、结果如何。"""
    pool = request.app.state.pool

    clauses: list[str] = []
    params: dict = {}
    if action:
        clauses.append("action = %(action)s")
        params["action"] = action
    if result:
        clauses.append("result = %(result)s")
        params["result"] = result
    if admin_username:
        clauses.append("admin_username = %(admin_username)s")
        params["admin_username"] = admin_username
    if target_user_id is not None:
        clauses.append("target_user_id = %(target_user_id)s")
        params["target_user_id"] = target_user_id
    where = f"where {' and '.join(clauses)}" if clauses else ""

    async with pool.connection() as conn:
        cur = await conn.execute(f"select count(*) as total from app_admin_logs {where}", params)
        total = (await cur.fetchone())["total"]

        cur = await conn.execute(
            f"""
            select id, created_at, admin_id, admin_username,
                   target_user_id, target_username,
                   action, detail, result, message, ip
            from app_admin_logs
            {where}
            order by id desc
            limit %(limit)s offset %(offset)s
            """,
            {**params, "limit": size, "offset": (page - 1) * size},
        )
        rows = await cur.fetchall()

    return {
        "total": total,
        "page": page,
        "size": size,
        "items": [
            {
                **row,
                "created_at": row["created_at"].isoformat() if row["created_at"] else None,
            }
            for row in rows
        ],
    }
