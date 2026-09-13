"""业务表（用户 / 登录令牌 / 会话归属）的初始化。

注意：这些表和 checkpointer 的 checkpoint_* 表是两回事。
checkpoint 表存对话内容，这里的表只负责"谁拥有哪个会话"。
"""
from __future__ import annotations

from psycopg_pool import AsyncConnectionPool

# 每条单独执行（psycopg 的扩展协议不支持一次执行多条语句）
AUTH_TABLES_SQL = [
    """
    create table if not exists app_users (
        id            bigserial primary key,
        username      text not null unique,
        password_hash text not null,
        created_at    timestamptz not null default now()
    )
    """,
    """
    create table if not exists app_sessions (
        token      text primary key,
        user_id    bigint not null references app_users(id) on delete cascade,
        created_at timestamptz not null default now(),
        expires_at timestamptz not null
    )
    """,
    "create index if not exists app_sessions_user_id_idx on app_sessions(user_id)",
    """
    create table if not exists app_threads (
        thread_id  text primary key,
        user_id    bigint not null references app_users(id) on delete cascade,
        created_at timestamptz not null default now()
    )
    """,
    "create index if not exists app_threads_user_id_idx on app_threads(user_id)",
]

# 用户资料 / 菜品偏好的列（后加的，用 add column if not exists 平滑升级）
PROFILE_COLUMNS_SQL = [
    "alter table app_users add column if not exists display_name text",
    "alter table app_users add column if not exists taste text",
    "alter table app_users add column if not exists spicy_level text",
    "alter table app_users add column if not exists diet_goal text",
    "alter table app_users add column if not exists avoid_ingredients text",
    "alter table app_users add column if not exists preferred_cuisines text",
    "alter table app_users add column if not exists notes text",
    # 基础信息
    "alter table app_users add column if not exists avatar text",
    "alter table app_users add column if not exists phone text",
    "alter table app_users add column if not exists signature text",
]


async def init_auth_tables(pool: AsyncConnectionPool) -> None:
    """幂等建表，应用启动时调用一次。"""
    async with pool.connection() as conn:
        for sql in AUTH_TABLES_SQL:
            await conn.execute(sql)
        for sql in PROFILE_COLUMNS_SQL:
            await conn.execute(sql)
