import asyncio
import sys
import os

# Add project root to path
sys.path.append(os.getcwd())

from app.shared.redis import redis_client, async_redis_client
from app.skills.reflexion.scripts.storage import reflexion_storage
from app.core.config import settings

async def verify_redis():
    print("\n--- Verifying Redis ---")
    try:
        # Sync Ping
        pong = redis_client.ping()
        print(f"Sync Redis Ping: {pong}")
        
        # Async Ping
        pong_async = await async_redis_client.ping()
        print(f"Async Redis Ping: {pong_async}")
        
        # Async Set/Get
        test_key = "daisy:verify:test"
        await async_redis_client.set(test_key, "working")
        val = await async_redis_client.get(test_key)
        print(f"Async Redis Get '{test_key}': {val}")
        
        # Cleanup
        await async_redis_client.delete(test_key)
        
    except Exception as e:
        print(f"Redis Verification Failed: {e}")
        import traceback
        traceback.print_exc()

async def verify_qdrant():
    print("\n--- Verifying Qdrant ---")
    try:
        if not reflexion_storage.client:
            print("Qdrant client not initialized in storage")
            return

        # Check collections
        collections = reflexion_storage.client.get_collections().collections
        names = [c.name for c in collections]
        print(f"Qdrant Collections: {names}")
        
        # Verify specific collection
        if reflexion_storage.collection_name in names:
            print(f"Collection '{reflexion_storage.collection_name}' exists.")
            count = reflexion_storage.client.count(collection_name=reflexion_storage.collection_name)
            print(f"Item count: {count}")
        else:
            print(f"Collection '{reflexion_storage.collection_name}' NOT found.")
            
    except Exception as e:
        print(f"Qdrant Verification Failed: {e}")
        import traceback
        traceback.print_exc()

async def main():
    print(f"Settings - Redis: {settings.REDIS_HOST}:{settings.REDIS_PORT}")
    print(f"Settings - Qdrant: {settings.QDRANT_HOST}:{settings.QDRANT_PORT}")
    
    await verify_redis()
    await verify_qdrant()

if __name__ == "__main__":
    asyncio.run(main())
