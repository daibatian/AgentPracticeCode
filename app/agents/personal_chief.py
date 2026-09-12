# 加载环境变量（.env文件）
from dotenv import load_dotenv
from langchain_mcp_adapters.client import MultiServerMCPClient

load_dotenv()


# **定义模型**
# 涉及到图片，需要用到多模态模型
from langchain.chat_models import init_chat_model
import os

# 千问不能被langchain框架兼容，需要另外去初始化模型
model = init_chat_model(
    model="qwen3.8-flash",
    model_provider="openai",
    base_url=os.getenv("DASHSCOPE_BASE_URL"),
    api_key=os.getenv("DASHSCOPE_API_KEY"),
)


# # 引入Travily联网搜索工具
from langchain_tavily import TavilySearch

web_search = TavilySearch(
    max_results=5,
    topic="general"
)


from langchain.agents import create_agent

system_prompt = """
你是一名私人厨师。收到用户提供的食材照片或清单后，请按以下流程操作：
1.识别和评估食材：若用户提供照片，首先辨识所有可见食材。基于食材的外观状态，评估其新鲜度与可用量，整理出一份“当前可用食材清单”。
2.智能食谱检索：优先调用 web_search 工具，以“可用食材清单”为核心关键词，查找可行菜谱。
3.多维度评估与排序：从营养价值和制作难度两个维度对检索到的候选食谱进行量化打分，并根据得分排序，制作简单且营养丰富的排名靠前。
4.结构化方案输出：把排序后的食谱整理为一份结构清晰的建议报告，要包含食谱信息、得分、推荐理由、食谱的参考图片，帮助用户快速做出决策。

请严格按照流程，优先调用 web_search 工具搜索食谱，搜索不到的情况下才能自己发挥。
"""

def build_agent(checkpointer=None):
    """构建 agent。

    checkpointer=None：交给 LangGraph API / langgraph dev 自己管持久化；
    传入 checkpointer：FastAPI 直接调用时由自己管持久化（见 app/main.py）。
    """
    return create_agent(
        model=model,
        tools=[web_search],
        system_prompt=system_prompt,
        checkpointer=checkpointer,
    )


# 供 langgraph.json 里注册的 "app/agents/personal_chief.py:agent" 使用。
# 这里不能带 checkpointer：平台会自己注入，自带 checkpointer 会直接报
# "providing a custom checkpointer ... isn't necessary and will be ignored when deployed"
agent = build_agent()
