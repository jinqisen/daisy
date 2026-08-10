from .core.patch import apply_patches
# 在导入任何其他可能依赖 langchain 的模块之前应用补丁
apply_patches()

from fastapi import Depends, FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from .api.server import router as api_router
from .api.auth import router as auth_router
from .api.admin import router as admin_router
from .api.metrics import router as metrics_router
from .core.config import settings
from .core.database import SessionLocal
from .services.system.schema_bootstrap import init_db
from .services.system.init_data import init_personality_data, init_portraits, load_llm_providers_to_redis
from .core.logger import configure_logging, shutdown_logging
from .services.persona.emotion import get_emotion_service
from .services.memory.store import get_memory_service
from .services.learning.rl_agent import get_rl_agent
from .core.cache import redis_client
from .core.task_queue import ARQClient
from .core.scheduler import scheduler_manager
from .services.learning.reflexion_system import reflexion_system
import uvicorn
import structlog
import asyncio
from contextlib import asynccontextmanager

# 初始化结构化日志记录器
logger = structlog.get_logger()

# ---- 后台初始化状态 ----
# 前端可通过 GET /api/status 轮询,展示加载进度和错误。
_init_status = {
    "phase": "pending",        # pending | running | done | error
    "progress": "",
    "errors": [],
}

def _set_init_status(phase: str, progress: str = "", error: str = ""):
    _init_status["phase"] = phase
    if progress:
        _init_status["progress"] = progress
    if error:
        _init_status["errors"].append(error)


