# Daisy_server 到 Daisy_skills 迁移技术方案

## 1. 概述

### 1.1 迁移目标
将 Daisy_server 的所有核心功能迁移到 Daisy_skills 的 Agent Skills 技术架构中，实现：
- 完全基于 Agent Skills 的模块化架构
- 保持 Daisy_server 的所有功能特性
- 提升系统的可扩展性和可维护性

### 1.2 迁移范围

| 功能模块 | Daisy_server 实现 | Daisy_skills 目标 | 优先级 |
|---------|------------------|------------------|--------|
| Reflexion 学习系统 | AsyncReflexionSystem + ReflexionService | reflexion Agent Skill | P0 |
| 主动服务 | ProactiveService | proactive Agent Skill | P0 |
| 角色卡生成 | generate_deep_character_card | character_generator Agent Skill | P0 |
| 三层路由架构 | IntelligentRouter + LangGraph | router Agent Skill + DialogueFlowOrchestrator | P0 |
| 情绪分析 | EmotionService | emotion Agent Skill (已实现) | - |
| 记忆服务 | MemoryService | memory Agent Skill (已实现) | - |
| 人格选择 | PersonaService | persona Agent Skill (已实现) | - |

### 1.3 技术架构映射

```
Daisy_server (单体架构)          Daisy_skills (Agent Skills 架构)
├── app/                          ├── app/
│   ├── workflow/                 │   ├── skills/
│   │   ├── graph.py              │   │   ├── reflexion/          ← 新增
│   │   └── nodes/                │   │   ├── proactive/          ← 新增
│   ├── services/                 │   │   ├── character_generator/ ← 新增
│   │   ├── reflexion/            │   │   ├── router/             ← 新增
│   │   ├── proactive_service.py  │   │   ├── emotion/            (已实现)
│   │   ├── character_card_service.py │   │   ├── memory/             (已实现)
│   │   ├── emotion.py            │   │   └── persona/            (已实现)
│   │   ├── memory.py             │   └── workflow/
│   │   └── persona.py            │       └── graph.py            (重构)
│   ├── agents/                   ├── runtime/
│   │   └── manager.py            │   ├── orchestrator.py        (扩展)
│   └── core/                     │   ├── executor.py            (扩展)
│       ├── router.py             │   └── state_manager.py       (扩展)
│       └── reflexion.py          └── docs/
                                    └── MIGRATION_TECHNICAL_PLAN.md
```

---

## 2. Reflexion 学习系统迁移方案

### 2.1 架构设计

#### 2.1.1 Daisy_skills 目标架构

```
app/skills/reflexion/
├── SKILL.md                      # Skill 定义
├── scripts/
│   ├── __init__.py
│   ├── service.py                # ReflexionService (核心逻辑)
│   ├── storage.py                # ReflexionStorage (Qdrant 适配)
│   ├── patching.py               # ReflexionPatcher (指令补丁)
│   ├── metrics.py                # MetricsService (指标计算)
│   └── worker.py                 # AsyncReflexionWorker (队列处理)
└── references/
    └── schemas.json              # 数据模型定义
```

#### 2.1.2 核心组件映射

| Daisy_server 组件 | Daisy_skills 实现 | 说明 |
|------------------|------------------|------|
| AsyncReflexionSystem | reflexion/scripts/worker.py | 异步队列处理 |
| ReflexionService | reflexion/scripts/service.py | 核心服务逻辑 |
| ReflexionStorage | reflexion/scripts/storage.py | Qdrant 向量存储 |
| ReflexionPatcher | reflexion/scripts/patching.py | 指令补丁生成 |
| metrics_service | reflexion/scripts/metrics.py | Q_I, E_U, D_R 计算 |

### 2.2 SKILL.md 定义

```yaml
---
name: reflexion
version: 1.0.0
description: Reflexion 学习系统，通过对话质量评估和用户反馈实现自我进化
author: Daisy Team
license: MIT
category: learning
tags:
  - reflexion
  - learning
  - self-improvement
  - metrics
dependencies:
  - name: emotion
    version: ">=1.0.0"
  - name: memory
    version: ">=1.0.0"
allowed_tools:
  - reflexion.enqueue_event
  - reflexion.get_metrics
  - reflexion.get_patches
  - reflexion.retrieve_exemplars
---

# Reflexion 学习系统

## 概述
Reflexion 是一个异步学习系统，通过分析对话质量、用户参与度和关系深度，实现 AI 伴侣的自我进化。

## 核心能力

### 1. 对话质量评估 (Q_I)
- 评估回复的情感一致性
- 检测回复的连贯性
- 计算回复的多样性

### 2. 用户参与度评估 (E_U)
- 分析用户回复长度
- 计算响应时间
- 检测情感提升

### 3. 关系深度评估 (D_R)
- 统计会话频率
- 计算留存率
- 追踪记忆更新

### 4. 自我进化机制
- 高质量对话 → 存储为范例 (RAG)
- 低质量对话 → 生成指令补丁

## 操作定义

### enqueue_event
将对话事件加入 Reflexion 处理队列。

**输入参数:**
```json
{
  "user_id": "string",
  "session_id": "string",
  "user_input": "string",
  "agent_response": "string",
  "agent_emotion": {
    "joy": 0.8,
    "sadness": 0.1
  },
  "target_emotion": {
    "joy": 0.7,
    "sadness": 0.2
  },
  "user_emotion": {
    "joy": 0.6,
    "sadness": 0.3
  },
  "history": ["string"]
}
```

**输出结果:**
```json
{
  "success": true,
  "message": "Event enqueued successfully",
  "queue_size": 5
}
```

### get_metrics
获取用户的 Reflexion 指标。

**输入参数:**
```json
{
  "user_id": "string",
  "session_id": "string"
}
```

**输出结果:**
```json
{
  "success": true,
  "metrics": {
    "Q_I": 0.85,
    "E_U": 0.72,
    "D_R": 0.90,
    "S_total": 0.82
  }
}
```

### get_patches
获取用户的活跃指令补丁。

**输入参数:**
```json
{
  "user_id": "string"
}
```

**输出结果:**
```json
{
  "success": true,
  "patches": {
    "global": [
      "避免使用过于正式的语言"
    ],
    "personal": [
      "用户偏好简洁的回复",
      "用户不喜欢过多的表情符号"
    ]
  }
}
```

### retrieve_exemplars
检索相似的高质量对话范例。

**输入参数:**
```json
{
  "query_text": "string",
  "limit": 3
}
```

**输出结果:**
```json
{
  "success": true,
  "exemplars": [
    {
      "text": "用户输入示例",
      "agent_response": "AI 回复示例",
      "score": 0.92,
      "metadata": {}
    }
  ]
}
```

## 使用示例

```python
# 在对话流程中集成 Reflexion
from runtime.orchestrator import SkillOrchestrator

orchestrator = SkillOrchestrator()

# 对话完成后，将事件加入 Reflexion 队列
await orchestrator.execute(
    skill="reflexion",
    operation="enqueue_event",
    input={
        "user_id": user_id,
        "session_id": session_id,
        "user_input": user_input,
        "agent_response": agent_response,
        "agent_emotion": agent_emotion,
        "target_emotion": target_emotion,
        "user_emotion": user_emotion,
        "history": history
    }
)

# 获取指令补丁用于生成
patches_result = await orchestrator.execute(
    skill="reflexion",
    operation="get_patches",
    input={"user_id": user_id}
)
```

## 配置要求

- Redis: 用于存储待处理的 Reflexion 事件 (TTL 24h)
- Qdrant: 用于存储高质量对话范例 (向量检索)
- 数据库: 用于存储 Reflexion 日志和补丁记录

## 性能指标

- 队列处理延迟: < 5s
- 指标计算延迟: < 1s
- 向量检索延迟: < 500ms
```

### 2.3 核心代码实现

#### 2.3.1 reflexion/scripts/service.py

