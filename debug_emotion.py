import sys
import os
import asyncio
import logging
import json

# Setup basic logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Add Daisy_server to sys.path so we can import 'app'
current_dir = os.getcwd()
daisy_server_path = os.path.join(current_dir, "Daisy_server")
sys.path.append(daisy_server_path)

try:
    from app.core.config import settings
    from app.core.redis import redis_client
except ImportError as e:
    print(f"Import Error: {e}")
    sys.exit(1)

async def main():
    logger.info(f"Redis Config: Host={settings.REDIS_HOST}, Port={settings.REDIS_PORT}")
    
    await redis_client.connect()
    
    if not redis_client.enabled:
        logger.error("Failed to connect to Redis!")
        return

    user_id = "1" # Assuming user 1 from logs
    key = f"user:{user_id}:emotional_state"
    
    try:
        data = await redis_client.get(key)
        logger.info(f"Emotional State for user {user_id}: {data}")
        
        if data:
            if isinstance(data, str):
                try:
                    parsed = json.loads(data)
                    logger.info(f"Parsed: {json.dumps(parsed, indent=2)}")
                except:
                    pass
    except Exception as e:
        logger.error(f"Error getting key: {e}")
        
    # Also check recent chat history for emotion labels if stored in Redis (unlikely but possible)
    # or check if there are other keys
    
    await redis_client.close()

if __name__ == "__main__":
    asyncio.run(main())
