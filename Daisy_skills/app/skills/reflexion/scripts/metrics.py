from __future__ import annotations

import numpy as np
from typing import Dict, Any, List
from sentence_transformers import SentenceTransformer


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
        
        consistency = 1.0 - (diff_sum / max_diff) if max_diff > 0 else 0.5
        return max(0.0, min(1.0, consistency))
    
    def _calculate_coherence(self, response: str, history: List[str]) -> float:
        if not history:
            return 0.5
        
        try:
            response_embedding = self._get_embedding(response)
            
            if len(history) > 0:
                last_input = history[-1]
                last_input_embedding = self._get_embedding(last_input)
                
                similarity = np.dot(response_embedding, last_input_embedding) / (
                    np.linalg.norm(response_embedding) * np.linalg.norm(last_input_embedding) + 1e-8
                )
                
                coherence = 0.5 + 0.5 * similarity
                return max(0.0, min(1.0, coherence))
        except Exception:
            pass
        
        return 0.5
    
    def _calculate_diversity(self, response: str, history: List[str]) -> float:
        if not history:
            return 0.5
        
        try:
            response_embedding = self._get_embedding(response)
            
            similarities = []
            for hist_item in history[-3:]:
                hist_embedding = self._get_embedding(hist_item)
                sim = np.dot(response_embedding, hist_embedding) / (
                    np.linalg.norm(response_embedding) * np.linalg.norm(hist_embedding) + 1e-8
                )
                similarities.append(sim)
            
            avg_similarity = np.mean(similarities) if similarities else 0.0
            diversity = 1.0 - avg_similarity
            return max(0.0, min(1.0, diversity))
        except Exception:
            pass
        
        return 0.5
    
    def calculate_user_engagement(
        self,
        agent_response: str,
        user_next_input: str,
        response_time_sec: float,
        prev_user_emotion: Dict[str, float],
        next_user_emotion: Dict[str, float]
    ) -> Dict[str, Any]:
        length_score = self._calculate_length_score(user_next_input)
        
        time_score = self._calculate_time_score(response_time_sec)
        
        emotion_improvement = self._calculate_emotion_improvement(
            prev_user_emotion, next_user_emotion
        )
        
        e_u = 0.3 * length_score + 0.3 * time_score + 0.4 * emotion_improvement
        
        return {
            "E_U": e_u,
            "length_score": length_score,
            "time_score": time_score,
            "emotion_improvement": emotion_improvement
        }
    
    def _calculate_length_score(self, user_input: str) -> float:
        length = len(user_input.strip())
        
        if length == 0:
            return 0.0
        elif length < 5:
            return 0.3
        elif length < 15:
            return 0.6
        elif length < 50:
            return 0.9
        else:
            return 1.0
    
    def _calculate_time_score(self, response_time_sec: float) -> float:
        if response_time_sec < 5:
            return 1.0
        elif response_time_sec < 15:
            return 0.8
        elif response_time_sec < 30:
            return 0.6
        elif response_time_sec < 60:
            return 0.4
        else:
            return 0.2
    
    def _calculate_emotion_improvement(
        self,
        prev_emotion: Dict[str, float],
        next_emotion: Dict[str, float]
    ) -> float:
        if not prev_emotion or not next_emotion:
            return 0.5
        
        prev_positive = prev_emotion.get("joy", 0.0) + prev_emotion.get("surprise", 0.0)
        next_positive = next_emotion.get("joy", 0.0) + next_emotion.get("surprise", 0.0)
        
        prev_negative = prev_emotion.get("sadness", 0.0) + prev_emotion.get("anger", 0.0) + prev_emotion.get("fear", 0.0)
        next_negative = next_emotion.get("sadness", 0.0) + next_emotion.get("anger", 0.0) + next_emotion.get("fear", 0.0)
        
        improvement = (next_positive - prev_positive) - (next_negative - prev_negative)
        
        normalized = 0.5 + 0.5 * improvement
        return max(0.0, min(1.0, normalized))
    
    def calculate_relationship_depth(
        self,
        session_count_7d: int,
        retention_rate_7d: float,
        memory_updates_count: int,
        total_interactions: int
    ) -> Dict[str, Any]:
        session_score = min(1.0, session_count_7d / 30.0)
        
        retention_score = retention_rate_7d
        
        memory_score = min(1.0, memory_updates_count / 100.0)
        
        interaction_score = min(1.0, total_interactions / 1000.0)
        
        d_r = 0.3 * session_score + 0.3 * retention_score + 0.2 * memory_score + 0.2 * interaction_score
        
        return {
            "D_R": d_r,
            "session_score": session_score,
            "retention_score": retention_score,
            "memory_score": memory_score,
            "interaction_score": interaction_score
        }


metrics_service = MetricsService()
