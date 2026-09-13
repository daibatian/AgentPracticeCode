# 加载环境变量（.env文件）
from dotenv import load_dotenv
from langchain_mcp_adapters.client import MultiServerMCPClient

load_dotenv()


# **定义模型**
# 涉及到图片，需要用到多模态模型
from langchain.chat_models import init_chat_model
import json
import os

from langchain_core.tools import tool

from app.common.llm import model_names

# 对话历史估算超过这么多 token 就自动做摘要（可用环境变量覆盖）
CONTEXT_MAX_TOKENS = int(os.getenv("CONTEXT_MAX_TOKENS", "12000"))
# 摘要后保留最近多少条消息
CONTEXT_KEEP_MESSAGES = int(os.getenv("CONTEXT_KEEP_MESSAGES", "8"))


# 千问不能被langchain框架兼容，需要另外去初始化模型
# 模型名从环境变量读（.env 里的 MODEL_NAME），换模型不用改代码
def create_model(model_name: str):
    return init_chat_model(
        model=model_name,
        model_provider="openai",
        base_url=os.getenv("DASHSCOPE_BASE_URL"),
        api_key=os.getenv("DASHSCOPE_API_KEY"),
    )


# 当前使用的主模型（.env 里的 MODEL_NAME，没配就用默认值）
MODEL_NAME = model_names()[0]


# # 引入Travily联网搜索工具
from langchain_tavily import TavilySearch

# 一条搜索结果的摘要保留多少字
SEARCH_SNIPPET_CHARS = 400
# 压缩后单次搜索结果的总长度上限
SEARCH_RESULT_MAX_CHARS = 3000
# 保留几张参考图
SEARCH_MAX_IMAGES = 3

# 国内图床 / CDN 的域名特征：命中就优先用
DOMESTIC_HOST_HINTS = (
    ".cn",
    "aliyuncs.com",
    "myqcloud.com",
    "qiniucdn.com",
    "qiniu.com",
    "zhimg.com",
    "hdslb.com",
    "byteimg.com",
    "toutiaoimg.com",
    "ixigua.com",
    "sinaimg",
    "weibo",
    "360buyimg",
    "jd.com",
    "meituan",
    "dianping",
    "baidu",
    "bdimg",
    "bdstatic",
    "sohu",
    "163.com",
    "ifeng",
    "qq.com",
    "gtimg",
    "xiachufang",
    "chuimg",
    "douguo",
    "meishichina",
    "xiangha",
    "meishij",
    "haodou",
    "huitu",
    "tuchong",
    "zcool",
    "huaban",
    "duitang",
    "699pic",
    "redocn",
)

# 中国大陆通常访问不了的境外图床 / CDN：直接从候选里剔除
BLOCKED_HOST_HINTS = (
    "fbcdn",
    "ggpht",
    "googleusercontent",
    "gstatic",
    "twimg",
    "ytimg",
    "pinimg",
    "imgur",
    "redd.it",
    "redditmedia",
    "cdninstagram",
    "tiktokcdn",
    "ttvnw",
    "tumblr",
    "blogspot",
    "wikimedia",
)


def _host_of(url: str) -> str:
    """从 URL 里取域名（不引依赖，简单切分够用）。"""
    try:
        return url.split("//", 1)[1].split("/", 1)[0].lower()
    except IndexError:
        return ""


def _rank_images(urls: list[str], limit: int) -> list[str]:
    """图片排序：优先国内图床，剔除大陆访问不了的，来源未知的放最后。"""
    domestic: list[str] = []
    unknown: list[str] = []

    for url in urls:
        host = _host_of(url)
        if any(hint in host for hint in BLOCKED_HOST_HINTS):
            continue
        if any(hint in host for hint in DOMESTIC_HOST_HINTS):
            domestic.append(url)
        else:
            unknown.append(url)

    return (domestic + unknown)[:limit]


# include_images=True：让搜索结果带参考图；
# country=china：让搜索结果偏向国内站点（更容易拿到国内能直接打开的图）
_tavily = TavilySearch(
    max_results=5,
    topic="general",
    include_images=True,
    country="china",
)


