from typing import List
import re
from typing import TYPE_CHECKING

if TYPE_CHECKING:  # 仅用于类型标注;运行期导入会让 core 反向依赖 models
    from ..models import ChatHistoryDB

def is_chinese(text: str) -> bool:
    """简单检查文本是否包含中文字符"""
    return bool(re.search(r'[\u4e00-\u9fff]', text))

def group_chat_history_by_pairs(messages: List["ChatHistoryDB"]) -> List[List["ChatHistoryDB"]]:
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

def is_offline_meetup_intent(text: str) -> bool:
    if not text:
        return False
    keywords = [
        "见面", "线下", "过来", "过去", "来找你", "去找你", "约你",
        "地址", "定位", "发位置", "在哪", "哪里见", "见一面",
        "什么时候", "几点", "哪天", "周末", "今晚", "明天",
        "酒店", "房间", "小区", "楼下", "接你"
    ]
    if any(k in text for k in keywords):
        return True
    patterns = [
        r"(我|我想|我打算).{0,6}(去|来).{0,6}(找|见)",
        r"(你|咱).{0,6}(见|碰).{0,6}(一面|面)",
    ]
    return any(re.search(p, text) for p in patterns)

def is_offline_meetup_violation(text: str) -> bool:
    if not text:
        return False
    deny_patterns = [
        "见不了", "不能见", "异地", "不方便见", "别约", "不约",
        "不能答应", "不行", "不可以",
    ]
    if any(p in text for p in deny_patterns):
        return False
    violation_keywords = [
        "我去找你", "我过去", "我来找你", "我去找你", "我过来",
        "见面", "约", "时间", "地点", "地址", "定位", "发位置",
        "今晚", "明天", "后天", "周末", "几点", "哪天", "哪里见",
        "酒店", "房间", "楼下", "接你",
    ]
    if any(k in text for k in violation_keywords):
        return True
    # 具体星期/日期也构成"约定见面时间",此前仅有"周末/明天"等模糊词,
    # 导致"周四老地方见"这类明确赴约的回复漏判。
    return bool(re.search(
        r"周[一二三四五六日天]|礼拜[一二三四五六日天]|星期[一二三四五六日天]|\d{1,2}\s*[号日]",
        text,
    ))

def split_response_into_parts(text: str) -> List[str]:
    """
    智能拆分 AI 回复为多个气泡。
    
    Strategy:
    1. 保护动作描述 (括号内容) 不被拆分。
    2. 优先使用双换行符 (\n\n) 作为段落分割。
    3. 如果段落过长 (>30 chars)，尝试按句子结束符 (。！？；……) 拆分。
    4. 避免拆分出过短的碎片，尝试智能合并。
    """
    if not text:
        return []
        
    # First, normalize newlines to be safe
    normalized_response = text.replace('\r\n', '\n')

    # Step 0: Protect Action Blocks (parentheses or <action> tags)
    # We replace them with placeholders to prevent splitting inside them
    placeholders = {}
    
    def replace_action(match):
        key = f"__ACTION_{len(placeholders)}__"
        placeholders[key] = match.group(0)
        return key

    # Protect (...) and （...） and <action>...</action>
    # Note: simple nested parentheses are not supported by standard re, assuming single level
    protected_text = re.sub(r'(\([^\)]*\)|（[^）]*）|<action>[\s\S]*?</action>)', replace_action, normalized_response)
    
    initial_parts = [p.strip() for p in re.split(r'\n\s*\n', protected_text) if p.strip()]
    
    final_parts = []
    for part in initial_parts:
        # Strategy update: Try to split even if short, to allow emotional pacing
        # But prevent splitting extremely short fragments
        
        # If part is extremely short, keep it
        if len(part) < 5:
            final_parts.append(part)
            continue
            
        # Try to split by sentence delimiters (。！？.!?；;……)
        # We use a lookbehind to keep the delimiter with the sentence
        sub_parts = re.split(r'(?<=[。！？.!?；;……])\s*', part)
        
        # Filter empty strings
        sub_parts = [s for s in sub_parts if s.strip()]
        
        if not sub_parts:
            continue

        # Smart merge logic
        current_chunk = ""
        for sub in sub_parts:
            # If current_chunk is empty, start new chunk
            if not current_chunk:
                current_chunk = sub
                continue
            
            # Decide whether to merge sub into current_chunk
            # Criteria for merging:
            # 1. If result would be too long (> 30), don't merge (unless single sub is huge)
            # 2. If current_chunk is very short (< 5), merge (to avoid dangling words)
            # 3. If sub is very short (< 3), merge (e.g. closing quote or punctuation orphan)
            # 4. Otherwise, if both are substantial sentences, split them
            
            will_be_length = len(current_chunk) + len(sub)
            
            should_merge = False
            
            if will_be_length < 15:
                # If combined is still very short, merge
                should_merge = True
            elif len(current_chunk) < 3:
                 # Current chunk too short to stand alone
                 should_merge = True
            elif len(sub) < 3:
                 # Incoming part too short to stand alone
                 should_merge = True
            
            if should_merge:
                current_chunk += sub
            else:
                final_parts.append(current_chunk)
                current_chunk = sub
        
        if current_chunk:
            final_parts.append(current_chunk)

    if not final_parts:
        final_parts = [protected_text] if protected_text else []
    
    # Restore placeholders
    restored_parts = []
    for part in final_parts:
        for key, value in placeholders.items():
            part = part.replace(key, value)
        restored_parts.append(part)
    
    return restored_parts
