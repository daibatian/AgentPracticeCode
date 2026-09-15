from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import StreamingResponse
from langchain_core.messages import AIMessageChunk, HumanMessage

from app.api.deps import get_current_user
from app.common.llm import should_fallback
from app.common.logger import logger
from app.common.preferences import format_user_context
from app.common.quota import add_usage, effective_quota, today_usage
from app.models.schemas import ChatRequest

router = APIRouter()

# LangChain 的消息类型 -> 前端认的角色名
ROLE_MAP = {"human": "user", "ai": "assistant", "system": "system", "tool": "assistant"}


def _to_human_message(payload: ChatRequest) -> HumanMessage:
    """把请求转成多模态 HumanMessage（带图片时走多模态格式）。"""
    if payload.image_url:
        return HumanMessage(content=[
            {"type": "text", "text": payload.message},
            {"type": "image", "url": payload.image_url},
        ])
    return HumanMessage(content=payload.message)


def _content_to_text(content) -> str:
    """消息内容可能是字符串，也可能是多模态列表，统一拍平成文本。"""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return "".join(
            part.get("text", "")
            for part in content
            if isinstance(part, dict) and part.get("type") == "text"
        )
    return ""


def _content_to_parts(content):
    """转成前端能直接用的形式：纯文本，或 [文本, 图片...] 数组。

    只返回文本的话，用户上传的图片在刷新/切换会话后就会消失
    （前端本来就支持数组形式，是后端把它拍平了）。
    """
    if isinstance(content, str):
        return content
    if not isinstance(content, list):
        return ""

    texts: list[str] = []
    images: list[str] = []
    for part in content:
        if not isinstance(part, dict):
            continue
        part_type = part.get("type")
        if part_type == "text":
            texts.append(part.get("text", ""))
        elif part_type in ("image", "image_url"):
            url = part.get("url")
            if not url and isinstance(part.get("image_url"), dict):
                url = part["image_url"].get("url")
            if url:
                images.append(url)

    text = "".join(texts)
    if not images:
        return text
    return [{"type": "text", "text": text}] + [
        {"type": "image", "url": url} for url in images
    ]


async def _thread_owner(pool, thread_id: str):
    """这个会话归谁所有？没登记过返回 None。"""
    async with pool.connection() as conn:
        cur = await conn.execute(
            "select user_id from app_threads where thread_id = %s", (thread_id,)
        )
        row = await cur.fetchone()
    return row["user_id"] if row else None


async def _ensure_thread_owned(pool, thread_id: str, user_id: int) -> None:
    """确认会话属于当前用户；第一次见到这个 thread_id 时登记归属。"""
    owner = await _thread_owner(pool, thread_id)
    if owner is None:
        async with pool.connection() as conn:
            await conn.execute(
                """
                insert into app_threads (thread_id, user_id) values (%s, %s)
                on conflict (thread_id) do nothing
                """,
                (thread_id, user_id),
            )
        owner = await _thread_owner(pool, thread_id)

    if owner != user_id:
        raise HTTPException(status_code=403, detail="无权访问该会话")


async def _load_preferences(pool, user_id: int) -> str:
    """取当前用户的称呼和菜品偏好，拼成给模型看的说明；都没设置返回空串。"""
    async with pool.connection() as conn:
        cur = await conn.execute(
            """
            select display_name, taste, spicy_level, diet_goal,
                   avoid_ingredients, preferred_cuisines, notes
            from app_users where id = %s
            """,
            (user_id,),
        )
        row = await cur.fetchone()
    return format_user_context(row)


