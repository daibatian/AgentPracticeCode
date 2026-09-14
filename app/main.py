import os
import asyncio
import sys
from contextlib import asynccontextmanager

# Windows 默认的 Proactor 事件循环不被 psycopg 的异步模式支持
# （会报 "Psycopg cannot use the 'ProactorEventLoop' to run in async mode"），
# 必须在事件循环创建之前切成 Selector。只影响本地 Windows 开发，
# Linux（生产 / 容器）默认就是可用的循环，没有这个问题。
if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
from psycopg.rows import dict_row
from psycopg_pool import AsyncConnectionPool

from app.agents.personal_chief import build_agent_pool
from app.api.v1 import chat
from app.api.v1 import oss
from app.api.v1 import auth
from app.api.v1 import profile
from app.common.db import init_auth_tables
from app.common.logger import setup_logging

# 先加载 .env，后面读环境变量才拿得到值
load_dotenv()

# 初始化日志配置
setup_logging()

# 数据库连接串只从环境变量读（在 .env 里配），代码里不留密码
POSTGRES_URI = os.getenv("POSTGRES_URI")
if not POSTGRES_URI:
    raise RuntimeError(
        "缺少数据库连接串：请在 .env 里配置 POSTGRES_URI，例如\n"
        "POSTGRES_URI=postgresql://用户名:密码@主机:5432/库名?sslmode=disable"
    )


@asynccontextmanager
async def lifespan(app: FastAPI):
    """启动时建好连接池、checkpointer 和 agent，之后全程复用。"""
    pool = AsyncConnectionPool(
        conninfo=POSTGRES_URI,
        max_size=10,
        kwargs={"autocommit": True, "row_factory": dict_row},
        open=False,
    )
    await pool.open()
    checkpointer = AsyncPostgresSaver(pool)
    await checkpointer.setup()  # 幂等建表，重复启动也不会出错
    await init_auth_tables(pool)  # 用户 / 登录令牌 / 会话归属三张表

    app.state.pool = pool
    app.state.checkpointer = checkpointer
    # 按「主模型 → 备用模型」的顺序建好一组 agent，调用时自动降级
    app.state.agents = build_agent_pool(checkpointer)
    try:
        yield
    finally:
        await pool.close()


# 接口文档默认关闭：把 /docs /redoc /openapi.json 挂在公网上等于公开接口清单
# 本地调试需要时，在 .env 里写 DOCS_ENABLED=true
DOCS_ENABLED = (os.getenv("DOCS_ENABLED") or "").strip().lower() in {
    "1", "true", "yes", "on",
}

app = FastAPI(
    title="Personal Chief API",
    description="私厨",
    version="0.1.0",
    lifespan=lifespan,
    docs_url="/docs" if DOCS_ENABLED else None,
    redoc_url="/redoc" if DOCS_ENABLED else None,
    openapi_url="/openapi.json" if DOCS_ENABLED else None,
)

# 1. 配置跨域资源共享 (CORS)
# 插件开发中，由于请求来自浏览器扩展环境，必须正确配置 CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # 生产环境建议指定插件的 ID 或具体域名
    # 注意：["*"] 和 allow_credentials=True 是无效组合，浏览器会直接拒绝请求
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 2.挂载路由
app.include_router(chat.router, prefix="/api/v1", tags=["对话"])
app.include_router(oss.router, prefix="/api/v1", tags=["申请上传签名url"])
app.include_router(auth.router, prefix="/api/v1", tags=["账号"])
app.include_router(profile.router, prefix="/api/v1", tags=["用户资料"])

# 3.挂载前端资源
static_dir = os.path.join(os.path.dirname(__file__), "static")
if os.path.exists(static_dir):
    app.mount("/", StaticFiles(directory=static_dir, html=True), name="static")

# 前端 fallback 路由 - 只处理非 API 请求
@app.get("/{path:path}", include_in_schema=False)
async def serve_frontend(path: str):
    # 排除 API 路径
    if path.startswith("api/"):
        from fastapi.responses import JSONResponse
        return JSONResponse({"error": "Not Found"}, status_code=404)
    # 如果请求的是静态文件，直接返回
    file_path = os.path.join(static_dir, path)
    if os.path.isfile(file_path):
        return FileResponse(file_path)
    # 否则返回 index.html（SPA fallback）
    index_path = os.path.join(static_dir, "index.html")
    if os.path.exists(index_path):
        return FileResponse(index_path)
    return {"message": "你的独家私厨上线了~", "status": "ok"}

if __name__ == "__main__":
    import uvicorn

    # 启动命令：python -m app.main（或 uv run python -m app.main）
    # 注意：不要加 reload=True。uvicorn 起子进程时会强制切回 Proactor 循环，
    # psycopg 的异步模式在那种循环下连不上数据库。
    # loop="none" 让 uvicorn 不指定事件循环，这样才会用上面设置的 Selector。
    uvicorn.run(
        app,
        host=os.getenv("HOST", "127.0.0.1"),
        port=int(os.getenv("PORT", "8001")),
        loop="none",
    )
