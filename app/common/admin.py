"""管理后台的表结构与管理员名单。

管理端自己的列由本模块维护（和 quota 模块一样的做法：模块自带建表），
业务表（用户 / 令牌 / 会话归属）的建表仍在 app/common/db.py。
"""
from __future__ import annotations

import os

from psycopg.types.json import Jsonb
from psycopg_pool import AsyncConnectionPool

from app.common.logger import logger

ADMIN_SQL = [
    "alter table app_users add column if not exists is_admin boolean not null default false",
    # 管理操作审计日志。
    # 管理员/对象的名字额外存一份快照：账号被删掉之后，日志仍然看得懂是谁对谁做的。
    """
    create table if not exists app_admin_logs (
        id              bigserial primary key,
        created_at      timestamptz not null default now(),
        admin_id        bigint references app_users(id) on delete set null,
        admin_username  text not null,
        target_user_id  bigint references app_users(id) on delete set null,
        target_username text,
        action          text not null,
        detail          jsonb,
        result          text not null default 'ok',
        message         text,
        ip              text
    )
    """,
    "create index if not exists app_admin_logs_created_idx on app_admin_logs(created_at desc)",
    "create index if not exists app_admin_logs_admin_idx on app_admin_logs(admin_id)",
    "create index if not exists app_admin_logs_target_idx on app_admin_logs(target_user_id)",
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


async def record_admin_action(
    pool: AsyncConnectionPool,
    *,
    admin_id: int,
    admin_username: str,
    action: str,
    target_user_id: int | None = None,
    target_username: str | None = None,
    detail: dict | None = None,
    result: str = "ok",
    message: str | None = None,
    ip: str | None = None,
) -> None:
    """记一条管理操作日志。

    刻意"尽力而为"：日志写失败只在服务端告警，绝不因为它把主操作也搞挂。
    也刻意不记敏感内容（比如新密码）——detail 里只放变更字段和数量。
    """
    try:
        async with pool.connection() as conn:
            await conn.execute(
                """
                insert into app_admin_logs
                    (admin_id, admin_username, target_user_id, target_username,
                     action, detail, result, message, ip)
                values (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                """,
                (
                    admin_id,
                    admin_username,
                    target_user_id,
                    target_username,
                    action,
                    Jsonb(detail) if detail is not None else None,
                    result,
                    message,
                    ip,
                ),
            )
    except Exception as exc:  # noqa: BLE001
        logger.warning("写管理操作日志失败（不影响主流程）：%s", exc)