async def _background_init():
    """后台异步初始化：LLM 配置、画像生成、模型预加载。"""
    _set_init_status("running", "正在加载 LLM 配置...")

    # ---- 1. 加载 LLM provider 配置到 Redis ----
    try:
        await load_llm_providers_to_redis()
        _set_init_status("running", "LLM 配置加载完成")
    except Exception as e:
        logger.error(f"后台初始化: 加载 LLM 配置失败: {e}")
        _set_init_status("running", "LLM 配置加载失败", str(e))

    # ---- 2. 初始化默认画像 ----
    try:
        _set_init_status("running", "正在生成角色画像...")
        await init_portraits()
        _set_init_status("running", "角色画像初始化完成")
    except Exception as e:
        logger.error(f"后台初始化: 画像生成失败: {e}")
        _set_init_status("running", "角色画像生成失败", str(e))

    # ---- 3. 预加载模型 ----
    logger.info("Starting model preloading...")

    try:
        _set_init_status("running", "正在加载情感分析模型...")
        get_emotion_service()
        _set_init_status("running", "情感模型加载完成")
    except Exception as e:
        logger.error(f"Failed to preload Emotion Service: {e}")
        _set_init_status("running", "情感模型加载失败", str(e))

    try:
        _set_init_status("running", "正在加载记忆服务...")
        get_memory_service()
        _set_init_status("running", "记忆服务加载完成")
    except Exception as e:
        from .core.llm_config import is_any_llm_configured
        if is_any_llm_configured():
            logger.error(f"Failed to preload Memory Service: {e}")
            _set_init_status("running", "记忆服务加载失败", str(e))
        else:
            logger.info("尚未配置模型,长期记忆将在配置完成后自动初始化。")

    try:
        _set_init_status("running", "正在加载 RL Agent...")
        get_rl_agent("default")
        _set_init_status("running", "RL Agent 加载完成")
    except Exception as e:
        logger.error(f"Failed to preload RL Agent: {e}")
        _set_init_status("running", "RL Agent 加载失败", str(e))

    logger.info("Model preloading completed.")

    if _init_status["errors"]:
        _set_init_status("done", "初始化完成（部分失败）")
    else:
        _set_init_status("done", "初始化完成")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    FastAPI 生命周期管理函数。

    启动分为两阶段:
      Phase 1 (同步, lifespan 内): 日志、DB、Redis、调度器 —— 必须就绪才能响应请求。
      Phase 2 (异步, 后台任务):  LLM 配置、画像生成、模型预加载 —— 不阻塞窗口打开。
    """
    # ========== Phase 1: 必要初始化（快速） ==========
    configure_logging()

    from .core.config import describe_config_sources
    for _line in describe_config_sources([
        "DEFAULT_LLM_PROVIDER", "DEFAULT_LLM_MODEL_NAME",
        "EMBEDDING_PROVIDER", "EMBEDDING_MODEL_NAME", "EMBEDDING_DIMS",
        "REDIS_HOST", "EMBEDDED_MODE",
    ]):
        logger.info(f"配置 {_line}")

    from .services.system.trace_store import install as install_trace_store
    install_trace_store()

    from .services.system.metrics_store import install as install_metrics_store
    install_metrics_store()

    init_db()
    db = SessionLocal()
    init_personality_data(db)
    db.close()

    await redis_client.connect()

    try:
        from .models import ChatHistoryDB
        with SessionLocal() as db:
            stale = (db.query(ChatHistoryDB)
                       .filter(ChatHistoryDB.status.in_(["pending", "processing"]))
                       .update({"status": "failed"}, synchronize_session=False))
            db.commit()
            if stale:
                logger.warning(f"回收上次运行遗留的 {stale} 条未完成消息(标记为失败,避免自动重放)")
    except Exception as e:
        logger.error(f"Failed to reclaim stale pending messages: {e}")

    from . import tasks as _tasks  # noqa: F401

    scheduler_manager.start()
    await reflexion_system.start()

    try:
        await ARQClient.get_pool()
    except Exception as e:
        logger.error(f"Failed to initialize ARQ pool: {e}")

    # 打印路由
    logger.info("Registered Routes:")
    for route in app.routes:
        if hasattr(route, "path"):
            methods = ", ".join(route.methods) if hasattr(route, "methods") else "ALL"
            logger.info(f"Route: {route.path} [{methods}]")

    # ========== Phase 2: 后台异步初始化（不阻塞） ==========
    asyncio.create_task(_background_init())

    yield
    # 关闭阶段
    scheduler_manager.shutdown()
    await ARQClient.close()
    await redis_client.close()
    shutdown_logging()

# 创建 FastAPI 应用实例
app = FastAPI(title=settings.PROJECT_NAME, lifespan=lifespan)

@app.get("/health")
async def health_check():
    """健康检查端点 —— 服务器就绪即返回,不等待后台初始化。"""
    return {"status": "ok"}

@app.get("/api/status")
async def init_status():
    """后台初始化状态。前端可轮询此端点展示加载进度和错误。"""
    return _init_status

# 配置跨域资源共享 (CORS)
if not settings.EMBEDDED_MODE:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.ALLOWED_ORIGINS,
        allow_origin_regex=r"https?://(localhost|127\.0\.0\.1|0\.0\.0\.0|192\.168\.\d+\.\d+|172\.\d+\.\d+\.\d+)(:\d+)?",
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
else:
    logger.info("Embedded mode: CORS disabled (same-origin desktop app)")

# 注册 API 路由
app.include_router(api_router, prefix=settings.API_V1_STR)
app.include_router(auth_router, prefix=f"{settings.API_V1_STR}/auth", tags=["auth"])
from .api.deps import require_server_mode
app.include_router(
    admin_router,
    prefix=f"{settings.API_V1_STR}/admin",
    tags=["admin"],
    dependencies=[Depends(require_server_mode)],
)
app.include_router(metrics_router, prefix=f"{settings.API_V1_STR}/metrics", tags=["metrics"])

# 挂载静态文件目录
import os
from .core.paths import get_writable_data_dir
static_dir = os.path.join(get_writable_data_dir(), "static")
if not os.path.exists(static_dir):
    os.makedirs(static_dir, exist_ok=True)
app.mount("/static", StaticFiles(directory=static_dir), name="static")

# ---- 前端 SPA 托管 ----
from fastapi.responses import FileResponse

def _resolve_frontend_dist():
    repo_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    candidates = [
        os.environ.get("FRONTEND_DIST"),
        os.path.join(repo_root, "Daisy_front", "dist"),
    ]
    for c in candidates:
        if c and os.path.isdir(c) and os.path.exists(os.path.join(c, "index.html")):
            return c
    return None

_frontend_dist = _resolve_frontend_dist()
if _frontend_dist:
    app.mount("/assets", StaticFiles(directory=os.path.join(_frontend_dist, "assets")), name="spa-assets")
    logger.info(f"Serving frontend SPA from {_frontend_dist}")

    _spa_index = os.path.join(_frontend_dist, "index.html")
    _api_prefixes = (settings.API_V1_STR.strip("/"), "static", "assets", "health", "docs", "openapi.json", "redoc", "api")

    @app.get("/{full_path:path}", include_in_schema=False)
    async def _spa_fallback(full_path: str):
        candidate = os.path.join(_frontend_dist, full_path)
        if full_path and os.path.isfile(candidate):
            return FileResponse(candidate)
        first = full_path.split("/", 1)[0]
        if first in _api_prefixes:
            from fastapi import HTTPException
            raise HTTPException(status_code=404, detail="Not Found")
        return FileResponse(_spa_index)

if __name__ == "__main__":
    import os
    from dotenv import load_dotenv
    load_dotenv()
    port = int(os.getenv("PORT", 10086))
    host = os.getenv("HOST", "0.0.0.0")
    uvicorn.run("app.main:app", host=host, port=port, reload=False)
