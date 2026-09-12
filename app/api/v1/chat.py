from fastapi import APIRouter, Request
from fastapi.responses import StreamingResponse
from langchain_core.messages import AIMessageChunk, HumanMessage

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


@router.post("/chat/stream")
async def chat_stream(payload: ChatRequest, request: Request):
    """流式对话：返回纯文本流，前端逐块拼接显示。"""
    agent = request.app.state.agent
    config = {"configurable": {"thread_id": payload.thread_id}}

    async def generate():
        async for chunk, _meta in agent.astream(
            {"messages": [_to_human_message(payload)]},
            config,
            stream_mode="messages",
        ):
            # 只转发"模型自己生成的文本增量"。
            # stream_mode="messages" 会把工具返回（ToolMessage，内容是 Tavily 的原始 JSON）
            # 也一起吐出来，直接透传前端会显示一大段 JSON。
            if not isinstance(chunk, AIMessageChunk):
                continue
            # 工具调用那一轮会产出内容为空的 chunk，这里也过滤掉
            if isinstance(chunk.content, str) and chunk.content:
                yield chunk.content

    # 注意：前端直接读原始响应体，所以吐纯文本，不能加 SSE 的 "data: " 前缀
    return StreamingResponse(generate(), media_type="text/plain; charset=utf-8")


@router.get("/chat/messages")
async def get_chat_messages(thread_id: str, request: Request):
    """读取某个会话的历史消息。"""
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
        text = _content_to_text(m.content)
        # 只有工具调用、没有正文的消息也跳过
        if not text:
            continue
        messages.append({"role": ROLE_MAP.get(m.type, m.type), "content": text})
    return {"messages": messages}


@router.get("/chat/threads")
async def list_threads(request: Request):
    """列出全部历史会话（最近活跃的在前），供前端侧边栏使用。"""
    pool = request.app.state.pool
    checkpointer = request.app.state.checkpointer

    # 每个会话最新的检查点时间，用它排序
    async with pool.connection() as conn:
        cur = await conn.execute(
            """
            select thread_id, max(checkpoint->>'ts') as last_active
            from checkpoints
            group by thread_id
            order by last_active desc nulls last
            limit 100
            """
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
async def clear_chat_messages(thread_id: str, request: Request):
    """清空某个会话的历史（checkpoints / blobs / writes 三张表一起删）。"""
    await request.app.state.checkpointer.adelete_thread(thread_id)
    return {"ok": True}