```python
import json
import asyncio
import structlog
from typing import Dict, Any, Optional
from datetime import datetime
from ...core.redis import redis_client
from ...core.database import SessionLocal
from ...models import ReflexionLogDB, UserDB
from ...agents.daisy.character_card import CharacterCard
from ...services.chat_history import history_service
from .metrics import metrics_service
from .storage import reflexion_storage
from .patching import reflexion_patcher

logger = structlog.get_logger()

class ReflexionService:
    def __init__(self):
        self.metrics = metrics_service
        self.storage = reflexion_storage
        self.patcher = reflexion_patcher

    async def process_turn(
        self,
        user_id: int,
        session_id: str,
        user_input: str,
        agent_response: str,
        agent_emotion: Dict[str, float],
        target_emotion: Dict[str, float],
        history: list[str],
        user_emotion: Dict[str, float] = None
    ):
        if user_emotion is None:
            user_emotion = {}

        await self._finalize_previous_turn(
            user_id, session_id, user_input, user_emotion
        )

        q_i_result = self.metrics.calculate_interaction_quality(
            response=agent_response,
            history=history,
            actual_emotion=agent_emotion,
            target_emotion=target_emotion
        )
        
        pending_data = {
            "user_input": user_input,
            "agent_response": agent_response,
            "q_i_result": q_i_result,
            "timestamp": datetime.now().timestamp(),
            "agent_emotion": agent_emotion,
            "user_emotion": user_emotion
        }
        
        try:
            loop = asyncio.get_running_loop()
            log_id = await loop.run_in_executor(
                None,
                lambda: history_service.create_pending_reflexion_log(
                    user_id=user_id,
                    session_id=session_id,
                    user_input=user_input,
                    agent_response=agent_response,
                    metrics=q_i_result
                )
            )
            pending_data["log_id"] = log_id
        except Exception as e:
            logger.error(f"Reflexion: Failed to save pending log: {e}")

        key = f"reflexion:pending:{session_id}"
        await redis_client.set(key, json.dumps(pending_data), ttl=86400)
        
        logger.info(f"Reflexion: Q_I calculated for {session_id}", 
                    q_i=q_i_result["Q_I"])

    async def _finalize_previous_turn(
        self,
        user_id: int,
        session_id: str,
        current_user_input: str,
        current_user_emotion: Dict[str, float] 
    ):
        key = f"reflexion:pending:{session_id}"
        data_str = await redis_client.get(key)
        
        if not data_str:
            return
            
        prev_data = json.loads(data_str)
        prev_user_input = prev_data.get("user_input", "")
        prev_response = prev_data["agent_response"]
        q_i_result = prev_data["q_i_result"]
        log_id = prev_data.get("log_id")
        prev_user_emotion = prev_data.get("user_emotion", {})
        
        response_time = datetime.now().timestamp() - prev_data["timestamp"]
        
        e_u_result = self.metrics.calculate_user_engagement(
            agent_response=prev_response,
            user_next_input=current_user_input,
            response_time_sec=response_time,
            prev_user_emotion=prev_user_emotion,
            next_user_emotion=current_user_emotion
        )

        dr_stats = await self._get_relationship_stats(user_id)
        d_r_result = self.metrics.calculate_relationship_depth(
            session_count_7d=dr_stats.get("session_count_7d", 0),
            retention_rate_7d=dr_stats.get("retention_rate_7d", 0.0),
            memory_updates_count=dr_stats.get("memory_updates_count", 0),
            total_interactions=dr_stats.get("total_interactions", 1)
        )
        
        s_total = 0.5 * q_i_result["Q_I"] + 0.3 * e_u_result["E_U"] + 0.2 * d_r_result["D_R"]
        
        logger.info(f"Reflexion: Finalized Turn. S={s_total:.2f}", 
                    q_i=q_i_result["Q_I"], e_u=e_u_result["E_U"], d_r=d_r_result["D_R"])
        
        all_metrics = {**q_i_result, **e_u_result, **d_r_result}
        
        try:
            loop = asyncio.get_running_loop()
            if log_id:
                await loop.run_in_executor(
                    None,
                    lambda: history_service.update_reflexion_log(
                        log_id=log_id,
                        critique="",
                        improvement_plan="",
                        metrics={**all_metrics, "S_total": s_total},
                        status="processed"
                    )
                )
            else:
                await loop.run_in_executor(
                    None,
                    lambda: history_service.save_reflexion_log(
                        user_id=user_id,
                        session_id=session_id,
                        user_input=prev_user_input,
                        agent_response=prev_response,
                        critique="",
                        improvement_plan="",
                        metrics={**all_metrics, "S_total": s_total},
                        status="processed"
                    )
                )
        except Exception as e:
            logger.error(f"Reflexion: Failed to save/update log: {e}")

        await self._trigger_evolution(
            user_id, 
            prev_user_input,
            prev_response, 
            current_user_input, 
            s_total, 
            all_metrics
        )

    async def _get_relationship_stats(self, user_id: int) -> Dict[str, Any]:
        return {
            "session_count_7d": 20,
            "retention_rate_7d": 0.95,
            "memory_updates_count": 50,
            "total_interactions": 500
        }

    async def _trigger_evolution(
        self, 
        user_id: int, 
        user_input_context: str,
        agent_response: str, 
        user_feedback: str, 
        score: float,
        metrics: Dict
    ):
        if score >= 0.85:
            logger.info("Reflexion: High Score! Triggering RAG Storage.")
            metadata = {
                "user_id": user_id,
                "agent_response": agent_response,
                "score": score,
                "metrics": metrics,
                "timestamp": datetime.now().isoformat()
            }
            await self.storage.store_exemplar(
                text=user_input_context, 
                metadata=metadata
            )
            
        elif score <= 0.40:
            logger.info("Reflexion: Low Score. Triggering Instruction Patching.")
            await self.patcher.generate_patch(
                user_id=user_id,
                user_input_context=user_input_context,
                agent_response=agent_response,
                user_feedback=user_feedback,
                score=score,
                metrics=metrics
            )

reflexion_service = ReflexionService()
```

#### 2.3.2 reflexion/scripts/worker.py

```python
import asyncio
import random
import structlog
from typing import Dict, Any, List
from .service import reflexion_service
from ...services.chat_history import history_service
from ...core.database import SessionLocal
from ...models import UserDB

logger = structlog.get_logger()

class AsyncReflexionWorker:
    def __init__(self):
        self.queue = asyncio.Queue()
        self._running = False
        self.service = reflexion_service
        
    async def start(self):
        if self._running:
            return
        self._running = True
        logger.info("Starting AsyncReflexionWorker...")
        asyncio.create_task(self._worker())

    async def enqueue_event(self, event: Dict[str, Any]):
        qsize = self.queue.qsize()
        await self.queue.put(event)
        logger.info(f"Reflexion event enqueued for user {event.get('user_id')}", 
                    session_id=event.get("session_id"),
                    queue_size=qsize + 1)

    async def _worker(self):
        while self._running:
            try:
                event = await self.queue.get()
                logger.info("Reflexion worker picked up event", 
                            user_id=event.get("user_id"), 
                            queue_size=self.queue.qsize())
                
                start_time = asyncio.get_running_loop().time()
                await self._process_event(event)
                duration = asyncio.get_running_loop().time() - start_time
                
                logger.info("Reflexion event processed", 
                            user_id=event.get("user_id"),
                            duration=f"{duration:.2f}s")
                            
                self.queue.task_done()
            except Exception as e:
                logger.error(f"Reflexion worker error: {e}", exc_info=True)
                await asyncio.sleep(1)

    def _should_process(self, event: Dict[str, Any]) -> bool:
        user_input = event.get("user_input", "")
        
        if len(user_input) > 10:
            return True
            
        user_emotion = event.get("user_emotion", {})
        if user_emotion and any(score > 0.6 for score in user_emotion.values()):
            return True
            
        return random.random() < 0.2

    async def _process_event(self, event: Dict[str, Any]):
        if not self._should_process(event):
            logger.info("Reflexion: Skipped event due to sampling strategy.")
            return

        try:
            user_id = int(event.get("user_id"))
            session_id = event.get("session_id")
            user_input = event.get("user_input")
            agent_response = event.get("agent_response")
            agent_emotion = event.get("agent_emotion", {})
            target_emotion = event.get("target_emotion")
            user_emotion = event.get("user_emotion", {})
            history = event.get("history", [])

            if not history:
                try:
                    loop = asyncio.get_running_loop()
                    def _get_history():
                        msgs = history_service.get_recent_history_limit(user_id, limit=10)
                        return [m.content for m in msgs]
                    
                    history = await loop.run_in_executor(None, _get_history)
                except Exception as e:
                    logger.warning(f"Reflexion: Failed to fetch history: {e}")
                    history = []

            await self.service.process_turn(
                user_id=user_id,
                session_id=session_id,
                user_input=user_input,
                agent_response=agent_response,
                agent_emotion=agent_emotion,
                target_emotion=target_emotion,
                history=history,
                user_emotion=user_emotion
            )

        except Exception as e:
            logger.error(f"Reflexion processing failed: {e}", exc_info=True)

reflexion_worker = AsyncReflexionWorker()
```

#### 2.3.3 reflexion/scripts/metrics.py

