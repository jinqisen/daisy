
import asyncio
import redis.asyncio as redis
import structlog
import sys

# 配置日志
logging_config = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "json": {
            "()": structlog.stdlib.ProcessorFormatter,
            "processor": structlog.processors.JSONRenderer(),
        },
    },
    "handlers": {
        "console": {
            "class": "logging.StreamHandler",
            "formatter": "json",
        },
    },
    "loggers": {
        "": {
            "handlers": ["console"],
            "level": "INFO",
        },
    },
}
import logging.config
logging.config.dictConfig(logging_config)

logger = structlog.get_logger()

async def main():
    logger.info("Starting Redis check...")
    
    # 尝试连接 localhost
    try:
        r = redis.Redis(host='localhost', port=6379, db=0, decode_responses=True)
        await r.ping()
        logger.info("Redis connected to localhost:6379")
        
        # 检查 last_active keys
        keys = await r.keys("user:*:last_active")
        print(f"Found {len(keys)} last_active keys: {keys}")
        logger.info(f"Found {len(keys)} last_active keys", keys=keys)
        
        # 检查 online keys
        online_keys = await r.keys("user:*:online")
        print(f"Found {len(online_keys)} online keys: {online_keys}")
        logger.info(f"Found {len(online_keys)} online keys", keys=online_keys)
        
        await r.close()

    except Exception as e:
        print(f"Error connecting to localhost: {e}")
        logger.error("Error during check", error=str(e))

if __name__ == "__main__":
    asyncio.run(main())