def _compact_search_result(raw) -> str:
    """把 Tavily 返回的原始 JSON 压缩成简短文本。

    实测一次搜索的原始 JSON 有 6KB 以上，里面大量是字段名、评分、request_id
    以及每个结果很长的正文；真正有用的只有标题、链接、一段摘要和参考图。
    原样塞进对话历史会让上下文迅速膨胀（实测占过一次会话的 93%）。
    """
    try:
        data = json.loads(raw) if isinstance(raw, str) else raw
    except (TypeError, ValueError):
        return str(raw)[:SEARCH_RESULT_MAX_CHARS]

    if not isinstance(data, dict):
        return str(data)[:SEARCH_RESULT_MAX_CHARS]

    lines: list[str] = []

    answer = data.get("answer")
    if answer:
        lines.append(f"【联网摘要】{' '.join(str(answer).split())}")

    results = data.get("results") or []
    lines.append(f"【搜索结果】共 {len(results)} 条")
    for index, item in enumerate(results[:5], start=1):
        if not isinstance(item, dict):
            continue
        title = (item.get("title") or "").strip()
        url = (item.get("url") or "").strip()
        content = " ".join((item.get("content") or "").split())[:SEARCH_SNIPPET_CHARS]
        lines.append(f"{index}. {title}\n   链接：{url}\n   摘要：{content}")

    images = [img for img in (data.get("images") or []) if isinstance(img, str)]
    picked = _rank_images(images, SEARCH_MAX_IMAGES)
    if picked:
        lines.append("【参考图片】" + " | ".join(picked))

    return "\n".join(lines)[:SEARCH_RESULT_MAX_CHARS]


@tool
def web_search(query: str) -> str:
    """联网搜索食材、菜谱和做法。输入搜索关键词，返回网页标题、链接和摘要。"""
    return _compact_search_result(_tavily.invoke({"query": query}))


from langchain.agents import create_agent
from langchain.agents.middleware import (
    ModelRequest,
    SummarizationMiddleware,
    dynamic_prompt,
)
from typing import TypedDict

system_prompt = """
你是一名私人厨师。收到用户提供的食材照片或清单后，请按以下流程操作：
1.识别和评估食材：若用户提供照片，首先辨识所有可见食材。基于食材的外观状态，评估其新鲜度与可用量，整理出一份“当前可用食材清单”。
2.智能食谱检索：优先调用 web_search 工具，以“可用食材清单”为核心关键词，查找可行菜谱。
3.多维度评估与排序：从营养价值和制作难度两个维度对检索到的候选食谱进行量化打分，并根据得分排序，制作简单且营养丰富的排名靠前。
4.结构化方案输出：把排序后的食谱整理为一份结构清晰的建议报告，要包含食谱信息、得分、推荐理由、食谱的参考图片，帮助用户快速做出决策。

注意：参考图片只能使用 web_search 返回的【参考图片】里给出的链接，不要自己编造图片地址，并且优先选择国内可访问的图片源。

请严格按照流程，优先调用 web_search 工具搜索食谱，搜索不到的情况下才能自己发挥。
"""


class ChefContext(TypedDict):
    """每次调用 agent 时带进来的运行时上下文。"""

    preferences: str


def _context_preferences(request: ModelRequest) -> str:
    """从运行时上下文里取用户偏好文本；没传就返回空串。"""
    context = getattr(getattr(request, "runtime", None), "context", None)
    if context is None:
        return ""
    if isinstance(context, dict):
        return context.get("preferences") or ""
    return getattr(context, "preferences", "") or ""


@dynamic_prompt
def chef_system_prompt(request: ModelRequest) -> str:
    """动态生成系统提示词：基础提示 + 当前用户的菜品偏好。

    没设置偏好的用户拿到的是原样的基础提示词，行为和加这个功能之前完全一致。
    """
    return system_prompt + _context_preferences(request)


def build_agent(checkpointer=None, model_name: str | None = None):
    """构建 agent。

    checkpointer=None：交给 LangGraph API / langgraph dev 自己管持久化；
    传入 checkpointer：FastAPI 直接调用时由自己管持久化（见 app/main.py）。
    model_name 不传就用 .env 里的 MODEL_NAME。
    """
    name = model_name or MODEL_NAME
    summarization = SummarizationMiddleware(
        # 摘要用它自己的模型实例生成（同一个模型）
        model=create_model(name),
        # 对话历史的估算 token 超过阈值就触发摘要
        trigger=("tokens", CONTEXT_MAX_TOKENS),
        # 摘要后保留最近这么多条消息，保证对话连贯
        keep=("messages", CONTEXT_KEEP_MESSAGES),
    )

    return create_agent(
        model=create_model(name),
        tools=[web_search],
        # 系统提示词改由中间件动态生成（要按用户拼偏好），
        # 所以这里不再传 system_prompt
        middleware=[chef_system_prompt, summarization],
        context_schema=ChefContext,
        checkpointer=checkpointer,
    )


def build_agent_pool(checkpointer=None):
    """按「主模型 → 备用模型」的顺序各建一个 agent。

    返回 [(模型名, agent), ...]；调用时从前到后试，前面的不可用就换下一个。
    """
    return [
        (name, build_agent(checkpointer=checkpointer, model_name=name))
        for name in model_names()
    ]


# 供 langgraph.json 里注册的 "app/agents/personal_chief.py:agent" 使用。
# 这里不能带 checkpointer：平台会自己注入，自带 checkpointer 会直接报
# "providing a custom checkpointer ... isn't necessary and will be ignored when deployed"
agent = build_agent()