```python
import structlog
import numpy as np
from typing import Dict, Any, List
from sentence_transformers import SentenceTransformer

logger = structlog.get_logger()

class MetricsService:
    def __init__(self):
        self.embedding_model = SentenceTransformer('all-MiniLM-L6-v2')
        
    def _get_embedding(self, text: str) -> np.ndarray:
        return self.embedding_model.encode(text, show_progress_bar=False)
    
    def calculate_interaction_quality(
        self,
        response: str,
        history: List[str],
        actual_emotion: Dict[str, float],
        target_emotion: Dict[str, float]
    ) -> Dict[str, Any]:
        emotion_consistency = self._calculate_emotion_consistency(
            actual_emotion, target_emotion
        )
        
        coherence = self._calculate_coherence(response, history)
        
        diversity = self._calculate_diversity(response, history)
        
        q_i = 0.4 * emotion_consistency + 0.4 * coherence + 0.2 * diversity
        
        return {
            "Q_I": q_i,
            "emotion_consistency": emotion_consistency,
            "coherence": coherence,
            "diversity": diversity
        }
    
    def _calculate_emotion_consistency(
        self,
        actual: Dict[str, float],
        target: Dict[str, float]
    ) -> float:
        if not actual or not target:
            return 0.5
        
        all_emotions = set(actual.keys()) | set(target.keys())
        diff_sum = sum(abs(actual.get(e, 0) - target.get(e, 0)) for e in all_emotions)
        max_diff = len(all_emotions) * 2.0
        
        return 1.0 - (diff_sum / max_diff)
    
    def _calculate_coherence(self, response: str, history: List[str]) -> float:
        if not history:
            return 1.0
        
        try:
            response_emb = self._get_embedding(response)
            history_embs = [self._get_embedding(h) for h in history[-3:]]
            
            similarities = [
                np.dot(response_emb, h_emb) / 
                (np.linalg.norm(response_emb) * np.linalg.norm(h_emb))
                for h_emb in history_embs
            ]
            
            return float(np.mean(similarities))
        except Exception as e:
            logger.error(f"Coherence calculation failed: {e}")
            return 0.5
    
    def _calculate_diversity(self, response: str, history: List[str]) -> float:
        if not history:
            return 1.0
        
        try:
            response_emb = self._get_embedding(response)
            history_embs = [self._get_embedding(h) for h in history[-5:]]
            
            similarities = [
                np.dot(response_emb, h_emb) / 
                (np.linalg.norm(response_emb) * np.linalg.norm(h_emb))
                for h_emb in history_embs
            ]
            
            avg_similarity = np.mean(similarities)
            return float(1.0 - avg_similarity)
        except Exception as e:
            logger.error(f"Diversity calculation failed: {e}")
            return 0.5
    
    def calculate_user_engagement(
        self,
        agent_response: str,
        user_next_input: str,
        response_time_sec: float,
        prev_user_emotion: Dict[str, float],
        next_user_emotion: Dict[str, float]
    ) -> Dict[str, Any]:
        response_length = len(user_next_input.strip())
        length_score = min(response_length / 50.0, 1.0)
        
        time_score = 1.0 if response_time_sec < 300 else max(0.5, 1.0 - (response_time_sec - 300) / 600)
        
        sentiment_lift = self._calculate_sentiment_lift(
            prev_user_emotion, next_user_emotion
        )
        
        e_u = 0.4 * length_score + 0.3 * time_score + 0.3 * sentiment_lift
        
        return {
            "E_U": e_u,
            "length_score": length_score,
            "time_score": time_score,
            "sentiment_lift": sentiment_lift
        }
    
    def _calculate_sentiment_lift(
        self,
        prev: Dict[str, float],
        next: Dict[str, float]
    ) -> float:
        if not prev or not next:
            return 0.5
        
        positive_emotions = ["joy", "surprise", "trust"]
        negative_emotions = ["sadness", "anger", "fear", "disgust"]
        
        prev_positive = sum(prev.get(e, 0) for e in positive_emotions)
        next_positive = sum(next.get(e, 0) for e in positive_emotions)
        
        lift = next_positive - prev_positive
        return float(max(0.0, min(1.0, 0.5 + lift)))
    
    def calculate_relationship_depth(
        self,
        session_count_7d: int,
        retention_rate_7d: float,
        memory_updates_count: int,
        total_interactions: int
    ) -> Dict[str, Any]:
        session_score = min(session_count_7d / 30.0, 1.0)
        retention_score = retention_rate_7d
        memory_score = min(memory_updates_count / 100.0, 1.0)
        
        d_r = 0.4 * session_score + 0.4 * retention_score + 0.2 * memory_score
        
        return {
            "D_R": d_r,
            "session_score": session_score,
            "retention_score": retention_score,
            "memory_score": memory_score
        }

metrics_service = MetricsService()
```

#### 2.3.4 reflexion/scripts/storage.py

```python
import structlog
import os
import uuid
import asyncio
from typing import Dict, Any
from qdrant_client import AsyncQdrantClient, QdrantClient
from qdrant_client.http import models
from ...core.config import settings
from .metrics import metrics_service

logger = structlog.get_logger()

class AsyncQdrantAdapter:
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
        return await self.query_points(collection_name, query=query_vector, limit=limit)

    async def get_collections(self):
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(
            None,
            lambda: self.client.get_collections()
        )
        
    async def close(self):
        pass

class ReflexionStorage:
    def __init__(self):
        self.client = None
        self.collection_name = "reflexion_exemplars"
        self.vector_size = 384

    def connect(self):
        host = settings.QDRANT_HOST
        port = settings.QDRANT_PORT
        api_key = os.getenv("QDRANT_API_KEY")
        
        try:
            if host and host != "localhost":
                logger.info(f"ReflexionStorage: Attempting connection to remote Qdrant at {host}:{port}")
                self.client = AsyncQdrantClient(
                    url=f"http://{host}:{port}",
                    api_key=api_key,
                    timeout=5.0
                )
                return
        except Exception as e:
            logger.warning(f"ReflexionStorage: Remote connection setup failed: {e}")

        logger.info("ReflexionStorage: Using local Qdrant storage (./qdrant_data).")
        try:
            local_client = QdrantClient(path="./qdrant_data")
            self.client = AsyncQdrantAdapter(local_client)
        except Exception as e:
             logger.error(f"ReflexionStorage: Failed to initialize local Qdrant: {e}")
             self.client = None

    async def initialize(self):
        if not self.client: 
            self.connect()
        
        if not self.client:
            return

        try:
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
             try:
                 logger.info("ReflexionStorage: Switching to local Qdrant storage.")
                 local_client = QdrantClient(path="./qdrant_data")
                 self.client = AsyncQdrantAdapter(local_client)
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
        if not self.client: await self.initialize()
        if not self.client: return []

        try:
            loop = asyncio.get_running_loop()
            vector_np = await loop.run_in_executor(None, metrics_service._get_embedding, query_text)
            vector = vector_np.tolist()
            
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
```

#### 2.3.5 reflexion/scripts/patching.py

```python
import structlog
import asyncio
import json
import os
from datetime import datetime
from typing import Dict, Any, List, Optional
from ...services.llm import get_llm_service
from ...core.config import settings

logger = structlog.get_logger()

class ReflexionPatcher:
    def __init__(self):
        self.patches_file = os.path.join(settings.DATA_DIR if hasattr(settings, 'DATA_DIR') else "data", "reflexion_patches.jsonl")
        self._ensure_file_exists()

    def _ensure_file_exists(self):
        os.makedirs(os.path.dirname(self.patches_file), exist_ok=True)
        if not os.path.exists(self.patches_file):
            with open(self.patches_file, 'w') as f:
                pass

    async def _append_line(self, line: str) -> None:
        def _write() -> None:
            with open(self.patches_file, 'a', encoding='utf-8') as f:
                f.write(line)

        await asyncio.to_thread(_write)

    async def _read_lines(self) -> List[str]:
        def _read() -> List[str]:
            with open(self.patches_file, 'r', encoding='utf-8') as f:
                return f.read().splitlines()

        return await asyncio.to_thread(_read)

    async def generate_patch(
        self,
        user_id: int,
        user_input_context: str,
        agent_response: str,
        user_feedback: str,
        score: float,
        metrics: Dict[str, Any]
    ) -> Optional[Dict[str, str]]:
        try:
            prompt = self._construct_patching_prompt(
                user_input_context, agent_response, user_feedback, score, metrics
            )
            
            llm = get_llm_service()
            
            system_prompt = "You are an expert AI behavior analyst. Your goal is to analyze a failed interaction and generate a concise 'Instruction Patch' to prevent it from happening again."
            
            metadata = {"route": "STANDARD", "agent_name": "ReflexionPatcher"}
            
            response_content = await llm.generate_response_async(
                system_prompt=system_prompt,
                user_input=prompt,
                context="",
                metadata=metadata
            )
            
            if not response_content or response_content.startswith("Error"):
                logger.error(f"ReflexionPatcher: LLM Error: {response_content}")
                return None

            try:
                content = response_content.strip()
                if "```json" in content:
                    content = content.split("```json")[1].split("```")[0].strip()
                elif "```" in content:
                    content = content.split("```")[1].strip()
                
                result = json.loads(content)
                patch_content = result.get("patch")
                scope = result.get("scope", "PERSONAL").upper()
                reasoning = result.get("reasoning", "")
                
                if scope not in ["GLOBAL", "PERSONAL"]:
                    scope = "PERSONAL"
                    
            except json.JSONDecodeError:
                logger.warning("ReflexionPatcher: Failed to parse JSON, falling back to text")
                patch_content = response_content.strip()
                scope = "PERSONAL"
                reasoning = "Legacy fallback"

            if not patch_content:
                return None

            logger.info(f"ReflexionPatcher: Generated {scope} patch: {patch_content[:50]}...")
            
            await self._store_patch(user_id, patch_content, scope, reasoning, score, metrics)
            
            return {"patch": patch_content, "scope": scope, "reasoning": reasoning}
            
        except Exception as e:
            logger.error(f"ReflexionPatcher: Failed to generate patch: {e}")
            return None

    def _construct_patching_prompt(
        self,
        context: str,
        response: str,
        feedback: str,
        score: float,
        metrics: Dict
    ) -> str:
        return f"""
Analyze the following interaction which received a low satisfaction score (S={score:.2f}).

CONTEXT (User's previous input):
"{context}"

AGENT RESPONSE:
"{response}"

USER FEEDBACK (Next turn input showing dissatisfaction/disengagement):
"{feedback}"

METRICS:
{json.dumps(metrics, indent=2)}

TASK:
1. Identify the core issue (e.g., tone mismatch, ignoring instructions, hallucination).
2. Determine the SCOPE of the issue:
   - "GLOBAL": A universal error that should be fixed for ALL users (e.g., code formatting, logical fallacy, toxicity).
   - "PERSONAL": A mismatch with this specific user's preferences (e.g., brevity, emoji usage, language style).
3. Formulate a concise "Instruction Patch" (a rule or guideline) that prevents this.

OUTPUT FORMAT (JSON ONLY):
{{
    "reasoning": "Explain why this is a failure and why you chose the scope.",
    "scope": "GLOBAL" or "PERSONAL",
    "patch": "The instruction string."
}}
"""

    async def _store_patch(self, user_id: int, patch: str, scope: str, reasoning: str, score: float, metrics: Dict):
        entry = {
            "user_id": user_id,
            "timestamp": datetime.now().isoformat(),
            "score": score,
            "metrics": metrics,
            "patch": patch,
            "scope": scope,
            "reasoning": reasoning,
            "status": "active"
        }
        
        await self._append_line(json.dumps(entry, ensure_ascii=False) + "\n")

    async def get_active_patches(self, user_id: int) -> Dict[str, List[str]]:
        patches = {"global": [], "personal": []}
        try:
            if not os.path.exists(self.patches_file):
                return patches

            for line in await self._read_lines():
                try:
                    entry = json.loads(line)
                    if entry.get("status") != "active":
                        continue

                    entry_scope = entry.get("scope", "PERSONAL").upper()
                    entry_user_id = entry.get("user_id")

                    if entry_scope == "GLOBAL":
                        patches["global"].append(entry.get("patch"))
                    elif entry_user_id == user_id:
                        patches["personal"].append(entry.get("patch"))

                except json.JSONDecodeError:
                    continue
        except Exception as e:
            logger.error(f"ReflexionPatcher: Failed to load patches: {e}")
            
        patches["global"] = patches["global"][-5:]
        patches["personal"] = patches["personal"][-5:]
        return patches

