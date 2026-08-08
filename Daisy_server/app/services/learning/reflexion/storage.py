import structlog
import os
import uuid
import asyncio
from typing import Dict, Any
from qdrant_client import AsyncQdrantClient, QdrantClient
from qdrant_client.http import models
from app.core.config import settings
from app.services.learning.reflexion.metrics import metrics_service

logger = structlog.get_logger()

class AsyncQdrantAdapter:
    """Adapts a synchronous QdrantClient to an async interface using run_in_executor."""
    def __init__(self, client: QdrantClient):
        self.client = client
        
    async def collection_exists(self, collection_name: str) -> bool:
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(None, self.client.collection_exists, collection_name)
        
    async def create_collection(self, collection_name: str, vectors_config):
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(
            None, 
            lambda: self.client.create_collection(collection_name=collection_name, vectors_config=vectors_config)
        )
        
    async def upsert(self, collection_name: str, points):
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(
            None,
            lambda: self.client.upsert(collection_name=collection_name, points=points)
        )

    async def query_points(self, collection_name: str, query, limit):
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(
            None,
            lambda: self.client.query_points(collection_name=collection_name, query=query, limit=limit)
        )
        
    async def search(self, collection_name: str, query_vector, limit):
        # Compatibility wrapper for search -> query_points
        return await self.query_points(collection_name, query=query_vector, limit=limit)

    async def get_collections(self):
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(
            None,
            lambda: self.client.get_collections()
        )
        
    async def close(self):
        # Sync client doesn't need await close usually, but for API compat
        pass

class ReflexionStorage:
    def __init__(self):
        self.client = None
        self.collection_name = "reflexion_exemplars"
        self.vector_size = 384 # all-MiniLM-L6-v2

    def connect(self):
        host = settings.QDRANT_HOST
        port = settings.QDRANT_PORT
        api_key = os.getenv("QDRANT_API_KEY")
        
        # Try Remote Connection First
        try:
            if host and host != "localhost":
                logger.info(f"ReflexionStorage: Attempting connection to remote Qdrant at {host}:{port}")
                self.client = AsyncQdrantClient(
                    url=f"http://{host}:{port}",
                    api_key=api_key,
                    timeout=5.0 # Short timeout to fail fast
                )
                # We can't easily verify connection with AsyncClient until we await something.
                # But we will handle errors in initialize().
                return
        except Exception as e:
            logger.warning(f"ReflexionStorage: Remote connection setup failed: {e}")

        # Fallback to Local/Memory
        logger.info("ReflexionStorage: Using local Qdrant storage (./qdrant_data).")
        try:
            local_client = QdrantClient(path="./qdrant_data")
            self.client = AsyncQdrantAdapter(local_client)
        except Exception as e:
             logger.error(f"ReflexionStorage: Failed to initialize local Qdrant: {e}")
             self.client = None

    async def initialize(self):
        """Ensure collection exists."""
        if not self.client: 
            self.connect()
        
        if not self.client:
            return

        try:
            # Test connection and create collection
            exists = await self.client.collection_exists(self.collection_name)
            if not exists:
                logger.info(f"Creating Qdrant collection: {self.collection_name}")
                await self.client.create_collection(
                    collection_name=self.collection_name,
                    vectors_config=models.VectorParams(
                        size=self.vector_size,
                        distance=models.Distance.COSINE
                    )
                )
        except Exception as e:
             logger.error(f"ReflexionStorage: Remote Initialization failed: {e}. Switching to Local Fallback.")
             # If remote failed (timeout etc), try switching to local immediately
             try:
                 logger.info("ReflexionStorage: Switching to local Qdrant storage.")
                 local_client = QdrantClient(path="./qdrant_data")
                 self.client = AsyncQdrantAdapter(local_client)
                 # Retry init
                 exists = await self.client.collection_exists(self.collection_name)
                 if not exists:
                     await self.client.create_collection(
                        collection_name=self.collection_name,
                        vectors_config=models.VectorParams(
                            size=self.vector_size,
                            distance=models.Distance.COSINE
                        )
                    )
             except Exception as local_e:
                 logger.error(f"ReflexionStorage: Local Fallback also failed: {local_e}")
                 self.client = None

    async def store_exemplar(self, text: str, metadata: Dict[str, Any]):
        if not self.client: await self.initialize()
        if not self.client: return
        
        # metrics_service._get_embedding is sync (numpy).
        try:
            loop = asyncio.get_running_loop()
            vector_np = await loop.run_in_executor(None, metrics_service._get_embedding, text)
            vector = vector_np.tolist()
        except Exception as e:
            logger.error(f"ReflexionStorage: Embedding generation failed: {e}")
            return
        
        try:
            point_id = str(uuid.uuid4())
            
            await self.client.upsert(
                collection_name=self.collection_name,
                points=[
                    models.PointStruct(
                        id=point_id,
                        vector=vector,
                        payload=metadata
                    )
                ]
            )
            logger.info("ReflexionStorage: Exemplar stored.")
        except Exception as e:
             logger.error(f"ReflexionStorage: Failed to store exemplar: {e}")

    async def retrieve_exemplars(self, query_text: str, limit: int = 3):
        """Retrieve similar exemplars using RAG."""
        if not self.client: await self.initialize()
        if not self.client: return []

        try:
            loop = asyncio.get_running_loop()
            vector_np = await loop.run_in_executor(None, metrics_service._get_embedding, query_text)
            vector = vector_np.tolist()
            
            # Use query_points (unified API)
            results = await self.client.query_points(
                collection_name=self.collection_name,
                query=vector,
                limit=limit
            )
            return results.points
        except Exception as e:
            logger.error(f"ReflexionStorage: Retrieval failed: {e}")
            return []

reflexion_storage = ReflexionStorage()
