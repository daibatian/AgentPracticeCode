from langchain.chat_models import init_chat_model
from langchain.agents import create_agent
from dotenv import load_dotenv
from langchain.tools import tool
import requests
from langchain_core.messages import SystemMessage,HumanMessage,AIMessage

load_dotenv()

@tool
def getWeather(location: str) -> str:
    """
    根据城市名称获取当前天气情况，并返回一段友好的中文描述。
    当用户询问某地天气时，调用此工具。

    Args:
        location: 城市名称，例如 "北京"、"Shanghai"、"London"

    Returns:
        一段包含天气状况、温度、体感温度、湿度、风速的中文描述。
    """
    # wttr.in 的 JSON 接口，会自动根据 IP 判断语言，但我们明确指定 zh 以获得中文天气状况描述
    url = f"https://wttr.in/{location}?format=j1&lang=zh"

    try:
        response = requests.get(url, timeout=10)
        response.raise_for_status()
        data = response.json()

        # 提取关键数据
        current = data["current_condition"][0]
        weather_desc = current["weatherDesc"][0]["value"]  # 天气状况（中文）
        temp_c = current["temp_C"]  # 温度（摄氏度）
        feels_like = current["FeelsLikeC"]  # 体感温度
        humidity = current["humidity"]  # 湿度百分比
        wind_speed = current["windspeedKmph"]  # 风速（km/h）
        city = data["nearest_area"][0]["areaName"][0]["value"]  # 城市名（中文）
        country = data["nearest_area"][0]["country"][0]["value"]  # 国家（中文）

        # 用自然语言组织成一段文字
        result = (
            f"📍 {city}（{country}）当前天气：\n"
            f"☁️ 天气状况：{weather_desc}\n"
            f"🌡️ 温度：{temp_c}°C（体感 {feels_like}°C）\n"
            f"💧 湿度：{humidity}%\n"
            f"💨 风速：{wind_speed} km/h\n"
            f"\n（数据来源：wttr.in）"
        )
        return result

    except requests.exceptions.RequestException as e:
        # 返回清晰的错误信息，方便 Agent 向用户反馈
        return f"❌ 获取“{location}”天气信息失败，原因：{str(e)}。请稍后重试或检查城市名称是否正确。"

model = init_chat_model(model="deepseek-chat")

agent = create_agent(model=model,tools=[getWeather])

# response = model.invoke("你是谁？")
# response = model.stream("你是谁？")

response = agent.stream({
    "messages": [
        SystemMessage("你是一名热情的AI"),
        HumanMessage("你好，我是虎哥"),
        AIMessage("你好，虎哥，很高兴认识你"),
        HumanMessage("北京今天的天气如何？")
    ],
},stream_mode="messages")

for token,message in response:
    if token.content:
        print(token.content,end="",flush=True)