reflexion_patcher = ReflexionPatcher()
```

### 2.4 集成到 SkillExecutor

在 `runtime/executor.py` 中添加 Reflexion 操作注册：

```python
from app.skills.reflexion.scripts.worker import reflexion_worker
from app.skills.reflexion.scripts.service import reflexion_service
from app.skills.reflexion.scripts.patching import reflexion_patcher
from app.skills.reflexion.scripts.storage import reflexion_storage

class SkillExecutor:
    def __init__(self):
        self._operations = {
            # ... existing operations ...
            
            "reflexion": {
                "enqueue_event": self._reflexion_enqueue_event,
                "get_metrics": self._reflexion_get_metrics,
                "get_patches": self._reflexion_get_patches,
                "retrieve_exemplars": self._reflexion_retrieve_exemplars,
            }
        }
    
    async def _reflexion_enqueue_event(self, input_data: Dict[str, Any], context: Optional[SkillContext] = None) -> SkillResult:
        try:
            await reflexion_worker.enqueue_event(input_data)
            return SkillResult(
                success=True,
                data={"message": "Event enqueued successfully", "queue_size": reflexion_worker.queue.qsize()}
            )
        except Exception as e:
            return SkillResult(success=False, error=str(e))
    
    async def _reflexion_get_metrics(self, input_data: Dict[str, Any], context: Optional[SkillContext] = None) -> SkillResult:
        try:
            user_id = input_data.get("user_id")
            session_id = input_data.get("session_id")
            
            key = f"reflexion:metrics:{session_id}"
            from ...core.redis import redis_client
            metrics_str = await redis_client.get(key)
            
            if metrics_str:
                metrics = json.loads(metrics_str)
            else:
                metrics = {"Q_I": 0.0, "E_U": 0.0, "D_R": 0.0, "S_total": 0.0}
            
            return SkillResult(success=True, data={"metrics": metrics})
        except Exception as e:
            return SkillResult(success=False, error=str(e))
    
    async def _reflexion_get_patches(self, input_data: Dict[str, Any], context: Optional[SkillContext] = None) -> SkillResult:
        try:
            user_id = input_data.get("user_id")
            patches = await reflexion_patcher.get_active_patches(user_id)
            return SkillResult(success=True, data={"patches": patches})
        except Exception as e:
            return SkillResult(success=False, error=str(e))
    
    async def _reflexion_retrieve_exemplars(self, input_data: Dict[str, Any], context: Optional[SkillContext] = None) -> SkillResult:
        try:
            query_text = input_data.get("query_text", "")
            limit = input_data.get("limit", 3)
            
            exemplars = await reflexion_storage.retrieve_exemplars(query_text, limit)
            
            formatted_exemplars = [
                {
                    "text": point.payload.get("text", ""),
                    "agent_response": point.payload.get("agent_response", ""),
                    "score": point.score,
                    "metadata": point.payload
                }
                for point in exemplars
            ]
            
            return SkillResult(success=True, data={"exemplars": formatted_exemplars})
        except Exception as e:
            return SkillResult(success=False, error=str(e))
```

### 2.5 启动 Reflexion Worker

在 `app/main.py` 中启动 Reflexion Worker：

```python
from app.skills.reflexion.scripts.worker import reflexion_worker

@app.on_event("startup")
async def startup_event():
    await reflexion_worker.start()
    logger.info("Reflexion worker started")
```

---

## 3. 主动服务迁移方案

### 3.1 架构设计

```
app/skills/proactive/
├── SKILL.md                      # Skill 定义
├── scripts/
│   ├── __init__.py
│   ├── service.py                # ProactiveService (核心逻辑)
│   ├── gatekeeper.py             # DualTrackGatekeeper (双轨门控)
│   └── scheduler.py              # ProactiveScheduler (定时调度)
└── references/
    └── schemas.json              # 数据模型定义
```

### 3.2 SKILL.md 定义

```yaml
---
name: proactive
version: 1.0.0
description: 主动对话服务，通过双轨门控和 Agent 决策实现智能主动发起对话
author: Daisy Team
license: MIT
category: interaction
tags:
  - proactive
  - engagement
  - dual-track
dependencies:
  - name: emotion
    version: ">=1.0.0"
  - name: memory
    version: ">=1.0.0"
  - name: persona
    version: ">=1.0.0"
allowed_tools:
  - proactive.check_and_trigger
  - proactive.get_daily_count
  - proactive.get_last_proactive_time
  - proactive.set_proactive_config
---

# 主动对话服务

## 概述
主动对话服务通过双轨门控机制（情感急救 + 常规陪伴）和 Agent 决策，智能判断何时主动发起对话。

## 核心能力

### 1. 双轨门控机制
- Track A: 情感急救 - 检测负面情绪并立即响应
- Track B: 常规陪伴 - 基于作息规律和活跃概率发起对话

### 2. 冷却与频次控制
- 每日最大主动次数: 5 次
- 默认冷却时间: 2 小时
- 情感急救模式冷却: 1 小时

### 3. Agent 决策
- 基于对话历史和情感状态
- 判断是否应该发起主动对话
- 生成合适的主动消息内容

## 操作定义

### check_and_trigger
检查并触发主动对话。

**输入参数:**
```json
{
  "user_id": "string"
}
```

**输出结果:**
```json
{
  "success": true,
  "triggered": true,
  "track": "emotional_aid",
  "message": "主动消息内容"
}
```

### get_daily_count
获取用户今日主动对话次数。

**输入参数:**
```json
{
  "user_id": "string"
}
```

**输出结果:**
```json
{
  "success": true,
  "count": 3,
  "max_daily": 5
}
```

### get_last_proactive_time
获取用户最后一次主动对话时间。

**输入参数:**
```json
{
  "user_id": "string"
}
```

**输出结果:**
```json
{
  "success": true,
  "last_proactive_time": 1704067200.0,
  "elapsed_hours": 1.5
}
```

### set_proactive_config
设置用户主动对话配置。

**输入参数:**
```json
{
  "user_id": "string",
  "config": {
    "enabled": true,
    "max_daily": 5,
    "cooldown_hours": 2,
    "override_cooldown_hours": 1
  }
}
```

**输出结果:**
```json
{
  "success": true,
  "message": "Configuration updated"
}
```

## 使用示例

```python
from runtime.orchestrator import SkillOrchestrator

orchestrator = SkillOrchestrator()

# 检查并触发主动对话
result = await orchestrator.execute(
    skill="proactive",
    operation="check_and_trigger",
    input={"user_id": user_id}
)

if result.data.get("triggered"):
    logger.info(f"Proactive message sent: {result.data.get('message')}")
```

## 配置要求

- Redis: 用于存储主动对话计数和时间戳
- StateService: 用于获取用户在线状态和情感状态
- AgentManager: 用于 Agent 决策和消息生成

## 性能指标

- 门控判定延迟: < 100ms
- Agent 决策延迟: < 2s
- 消息发送延迟: < 500ms
```

### 3.3 核心代码实现

#### 3.3.1 proactive/scripts/service.py

```python
import datetime
import json
import structlog
from typing import Optional, Dict, Any, List
from sqlalchemy.orm import Session
from ...core.redis import redis_client
from ...services.state_service import StateService
from ...services.chat_history import history_service
from ...models import UserDB
from ...core.database import SessionLocal
from ...agents.manager import AgentManager

logger = structlog.get_logger()

