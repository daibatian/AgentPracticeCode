from langchain.chat_models import init_chat_model
from langchain.agents import create_agent
from dotenv import load_dotenv
from langchain_core.messages import SystemMessage,HumanMessage,AIMessage
import os
from langgraph.checkpoint.memory import InMemorySaver

load_dotenv()

agent = create_agent(
    model="deepseek-chat",
    checkpointer=InMemorySaver(),
    )

# 定义HumanMessage
human_message1 = HumanMessage(content="你好，我叫虎哥，我喜欢猫")

config = {"configurable": { "thread_id": "thread_1" }}

response1 = agent.invoke(
    {"messages": human_message1},
    config=config,
)

human_message2 = HumanMessage(content="我最喜欢的动物是什么")

response2 = agent.invoke(
    {"messages": human_message2},
    config=config,
)

print(response2)


