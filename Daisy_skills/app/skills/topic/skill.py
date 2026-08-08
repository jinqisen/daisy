from typing import Any, Dict, List, Optional
from datetime import datetime


def _compact_texts(texts: List[str], max_chars: int = 400) -> str:
    result = []
    current_length = 0
    for text in texts:
        if current_length + len(text) > max_chars:
            remaining = max_chars - current_length
            if remaining > 0:
                result.append(text[:remaining])
            break
        result.append(text)
        current_length += len(text)
    return " ".join(result)


def _truncate_text(text: str, max_length: int = 400) -> str:
    if len(text) <= max_length:
        return text
    return text[:max_length]


def _extract_keywords(text: str, top_n: int = 5) -> List[str]:
    stop_words = {"的", "了", "是", "在", "我", "你", "他", "她", "它", "我们", "你们", "他们", "这", "那", "有", "没有", "不", "也", "就", "都", "而", "及", "与", "或", "the", "a", "an", "is", "are", "was", "were", "be", "been", "being", "have", "has", "had", "do", "does", "did", "will", "would", "could", "should", "may", "might", "must", "shall", "can", "need", "dare", "ought", "used", "to", "of", "in", "for", "on", "with", "at", "by", "from", "as", "into", "through", "during", "before", "after", "above", "below", "between", "under", "again", "further", "then", "once", "here", "there", "when", "where", "why", "how", "all", "each", "few", "more", "most", "other", "some", "such", "no", "nor", "not", "only", "own", "same", "so", "than", "too", "very", "s", "t", "can", "will", "just", "don", "should", "now"}
    
    words = text.split()
    word_freq = {}
    for word in words:
        word = word.strip(".,!?;:\"'()[]{}")
        if len(word) > 1 and word.lower() not in stop_words:
            word_freq[word] = word_freq.get(word, 0) + 1
    
    sorted_words = sorted(word_freq.items(), key=lambda x: x[1], reverse=True)
    return [word for word, freq in sorted_words[:top_n]]


def _detect_topic_from_keywords(keywords: List[str]) -> str:
    topic_keywords = {
        "技术": ["技术", "编程", "代码", "开发", "软件", "算法", "数据", "人工智能", "AI", "machine", "learning", "code", "programming", "development"],
        "生活": ["生活", "日常", "工作", "学习", "健康", "运动", "饮食", "sleep", "health", "exercise", "daily", "life"],
        "娱乐": ["娱乐", "游戏", "电影", "音乐", "小说", "阅读", "game", "movie", "music", "entertainment", "reading"],
        "情感": ["情感", "心情", "情绪", "感受", "开心", "难过", "emotion", "feeling", "mood", "happy", "sad"],
        "学习": ["学习", "知识", "教育", "课程", "考试", "study", "learn", "education", "knowledge", "course", "exam"],
        "工作": ["工作", "职业", "职场", "公司", "项目", "work", "job", "career", "company", "project", "business"],
    }
    
    topic_scores = {}
    for topic, topic_words in topic_keywords.items():
        score = sum(1 for kw in keywords if kw in topic_words)
        if score > 0:
            topic_scores[topic] = score
    
    if topic_scores:
        return max(topic_scores.items(), key=lambda x: x[1])[0]
    return "通用"


async def summarize(input_data: Dict[str, Any], context: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    history = input_data.get("history", [])
    latest_message = input_data.get("latest_message", "")
    session_id = input_data.get("session_id", "")
    max_tokens = input_data.get("max_tokens", 100)
    language_hint = input_data.get("language_hint", "zh")
    
    max_chars = max_tokens * 4 if max_tokens else 400
    
    history_texts = [msg.get("content", "") for msg in history if isinstance(msg, dict)]
    combined = _compact_texts(history_texts + [latest_message], max_chars)
    summary = _truncate_text(combined, max_chars)
    
    keywords = _extract_keywords(summary)
    primary_topic = _detect_topic_from_keywords(keywords)
    
    confidence = min(1.0, len(keywords) / 5.0)
    
    return {
        "summary": summary,
        "session_id": session_id,
        "topic_tags": keywords,
        "primary_topic": primary_topic,
        "confidence": confidence,
        "metadata": {
            "language_hint": language_hint,
            "max_tokens": max_tokens,
            "timestamp": datetime.utcnow().isoformat()
        }
    }


async def detect(input_data: Dict[str, Any], context: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    messages = input_data.get("messages", [])
    session_id = input_data.get("session_id", "")
    
    all_text = " ".join([msg.get("content", "") if isinstance(msg, dict) else str(msg) for msg in messages])
    keywords = _extract_keywords(all_text, top_n=10)
    
    primary_topic = _detect_topic_from_keywords(keywords)
    
    topics = []
    for keyword in keywords:
        topic = _detect_topic_from_keywords([keyword])
        if topic not in topics:
            topics.append(topic)
    
    confidence = min(1.0, len(keywords) / 8.0)
    
    return {
        "topics": topics,
        "primary_topic": primary_topic,
        "confidence": confidence,
        "keywords": keywords,
        "metadata": {
            "session_id": session_id,
            "message_count": len(messages),
            "timestamp": datetime.utcnow().isoformat()
        }
    }


async def track(input_data: Dict[str, Any], context: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    session_id = input_data.get("session_id", "")
    current_message = input_data.get("current_message", "")
    previous_topic = input_data.get("previous_topic", "")
    
    current_keywords = _extract_keywords(current_message, top_n=5)
    current_topic = _detect_topic_from_keywords(current_keywords)
    
    topic_changed = previous_topic and current_topic != previous_topic
    
    change_confidence = 0.0
    if topic_changed:
        change_confidence = min(1.0, len(current_keywords) / 5.0)
    
    return {
        "current_topic": current_topic,
        "previous_topic": previous_topic,
        "topic_changed": topic_changed,
        "change_confidence": change_confidence,
        "keywords": current_keywords,
        "metadata": {
            "session_id": session_id,
            "timestamp": datetime.utcnow().isoformat()
        }
    }


__all__ = ["summarize", "detect", "track"]