class ProactiveService:
    MAX_DAILY_COUNT = 5
    DEFAULT_COOLDOWN_HOURS = 2
    OVERRIDE_COOLDOWN_HOURS = 1
    
    @staticmethod
    async def check_and_trigger(user_id: str):
        is_online = await StateService.is_user_online(user_id)
        
        now = datetime.datetime.now()
        current_hour = now.hour
        last_active = await StateService.get_last_active_time(user_id)
        
        logger.info(f"Checking proactive trigger for user {user_id} | Online: {is_online} | Last Active: {last_active}")

        if not is_online:
            logger.debug(f"User {user_id} is offline. Message will be stored if generated.")
        
        if last_active and (now.timestamp() - last_active < 120):
            logger.info(f"User {user_id} is busy (active < 2m). Skipping.")
            return {"triggered": False, "reason": "user_busy"}

        emotional_state = await StateService.get_emotional_state(user_id)
        
        track = "routine"
        override = False
        
        if emotional_state:
            label = emotional_state.get("label", "").lower()
            score = emotional_state.get("score", 0)
            ts = emotional_state.get("timestamp", 0)
            
            if (now.timestamp() - ts) < 43200:
                if label in ["sadness", "lonely", "grief", "anxiety"] and score > 0.6:
                    track = "emotional_aid"
                    override = True
                    logger.info(f"Emotional Override activated for {user_id}: {label} ({score})")

        if not override:
            prob = await StateService.get_activity_probability(user_id, current_hour)
            if prob < 0.05:
                logger.info(f"Low activity probability ({prob:.2f}) for hour {current_hour}. Skipping.")
                return {"triggered": False, "reason": "low_activity"}

        daily_count = await ProactiveService._get_daily_count(user_id)
        max_daily = ProactiveService.MAX_DAILY_COUNT + (1 if override else 0)
        
        if daily_count >= max_daily:
            logger.info(f"Daily limit reached ({daily_count}/{max_daily}). Skipping.")
            return {"triggered": False, "reason": "daily_limit"}

        last_proactive = await ProactiveService._get_last_proactive_time(user_id)
        cooldown = ProactiveService.OVERRIDE_COOLDOWN_HOURS if override else ProactiveService.DEFAULT_COOLDOWN_HOURS
        
        if last_proactive:
            elapsed_hours = (now.timestamp() - last_proactive) / 3600
            if elapsed_hours < cooldown:
                logger.info(f"In cooldown ({elapsed_hours:.2f}h < {cooldown}h). Skipping.")
                return {"triggered": False, "reason": "cooldown"}

        db = SessionLocal()
        try:
            history = history_service.get_recent_history_limit(user_id=user_id, limit=5, db=db)
            history_str = "\n".join([f"{h.role}: {h.content}" for h in history])
            
            agent_manager = AgentManager.get_instance()
            agent = agent_manager.get_agent("daisy")
            
            if not agent:
                logger.error("No active agent found for user.")
                return {"triggered": False, "reason": "no_agent"}

            context = {
                "user_id": user_id,
                "history": history_str,
                "emotion": emotional_state if override else None,
                "time": now
            }
            
            decision = await agent.check_proactive_trigger(context)
            
            if decision and decision.get("should_act"):
                content = decision.get("content")
                logger.info(f"Proactive message generated for {user_id} by {agent.name}: {content}")
                
                await ProactiveService._send_message(user_id, content, db, is_online)
                
                await ProactiveService._incr_daily_count(user_id)
                await ProactiveService._set_last_proactive_time(user_id)
                
                return {
                    "triggered": True,
                    "track": track,
                    "message": content
                }
                
            else:
                logger.info(f"Agent {agent.name} decided not to act. Reason: {decision.get('reason')}")
                return {"triggered": False, "reason": decision.get('reason', 'agent_declined')}
                
        finally:
            db.close()

    @staticmethod
    async def _send_message(user_id: str, content: str, db: Session, is_online: bool = True):
        from ...models import ChatHistoryDB
        
        ai_msg = ChatHistoryDB(
            session_id=str(datetime.datetime.now().timestamp()),
            user_id=user_id,
            role="ai",
            content=content,
            timestamp=datetime.datetime.now()
        )
        db.add(ai_msg)
        db.commit()
        
        if is_online:
            channel = f"chat:stream:{user_id}"
            msg_payload = {
                "type": "proactive_message", 
                "content": content,
                "timestamp": ai_msg.timestamp.isoformat()
            }
            await redis_client.redis.publish(channel, json.dumps(msg_payload))
            logger.info(f"Pushed proactive message to online user {user_id}")
        else:
            logger.info(f"Stored proactive message for offline user {user_id}")

    @staticmethod
    async def _get_daily_count(user_id: str) -> int:
        key = f"user:{user_id}:proactive:daily_count"
        count = await redis_client.redis.get(key)
        return int(count) if count else 0

    @staticmethod
    async def _incr_daily_count(user_id: str):
        key = f"user:{user_id}:proactive:daily_count"
        now = datetime.datetime.now()
        tomorrow = now.replace(hour=0, minute=0, second=0, microsecond=0) + datetime.timedelta(days=1)
        ttl = int((tomorrow - now).total_seconds())
        
        await redis_client.redis.incr(key)
        await redis_client.redis.expire(key, ttl)

    @staticmethod
    async def _get_last_proactive_time(user_id: str) -> Optional[float]:
        key = f"user:{user_id}:proactive:last_ts"
        ts = await redis_client.redis.get(key)
        return float(ts) if ts else None

    @staticmethod
    async def _set_last_proactive_time(user_id: str):
        key = f"user:{user_id}:proactive:last_ts"
        await redis_client.redis.set(key, str(datetime.datetime.now().timestamp()), ex=604800)

proactive_service = ProactiveService()
```

#### 3.3.2 proactive/scripts/scheduler.py

```python
import asyncio
import structlog
from typing import List
from .service import proactive_service

logger = structlog.get_logger()

class ProactiveScheduler:
    def __init__(self):
        self._running = False
        self._check_interval = 300  # 5 minutes
        
    async def start(self):
        if self._running:
            return
        self._running = True
        logger.info("Starting ProactiveScheduler...")
        asyncio.create_task(self._worker())
    
    async def stop(self):
        self._running = False
        logger.info("ProactiveScheduler stopped")
    
    async def _worker(self):
        while self._running:
            try:
                await self._check_all_users()
                await asyncio.sleep(self._check_interval)
            except Exception as e:
                logger.error(f"ProactiveScheduler error: {e}", exc_info=True)
                await asyncio.sleep(60)
    
    async def _check_all_users(self):
        from ...core.database import SessionLocal
        from ...models import UserDB
        
        with SessionLocal() as db:
            users = db.query(UserDB).all()
            
            for user in users:
                try:
                    result = await proactive_service.check_and_trigger(user.username)
                    if result.get("triggered"):
                        logger.info(f"Proactive message sent to {user.username}")
                except Exception as e:
                    logger.error(f"Failed to check proactive for {user.username}: {e}")

proactive_scheduler = ProactiveScheduler()
```

### 3.4 集成到 SkillExecutor

```python
from app.skills.proactive.scripts.service import proactive_service
from app.skills.proactive.scripts.scheduler import proactive_scheduler

class SkillExecutor:
    def __init__(self):
        self._operations = {
            # ... existing operations ...
            
            "proactive": {
                "check_and_trigger": self._proactive_check_and_trigger,
                "get_daily_count": self._proactive_get_daily_count,
                "get_last_proactive_time": self._proactive_get_last_proactive_time,
                "set_proactive_config": self._proactive_set_config,
            }
        }
    
    async def _proactive_check_and_trigger(self, input_data: Dict[str, Any], context: Optional[SkillContext] = None) -> SkillResult:
        try:
            user_id = input_data.get("user_id")
            result = await proactive_service.check_and_trigger(user_id)
            return SkillResult(success=True, data=result)
        except Exception as e:
            return SkillResult(success=False, error=str(e))
    
    async def _proactive_get_daily_count(self, input_data: Dict[str, Any], context: Optional[SkillContext] = None) -> SkillResult:
        try:
            user_id = input_data.get("user_id")
            count = await proactive_service._get_daily_count(user_id)
            return SkillResult(success=True, data={"count": count, "max_daily": proactive_service.MAX_DAILY_COUNT})
        except Exception as e:
            return SkillResult(success=False, error=str(e))
    
    async def _proactive_get_last_proactive_time(self, input_data: Dict[str, Any], context: Optional[SkillContext] = None) -> SkillResult:
        try:
            user_id = input_data.get("user_id")
            last_time = await proactive_service._get_last_proactive_time(user_id)
            
            elapsed_hours = 0
            if last_time:
                elapsed_hours = (datetime.datetime.now().timestamp() - last_time) / 3600
            
            return SkillResult(success=True, data={
                "last_proactive_time": last_time,
                "elapsed_hours": elapsed_hours
            })
        except Exception as e:
            return SkillResult(success=False, error=str(e))
    
    async def _proactive_set_config(self, input_data: Dict[str, Any], context: Optional[SkillContext] = None) -> SkillResult:
        try:
            user_id = input_data.get("user_id")
            config = input_data.get("config", {})
            
            key = f"user:{user_id}:proactive:config"
            from ...core.redis import redis_client
            await redis_client.set(key, json.dumps(config), ex=86400 * 30)
            
            return SkillResult(success=True, data={"message": "Configuration updated"})
        except Exception as e:
            return SkillResult(success=False, error=str(e))
```

### 3.5 启动 Proactive Scheduler

```python
from app.skills.proactive.scripts.scheduler import proactive_scheduler

@app.on_event("startup")
async def startup_event():
    await proactive_scheduler.start()
    logger.info("Proactive scheduler started")
```

---

## 4. 角色卡生成迁移方案

### 4.1 架构设计

```
app/skills/character_generator/
├── SKILL.md                      # Skill 定义
├── scripts/
│   ├── __init__.py
│   ├── generator.py              # CharacterCardGenerator (核心逻辑)
│   ├── models.py                 # CharacterCard 数据模型
│   └── prompts.py                # Prompt 模板
└── references/
    └── schemas.json              # 数据模型定义
```

### 4.2 SKILL.md 定义

```yaml
---
name: character_generator
version: 1.0.0
description: 深度角色卡生成器，基于用户设定生成完整的角色档案
author: Daisy Team
license: MIT
category: generation
tags:
  - character
  - generation
  - persona
dependencies:
  - name: persona
    version: ">=1.0.0"
allowed_tools:
  - character_generator.generate_deep_card
  - character_generator.generate_portrait
  - character_generator.get_character_card
  - character_generator.build_prompt_addendum
---

# 深度角色卡生成器

