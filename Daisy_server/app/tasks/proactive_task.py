import structlog
from typing import Dict, Any
from ..services.proactive.service import ProactiveService
from ..services.proactive.state import StateService
from ..core.redis import redis_client

logger = structlog.get_logger()

async def trigger_proactive_checks(ctx: Dict[Any, Any]):
    """
    定时任务：触发主动对话检查
    遍历所有用户（不限于在线），为每个用户分发一个具体的检查任务。
    """
    logger.info("Task [trigger_proactive_checks] started.")
    try:
        # 获取所有活跃用户（包括离线但近期活跃的）
        # 这里为了演示简单，我们仍然从 Redis 获取 "last_active" 记录过的所有用户
        # 或者从数据库获取所有用户 ID (如果用户量巨大，需要分批处理)
        
        # 暂时策略：扫描所有有 last_active 记录的用户
        # 更好的策略是从 DB 获取所有启用 AI 伴侣的用户
        # 但考虑到性能，我们先从 StateService 获取“所有已知用户”
        
        all_users = await StateService.get_all_known_users()
        logger.info(f"Task [trigger_proactive_checks] found {len(all_users)} known users: {all_users}")
        
        for user_id in all_users:
            await ctx['redis'].enqueue_job('proactive_check_task', user_id)
            logger.info(f"Enqueued proactive check for user {user_id}")
            
    except Exception as e:
        logger.error(f"Task [trigger_proactive_checks] failed: {e}")

async def proactive_check_task(ctx: Dict[Any, Any], user_id: str):
    """
    具体的检查任务：针对单个用户执行 ProactiveService.check_and_trigger
    """
    logger.info(f"Task [proactive_check_task] started for user {user_id}.")
    try:
        # 确保 Redis 连接可用 (虽然 ProactiveService 使用全局 redis_client，但在 Worker 中最好确保连接状态)
        # 这里假设 ProactiveService 内部处理好了依赖
        
        await ProactiveService.check_and_trigger(user_id)
        
    except Exception as e:
        logger.error(f"Task [proactive_check_task] failed for user {user_id}: {e}")
