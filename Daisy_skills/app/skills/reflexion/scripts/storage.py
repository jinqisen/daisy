from __future__ import annotations

import asyncio
import numpy as np
from typing import Dict, Any, List, Optional
import socket
from sentence_transformers import SentenceTransformer
from qdrant_client import QdrantClient
from qdrant_client.models import Distance, VectorParams, PointStruct, Filter, FieldCondition, MatchValue
from ....core.config import settings


class ReflexionStorage:
    def __init__(
        self,
        qdrant_url: Optional[str] = None,
        qdrant_api_key: Optional[str] = None,
        collection_name: str = "reflexion_exemplars"
    ):
        self.collection_name = collection_name
        self.embedding_model = SentenceTransformer('all-MiniLM-L6-v2')
        
        try:
            if qdrant_url:
                self.client = QdrantClient(url=qdrant_url, api_key=qdrant_api_key)
            elif settings.QDRANT_HOST:
                host = self._resolve_qdrant_host(settings.QDRANT_HOST, settings.QDRANT_PORT)
                self.client = QdrantClient(
                    host=host,
                    port=settings.QDRANT_PORT
                )
            else:
                self.client = QdrantClient(":memory:")

            self._ensure_collection()
        except Exception as e:
            print(f"Failed to initialize Qdrant client: {e}")
            self.client = None

    def _is_tcp_open(self, host: str, port: int, timeout_sec: float = 0.35) -> bool:
        try:
            with socket.create_connection((host, port), timeout=timeout_sec):
                return True
        except OSError:
            return False

    def _resolve_qdrant_host(self, host: str, port: int) -> str:
        if self._is_tcp_open(host, port):
            return host
        if host not in {"localhost", "127.0.0.1"} and self._is_tcp_open("localhost", port):
            return "localhost"
        return host
    
    def _ensure_collection(self):
        if not self.client:
            return
        
        try:
            collections = self.client.get_collections().collections
            collection_names = [c.name for c in collections]
            
            if self.collection_name not in collection_names:
                self.client.create_collection(
                    collection_name=self.collection_name,
                    vectors_config=VectorParams(size=384, distance=Distance.COSINE)
                )
        except Exception as e:
            print(f"Failed to ensure collection: {e}")
    
    def _get_embedding(self, text: str) -> np.ndarray:
        return self.embedding_model.encode(text, show_progress_bar=False)
    
    async def store_exemplar(
        self,
        text: str,
        metadata: Dict[str, Any]
    ) -> bool:
        if not self.client:
            return False
        
        try:
            loop = asyncio.get_running_loop()
            
            def _store():
                embedding = self._get_embedding(text)
                
                point_id = metadata.get("log_id", hash(text))
                
                point = PointStruct(
                    id=point_id,
                    vector=embedding.tolist(),
                    payload={
                        "text": text,
                        **metadata
                    }
                )
                
                self.client.upsert(
                    collection_name=self.collection_name,
                    points=[point]
                )
                
                return True
            
            return await loop.run_in_executor(None, _store)
        except Exception as e:
            print(f"Failed to store exemplar: {e}")
            return False
    
    async def retrieve_exemplars(
        self,
        query_text: str,
        limit: int = 3,
        user_id: Optional[int] = None,
        min_score: float = 0.7
    ) -> List[Dict[str, Any]]:
        if not self.client:
            return []
        
        try:
            loop = asyncio.get_running_loop()
            
            def _retrieve():
                query_embedding = self._get_embedding(query_text)
                
                search_filter = None
                if user_id is not None:
                    search_filter = Filter(
                        must=[
                            FieldCondition(
                                key="user_id",
                                match=MatchValue(value=user_id)
                            )
                        ]
                    )
                
                results = self.client.search(
                    collection_name=self.collection_name,
                    query_vector=query_embedding.tolist(),
                    query_filter=search_filter,
                    limit=limit,
                    score_threshold=min_score
                )
                
                exemplars = []
                for result in results:
                    exemplars.append({
                        "text": result.payload.get("text", ""),
                        "agent_response": result.payload.get("agent_response", ""),
                        "score": result.score,
                        "metadata": {k: v for k, v in result.payload.items() if k not in ["text", "agent_response"]}
                    })
                
                return exemplars
            
            return await loop.run_in_executor(None, _retrieve)
        except Exception as e:
            print(f"Failed to retrieve exemplars: {e}")
            return []
    
    async def delete_exemplar(self, point_id: int) -> bool:
        if not self.client:
            return False
        
        try:
            loop = asyncio.get_running_loop()
            
            def _delete():
                self.client.delete(
                    collection_name=self.collection_name,
                    points_selector=[point_id]
                )
                return True
            
            return await loop.run_in_executor(None, _delete)
        except Exception as e:
            print(f"Failed to delete exemplar: {e}")
            return False
    
    async def get_collection_stats(self) -> Dict[str, Any]:
        if not self.client:
            return {"count": 0}
        
        try:
            loop = asyncio.get_running_loop()
            
            def _get_stats():
                info = self.client.get_collection(self.collection_name)
                return {
                    "count": info.points_count,
                    "status": info.status
                }
            
            return await loop.run_in_executor(None, _get_stats)
        except Exception as e:
            print(f"Failed to get collection stats: {e}")
            return {"count": 0}


reflexion_storage = ReflexionStorage()