## 概述
深度角色卡生成器基于用户提供的简单设定（姓名、职业、年龄等），利用 LLM 的逻辑推演，生成具有文学深度、逻辑自洽的完整角色档案。

## 核心能力

### 1. 深度角色生成
- 反套路设计，避免刻板印象
- 逻辑推演，每个性格特征都有来源
- 复杂性设计，表层面具与深层底色的反差

### 2. 角色画像生成
- 基于通用设置生成简洁的角色画像
- 整合事实与背景故事
- 约 100-150 字的精炼描述

### 3. Prompt 补充生成
- 根据路由生成不同的 Prompt 补充
- FAST: 概念 + 风格
- STANDARD: 人格 + 关系
- DEEP: 约束 + 内心独白模式

## 操作定义

### generate_deep_card
生成深度角色卡。

**输入参数:**
```json
{
  "name": "静雯",
  "gender": "女",
  "age": 24,
  "occupation": "心理学家",
  "backstory": "来自小镇的温柔女孩",
  "world_setting": "Modern Realism",
  "avatar_path": "/path/to/avatar.jpg"
}
```

**输出结果:**
```json
{
  "success": true,
  "character_card": {
    "identity": {
      "name": "静雯",
      "gender": "女",
      "age": 24,
      "occupation": "心理学家",
      "mbti": "INFJ"
    },
    "personality": {
      "description": "...",
      "core_traits": ["温柔", "敏感", "坚韧"]
    },
    "language_style": {
      "tone": "温柔",
      "quirks": ["喜欢用比喻"],
      "common_phrases": {
        "greeting": ["嗨"],
        "agreement": ["嗯嗯"],
        "thinking": ["让我想想..."]
      }
    },
    "context": {
      "backstory": "...",
      "world_setting": "Modern Realism"
    },
    "constraints": [
      {
        "type": "emotional",
        "description": "避免过度共情导致情绪耗竭",
        "coping_strategy": ["设定边界", "自我关怀"]
      }
    ],
    "behavior": {
      "push_pull_pattern": {
        "description": "...",
        "pull_behaviors": ["倾听", "支持"],
        "push_behaviors": ["挑战", "引导"]
      }
    },
    "relationship_dynamics": [
      {
        "level": 1,
        "name": "acquaintance",
        "description": "...",
        "prompt_addon": "..."
      }
    ],
    "dialogue_examples": [
      {
        "scene": "...",
        "user": "...",
        "agent": "..."
      }
    ],
    "inner_monologue_patterns": [
      {
        "emotion": "joy",
        "pattern": "..."
      }
    ]
  }
}
```

### generate_portrait
生成角色画像。

**输入参数:**
```json
{
  "user_id": "string",
  "name": "静雯",
  "gender": "女",
  "age": 24,
  "occupation": "心理学家",
  "backstory": "来自小镇的温柔女孩",
  "world_setting": "Modern Realism"
}
```

**输出结果:**
```json
{
  "success": true,
  "portrait": "静雯是一位24岁的心理学家，生活在2025年的武汉。她将小镇出身的温柔与顶尖医学院的学术严谨相结合..."
}
```

### get_character_card
获取用户的角色卡。

**输入参数:**
```json
{
  "user_id": "string"
}
```

**输出结果:**
```json
{
  "success": true,
  "character_card": { ... }
}
```

### build_prompt_addendum
根据路由生成 Prompt 补充。

**输入参数:**
```json
{
  "character_card": { ... },
  "route": "DEEP",
  "user_input": "用户输入",
  "relationship_stage": "trust"
}
```

**输出结果:**
```json
{
  "success": true,
  "prompt_addendum": "# [Constraints]\n- 避免过度共情导致情绪耗竭\n\n# [Inner Monologue Patterns]\n- [joy]: ..."
}
```

## 使用示例

```python
from runtime.orchestrator import SkillOrchestrator

orchestrator = SkillOrchestrator()

# 生成深度角色卡
result = await orchestrator.execute(
    skill="character_generator",
    operation="generate_deep_card",
    input={
        "name": "静雯",
        "gender": "女",
        "age": 24,
        "occupation": "心理学家",
        "backstory": "来自小镇的温柔女孩",
        "world_setting": "Modern Realism"
    }
)

character_card = result.data.get("character_card")
```

## 配置要求

- LLM Service: 用于生成角色卡内容
- Database: 用于存储角色卡

## 性能指标

- 深度角色卡生成延迟: < 10s
- 角色画像生成延迟: < 3s
- Prompt 补充生成延迟: < 100ms
```

### 4.3 核心代码实现

#### 4.3.1 character_generator/scripts/models.py

```python
from pydantic import BaseModel, Field
from typing import List, Dict, Any, Optional

class Identity(BaseModel):
    name: str
    gender: str
    age: int
    occupation: str
    mbti: Optional[str] = None
    avatar_path: Optional[str] = None

class Personality(BaseModel):
    description: str
    core_traits: List[str]

class LanguageStyle(BaseModel):
    tone: str
    quirks: List[str]
    common_phrases: Dict[str, List[str]]

class Context(BaseModel):
    backstory: str
    world_setting: str

class Constraint(BaseModel):
    type: str
    description: str
    coping_strategy: List[str]

class PushPullPattern(BaseModel):
    description: str
    pull_behaviors: List[str]
    push_behaviors: List[str]

class Behavior(BaseModel):
    push_pull_pattern: PushPullPattern

class RelationshipDynamic(BaseModel):
    level: int
    name: str
    description: str
    prompt_addon: str

class DialogueExample(BaseModel):
    scene: str
    user: str
    agent: str

class InnerMonologuePattern(BaseModel):
    emotion: str
    pattern: str

class CharacterCard(BaseModel):
    identity: Identity
    personality: Personality
    language_style: LanguageStyle
    context: Context
    constraints: List[Constraint]
    behavior: Behavior
    relationship_dynamics: List[RelationshipDynamic]
    dialogue_examples: List[DialogueExample]
    inner_monologue_patterns: List[InnerMonologuePattern]
```

#### 4.3.2 character_generator/scripts/generator.py

```python
import json
import structlog
from typing import Optional, Dict, Any
from .models import CharacterCard
from ...services.llm import get_llm_service

logger = structlog.get_logger()

class CharacterCardGenerator:
    def __init__(self):
        self.llm = get_llm_service()
    
    async def generate_deep_card(
        self,
        name: str,
        gender: str,
        age: int,
        occupation: str,
        backstory: str = "",
        world_setting: str = "Modern Realism",
        avatar_path: Optional[str] = None
    ) -> Optional[CharacterCard]:
        system_prompt = """
# Role: Deep Character Profiler & Novelist
你是一位擅长心理侧写的小说家。你的任务是将用户提供的简单人物设定（姓名、职业、年龄）扩写成一份具有文学深度、逻辑自洽的完整角色档案。

# Core Philosophy
1. **Anti-Cliché (反套路)**: 不要默认高官就是霸道，医生就是洁癖。寻找"意料之外，情理之中"的设定。
2. **Logical Deduction (逻辑推演)**: 每一个性格特征必须有来源 (Backstory)。如果他冷漠，是因为受过伤，还是天生迟钝？
3. **Complexity (复杂性)**: 人是矛盾的。为角色设计"表层面具"和"深层底色"的反差。

# Output Format
你必须输出一个符合特定 JSON Schema 的 JSON 对象。不要包含任何 Markdown 格式（如 ```json）。

# Schema Definition
{
  "identity": {
    "name": "...", "gender": "...", "age": 25, 
    "occupation": "...", "mbti": "..."
  },
  "personality": {
    "description": "...", "core_traits": ["..."]
  },
  "language_style": {
    "tone": "...", "quirks": ["..."], 
    "common_phrases": {
        "greeting": ["..."], 
        "agreement": ["..."], 
        "thinking": ["..."]
    }
  },
  "context": {
    "backstory": "...", "world_setting": "..."
  },
  "constraints": [
    {"type": "...", "description": "...", "coping_strategy": ["..."]}
  ],
  "behavior": {
    "push_pull_pattern": {
        "description": "...", 
        "pull_behaviors": ["..."], 
        "push_behaviors": ["..."]
    }
  },
  "relationship_dynamics": [
    {"level": 1, "name": "...", "description": "...", "prompt_addon": "..."}
  ],
  "dialogue_examples": [
    {"scene": "...", "user": "...", "agent": "..."}
  ],
  "inner_monologue_patterns": [
    {"emotion": "...", "pattern": "..."}
  ]
}
"""
        
        user_input = f"""
请基于以下种子信息生成角色卡：
- Name: {name}
- Gender: {gender}
- Age: {age}
- Occupation: {occupation}
- Backstory Hint: {backstory or "N/A"}
- World Setting: {world_setting}
"""
        
        try:
            response_text = await self.llm.generate_response_async(
                system_prompt=system_prompt,
                user_input=user_input,
                context="",
                metadata={"agent_name": "DeepCharacterGenerator"}
            )
            
            json_str = response_text.strip()
            if json_str.startswith("```json"):
                json_str = json_str[7:]
            if json_str.endswith("```"):
                json_str = json_str[:-3]
            
            data = json.loads(json_str)
            
            if avatar_path and "identity" in data:
                data["identity"]["avatar_path"] = avatar_path

            card = CharacterCard(**data)
            logger.info(f"Generated deep character card for {name}")
            return card
            
        except Exception as e:
            logger.error(f"Failed to generate deep character card: {e}")
            return None
    
    async def generate_portrait(
        self,
        user_id: str,
        name: str,
        gender: str,
        age: int,
        occupation: str,
        backstory: str = "",
        world_setting: str = "Modern Realism"
    ) -> str:
        raw_info = f"""
Name: {name}
Gender: {gender}
Age: {age}
Occupation: {occupation}
World Setting: {world_setting}
Backstory: {backstory}
"""
        
        portrait_prompt = f"""
基于以下原始信息合成一个"角色画像"。

**原始信息**:
{raw_info}

**目标**:
创建一个简洁、整合的段落（约100-150字），捕捉角色的本质。
将事实（年龄、工作、学校）与背景故事中提到的个性特征和矛盾融合在一起。

**示例输出风格**:
"静雯是一位24岁的心理学家，生活在2025年的武汉。她将小镇出身的温柔与顶尖医学院的学术严谨相结合..."

用中文输出角色画像。
"""
        
        try:
            portrait = await self.llm.generate_response_async(
                system_prompt="你是一位专家级的人物画像分析师。",
                user_input=portrait_prompt,
                context="",
                metadata={"agent_name": "ProfileAgent", "user_id": user_id}
            )
            return portrait
        except Exception as e:
            logger.error(f"Failed to generate portrait: {e}")
            return f"{name} is a {age}-year-old {gender} {occupation}."
    
    def build_prompt_addendum(
        self,
        card: CharacterCard,
        route: str,
        user_input: str,
        relationship_stage: str
    ) -> str:
        route = (route or "").upper()
        name = card.identity.name
        
        if route == "FAST":
            core_concept = card.personality.description
            style = card.language_style.tone
            
            addendum = f"""# [Character Essence]
Name: {name}
Concept: {core_concept}
Style: {style}"""
            return addendum.strip()

        if route == "STANDARD":
            description = card.personality.description
            pattern = ""
            if card.behavior.push_pull_pattern:
                pattern = card.behavior.push_pull_pattern.description
                
            addendum = f"""# [Character Persona]
Description: {description}

# [Relationship Dynamics]
Pattern: {pattern}"""
            return addendum.strip()

        if route == "DEEP":
            constraints_list = [f"- {c.description}" for c in card.constraints]
            monologues = [f"- [{m.emotion}]: {m.pattern}" for m in card.inner_monologue_patterns]
            
            addendum = f"""# [Constraints]
{chr(10).join(constraints_list) if constraints_list else "(none)"}

# [Inner Monologue Patterns]
{chr(10).join(monologues) if monologues else "(none)"}"""
            return addendum.strip()

        return ""

