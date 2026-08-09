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
from contextlib import asynccontextmanager

# 初始化结构化日志记录器
logger = structlog.get_logger()

@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    FastAPI 生命周期管理函数
    在应用启动时初始化日志和预加载模型，在应用关闭时清理资源。
    """
    # 启动阶段: 配置日志
    configure_logging()

    # 关键配置项及其**来源**。配置有三处(真实环境变量 / server_config.json / .env)
    # 外加字段默认值,历史上出现过三处不一致、排查很久的情况
    # (换嵌入模型时只改了 Python 默认值,而另两处还指向旧模型)。有这几行就是 10 秒的事。
    from .core.config import describe_config_sources
    for _line in describe_config_sources([
        "DEFAULT_LLM_PROVIDER", "DEFAULT_LLM_MODEL_NAME",
        "EMBEDDING_PROVIDER", "EMBEDDING_MODEL_NAME", "EMBEDDING_DIMS",
        "REDIS_HOST", "EMBEDDED_MODE",
    ]):
        logger.info(f"配置 {_line}")

    # 注入 LLM 轨迹落库实现(core 只持接口,见 core/trace_sink.py)
    from .services.system.trace_store import install as install_trace_store
    install_trace_store()

    # 指标事件落库(同样的注入模式,见 core/metrics_sink.py)
    from .services.system.metrics_store import install as install_metrics_store
    install_metrics_store()

    init_db()
    db = SessionLocal()
    init_personality_data(db)
    db.close()
    
    # 连接 Redis
    await redis_client.connect()

    # 回收上次运行遗留的 pending 消息。
    # 进程崩溃/被强杀时,正在处理的消息会永远停在 pending —— 下次启动或用户
    # 下一次发送时,chat_task 会把它们**全部重放**,表现为"一点发送就自动发出
    # 之前的旧消息"(已实测复现)。这些消息的处理任务早已随进程消失,
    # 只能判定为失败;前端会显示重试入口,由用户决定要不要再发。
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

    # 导入即注册后台任务(见 core/job_registry.py)。
    # 必须在调度器/分发之前完成,否则 enqueue 时查不到任务函数。
    #
    # 注意写法:**不能**写 `import app.tasks` —— 那会把名字 `app` 绑到顶层包,
    # 遮蔽本模块里同名的 FastAPI 实例,后面 `app.routes` 就会报
    # "module 'app' has no attribute 'routes'",应用直接启动失败(已实测踩到)。
    from . import tasks as _tasks  # noqa: F401

    # 启动定时任务调度器
    scheduler_manager.start()

    # 启动异步反思系统 Worker
    await reflexion_system.start()
    
    # 预热 ARQ 连接池
    try:
        await ARQClient.get_pool()
    except Exception as e:
        logger.error(f"Failed to initialize ARQ pool: {e}")

    # 加载 LLM 配置到 Redis (优先于其他可能使用 LLM 的服务)
    await load_llm_providers_to_redis()

    # 初始化默认画像 (需要 Redis 连接)
    await init_portraits()
    
    # 预加载模型以避免首次请求的延迟
    logger.info("Starting model preloading...")
    
    try:
        # 1. 预加载情感分析服务 (BERT 模型)
        logger.info("Preloading Emotion Service...")
        get_emotion_service()
        logger.info("Emotion Service preloaded.")
    except Exception as e:
        logger.error(f"Failed to preload Emotion Service: {e}")
        
    try:
        # 2. 预加载记忆服务 (Embeddings 模型 + 向量数据库连接)
        logger.info("Preloading Memory Service...")
        get_memory_service()
        logger.info("Memory Service preloaded.")
    except Exception as e:
        # 首次运行时用户还没填密钥,预热必然失败 —— 这是**预期**流程,不是故障。
        # 用户填入密钥后热重载会清缓存并重建(见 init_data.load_llm_providers_to_redis)。
        # 原先打 ERROR,让正常的首次启动看起来像坏了。
        from .core.llm_config import is_any_llm_configured
        if is_any_llm_configured():
            logger.error(f"Failed to preload Memory Service: {e}")
        else:
            logger.info("尚未配置模型,长期记忆将在配置完成后自动初始化。")

    try:
        # 3. 预加载强化学习代理 (默认代理)
        logger.info("Preloading Default RL Agent...")
        get_rl_agent("default")
        logger.info("Default RL Agent preloaded.")
    except Exception as e:
        logger.error(f"Failed to preload RL Agent: {e}")

    logger.info("Model preloading completed.")
    
    # 打印所有注册的路由以供调试
    logger.info("Registered Routes:")
    for route in app.routes:
        if hasattr(route, "path"):
            methods = ", ".join(route.methods) if hasattr(route, "methods") else "ALL"
            logger.info(f"Route: {route.path} [{methods}]")
    
    yield
    # 关闭阶段: 清理日志资源
    scheduler_manager.shutdown()
    await ARQClient.close()
    await redis_client.close()
    shutdown_logging()

# 创建 FastAPI 应用实例
app = FastAPI(title=settings.PROJECT_NAME, lifespan=lifespan)

@app.get("/health")
async def health_check():
    """
    健康检查端点
    """
    return {"status": "ok"}

# 配置跨域资源共享 (CORS)
# 桌面版(嵌入模式)前端由本后端同源托管,不存在跨域场景;开放 CORS 反而让
# 本机上任意网页都能调用这些接口,是不必要的攻击面,故仅在 server 部署时启用。
if not settings.EMBEDDED_MODE:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.ALLOWED_ORIGINS, # 使用配置中的允许来源
        allow_origin_regex=r"https?://(localhost|127\.0\.0\.1|0\.0\.0\.0|192\.168\.\d+\.\d+|172\.\d+\.\d+\.\d+)(:\d+)?", # 允许本地和局域网开发环境
        allow_credentials=True,
        allow_methods=["*"], # 允许所有方法
        allow_headers=["*"], # 允许所有头信息
    )
else:
    logger.info("Embedded mode: CORS disabled (same-origin desktop app)")

# 注册 API 路由
app.include_router(api_router, prefix=settings.API_V1_STR)
app.include_router(auth_router, prefix=f"{settings.API_V1_STR}/auth", tags=["auth"])
# 白名单管理属 server 部署概念(控制谁能注册);单机桌面版无此语义,整router 关闭
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
# 冻结环境下包内只读,static 必须落在可写数据目录(见 config.get_writable_data_dir)
from .core.paths import get_writable_data_dir
static_dir = os.path.join(get_writable_data_dir(), "static")
if not os.path.exists(static_dir):
    os.makedirs(static_dir, exist_ok=True)
app.mount("/static", StaticFiles(directory=static_dir), name="static")

# ---- 前端 SPA 托管(本地 C 端桌面 App:后端同源托管前端产物)----
# 查找前端构建产物:优先环境变量,其次仓库内 Daisy_front/dist(开发/打包前),
# 打包后由 PyInstaller 数据文件提供。找到才挂载,server 部署无 dist 时不影响。
from fastapi.responses import FileResponse

def _resolve_frontend_dist():
    # __file__ = <root>/Daisy_server/app/main.py → 退 3 层到 <root>(Daisy_Demo)
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
    # 静态资源(/assets 等)由 StaticFiles 处理,其余非 API 路由回退 index.html(SPA 路由)
    app.mount("/assets", StaticFiles(directory=os.path.join(_frontend_dist, "assets")), name="spa-assets")
    logger.info(f"Serving frontend SPA from {_frontend_dist}")

    _spa_index = os.path.join(_frontend_dist, "index.html")
    # API 前缀集合:命中这些的路由不走 SPA 回退,交由后续 404 处理
    _api_prefixes = (settings.API_V1_STR.strip("/"), "static", "assets", "health", "docs", "openapi.json", "redoc")

    @app.get("/{full_path:path}", include_in_schema=False)
    async def _spa_fallback(full_path: str):
        # 命中根目录下的真实文件(favicon 等)直接返回
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
    
    # 尝试加载 .env 文件 (如果尚未加载)
    load_dotenv()

    # 获取端口号，默认为 10086
    # 优先使用环境变量 PORT (可能来自 .env 或 系统环境变量)
    port = int(os.getenv("PORT", 10086))
    host = os.getenv("HOST", "0.0.0.0")
    
    # 启动 uvicorn 服务器
    uvicorn.run("app.main:app", host=host, port=port, reload=False)
