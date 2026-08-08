import structlog
import asyncio
import json
import os
import time
from datetime import datetime
from typing import Dict, Any, List, Optional, Tuple
from app.core.llm import get_llm_service
from app.core.config import settings

logger = structlog.get_logger()


class ReflexionPatcher:
    """
    Reflexion 补丁生成与存储(深改点 #3:持久层 JSONL → Redis)。

    存储布局:
      - reflexion:patches:global               全局补丁 Redis 列表(JSON 条目)
      - reflexion:patches:personal:{user_id}   个人补丁 Redis 列表
      - reflexion:patches:migrated             一次性迁移标记

    读取路径 get_active_patches 每轮生成都会调用,由 O(整个 JSONL 文件) 优化为
    LRANGE 列表尾部 + 30s 进程内缓存。JSONL 仍然双写作为备份/审计,并在 Redis
    不可用时作为只读回退,保证行为可用性不回退。
    """

    GLOBAL_KEY = "reflexion:patches:global"
    PERSONAL_KEY_PREFIX = "reflexion:patches:personal:"
    MIGRATION_FLAG_KEY = "reflexion:patches:migrated"
    MAX_LIST_LEN = 500      # 每个列表保留的最大条目数(LTRIM 上界)
    READ_TAIL = 100         # 读取时取尾部条数(再过滤 status 后取最后 5 条)
    ACTIVE_LIMIT = 5        # 注入上下文的每类补丁上限(与旧实现一致)
    CACHE_TTL_SEC = 30

    def __init__(self):
        self.patches_file = os.path.join(settings.DATA_DIR if hasattr(settings, 'DATA_DIR') else "data", "reflexion_patches.jsonl")
        self._ensure_file_exists()
        # user_id -> (cached_at_ts, patches_dict)
        self._cache: Dict[Any, Tuple[float, Dict[str, List[str]]]] = {}
        self._migration_checked = False

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

    # ------------------------------------------------------------------
    # Redis 存储层
    # ------------------------------------------------------------------

    async def _get_redis(self):
        """获取可用的 Redis 连接;不可用返回 None(调用方回退 JSONL)。"""
        try:
            from app.core.redis import redis_client
            if not redis_client.enabled:
                await redis_client.connect()
            if redis_client.enabled and redis_client.redis:
                return redis_client.redis
        except Exception:
            pass
        return None

    def _personal_key(self, user_id) -> str:
        return f"{self.PERSONAL_KEY_PREFIX}{user_id}"

    def _entry_key(self, entry: dict) -> str:
        scope = (entry.get("scope") or "PERSONAL").upper()
        if scope == "GLOBAL":
            return self.GLOBAL_KEY
        return self._personal_key(entry.get("user_id"))

    async def _ensure_migrated(self, redis) -> None:
        """把存量 JSONL 条目一次性搬进 Redis。迁移与标记在同一事务管道内,失败可重试。"""
        if self._migration_checked:
            return
        try:
            if await redis.get(self.MIGRATION_FLAG_KEY):
                self._migration_checked = True
                return
            lines = await self._read_lines()
            pipe = redis.pipeline()  # redis-py pipeline 默认 MULTI/EXEC,整体原子
            count = 0
            for line in lines:
                try:
                    entry = json.loads(line)
                except json.JSONDecodeError:
                    continue
                pipe.rpush(self._entry_key(entry), json.dumps(entry, ensure_ascii=False))
                count += 1
            pipe.set(self.MIGRATION_FLAG_KEY, datetime.now().isoformat())
            await pipe.execute()
            self._migration_checked = True
            logger.info(f"ReflexionPatcher: migrated {count} JSONL patch entries to Redis")
        except Exception as e:
            # 保持未迁移状态,下次调用重试;读取路径会回退 JSONL,不丢功能
            logger.error(f"ReflexionPatcher: JSONL→Redis migration failed: {e}")

    @staticmethod
    def _decode(raw) -> str:
        return raw.decode() if isinstance(raw, bytes) else raw

    # ------------------------------------------------------------------
    # 补丁生成(逻辑不变)
    # ------------------------------------------------------------------

    async def generate_patch(
        self,
        user_id: int,
        user_input_context: str,
        agent_response: str,
        user_feedback: str,
        score: float,
        metrics: Dict[str, Any]
    ) -> Optional[Dict[str, str]]:
        """
        Generate an instruction patch using LLM based on negative feedback.
        Returns a dict with 'patch', 'scope', 'reasoning'.
        """
        try:
            prompt = self._construct_patching_prompt(
                user_input_context, agent_response, user_feedback, score, metrics
            )

            # Use the LLM service to generate the patch
            llm = get_llm_service()

            system_prompt = "You are an expert AI behavior analyst. Your goal is to analyze a failed interaction and generate a concise 'Instruction Patch' to prevent it from happening again."

            # Using metadata to identify this as internal system task
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

            # Parse JSON
            try:
                # Attempt to find JSON in markdown block if present
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

            # Store the patch
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

    # ------------------------------------------------------------------
    # 存取(Redis 主、JSONL 备份/回退)
    # ------------------------------------------------------------------

    async def _store_patch(self, user_id: int, patch: str, scope: str, reasoning: str, score: float, metrics: Dict):
        entry = {
            "user_id": user_id,
            "timestamp": datetime.now().isoformat(),
            "score": score,
            "metrics": metrics,
            "patch": patch,
            "scope": scope,
            "reasoning": reasoning,
            "status": "active" # active, verified, archived
        }

        # 1. 先确保存量迁移完成(必须在 JSONL 追加之前,否则本条会被迁移重复搬入)
        redis = await self._get_redis()
        if redis is not None:
            await self._ensure_migrated(redis)

        # 2. JSONL 双写(备份/审计,保持旧格式兼容)
        await self._append_line(json.dumps(entry, ensure_ascii=False) + "\n")

        # 3. Redis 主存储
        if redis is not None:
            try:
                key = self._entry_key(entry)
                pipe = redis.pipeline()
                pipe.rpush(key, json.dumps(entry, ensure_ascii=False))
                pipe.ltrim(key, -self.MAX_LIST_LEN, -1)
                await pipe.execute()
            except Exception as e:
                logger.error(f"ReflexionPatcher: Redis store failed (JSONL backup kept): {e}")

        # 3. 缓存失效:GLOBAL 影响所有用户,清全部;PERSONAL 只清该用户
        if scope == "GLOBAL":
            self._cache.clear()
        else:
            self._cache.pop(user_id, None)

    async def get_active_patches(self, user_id: int) -> Dict[str, List[str]]:
        """
        Retrieve active patches for a user, separated by scope.
        Returns: {"global": [], "personal": []}
        """
        now = time.time()
        cached = self._cache.get(user_id)
        if cached and now - cached[0] < self.CACHE_TTL_SEC:
            return cached[1]

        redis = await self._get_redis()
        patches: Optional[Dict[str, List[str]]] = None
        if redis is not None:
            try:
                await self._ensure_migrated(redis)
                patches = {"global": [], "personal": []}
                raw_global = await redis.lrange(self.GLOBAL_KEY, -self.READ_TAIL, -1)
                raw_personal = await redis.lrange(self._personal_key(user_id), -self.READ_TAIL, -1)
                for raw_items, bucket in ((raw_global, "global"), (raw_personal, "personal")):
                    for raw in raw_items or []:
                        try:
                            entry = json.loads(self._decode(raw))
                        except json.JSONDecodeError:
                            continue
                        if entry.get("status") != "active":
                            continue
                        if entry.get("patch"):
                            patches[bucket].append(entry["patch"])
            except Exception as e:
                logger.error(f"ReflexionPatcher: Redis read failed, falling back to JSONL: {e}")
                patches = None

        if patches is None:
            patches = await self._get_active_patches_from_file(user_id)

        # Limit to last N of each to avoid context overflow
        patches["global"] = patches["global"][-self.ACTIVE_LIMIT:]
        patches["personal"] = patches["personal"][-self.ACTIVE_LIMIT:]
        self._cache[user_id] = (now, patches)
        return patches

    async def _get_active_patches_from_file(self, user_id: int) -> Dict[str, List[str]]:
        """旧实现保留为回退路径:全量读 JSONL(仅在 Redis 不可用时使用)。"""
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

        return patches

reflexion_patcher = ReflexionPatcher()