character_generator = CharacterCardGenerator()
```

### 4.4 集成到 SkillExecutor

```python
from app.skills.character_generator.scripts.generator import character_generator
from app.skills.character_generator.scripts.models import CharacterCard

class SkillExecutor:
    def __init__(self):
        self._operations = {
            # ... existing operations ...
            "character_generator": {
                "generate_deep_card": self._character_generate_deep_card,
                "build_prompt_addendum": self._character_build_prompt_addendum,
                "validate_card": self._character_validate_card,
            }
        }
    
    async def _character_generate_deep_card(
        self,
        name: str,
        gender: str,
        age: int,
        occupation: str,
        backstory: str = "",
        world_setting: str = "Modern Realism",
        avatar_path: Optional[str] = None
    ) -> Dict[str, Any]:
        card = await character_generator.generate_deep_card(
            name=name,
            gender=gender,
            age=age,
            occupation=occupation,
            backstory=backstory,
            world_setting=world_setting,
            avatar_path=avatar_path
        )
        if card:
            return card.model_dump()
        return {"error": "Failed to generate character card"}
    
    async def _character_build_prompt_addendum(
        self,
        card_data: Dict[str, Any],
        route: str,
        user_input: str,
        relationship_stage: str
    ) -> str:
        card = CharacterCard.model_validate(card_data)
        return character_generator.build_prompt_addendum(
            card=card,
            route=route,
            user_input=user_input,
            relationship_stage=relationship_stage
        )
    
    async def _character_validate_card(
        self,
        card_data: Dict[str, Any]
    ) -> Dict[str, Any]:
        try:
            card = CharacterCard.model_validate(card_data)
            return {"valid": True, "card": card.model_dump()}
        except Exception as e:
            return {"valid": False, "error": str(e)}
```

---

## 5. 三层路由架构迁移方案

### 5.1 架构设计

#### 5.1.1 Daisy_skills 目标架构

```
app/skills/router/
├── SKILL.md                      # Skill 定义
├── scripts/
│   ├── __init__.py
│   ├── intelligent_router.py     # IntelligentRouter (核心路由逻辑)
│   ├── route_judge.py            # RouteJudge (LLM 判决器)
│   └── patterns.py               # 路由模式定义
└── references/
    └── schemas.json              # 数据模型定义
```

#### 5.1.2 核心组件映射

| Daisy_server 组件 | Daisy_skills 实现 | 说明 |
|------------------|------------------|------|
| IntelligentRouter | router/scripts/intelligent_router.py | 核心路由逻辑 |
| RouteJudge | router/scripts/route_judge.py | LLM 路由判决 |
| fast_patterns | router/scripts/patterns.py | FAST 路径正则模式 |
| DialogueFlowOrchestrator | runtime/orchestrator.py (扩展) | 对话流程编排 |

### 5.2 SKILL.md 定义

```yaml
---
name: router
version: 1.0.0
description: 三层路由架构，根据用户输入复杂度选择 FAST/STANDARD/DEEP 处理路径
author: Daisy Team
license: MIT
category: routing
tags:
  - router
  - routing
  - dialogue-flow
  - intelligent-routing
dependencies:
  - name: emotion
    version: ">=1.0.0"
  - name: persona
    version: ">=1.0.0"
allowed_tools:
  - router.route_input
  - router.get_route_info
  - router.update_route_patterns
---

## Operations

### route_input

路由用户输入到适当的处理路径。

**Parameters:**
- `user_input` (string, required): 用户输入文本
- `user_id` (string, required): 用户ID
- `session_id` (string, required): 会话ID
- `context` (object, optional): 上下文信息

**Returns:**
- `route` (string): 路由结果 ("FAST", "STANDARD", "DEEP")
- `confidence` (number): 路由置信度 (0-1)
- `reasoning` (string): 路由决策理由

**Example:**
```json
{
  "route": "STANDARD",
  "confidence": 0.85,
  "reasoning": "用户输入包含情感表达，需要标准处理"
}
```

### get_route_info

获取路由配置信息。

**Parameters:**
- None

**Returns:**
- `routes` (array): 可用路由列表
- `fast_patterns` (array): FAST 路径正则模式
- `thresholds` (object): 路由阈值配置

### update_route_patterns

更新 FAST 路径的正则模式。

**Parameters:**
- `patterns` (array, required): 新的正则模式列表

**Returns:**
- `success` (boolean): 更新是否成功
- `count` (number): 更新的模式数量
```

### 5.3 核心实现

#### 5.3.1 IntelligentRouter

```python
from typing import Dict, List, Optional, Tuple
import re
from pydantic import BaseModel, Field

class RouteResult(BaseModel):
    route: str = Field(..., description="路由结果: FAST/STANDARD/DEEP")
    confidence: float = Field(..., ge=0.0, le=1.0, description="置信度")
    reasoning: str = Field(..., description="决策理由")

class RouteConfig(BaseModel):
    fast_patterns: List[str] = Field(default_factory=list)
    standard_threshold: float = Field(default=0.6, ge=0.0, le=1.0)
    deep_threshold: float = Field(default=0.8, ge=0.0, le=1.0)

class IntelligentRouter:
    def __init__(self, config: Optional[RouteConfig] = None):
        self.config = config or RouteConfig()
        self._compile_patterns()
    
    def _compile_patterns(self):
        self._compiled_patterns = [
            re.compile(pattern) for pattern in self.config.fast_patterns
        ]
    
    def route_input(
        self,
        user_input: str,
        user_id: str,
        session_id: str,
        context: Optional[Dict] = None
    ) -> RouteResult:
        context = context or {}
        
        # 1. FAST 路径检查（正则匹配）
        fast_result = self._check_fast_path(user_input)
        if fast_result:
            return fast_result
        
        # 2. LLM 判决（STANDARD vs DEEP）
        from app.skills.router.scripts.route_judge import route_judge
        llm_result = route_judge.judge_route(
            user_input=user_input,
            context=context
        )
        
        return llm_result
    
    def _check_fast_path(self, user_input: str) -> Optional[RouteResult]:
        for pattern in self._compiled_patterns:
            if pattern.match(user_input.strip()):
                return RouteResult(
                    route="FAST",
                    confidence=1.0,
                    reasoning=f"匹配 FAST 模式: {pattern.pattern}"
                )
        return None
    
    def update_patterns(self, patterns: List[str]) -> Dict[str, any]:
        self.config.fast_patterns = patterns
        self._compile_patterns()
        return {
            "success": True,
            "count": len(patterns)
        }
    
    def get_route_info(self) -> Dict[str, any]:
        return {
            "routes": ["FAST", "STANDARD", "DEEP"],
            "fast_patterns": self.config.fast_patterns,
            "thresholds": {
                "standard": self.config.standard_threshold,
                "deep": self.config.deep_threshold
            }
        }

intelligent_router = IntelligentRouter()
```

#### 5.3.2 RouteJudge

```python
from typing import Dict, Optional
from pydantic import BaseModel, Field

class RouteJudgment(BaseModel):
    route: str = Field(..., description="路由结果: STANDARD/DEEP")
    confidence: float = Field(..., ge=0.0, le=1.0, description="置信度")
    reasoning: str = Field(..., description="决策理由")

