import sys

from dotenv import load_dotenv
from langgraph.checkpoint.postgres import PostgresSaver
from langchain.agents import create_agent
from langchain_core.messages import SystemMessage,HumanMessage,AIMessage

# Windows 控制台默认是 GBK 编码，模型回复里带 emoji 时 print 会抛 UnicodeEncodeError
sys.stdout.reconfigure(encoding="utf-8")

load_dotenv()

DB_URI = "postgresql://postgres:880921@localhost:5432/postgres?sslmode=disable"
with PostgresSaver.from_conn_string(DB_URI) as checkpointer:
    checkpointer.setup() # auto create tables in PostgreSQL
    agent = create_agent(
        "deepseek-chat",
        checkpointer=checkpointer,
    )

    # 定义HumanMessage
    human_message1 = HumanMessage(content="你好，我叫虎哥，我喜欢猫")

    config = {"configurable": { "thread_id": "thread_2" }}

    response1 = agent.invoke(
        {"messages": [human_message1]},
        config=config,
    )

    print(response1)

    # 注意：agent 的调用必须留在 with 代码块内部。
    # 一旦离开 with，Postgres 连接会被关闭，再调用就会报 "the connection is closed"。
    # human_message2 = HumanMessage(content="我最喜欢的动物是什么")
    #
    # response2 = agent.invoke(
    #     {"messages": [human_message2]},
    #     config=config,
    # )
    # print(response2)
