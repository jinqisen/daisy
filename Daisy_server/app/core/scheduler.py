from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
import structlog
from typing import Optional

logger = structlog.get_logger()

class SchedulerManager:
    _instance = None
    
    def __init__(self):
        self.scheduler: Optional[BackgroundScheduler] = None
        # 嵌入模式下派发任务必须回到主事件循环:进程内缓存 / Qdrant 等组件
        # 的内部结构绑定在创建它们的循环上,在 APScheduler 线程里新开一个循环去碰
        # 会报 "bound to a different event loop"。start() 由 lifespan 调用,
        # 此时正处于主循环中,故在那里把循环记下来。
        self._main_loop = None

    @classmethod
    def get_instance(cls):
        if cls._instance is None:
            cls._instance = SchedulerManager()
        return cls._instance
        
    def start(self):
        """启动调度器"""
        if self.scheduler and self.scheduler.running:
            logger.info("Scheduler already running.")
            return

        import asyncio
        try:
            self._main_loop = asyncio.get_running_loop()
        except RuntimeError:
            self._main_loop = None  # 非 async 上下文启动(如测试),回落到原路径

        self.scheduler = BackgroundScheduler()
        self.scheduler.start()
        logger.info("Scheduler started.")
        
        # 注册主动对话检查任务 (每 15 分钟触发一次)
        # 注意：这里我们不能直接调用 async 函数，需要用 sync wrapper 或者利用 fire-and-forget
        # 更优雅的方式是：Scheduler -> Enqueue ARQ Job -> Worker Execute
        self.add_job(self._trigger_proactive_checks, "interval", minutes=15, id="proactive_check_cron")

    def shutdown(self):
        """关闭调度器"""
        if self.scheduler and self.scheduler.running:
            self.scheduler.shutdown()
            logger.info("Scheduler shut down.")

    def add_job(self, func, trigger_type, **trigger_args):
        """添加任务"""
        if not self.scheduler:
            logger.warning("Scheduler not initialized. Call start() first.")
            return
            
        try:
            job = self.scheduler.add_job(func, trigger_type, **trigger_args)
            logger.info(f"Job added: {job.id}")
            return job
        except Exception as e:
            logger.error(f"Failed to add job: {e}")

    def _trigger_proactive_checks(self):
        """
        定时触发：将任务推送到 ARQ 队列
        这是同步函数，由 APScheduler 调用
        """
        import asyncio
        from arq import create_pool
        from arq.connections import RedisSettings
        from .config import settings
        
        if settings.EMBEDDED_MODE:
            # 嵌入模式:任务在进程内直接执行,必须跑在主循环上(见 __init__ 注释)。
            # 用 run_coroutine_threadsafe 从调度线程投递,而不是 asyncio.run 新建循环。
            from .redis import _EmbeddedArqShim

            if self._main_loop is None or self._main_loop.is_closed():
                logger.error("Embedded dispatch skipped: main event loop unavailable.")
                return
            try:
                asyncio.run_coroutine_threadsafe(
                    _EmbeddedArqShim.get_instance().enqueue_job('trigger_proactive_checks'),
                    self._main_loop,
                ).result(timeout=10)
                logger.info("Dispatched 'trigger_proactive_checks' in-process (embedded).")
            except Exception as e:
                logger.error(f"Failed to dispatch proactive check job: {e}")
            return

        async def _enqueue():
            pool = None
            try:
                # Create a fresh pool for this thread/loop to avoid "Future attached to a different loop" error
                # when reusing the global pool created in the main loop.
                pool = await create_pool(
                    RedisSettings(
                        host=settings.REDIS_HOST,
                        port=settings.REDIS_PORT,
                        database=settings.REDIS_DB,
                        password=settings.REDIS_PASSWORD
                    )
                )
                await pool.enqueue_job('trigger_proactive_checks')
                logger.info("Enqueued 'trigger_proactive_checks' job from scheduler.")
            except Exception as e:
                logger.error(f"Failed to enqueue proactive check job: {e}")
            finally:
                if pool:
                    # DeprecationWarning: Call to deprecated close. (Use aclose() instead)
                    # arq >= 0.26 recommends aclose()
                    # But checking if hasattr is safer for backward compatibility
                    if hasattr(pool, 'aclose'):
                         await pool.aclose()
                    else:
                         await pool.close()
        
        # 在同步环境中运行异步任务
        # 注意：如果 APScheduler 运行在独立线程，创建新的 loop 可能是安全的
        # 或者使用 asyncio.run (Python 3.7+)
        try:
            asyncio.run(_enqueue())
        except Exception as e:
             logger.error(f"Scheduler execution error: {e}")

    def _health_check(self):
        logger.info("Scheduler health check: tick-tock")

scheduler_manager = SchedulerManager.get_instance()
