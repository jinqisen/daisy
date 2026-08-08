from __future__ import annotations

import asyncio
import json
from typing import Dict, Any, List, Optional
from datetime import datetime, timedelta
from ....shared.redis import redis_client


class ReflexionPatcher:
    def __init__(self):
        self.global_patches_key = "reflexion:patches:global"
        self.personal_patches_prefix = "reflexion:patches:user:"
        self.patch_ttl = 86400 * 30
    
    async def generate_patch(
        self,
        user_id: int,
        user_input_context: str,
        agent_response: str,
        user_feedback: str,
        score: float,
        metrics: Dict[str, Any]
    ) -> bool:
        try:
            loop = asyncio.get_running_loop()
            
            def _generate():
                patch_content = self._analyze_failure(
                    user_input_context,
                    agent_response,
                    user_feedback,
                    score,
                    metrics
                )
                
                if not patch_content:
                    return False
                
                patch_type = self._determine_patch_type(patch_content, metrics)
                
                if patch_type == "global":
                    self._add_global_patch(patch_content)
                else:
                    self._add_personal_patch(user_id, patch_content)
                
                return True
            
            return await loop.run_in_executor(None, _generate)
        except Exception as e:
            print(f"Failed to generate patch: {e}")
            return False
    
    def _analyze_failure(
        self,
        user_input: str,
        agent_response: str,
        user_feedback: str,
        score: float,
        metrics: Dict[str, Any]
    ) -> Optional[str]:
        q_i = metrics.get("Q_I", 0.0)
        e_u = metrics.get("E_U", 0.0)
        
        if q_i < 0.3:
            if "emotion_consistency" in metrics and metrics["emotion_consistency"] < 0.4:
                return "回复的情感表达与目标情绪不一致，需要调整语气和情感强度"
            elif "coherence" in metrics and metrics["coherence"] < 0.4:
                return "回复与上下文不够连贯，需要更好地衔接对话内容"
            elif "diversity" in metrics and metrics["diversity"] < 0.3:
                return "回复过于重复，需要增加表达的多样性"
        
        if e_u < 0.3:
            if "length_score" in metrics and metrics["length_score"] < 0.4:
                return "用户回复过短，可能是因为回复不够吸引人，需要增加互动性"
            elif "emotion_improvement" in metrics and metrics["emotion_improvement"] < 0.3:
                return "未能有效改善用户情绪，需要更加关注用户的情感需求"
        
        if len(user_feedback) > 10:
            return f"用户反馈: {user_feedback[:100]}"
        
        return None
    
    def _determine_patch_type(
        self,
        patch_content: str,
        metrics: Dict[str, Any]
    ) -> str:
        generic_keywords = ["过于", "不够", "需要", "应该", "避免"]
        
        if any(kw in patch_content for kw in generic_keywords):
            return "global"
        
        return "personal"
    
    def _add_global_patch(self, patch_content: str):
        try:
            patches = redis_client.lrange(self.global_patches_key, 0, -1)
            existing_patches = [json.loads(p) for p in patches]
            
            for existing in existing_patches:
                if existing["content"] == patch_content:
                    existing["count"] += 1
                    existing["updated_at"] = datetime.now().isoformat()
                    return
            
            new_patch = {
                "content": patch_content,
                "count": 1,
                "created_at": datetime.now().isoformat(),
                "updated_at": datetime.now().isoformat()
            }
            
            redis_client.lpush(self.global_patches_key, json.dumps(new_patch))
            redis_client.expire(self.global_patches_key, self.patch_ttl)
        except Exception as e:
            print(f"Failed to add global patch: {e}")
    
    def _add_personal_patch(self, user_id: int, patch_content: str):
        try:
            key = f"{self.personal_patches_prefix}{user_id}"
            patches = redis_client.lrange(key, 0, -1)
            existing_patches = [json.loads(p) for p in patches]
            
            for existing in existing_patches:
                if existing["content"] == patch_content:
                    existing["count"] += 1
                    existing["updated_at"] = datetime.now().isoformat()
                    return
            
            new_patch = {
                "content": patch_content,
                "count": 1,
                "created_at": datetime.now().isoformat(),
                "updated_at": datetime.now().isoformat()
            }
            
            redis_client.lpush(key, json.dumps(new_patch))
            redis_client.expire(key, self.patch_ttl)
        except Exception as e:
            print(f"Failed to add personal patch: {e}")
    
    async def get_patches(self, user_id: int) -> Dict[str, List[str]]:
        try:
            loop = asyncio.get_running_loop()
            
            def _get():
                global_patches = []
                try:
                    raw_global = redis_client.lrange(self.global_patches_key, 0, 9)
                    global_patches = [json.loads(p)["content"] for p in raw_global]
                except Exception:
                    pass
                
                personal_patches = []
                try:
                    key = f"{self.personal_patches_prefix}{user_id}"
                    raw_personal = redis_client.lrange(key, 0, 9)
                    personal_patches = [json.loads(p)["content"] for p in raw_personal]
                except Exception:
                    pass
                
                return {
                    "global": global_patches,
                    "personal": personal_patches
                }
            
            return await loop.run_in_executor(None, _get)
        except Exception as e:
            print(f"Failed to get patches: {e}")
            return {"global": [], "personal": []}
    
    async def clear_expired_patches(self):
        try:
            loop = asyncio.get_running_loop()
            
            def _clear():
                cutoff = datetime.now() - timedelta(days=30)
                
                try:
                    global_patches = redis_client.lrange(self.global_patches_key, 0, -1)
                    valid_patches = []
                    
                    for raw_patch in global_patches:
                        patch = json.loads(raw_patch)
                        updated_at = datetime.fromisoformat(patch["updated_at"])
                        
                        if updated_at > cutoff:
                            valid_patches.append(raw_patch)
                    
                    redis_client.delete(self.global_patches_key)
                    for patch in valid_patches:
                        redis_client.lpush(self.global_patches_key, patch)
                except Exception as e:
                    print(f"Failed to clear global patches: {e}")
                
                try:
                    pattern = f"{self.personal_patches_prefix}*"
                    keys = redis_client.keys(pattern)
                    
                    for key in keys:
                        patches = redis_client.lrange(key, 0, -1)
                        valid_patches = []
                        
                        for raw_patch in patches:
                            patch = json.loads(raw_patch)
                            updated_at = datetime.fromisoformat(patch["updated_at"])
                            
                            if updated_at > cutoff:
                                valid_patches.append(raw_patch)
                        
                        redis_client.delete(key)
                        for patch in valid_patches:
                            redis_client.lpush(key, patch)
                except Exception as e:
                    print(f"Failed to clear personal patches: {e}")
            
            await loop.run_in_executor(None, _clear)
        except Exception as e:
            print(f"Failed to clear expired patches: {e}")


reflexion_patcher = ReflexionPatcher()
