import numpy as np
from typing import List, Dict, Optional, Tuple
import math
import structlog
from sentence_transformers import SentenceTransformer
from sentence_transformers.util import cos_sim
import re

try:
    import jieba  # type: ignore
except ModuleNotFoundError:
    jieba = None

logger = structlog.get_logger()

class MetricsService:
    _instance = None
    _model = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(MetricsService, cls).__new__(cls)
            cls._instance._initialize()
        return cls._instance

    def _initialize(self):
        """Initialize heavy models (Sentence-BERT)."""
        try:
            # Load a lightweight model for efficiency
            # 优先用随包分发的本地模型。原先直接写 HF Hub ID,运行时按需下载 ——
            # 开发机有缓存所以一直没暴露,而用户拿到的是干净的安装包,
            # 首次使用要联网拉 ~90MB,断网就直接失败。
            from app.core.paths import resolve_local_model
            model_ref = resolve_local_model("all-MiniLM-L6-v2") or "all-MiniLM-L6-v2"
            self._model = SentenceTransformer(model_ref)
            logger.info(f"MetricsService: Sentence-BERT model loaded from {model_ref}")
        except Exception as e:
            logger.error(f"MetricsService: Failed to load Sentence-BERT model: {e}")
            self._model = None

    # --- Helper Methods ---

    def _get_embedding(self, text: str) -> np.ndarray:
        """Get embedding vector for a text."""
        if self._model is None or not text.strip():
            return np.zeros(384) # Return zero vector if model fails
        return self._model.encode(text)

    def _cosine_similarity(self, vec1: np.ndarray, vec2: np.ndarray) -> float:
        if np.all(vec1 == 0) or np.all(vec2 == 0):
            return 0.0
        return float(cos_sim(vec1, vec2)[0][0])

    def _normalize(self, value: float, min_val: float, max_val: float) -> float:
        """MinMax Normalization."""
        if max_val - min_val == 0:
            return 0.0
        return max(0.0, min(1.0, (value - min_val) / (max_val - min_val)))

    def _sigmoid(self, x: float) -> float:
        return 1 / (1 + np.exp(-x))

    def _tokenize(self, text: str) -> List[str]:
        if not text:
            return []
        if jieba is not None:
            return [t for t in jieba.cut(text) if t.strip()]
        tokens = re.findall(r"[A-Za-z0-9]+|[\u4e00-\u9fff]", text)
        if tokens:
            return tokens
        return [t for t in re.split(r"\s+", text) if t]

    def _split_sentences(self, text: str) -> List[str]:
        # Updated regex to include ellipsis and semicolons as delimiters
        return [s for s in re.split(r"[。！？.!?\n；;……]+", text) if s.strip()]

    def _get_valence(self, ekman_scores: Dict[str, float]) -> float:
        """
        Calculate emotional valence from Ekman scores.
        Valence = Joy + 0.5*Surprise - (Anger + Disgust + Fear + Sadness)
        Range: roughly [-1, 1.5]
        """
        joy = ekman_scores.get('joy', 0.0)
        surprise = ekman_scores.get('surprise', 0.0)
        anger = ekman_scores.get('anger', 0.0)
        disgust = ekman_scores.get('disgust', 0.0)
        fear = ekman_scores.get('fear', 0.0)
        sadness = ekman_scores.get('sadness', 0.0)
        
        return joy + 0.5 * surprise - (anger + disgust + fear + sadness)

    # --- Interaction Quality (Q_I) ---

    def calculate_interaction_quality(
        self, 
        response: str, 
        history: List[str], 
        actual_emotion: Dict[str, float],
        target_emotion: Dict[str, float]
    ) -> Dict[str, float]:
        """
        Calculate Q_I metrics: M_coh, M_hum, M_emo.
        """
        m_coh = self._calculate_coherence(response, history)
        m_hum = self._calculate_human_likeness(response)
        m_emo = self._calculate_emotional_rationality(actual_emotion, target_emotion)
        
        # Weighted sum (Default weights, can be overridden by Intent)
        # Weights: coh=0.4, hum=0.3, emo=0.3 (Base)
        score = 0.4 * m_coh + 0.3 * m_hum + 0.3 * m_emo
        
        return {
            "Q_I": score,
            "M_coh": m_coh,
            "M_hum": m_hum,
            "M_emo": m_emo
        }

    def _calculate_coherence(self, response: str, history: List[str], k: int = 3) -> float:
        """M_coh: Semantic similarity with recent history."""
        if not history:
            return 1.0 # Default to high coherence if no history
            
        resp_vec = self._get_embedding(response)
        
        # Limit to last K turns
        recent_history = history[-k:]
        similarities = []
        
        for hist_msg in recent_history:
            hist_vec = self._get_embedding(hist_msg)
            similarities.append(self._cosine_similarity(resp_vec, hist_vec))
            
        avg_sim = sum(similarities) / len(similarities) if similarities else 0.0
        
        # Sigmoid normalization: center at 0.3 (theta), slope 10 (gamma)
        # S(10 * (avg_sim - 0.3))
        theta = 0.3
        gamma = 10
        return self._sigmoid(gamma * (avg_sim - theta))

    def _calculate_human_likeness(self, response: str) -> float:
        """M_hum: TTR + Sentence Length StdDev + Length Penalty + Particle Bonus."""
        if not response:
            return 0.0
            
        # 1. TTR (Type-Token Ratio)
        words = self._tokenize(response)
        if not words:
            return 0.0
        ttr = len(set(words)) / len(words)
        norm_ttr = self._normalize(ttr, 0.3, 0.8) # Typical range for chat
        
        # 2. Sentence Length StdDev & Max Length Penalty
        sentences = self._split_sentences(response)
        max_len_penalty = 0.0
        
        # Calculate max length across all sentences
        if sentences:
            max_len = max(len(s) for s in sentences)
        else:
            max_len = 0

        # Strict length penalties as requested
        if max_len > 25:
            max_len_penalty = 0.3
        elif max_len > 10:
            max_len_penalty = 0.1
        
        if len(sentences) <= 1:
            norm_std = 0.3 # Penalize single sentence slightly more because no rhythm variety
        else:
            lengths = [len(s) for s in sentences]
            std_dev = np.std(lengths)
            # Human speech has variance. AI is often uniform.
            norm_std = self._normalize(std_dev, 0, 20)

        # 3. Particle Bonus (Chinese specific)
        # Presence of modal particles indicates casual speech
        particles = {'呢', '呀', '吧', '嘛', '呗', '啦', '哦', '哈', '哎', '啊', '唔', '嗯'}
        # Check occurrence in tokens
        particle_count = sum(1 for w in words if w in particles)
        particle_bonus = min(0.15, particle_count * 0.03) # Max 0.15 bonus

        # Weighted Sum
        # Weights: TTR=0.3, Std=0.5 (Variance is key), Penalty/Bonus adjustments
        base_score = 0.3 * norm_ttr + 0.5 * norm_std
        final_score = base_score - max_len_penalty + particle_bonus
            
        return max(0.0, min(1.0, final_score))

    def _calculate_emotional_rationality(self, actual: Dict[str, float], target: Dict[str, float]) -> float:
        """M_emo: Euclidean distance in Ekman space."""
        # If no target emotion is specified, assume behavior is rational (score 1.0)
        if not target:
            return 1.0

        # Ensure ordered vectors
        emotions = ['anger', 'disgust', 'fear', 'joy', 'neutral', 'sadness', 'surprise']
        v_actual = np.array([actual.get(e, 0.0) for e in emotions])
        v_target = np.array([target.get(e, 0.0) for e in emotions])
        
        dist = float(np.linalg.norm(v_actual - v_target))
        # Max distance in 7D unit hypercube is sqrt(7) ~ 2.6
        # But emotions usually sum to 1? If prob distribution, max dist is sqrt(2) = 1.414
        # Normalized score: 1 - dist / sqrt(2)
        
        return max(0.0, 1.0 - (dist / math.sqrt(2)))

    # --- User Engagement (E_U) ---

    def calculate_user_engagement(
        self,
        agent_response: str,
        user_next_input: str,
        response_time_sec: float,
        prev_user_emotion: Dict[str, float],
        next_user_emotion: Dict[str, float]
    ) -> Dict[str, float]:
        """
        Calculate E_U metrics: M_cont, M_rtl, M_sent.
        """
        m_cont = self._calculate_topic_continuation(agent_response, user_next_input)
        m_rtl = self._calculate_rtl_ratio(user_next_input, response_time_sec)
        m_sent = self._calculate_sentiment_lift(prev_user_emotion, next_user_emotion)
        
        # Weights: cont=0.5, rtl=0.3, sent=0.2
        score = 0.5 * m_cont + 0.3 * m_rtl + 0.2 * m_sent
        
        return {
            "E_U": score,
            "M_cont": m_cont,
            "M_rtl": m_rtl,
            "M_sent": m_sent
        }

    def _calculate_topic_continuation(self, agent_resp: str, user_next: str) -> float:
        """M_cont: Cosine similarity between agent response and user follow-up."""
        vec1 = self._get_embedding(agent_resp)
        vec2 = self._get_embedding(user_next)
        sim = self._cosine_similarity(vec1, vec2)
        return max(0.0, sim)

    def _calculate_rtl_ratio(self, text: str, seconds: float) -> float:
        """M_rtl: Tanh(ln(Len+1) / ln(Time+e) * lambda)."""
        if seconds <= 0: seconds = 0.1 # Avoid div by zero
        length = len(text)
        
        num = math.log(length + 1)
        den = math.log(seconds + math.e)
        ratio = (num / den) * 2.0 # lambda = 2.0
        
        return math.tanh(ratio)

    def _calculate_sentiment_lift(self, prev_emo: Dict[str, float], next_emo: Dict[str, float]) -> float:
        """M_sent: Positive change in valence."""
        v_prev = self._get_valence(prev_emo)
        v_next = self._get_valence(next_emo)
        
        delta = v_next - v_prev
        # Sigmoid normalize delta centered at 0
        # Slope 2
        return self._sigmoid(2 * delta)

    # --- Relationship Depth (D_R) ---

    def calculate_relationship_depth(
        self,
        session_count_7d: int,
        retention_rate_7d: float,
        memory_updates_count: int,
        total_interactions: int
    ) -> Dict[str, float]:
        """
        Calculate D_R metrics: M_freq, M_mem.
        """
        m_freq = self._calculate_interaction_frequency(session_count_7d, retention_rate_7d)
        m_mem = self._calculate_memory_density(memory_updates_count, total_interactions)
        
        # Weights: freq=0.7, mem=0.3
        score = 0.7 * m_freq + 0.3 * m_mem
        
        return {
            "D_R": score,
            "M_freq": m_freq,
            "M_mem": m_mem
        }

    def _calculate_interaction_frequency(self, count: int, retention: float) -> float:
        """M_freq: 0.5 * Retention + 0.5 * Norm(Count)."""
        # Normalize count: assume 10 sessions/week is max score
        norm_count = self._normalize(float(count), 0, 10)
        return 0.5 * retention + 0.5 * norm_count

    def _calculate_memory_density(self, updates: int, total: int) -> float:
        """M_mem: Updates / Total Interactions."""
        if total == 0:
            return 0.0
        # Assume 1 update per 10 interactions is good (density = 0.1) -> Score 1.0
        density = updates / total
        return self._normalize(density, 0, 0.1)

# Singleton
metrics_service = MetricsService()