@router.post("/chat/stream")
async def chat_stream(
    payload: ChatRequest,
    request: Request,
    user: dict = Depends(get_current_user),
):
    """流式对话：返回纯文本流，前端逐块拼接显示。"""
    pool = request.app.state.pool
    await _ensure_thread_owned(pool, payload.thread_id, user["id"])

    # 1) 限流：挡住脚本式的突发请求（按用户计，每分钟 N 次）
    limiter = getattr(request.app.state, "rate_limiter", None)
    if limiter is not None:
        retry_after = limiter.check(str(user["id"]))
        if retry_after:
            limiter.prune()
            logger.warning("用户 %s 触发限流，%s 秒后可再试", user["id"], retry_after)
            raise HTTPException(
                status_code=429,
                detail=f"请求太频繁了，请 {retry_after} 秒后再试",
                headers={"Retry-After": str(retry_after)},
            )

    # 2) 每日额度：先看今天已经用掉多少（本轮用量在回复结束后累加）
    quota = await effective_quota(pool, user["id"])
    if quota > 0:
        usage = await today_usage(pool, user["id"])
        used = int(usage["input_tokens"] or 0) + int(usage["output_tokens"] or 0)
        if used >= quota:
            logger.warning("用户 %s 今日额度已用完：%s/%s token", user["id"], used, quota)
            raise HTTPException(
                status_code=429,
                detail=f"今日额度已用完（{used}/{quota} token），明天再来吧",
            )

    preferences = await _load_preferences(pool, user["id"])

    candidates: list = list(getattr(request.app.state, "agents", []) or [])
    if not candidates:
        raise HTTPException(status_code=503, detail="当前没有可用的模型")
    config = {"configurable": {"thread_id": payload.thread_id}}

    # 本次请求累计的 token 用量（一次对话可能包含多轮模型调用）
    usage = {"input": 0, "output": 0}
    recorded = False

    async def persist_usage() -> None:
        """把本轮消耗的 token 累加进今天的用量里，一次请求只记一次。

        记在整个请求结束时（正常结束 / 报错 / 客户端断开都会走到），而不是
        每次模型尝试结束时——降级时失败的那次会把"已记录"提前置上，后面
        真正成功那次的用量就漏记了。
        """
        nonlocal recorded
        if recorded:
            return
        recorded = True
        try:
            await add_usage(
                pool,
                user["id"],
                input_tokens=usage["input"],
                output_tokens=usage["output"],
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning("记录用量失败（不影响本次回复）：%s", exc)

    async def stream_from_models():
        """按主模型 → 备用模型的顺序尝试；额度用尽/限流/不可用就换下一个。"""
        last_error: Exception | None = None

        for index, (model_name, agent) in enumerate(candidates):
            emitted = False
            try:
                async for chunk, _meta in agent.astream(
                    {"messages": [_to_human_message(payload)]},
                    config,
                    # 把该用户的称呼和菜品偏好作为运行时上下文传给 agent，
                    # 由 chef_system_prompt 中间件拼进系统提示词
                    context={"preferences": preferences},
                    stream_mode="messages",
                ):
                    # 只转发"模型自己生成的文本增量"。
                    # stream_mode="messages" 会把工具返回（ToolMessage，内容是 Tavily 的原始 JSON）
                    # 也一起吐出来，直接透传前端会显示一大段 JSON。
                    if not isinstance(chunk, AIMessageChunk):
                        continue
                    # 一次对话可能调用多轮模型（工具循环），每轮的用量都要累加；
                    # 如果发生了降级，失败那轮真实消耗的 token 也会被算进去
                    meta = getattr(chunk, "usage_metadata", None)
                    if meta:
                        usage["input"] += meta.get("input_tokens") or 0
                        usage["output"] += meta.get("output_tokens") or 0
                    # 工具调用那一轮会产出内容为空的 chunk，这里也过滤掉
                    if isinstance(chunk.content, str) and chunk.content:
                        emitted = True
                        yield chunk.content

                if index > 0:
                    logger.info("本次回复由备用模型 %s 生成", model_name)
                return

            except Exception as exc:  # noqa: BLE001
                last_error = exc
                if emitted:
                    # 已经开始往外吐字了，重试会造成内容重复，只能如实报错
                    logger.error("模型 %s 输出中断：%s", model_name, exc)
                    raise
                if index + 1 >= len(candidates) or not should_fallback(exc):
                    logger.error("模型 %s 调用失败，且没有可用的备用模型：%s", model_name, exc)
                    raise
                logger.warning(
                    "模型 %s 调用失败（%s），自动切换到 %s",
                    model_name,
                    exc,
                    candidates[index + 1][0],
                )
        if last_error:
            raise last_error

    async def generate():
        """透传模型输出，并在请求真正结束时记录用量。"""
        try:
            async for piece in stream_from_models():
                yield piece
        finally:
            # 正常结束、报错、客户端中途断开都会走到这里
            await persist_usage()

    # 注意：前端直接读原始响应体，所以吐纯文本，不能加 SSE 的 "data: " 前缀
    return StreamingResponse(generate(), media_type="text/plain; charset=utf-8")


@router.get("/chat/messages")
async def get_chat_messages(
    thread_id: str,
    request: Request,
    user: dict = Depends(get_current_user),
):
    """读取某个会话的历史消息。"""
    owner = await _thread_owner(request.app.state.pool, thread_id)
    if owner is None:
        return {"messages": []}
    if owner != user["id"]:
        raise HTTPException(status_code=403, detail="无权访问该会话")

    tup = await request.app.state.checkpointer.aget_tuple(
        {"configurable": {"thread_id": thread_id}}
    )
    if tup is None:
        return {"messages": []}

    raw_messages = tup.checkpoint.get("channel_values", {}).get("messages", [])
    messages = []
    for m in raw_messages:
        # 工具调用结果（Tavily 返回的原始 JSON）不返回给前端
        if m.type == "tool":
            continue
        content = _content_to_parts(m.content)
        # 既没正文、也没图片的消息跳过
        if not content:
            continue
        if isinstance(content, str) and not content.strip():
            continue
        messages.append({"role": ROLE_MAP.get(m.type, m.type), "content": content})
    return {"messages": messages}


@router.get("/chat/threads")
async def list_threads(
    request: Request,
    user: dict = Depends(get_current_user),
):
    """列出**当前用户**的历史会话（最近活跃的在前），供前端侧边栏使用。"""
    pool = request.app.state.pool
    checkpointer = request.app.state.checkpointer

    # 每个会话最新的检查点时间，用它排序
    async with pool.connection() as conn:
        cur = await conn.execute(
            """
            select c.thread_id, max(c.checkpoint->>'ts') as last_active
            from checkpoints c
            join app_threads t on t.thread_id = c.thread_id
            where t.user_id = %s
            group by c.thread_id
            order by last_active desc nulls last
            limit 100
            """,
            (user["id"],),
        )
        rows = await cur.fetchall()

    threads = []
    for row in rows:
        thread_id = row["thread_id"]
        tup = await checkpointer.aget_tuple(
            {"configurable": {"thread_id": thread_id}}
        )
        if tup is None:
            continue

        raw_messages = (tup.checkpoint.get("channel_values") or {}).get(
            "messages", []
        )
        title = None
        count = 0
        for m in raw_messages:
            if m.type not in ("human", "ai"):
                continue
            text = _content_to_text(m.content).strip()
            if not text:
                continue
            count += 1
            if title is None and m.type == "human":
                title = text

        if count == 0:  # 空会话不展示
            continue

        threads.append(
            {
                "thread_id": thread_id,
                "title": (title or "新对话").replace("\n", " ")[:30],
                "last_active": row["last_active"],
                "message_count": count,
            }
        )

    return {"threads": threads}


@router.delete("/chat/messages")
async def clear_chat_messages(
    thread_id: str,
    request: Request,
    user: dict = Depends(get_current_user),
):
    """清空某个会话的历史（checkpoints / blobs / writes 三张表一起删）。"""
    owner = await _thread_owner(request.app.state.pool, thread_id)
    if owner is not None and owner != user["id"]:
        raise HTTPException(status_code=403, detail="无权删除该会话")

    await request.app.state.checkpointer.adelete_thread(thread_id)
    async with request.app.state.pool.connection() as conn:
        await conn.execute(
            "delete from app_threads where thread_id = %s", (thread_id,)
        )
    return {"ok": True}
