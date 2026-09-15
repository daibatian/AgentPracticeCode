"""管理后台的表结构与管理员名单。

管理端自己的列由本模块维护（和 quota 模块一样的做法：模块自带建表），
业务表（用户 / 令牌 / 会话归属）的建表仍在 app/common/db.py。
"""
from __future__ import annotations

import os

from psycopg_pool import AsyncConnectionPool

ADMIN_SQL = [
    "alter table app_users add column if not exists is_admin boolean not null default false",
]


def admin_usernames() -> list[str]:
    """从 .env 读「保证是管理员」的账号名单（逗号分隔，中英文逗号都认）。"""
    raw = os.getenv("ADMIN_USERNAMES") or ""
    names: list[str] = []
    for item in raw.replace("，", ",").split(","):
        name = item.strip()
        if name and name not in names:
            names.append(name)
    return names


async def init_admin_schema(pool: AsyncConnectionPool) -> None:
    """幂等建列；必须在 init_auth_tables 之后调用（app_users 要先存在）。"""
    async with pool.connection() as conn:
        for sql in ADMIN_SQL:
            await conn.execute(sql)


async def sync_admin_usernames(pool: AsyncConnectionPool) -> list[str]:
    """把 .env 里列出的账号补成管理员，返回本次实际提升的用户名。

    只提升、不降级。这样做有两个好处：
    1. 无论后台里怎么改，名单上的账号下次启动一定会恢复管理员身份，
       也就是"永远留一条能进后台的路"，不会把自己锁在门外；
    2. 不会覆盖你在界面上手动给其他账号调整过的权限。
    """
    names = admin_usernames()
    if not names:
        return []
    async with pool.connection() as conn:
        cur = await conn.execute(
            """
            update app_users set is_admin = true
            where username = any(%s) and is_admin = false
            returning username
            """,
            (names,),
        )
        return [row["username"] for row in await cur.fetchall()]


async def is_admin_user(pool: AsyncConnectionPool, user_id: int) -> bool:
    async with pool.connection() as conn:
        cur = await conn.execute(
            "select is_admin from app_users where id = %s", (user_id,)
        )
        row = await cur.fetchone()
    return bool(row and row["is_admin"])


async def count_admins(pool: AsyncConnectionPool) -> int:
    async with pool.connection() as conn:
        cur = await conn.execute("select count(*) as c from app_users where is_admin")
        return (await cur.fetchone())["c"]
