from typing import List
from ..models.chat import ChatHistoryDB

def group_chat_history_by_pairs(messages: List[ChatHistoryDB]) -> List[List[ChatHistoryDB]]:
    """
    将消息分组为问答对。
    一个对以用户消息开始，以 AI 消息结束。
    输入消息必须按时间顺序排列（最旧的在前）。
    """
    groups = []
    current_group = []
    
    for msg in messages:
        is_user = (msg.role == "user")
        
        if is_user:
            # 检查是否应该开始新组
            # 如果当前组已经包含 AI 回复，则开始新组
            # 这意味着上一轮对话已完成。
            has_ai_reply = any(m.role == "ai" for m in current_group)
            if has_ai_reply:
                groups.append(current_group)
                current_group = []
        
        current_group.append(msg)
        
    if current_group:
        groups.append(current_group)
        
    return groups
