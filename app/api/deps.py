"""接口的公共依赖：从请求头里解析当前登录用户。"""
from __future__ import annotations

from datetime import datetime, timezone

from fastapi import Header, HTTPException, Request


def extract_token(authorization: str | None) -> str | None:
    """从 `Authorization: Bearer xxx` 里取出令牌。"""
    if not authorization:
        return None
    parts = authorization.split(" ", 1)
    if len(parts) != 2 or parts[0].lower() != "bearer":
        return None
    return parts[1].strip() or None


async def get_current_user(
    request: Request,
    authorization: str | None = Header(default=None),
) -> dict:
    """校验令牌并返回当前用户；未登录或已过期一律 401。"""
    token = extract_token(authorization)
    if not token:
        raise HTTPException(status_code=401, detail="未登录")

    pool = request.app.state.pool
    async with pool.connection() as conn:
        cur = await conn.execute(
            """
            select u.id, u.username, s.expires_at
            from app_sessions s
            join app_users u on u.id = s.user_id
            where s.token = %s
            """,
            (token,),
        )
        row = await cur.fetchone()

    if row is None:
        raise HTTPException(status_code=401, detail="登录已失效，请重新登录")

    expires_at = row["expires_at"]
    if expires_at is not None and expires_at < datetime.now(timezone.utc):
        raise HTTPException(status_code=401, detail="登录已过期，请重新登录")

    return {"id": row["id"], "username": row["username"], "token": token}