class RouteJudge:
    def __init__(self, llm_client=None):
        self.llm_client = llm_client
    
    def judge_route(
        self,
        user_input: str,
        context: Optional[Dict] = None
    ) -> RouteJudgment:
        context = context or {}
        
        prompt = self._build_judgment_prompt(user_input, context)
        
        # 调用 LLM 进行路由判决
        response = self._call_llm(prompt)
        
        return self._parse_response(response)
    
    def _build_judgment_prompt(self, user_input: str, context: Dict) -> str:
        return f"""请判断以下用户输入应该走 STANDARD 还是 DEEP 路由：

用户输入: {user_input}

上下文信息:
- 会话轮数: {context.get('turn_count', 0)}
- 最近情绪: {context.get('recent_emotion', 'unknown')}
- 关系阶段: {context.get('relationship_stage', 'initial')}

路由标准:
- STANDARD: 常规对话、简单情感表达、日常闲聊
- DEEP: 复杂情感问题、深度角色扮演、需要工具调用

请以 JSON 格式返回:
{{
  "route": "STANDARD" or "DEEP",
  "confidence": 0.0-1.0,
  "reasoning": "决策理由"
}}"""
    
    def _call_llm(self, prompt: str) -> str:
        # 实际实现中调用 LLM API
        # 这里返回模拟结果
        return '{"route": "STANDARD", "confidence": 0.75, "reasoning": "常规对话，适合标准处理"}'
    
    def _parse_response(self, response: str) -> RouteJudgment:
        import json
        try:
            data = json.loads(response)
            return RouteJudgment.model_validate(data)
        except Exception as e:
            return RouteJudgment(
                route="STANDARD",
                confidence=0.5,
                reasoning=f"解析失败，默认 STANDARD: {str(e)}"
            )

route_judge = RouteJudge()
```

#### 5.3.3 patterns.py

```python
FAST_PATTERNS = [
    r'^(好|嗯|是|对|行|可以)[啊呀的吗]*[！!。.]*$',
    r'^(早|早安|早上好|晚安)[！!。.]*$',
    r'^(你好|嗨|哈喽|在吗|在不在|吃了吗|睡了吗)[！!。.]*$',
    r'^(谢谢|谢了|OK|Ok|ok|好的|收到|行吧|可以呀)[！!。.]*$',
    r'^(👍|👌|🙏)[！!。.]*$',
    r'^(哈哈|呵呵|嘿嘿|嘻嘻)[！!。.]*$',
    r'^(嗯嗯|好的好的|没问题)[！!。.]*$',
    r'^(再见|拜拜|回见)[！!。.]*$',
    r'^(没事|没关系|不客气)[！!。.]*$',
    r'^(嗯哼|嗯呢|嗯嗯嗯)[！!。.]*$'
]
```

### 5.4 集成到 SkillExecutor

```python
from app.skills.router.scripts.intelligent_router import intelligent_router
from app.skills.router.scripts.patterns import FAST_PATTERNS

class SkillExecutor:
    def __init__(self):
        self._operations = {
            # ... existing operations ...
            "router": {
                "route_input": self._router_route_input,
                "get_route_info": self._router_get_route_info,
                "update_route_patterns": self._router_update_patterns,
            }
        }
    
    async def _router_route_input(
        self,
        user_input: str,
        user_id: str,
        session_id: str,
        context: Optional[Dict] = None
    ) -> Dict[str, Any]:
        result = intelligent_router.route_input(
            user_input=user_input,
            user_id=user_id,
            session_id=session_id,
            context=context
        )
        return result.model_dump()
    
    async def _router_get_route_info(self) -> Dict[str, Any]:
        return intelligent_router.get_route_info()
    
    async def _router_update_patterns(
        self,
        patterns: List[str]
    ) -> Dict[str, Any]:
        return intelligent_router.update_patterns(patterns)
```

---

## 6. 迁移实施计划

### 6.1 阶段划分

| 阶段 | 任务 | 预计工期 | 依赖 |
|------|------|---------|------|
| Phase 1 | Reflexion 学习系统迁移 | 2 周 | 无 |
| Phase 2 | 主动服务迁移 | 1 周 | Phase 1 |
| Phase 3 | 角色卡生成迁移 | 1 周 | Phase 1 |
| Phase 4 | 三层路由架构迁移 | 2 周 | Phase 2, Phase 3 |
| Phase 5 | 集成测试与优化 | 1 周 | Phase 4 |

### 6.2 Phase 1: Reflexion 学习系统迁移

**任务清单:**
- [ ] 创建 `app/skills/reflexion/` 目录结构
- [ ] 编写 `SKILL.md` 定义文件
- [ ] 实现 `scripts/service.py` (ReflexionService)
- [ ] 实现 `scripts/storage.py` (ReflexionStorage)
- [ ] 实现 `scripts/patching.py` (ReflexionPatcher)
- [ ] 实现 `scripts/metrics.py` (MetricsService)
- [ ] 实现 `scripts/worker.py` (AsyncReflexionWorker)
- [ ] 集成到 SkillExecutor
- [ ] 单元测试覆盖

**验收标准:**
- 所有 Q_I, E_U, D_R 指标计算正确
- RAG 存储和检索功能正常
- 指令补丁生成和应用正常
- 异步队列处理无阻塞

### 6.3 Phase 2: 主动服务迁移

**任务清单:**
- [ ] 创建 `app/skills/proactive/` 目录结构
- [ ] 编写 `SKILL.md` 定义文件
- [ ] 实现 `scripts/service.py` (ProactiveService)
- [ ] 实现双轨道门控逻辑
- [ ] 实现冷却和频次控制
- [ ] 集成到 SkillExecutor
- [ ] 单元测试覆盖

**验收标准:**
- Track A 和 Track B 门控逻辑正确
- 冷却时间和频次限制生效
- 主动消息触发时机准确

### 6.4 Phase 3: 角色卡生成迁移

**任务清单:**
- [ ] 创建 `app/skills/character_generator/` 目录结构
- [ ] 编写 `SKILL.md` 定义文件
- [ ] 实现 `scripts/models.py` (Pydantic 模型)
- [ ] 实现 `scripts/generator.py` (CharacterCardGenerator)
- [ ] 实现 `build_prompt_addendum` 方法
- [ ] 集成到 SkillExecutor
- [ ] 单元测试覆盖

**验收标准:**
- 角色卡生成符合反陈词滥调要求
- 复杂度评分准确
- Pydantic 模型验证通过
- Prompt 补充内容正确

### 6.5 Phase 4: 三层路由架构迁移

**任务清单:**
- [ ] 创建 `app/skills/router/` 目录结构
- [ ] 编写 `SKILL.md` 定义文件
- [ ] 实现 `scripts/intelligent_router.py` (IntelligentRouter)
- [ ] 实现 `scripts/route_judge.py` (RouteJudge)
- [ ] 实现 `scripts/patterns.py` (路由模式)
- [ ] 扩展 DialogueFlowOrchestrator
- [ ] 集成到 SkillExecutor
- [ ] 单元测试覆盖

**验收标准:**
- FAST 路径正则匹配准确
- LLM 路由判决合理
- 三层路由切换流畅
- 性能指标达标

### 6.6 Phase 5: 集成测试与优化

**任务清单:**
- [ ] 端到端集成测试
- [ ] 性能基准测试
- [ ] 压力测试
- [ ] 代码审查和优化
- [ ] 文档更新

**验收标准:**
- 所有功能正常工作
- 性能不低于 Daisy_server
- 无严重 Bug
- 文档完整

---

## 7. 风险评估与缓解措施

### 7.1 技术风险

| 风险 | 影响 | 概率 | 缓解措施 |
|------|------|------|---------|
| Qdrant 向量存储迁移失败 | 高 | 中 | 提前验证 Qdrant 适配器，准备降级方案 |
| LLM 路由判决性能不足 | 中 | 中 | 实现缓存机制，考虑本地模型替代 |
| 异步队列处理阻塞 | 高 | 低 | 实现队列监控和自动扩容 |
| Pydantic 模型验证失败 | 中 | 低 | 充分测试边界情况，提供降级处理 |

### 7.2 业务风险

| 风险 | 影响 | 概率 | 缓解措施 |
|------|------|------|---------|
| 主动服务触发时机不准确 | 高 | 中 | A/B 测试验证，收集用户反馈 |
| 角色卡生成质量下降 | 中 | 中 | 保留 Daisy_server 生成逻辑作为对比 |
| 路由决策错误率高 | 高 | 低 | 实现人工审核机制，持续优化 |

### 7.3 项目风险

| 风险 | 影响 | 概率 | 缓解措施 |
|------|------|------|---------|
| 工期延误 | 中 | 中 | 分阶段交付，优先核心功能 |
| 人员变动 | 高 | 低 | 充分文档化，知识共享 |
| 需求变更 | 中 | 中 | 敏捷开发，快速响应 |

---

## 8. 总结

本迁移技术方案详细规划了将 Daisy_server 的所有核心功能迁移到 Daisy_skills 的 Agent Skills 技术架构中的具体步骤。通过模块化的 Agent Skills 架构，系统将获得更好的可扩展性和可维护性，同时保持所有原有功能特性。

关键成功因素:
1. 严格按照 SKILL.md 规范实现每个 Skill
2. 充分测试异步处理和并发场景
3. 保持与 Daisy_server 功能对等
4. 持续监控性能指标，及时优化

预期收益:
- 系统架构更加清晰，模块职责明确
- 新功能开发效率提升
- 系统可维护性显著改善
- 为未来扩展奠定坚实基础