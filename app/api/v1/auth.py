"""注册 / 登录 / 登出。"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, Header, HTTPException, Request

from app.api.deps import extract_token, get_current_user
from app.common.security import hash_password, new_token, verify_password
from app.models.schemas import AuthResponse, LoginRequest, RegisterRequest

router = APIRouter()

# 登录有效期：30 天
TOKEN_TTL = timedelta(days=30)


def _validate(username: str, password: str) -> tuple[str, str]:
    username = (username or "").strip()
    if not 2 <= len(username) <= 20:
        raise HTTPException(status_code=400, detail="用户名长度需在 2-20 个字符之间")
    if any(c.isspace() for c in username):
        raise HTTPException(status_code=400, detail="用户名不能包含空格")
    if len(password or "") < 6:
        raise HTTPException(status_code=400, detail="密码至少 6 位")
    return username, password


async def _create_session(pool, user_id: int) -> str:
    token = new_token()
    async with pool.connection() as conn:
        await conn.execute(
            "insert into app_sessions (token, user_id, expires_at) values (%s, %s, %s)",
            (token, user_id, datetime.now(timezone.utc) + TOKEN_TTL),
        )
    return token


@router.post("/auth/register", response_model=AuthResponse)
async def register(payload: RegisterRequest, request: Request):
    username, password = _validate(payload.username, payload.password)
    pool = request.app.state.pool

    async with pool.connection() as conn:
        cur = await conn.execute(
            "select id from app_users where username = %s", (username,)
        )
        if await cur.fetchone() is not None:
            raise HTTPException(status_code=400, detail="该用户名已被注册")

        cur = await conn.execute(
            "insert into app_users (username, password_hash) values (%s, %s) returning id",
            (username, hash_password(password)),
        )
        user_id = (await cur.fetchone())["id"]

        # 兼容旧数据：如果这是系统里的第一个用户，
        # 把此前没有归属的会话（加账号体系之前产生的）都认领给他
        cur = await conn.execute("select count(*) as c from app_users")
        if (await cur.fetchone())["c"] == 1:
            await conn.execute(
                """
                insert into app_threads (thread_id, user_id)
                select thread_id, %s from checkpoints
                on conflict (thread_id) do nothing
                """,
                (user_id,),
            )

    token = await _create_session(pool, user_id)
    return AuthResponse(token=token, username=username)


@router.post("/auth/login", response_model=AuthResponse)
async def login(payload: LoginRequest, request: Request):
    pool = request.app.state.pool
    username = (payload.username or "").strip()

    async with pool.connection() as conn:
        cur = await conn.execute(
            "select id, username, password_hash from app_users where username = %s",
            (username,),
        )
        row = await cur.fetchone()

    # 用户不存在和密码错误返回同一句话，避免泄露"哪些用户名存在"
    if row is None or not verify_password(payload.password or "", row["password_hash"]):
        raise HTTPException(status_code=401, detail="用户名或密码错误")

    token = await _create_session(pool, row["id"])
    return AuthResponse(token=token, username=row["username"])


@router.get("/auth/me")
async def me(user: dict = Depends(get_current_user)):
    return {"id": user["id"], "username": user["username"]}


@router.post("/auth/logout")
async def logout(
    request: Request,
    authorization: str | None = Header(default=None),
):
    token = extract_token(authorization)
    if token:
        pool = request.app.state.pool
        async with pool.connection() as conn:
            await conn.execute("delete from app_sessions where token = %s", (token,))
    return {"ok": True}
