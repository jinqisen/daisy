from arq.connections import RedisSettings
from ..core.config import settings
from ..services.system.schema_bootstrap import init_db
from ..core.database import SessionLocal
from ..services.system.init_data import load_llm_providers_to_redis
from ..services.system.init_data import init_personality_data
from ..core.cache import redis_client
from ..core.logger import configure_logging
import structlog
from .chat_task import chat_task
from .proactive_task import proactive_check_task, trigger_proactive_checks
from ..services.learning.reflexion_system import reflexion_system

logger = structlog.get_logger()

async def startup(ctx):
    """
    Worker 启动时执行
    """
    # 初始化 Worker 日志
    configure_logging("daisy_worker.log")
    
    logger.info("ARQ Worker Starting...")
    
    # 连接 Redis (用于应用层逻辑，如 LLMConfigManager 和缓存)
    await redis_client.connect()
    
    # 启动异步反思系统 Worker (在 Worker 进程中处理反思队列)
    await reflexion_system.start()
    
    # 加载 LLM 配置 (关键修复：确保 Worker 进程有 LLM 配置)
    await load_llm_providers_to_redis()

    init_db()
    with SessionLocal() as db:
        init_personality_data(db)
    
    # 初始化数据库连接
    # 虽然 SessionLocal 是同步的/轻量的，但如果需要预热连接可以在这里做
    # ctx['db'] = SessionLocal() # 可以在 ctx 中共享
    logger.info("ARQ Worker Started.")

async def shutdown(ctx):
    """
    Worker 关闭时执行
    """
    logger.info("ARQ Worker Shutting down...")
    
    # 关闭 Redis 连接
    await redis_client.close()
    
    # if 'db' in ctx:
    #     ctx['db'].close()
    logger.info("ARQ Worker Stopped.")

class WorkerSettings:
    """
    ARQ Worker 配置
    """
    # 任务函数列表
    functions = [chat_task, proactive_check_task, trigger_proactive_checks]
    
    # Redis 配置
    redis_settings = RedisSettings(
        host=settings.REDIS_HOST,
        port=settings.REDIS_PORT,
        database=settings.REDIS_DB,
        password=settings.REDIS_PASSWORD
    )
    
    # 生命周期钩子
    on_startup = startup
    on_shutdown = shutdown
    
    # 任务最大重试次数
    max_retries = 3
    
    # 作业超时 (秒) - 根据 AI 生成时间设定，建议稍长
    job_timeout = 300 # 5分钟
