from langchain_core.messages import SystemMessage, HumanMessage
from ...core.llm import get_llm_service
from ...services.memory.chat_history import history_service
from ...core.database import SessionLocal
from .state import AgentState
from .tools import add_trace, monitor_execution_time
import structlog
import re

logger = structlog.get_logger()

# 预编译正则：纯标点/表情/特殊符号
RE_ONLY_SYMBOLS = re.compile(r"^[\s\W_]+$")

@monitor_execution_time
async def correct_typo(state: AgentState) -> AgentState:
    """
    独立节点：输入纠错 (Correction)
    在路由之前执行，检查并修正用户输入的错别字
    """
    try:
        user_input = state.get("user_input", "")
        user_id = state.get("user_id")
        
        # --- 1. 启发式过滤 (Heuristic Filter) ---
        
        # 规则 A: 极短文本且无明显歧义可能不需要纠错 (如 "嗯", "好")
        # 但 "像你" 也很短，所以长度限制不能太死。
        # 这里的策略是：只有纯符号才绝对跳过。
        if not user_input or RE_ONLY_SYMBOLS.match(user_input):
            logger.debug(f"Correction skipped: Only symbols/empty. '{user_input}'")
            return {}

        # 规则 B: 长度超过 50 字，认为上下文冗余度够高，AI 自己能容错，跳过以节省成本
        # (除非用户显式要求纠错，但这里是隐式的)
        if len(user_input) > 50:
            logger.debug(f"Correction skipped: Length > 50. '{user_input[:10]}...'")
            return {}

        # --- 2. 获取上下文 ---
        context_msgs = []
        try:
            # 使用同步 Session 获取历史
            with SessionLocal() as db:
                # 获取最近 5 条消息作为背景
                history = history_service.get_recent_history_limit(user_id, 5, db, exclude_statuses=["pending", "processing", "failed"])
                
                # 获取当前消息 ID (如果有)
                current_msg_id = state.get("user_message_id")
                
                for msg in history:
                    # 排除掉当前这条消息本身（如果已经入库）
                    if current_msg_id and msg.id == current_msg_id:
                        continue
                    # 简单内容去重：如果是最近的一条且内容完全一样，大概率是重复获取
                    if msg.role == "user" and msg.content == user_input:
                        # 仅当它是列表最后一条时才怀疑是自己
                        pass 

                    role_str = "User" if msg.role == "user" else "AI"
                    context_msgs.append(f"{role_str}: {msg.content}")
        except Exception as e:
            logger.warning(f"Failed to fetch history for correction: {e}")
            
        context_text = "\n".join(context_msgs)

        # --- 3. 构建 Prompt ---
        system_prompt = """你是一个专业的中文输入纠错助手，专门处理拼音输入法导致的同音字错误。
你的任务是根据对话上下文，判断用户最新的输入是否存在明显的同音错别字。

**纠错原则：**
1. **优先假设是恋爱/暧昧语境**：Daisy 是情感伴侣 AI，用户更可能在调情而非讨论哲学（如“像不像”）。
2. **重点修正同音字**：特别关注“像/想”、“再/在”、“做/作”、“那/哪”等常见混淆。
3. **高置信度才改**：如果原句在语境下极其通顺且无歧义，则不改。但如果原句略显生硬（如“像你呢”作为回答），而同音字（“想你呢”）非常完美，请果断修改。

**示例：**
Context:
AI: 这么晚了还没睡？
User: 有没有可能，像你呢？
Output: 有没有可能，想你呢？ (语境：晚安暧昧 -> 想念)

Context:
AI: 你长得像谁？
User: 有没有可能，像你呢？
Output: 有没有可能，像你呢？ (语境：讨论长相 -> 相似)

Context:
AI: 我在吃饭
User: 我也再吃
Output: 我也在吃
"""

        user_prompt = f"""对话上下文：
{context_text}

用户最新输入：
{user_input}

请输出修正后的文本（如果无需修正，请直接输出原文本，不要包含任何解释）："""

        # --- 4. 调用 LLM ---
        # 使用轻量级模型 (e.g. GPT-3.5-Turbo / Gemini Flash)
        llm = get_llm_service().get_lightweight_llm()
        
        response = await llm.ainvoke([
            SystemMessage(content=system_prompt),
            HumanMessage(content=user_prompt)
        ])
        
        corrected_text = response.content.strip()
        
        # 清理可能的 Markdown 或引号
        if corrected_text.startswith('"') and corrected_text.endswith('"'):
            corrected_text = corrected_text[1:-1]
            
        # --- 5. 结果处理 ---
        # 只有当文本确实发生变化且非空时才更新
        if corrected_text and corrected_text != user_input:
            logger.info(f"Typo Corrected", original=user_input, corrected=corrected_text)
            
            # 记录 Trace
            trace = await add_trace(state, "correct_typo", 
                input_data={
                    "original_input": user_input,
                    "context": context_text
                }, 
                output_data={
                    "corrected_input": corrected_text
                } 
            )
            
            return {
                "user_input": corrected_text,
                "original_input": user_input,
                "workflow_trace": trace
            }
        else:
            return {}

    except Exception as e:
        logger.error(f"Error in correct_typo: {e}")
        return {}
