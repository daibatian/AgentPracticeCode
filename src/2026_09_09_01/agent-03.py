from langchain.chat_models import init_chat_model
from langchain.agents import create_agent
from dotenv import load_dotenv
from langchain_core.messages import SystemMessage,HumanMessage,AIMessage
import os

load_dotenv()

model = init_chat_model(
    model="qwen3.8-max",
    model_provider="openai",
    base_url=os.getenv("DASHSCOPE_BASE_URL"),
    api_key=os.getenv("DASHSCOPE_API_KEY"),
)

agent = create_agent(model=model)

# 定义HumanMessage
human_message = HumanMessage([
        {"type": "text", "text": "描述这张图片的内容"},
        {"type": "image", "url": "https://tse2-mm.cn.bing.net/th/id/OIP-C.K1Q5dch5SvONb6T8s-zf7QHaE7?w=253&h=180&c=7&r=0&o=7&pid=1.7&rm=3"},
    ])

stream = agent.stream({
    "messages": human_message,
},stream_mode="messages")

for chunk,message in stream:
    if chunk.content:
        print(chunk.content,end="",flush=True)

