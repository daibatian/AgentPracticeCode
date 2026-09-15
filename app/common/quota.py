"""每用户每周配额与限流。

设计要点：
- **额度按 token 计**，因为 token 才是真实成本；按"次数"计在图片提问场景会差 6 倍
  （实测一次文字提问约 3.6k token，一次图片提问约 22k token）。
- **额度按自然周重置**：每周一 00:00 起算，时区可配（服务器通常是 UTC，不配会把
  重置时刻挪到北京时间周二早上 8 点）。
- **默认额度全局配置、按用户可覆盖**：新用户不用逐个分配额度，`app_users.weekly_token_quota`
  留空就用全局默认值；后台要给某个用户加量时，才写这一列。
- **用量按天存、按周汇总**：`app_usage_daily` 每天一行（后台看趋势用），配额判断时
  把本周的行求和——既能按周限额，又不丢日粒度。
- **限流是内存滑动窗口**：只约束"每分钟发起多少次对话"，用于挡住脚本式的突发请求；
  它是单进程内的计数，多实例部署时每个实例各限一份（要全局精确就得换 Redis）。
"""
from __future__ import annotations

import os
import time
from collections import defaultdict, deque

from psycopg_pool import AsyncConnectionPool


def _int_env(name: str, default: int) -> int:
    raw = (os.getenv(name) or "").strip()
    if not raw:
        return default
    try:
        return max(int(raw), 0)
    except ValueError:
        return default


# 新用户的默认每周 token 额度；0 = 不限
DEFAULT_WEEKLY_TOKEN_QUOTA = _int_env("DEFAULT_WEEKLY_TOKEN_QUOTA", 0)
# 每个用户每分钟最多发起多少次对话；0 = 不限
RATE_LIMIT_PER_MINUTE = _int_env("RATE_LIMIT_PER_MINUTE", 0)
# 额度按哪个时区的自然周重置
QUOTA_TIMEZONE = (os.getenv("QUOTA_TIMEZONE") or "Asia/Shanghai").strip()

# 用量表 + 用户额度覆盖列。
# 这里自带建表语句，是因为配额模块的表结构由模块自己维护；
# 业务表（用户/令牌/会话归属）的建表仍在 app/common/db.py。
QUOTA_SQL = [
    """
    create table if not exists app_usage_daily (
        user_id       bigint  not null references app_users(id) on delete cascade,
        day           date    not null,
        requests      int     not null default 0,
        input_tokens  bigint  not null default 0,
        output_tokens bigint  not null default 0,
        primary key (user_id, day)
    )
    """,
    "create index if not exists app_usage_daily_day_idx on app_usage_daily(day)",
    # 额度覆盖列：口径从"每日"改成"每周"（老列是本次新加的、且全为空值，直接换掉）
    "alter table app_users add column if not exists weekly_token_quota int",
    "alter table app_users drop column if exists daily_token_quota",
]


async def init_quota_schema(pool: AsyncConnectionPool) -> None:
    """幂等建表；必须在 init_auth_tables 之后调用（app_users 要先存在）。"""
    async with pool.connection() as conn:
        for sql in QUOTA_SQL:
            await conn.execute(sql)


def resolve_quota(override: int | None) -> int:
    """用户没单独配额度时用全局默认值。"""
    if override is None:
        return DEFAULT_WEEKLY_TOKEN_QUOTA
    return max(int(override), 0)


async def effective_quota(pool: AsyncConnectionPool, user_id: int) -> int:
    """这个用户本周生效的 token 额度（0 = 不限）。"""
    async with pool.connection() as conn:
        cur = await conn.execute(
            "select weekly_token_quota from app_users where id = %s", (user_id,)
        )
        row = await cur.fetchone()
    override = row["weekly_token_quota"] if row else None
    return resolve_quota(override)


