from typing import TypedDict, List, Dict, Any, Annotated

class AgentState(TypedDict):
    """
    Agent 状态定义
    存储工作流中各节点之间传递的数据

    == 状态合并契约(并行安全)==
    LangGraph 对无 reducer 的键使用 LastValue 通道:同一 superstep 内两个并行节点
    返回同一键会抛 InvalidUpdateError(不是覆盖,是崩溃)。因此:

    1. 每个键要么是「单写者」——任一 superstep 内至多一个节点返回它;
       要么显式声明 reducer(如 workflow_trace 的 dict-merge)。
    2. 并行分支(analyze 之后的 fan-out 与其二层任务)只允许返回自己名下的产物键:
       retrieve→retrieved_memories, summarize_topic→topic_summary,
       ensure_portrait→portrait, analyze_style→style_analysis,
       agent_thoughts→agent_thoughts, tool_check→tool_results。
    3. _skip_generation 的写者只有生成节点(generate/fast_generate/standard_generate);
       上游任务节点依赖缺失时返回 {} 跳过自身,由 generate 的汇聚检查兜底跳过语义。
    4. 通过 state[...] = ... 的就地修改不经过通道、不参与合并,只在本节点内可见,
       不能当作跨节点传值手段。
    5. route_logic 是 conditional entry point:它的返回值只用于选择分支,不是状态更新,
       其内部的 state["route"] = ... 同样不进通道。因此 route 必须由三个入口节点
       (analyze_emotion→DEEP / fast_generate→FAST / standard_generate→STANDARD)
       在返回 dict 中显式写入,否则 tool_check 会早退、DEEP 的角色卡 addendum、
       超时保护与专用模型选择全部静默失效。
    """
    user_input: str               # 用户输入的原始文本
    original_input: str           # 纠错前的原始文本 (如果发生纠错)
    route: str                    # 路由决策 (FAST, STANDARD, DEEP)
    user_id: int                  # 用户 ID (Integer)
    session_id: str               # 会话 ID
    execution_id: str             # 唯一执行 ID (用于当前轮次的工作流追踪)。入口节点(analyze/fast/standard)初始化后必须在返回 dict 中显式传递
    request_start_ts: float       # 本轮请求开始时间戳。同上必须显式返回,save 节点依赖它记录 SLO e2e 延迟
    emotion_scores: Dict[str, float] # GoEmotions 原始情感分数 (27维)
    ekman_scores: Dict[str, float]   # 映射后的 Ekman 基础情感分数 (6维) - 用于前端展示一致性
    top_emotions: List[tuple]     # 排序后的主要情感列表 [(emotion, score), ...]
    engagement_score: float       # 用户投入度评分 (0-100) - 替代了旧的 emotion_variance
    retrieved_memories: List[str] # 检索到的相关记忆列表
    selected_personality: str     # 当前选择的或主要的人格名称
    personality_weights: Dict[str, float] # 各人格的混合权重
    love_style_weights: Dict[str, float] # 恋爱风格分析结果 (保留字段名兼容，实际存储沟通情感分析权重)
    agent_thoughts: Dict[str, str] # 不同人格/角色的内心独白 (Thought)
    style_analysis: str           # 风格分析结果 (Task 2)
    topic_summary: str            # 话题和上下文总结
    portrait: str                 # 角色画像 (Task 1)
    response: str                 # 最终生成的回复文本
    response_parts: List[str]     # 最终生成的回复文本（分段列表）
    system_prompt: str            # 生成回复时使用的系统提示词 (用于调试)
    rl_action_idx: int            # RL Agent 选择的动作索引 (用于强化学习反馈)
    user_message_id: int          # 用户消息 ID (DB ID)
    ai_message_id: int            # AI 消息 ID (DB ID)
    _skip_generation: bool        # 内部标志：跳过生成。单写者键:仅 generate/fast/standard 可写(见类 docstring 契约第 3 条)
    # logs: List[Dict[str, Any]]    # 关键日志列表，用于前端调试面板展示 (已移除)
    workflow_trace: Annotated[Dict[str, Dict[str, Any]], lambda x, y: {**x, **y}] # 工作流追踪数据：(保留用于向后兼容，但数据已持久化到 DB)
    
    # 共享数据缓存 (避免重复 DB 查询)
    common_settings: Any          # Pydantic Model: CommonSettings
    active_profiles: List[Any]    # List[Pydantic Model: RoleProfile]
    tool_results: Dict[str, str]  # 工具调用结果