async def week_usage(pool: AsyncConnectionPool, user_id: int) -> dict:
    """本周（周一 00:00 起）的用量汇总；本周还没记录时返回全 0。

    顺带带回本周起止日期和下次重置时刻，接口/前端要显示"下周一重置"时直接用。
    """
    async with pool.connection() as conn:
        cur = await conn.execute(
            """
            with w as (
                select date_trunc('week', (now() at time zone %(tz)s)::date)::date as week_start
            )
            select w.week_start                                        as week_start,
                   (w.week_start + 7)                                  as week_end,
                   ((w.week_start + 7)::timestamp at time zone %(tz)s) as resets_at,
                   coalesce(sum(u.requests), 0)                        as requests,
                   coalesce(sum(u.input_tokens), 0)                    as input_tokens,
                   coalesce(sum(u.output_tokens), 0)                   as output_tokens
            from w
            left join app_usage_daily u
                   on u.user_id = %(user_id)s
                  and u.day >= w.week_start
                  and u.day <  w.week_start + 7
            group by w.week_start
            """,
            {"tz": QUOTA_TIMEZONE, "user_id": user_id},
        )
        return await cur.fetchone()


async def add_usage(
    pool: AsyncConnectionPool,
    user_id: int,
    input_tokens: int = 0,
    output_tokens: int = 0,
    requests: int = 1,
) -> None:
    """累加当天那一行的用量（一次对话算一次 requests，token 从模型返回里取）。"""
    async with pool.connection() as conn:
        await conn.execute(
            """
            insert into app_usage_daily (user_id, day, requests, input_tokens, output_tokens)
            values (%s, (now() at time zone %s)::date, %s, %s, %s)
            on conflict (user_id, day) do update
               set requests      = app_usage_daily.requests + excluded.requests,
                   input_tokens  = app_usage_daily.input_tokens + excluded.input_tokens,
                   output_tokens = app_usage_daily.output_tokens + excluded.output_tokens
            """,
            (user_id, QUOTA_TIMEZONE, requests, input_tokens, output_tokens),
        )


async def quota_snapshot(pool: AsyncConnectionPool, user_id: int) -> dict:
    """给接口用的一览：本周额度、已用、剩余、下次重置时间。"""
    quota = await effective_quota(pool, user_id)
    usage = await week_usage(pool, user_id)
    used = int(usage["input_tokens"] or 0) + int(usage["output_tokens"] or 0)
    return {
        "timezone": QUOTA_TIMEZONE,
        "week_start": usage["week_start"].isoformat(),
        "week_end": usage["week_end"].isoformat(),
        "resets_at": usage["resets_at"].isoformat(),
        "quota": quota,
        "used": used,
        "remaining": None if quota <= 0 else max(quota - used, 0),
        "requests": int(usage["requests"] or 0),
        "rate_limit_per_minute": RATE_LIMIT_PER_MINUTE,
    }


class SlidingWindowLimiter:
    """单进程内存限流：同一个 key 在 window 秒内最多 limit 次。

    limit <= 0 表示不限流，此时 check() 永远放行。
    """

    def __init__(self, limit: int, window_seconds: int = 60) -> None:
        self.limit = limit
        self.window = window_seconds
        self._hits: dict[str, deque[float]] = defaultdict(deque)

    def check(self, key: str) -> int:
        """放行返回 0；被限流返回还需要等待的秒数。"""
        if self.limit <= 0:
            return 0

        now = time.monotonic()
        hits = self._hits[key]
        while hits and now - hits[0] >= self.window:
            hits.popleft()

        if len(hits) >= self.limit:
            return max(int(self.window - (now - hits[0])) + 1, 1)

        hits.append(now)
        return 0

    def reset(self, key: str) -> None:
        """清掉某个 key 的计数（后台解封、测试时用）。"""
        self._hits.pop(key, None)

    def prune(self) -> None:
        """清掉过期的空队列，避免长期运行内存缓慢增长。"""
        now = time.monotonic()
        for key in list(self._hits):
            hits = self._hits[key]
            while hits and now - hits[0] >= self.window:
                hits.popleft()
            if not hits:
                self._hits.pop(key, None)
