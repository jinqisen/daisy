"""
Agent 颗粒度对比测试
比较四种方案在同一输入下的延迟和输出质量：

A: Fixed     - 当前架构 + bug 修复 (Rubric_Check 解析, Final Thought 存储)
B: NoAgent   - 砍掉 agent_thoughts 层, 最终 LLM 直接看人格描述
C: Simple    - 精简 agent_thoughts (每个 Agent 只输出一句 Thought)
D: Merged    - 合并为一轮 (单次 LLM 调用, 内部模拟多声音冲突)

测试用例:
- 输入: 3 条不同场景的用户消息
- 每方案每条跑 3 次取平均
- 记录延迟 + 完整输出
"""
import asyncio
import time
import json
import sys
import os
import re

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from dotenv import load_dotenv
load_dotenv(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env"))

from app.core.llm_config import llm_config_manager
from app.core.llm import LLMService
from langchain_core.messages import SystemMessage, HumanMessage

# Load provider
with open(os.path.join(os.path.dirname(__file__), "llm_providers.json"), "r") as f:
    providers = json.load(f)
for key, config in providers.items():
    api_key_env = config.get("api_key_env")
    if api_key_env:
        env_key = os.environ.get(api_key_env)
        if env_key:
            config["api_key"] = env_key.strip().strip('"').strip("'")
    llm_config_manager.set_provider_config(key, config)
llm_config_manager.set_current_provider("huaweicloud")

# ============================================================
# 角色上下文 (静雯)
# ============================================================
CHARACTER = {
    "name": "静雯",
    "gender": "女",
    "age": 24,
    "occupation": "心理医生",
    "relationship": "朋友及以上",
    "backstory": "来自江南小镇，华中科技大学同济医学院毕业，在武汉执业。职业训练让她看透世情，内心却渴望亲密关系。",
    "world_setting": "2025年武汉，现代都市",
}

PERSONALITIES = [
    {
        "name": "Storge",
        "weight": 0.54,
        "description": "深厚、稳定的情感联结，重视长期可靠的关系，温暖踏实",
        "style": "温和、支持性、务实"
    },
    {
        "name": "Ludus",
        "weight": 0.26,
        "description": "轻松随性，享受游戏般的互动，保持若即若离的神秘感",
        "style": "幽默、调侃、不认真"
    },
    {
        "name": "Eros",
        "weight": 0.20,
        "description": "热烈浪漫，渴望深度亲密，情感表达直接",
        "style": "热情、直白、感性"
    },
]

# 测试输入
TEST_INPUTS = [
    {
        "id": "neutral",
        "text": "还行",
        "desc": "中性/敷衍回复"
    },
    {
        "id": "emotional",
        "text": "今天被老板骂了，好难受",
        "desc": "负面情绪倾诉"
    },
    {
        "id": "flirty",
        "text": "你今天穿的衣服挺好看的",
        "desc": "轻微暧昧/夸奖"
    },
]

# ============================================================
# 共享的 System Prompt 构建
# ============================================================
def _build_portrait_text():
    return f"""Character Portrait: {CHARACTER['name']}是一位{CHARACTER['age']}岁的{CHARACTER['occupation']}，在{CHARACTER['world_setting']}。{CHARACTER['backstory']}"""

def _build_style_text():
    return "Language Style: 真诚、温和、偶尔风趣，口语化表达，避免AI腔。"

def _build_personality_descriptions():
    """构建人格描述文本（用于 B/D 方案）"""
    lines = []
    for p in PERSONALITIES:
        lines.append(f"- {p['name']} ({p['weight']:.0%}): {p['description']}。风格: {p['style']}")
    return "\n".join(lines)

def _build_costar_base(portrait_text, style_text, os_text, history_text, prev_thought=""):
    """构建 CO-STAR 框架的基础部分"""
    prev_block = ""
    if prev_thought:
        prev_block = f"\n**上一轮内心独白**: \"{prev_thought}\"\n请保持内心状态一致。"
    
    return f"""# CO-STAR PROMPT

## C (Context)
{portrait_text}
{history_text}
当前时间: 2026-08-12 晚上{prev_block}

## O (Objective)
你是{CHARACTER['name']}，{CHARACTER['relationship']}。口语化、生活化地回复，不要AI腔。

## S (Style)
{style_text}

## T (Tone)
根据内心独白和当前对话氛围决定。

## I (Internal Monologue Synthesis)
{os_text}

## A (Audience)
用户是你的{CHARACTER['relationship']}。

## R (Response)
回复要求：简短，不超过两句话。保持微信聊天风格。"""


# ============================================================
# 方案 A: Fixed (当前架构 + bug 修复)
# ============================================================
async def approach_a_fixed(llm_service, provider_config, user_input, run_id):
    """
    当前架构: 3 路 agent_thoughts → 1 路 final response
    Bug 修复: Rubric_Check 被解析并注入 OS 文本
    """
    # Step 1: 3 concurrent agent_thoughts
    t0 = time.time()
    
    async def agent_thought(personality):
        llm = llm_service.get_llm(provider_config=provider_config)
        sys_prompt = f"""你是{CHARACTER['name']}的{personality['name']}人格面。
背景: {CHARACTER['backstory']}
你的特质: {personality['description']}
风格: {personality['style']}

你需要：
1. 从以下策略中选择一个：[Empathetic_Support, Playful_Teasing, Constructive_Challenge, Emotional_Mirroring, Strategic_Withdrawal, Direct_Advice]
2. 自我校准 (Rubric Check): 检查风格一致性、情商、沉浸感
3. 生成 1-2 句内心独白

输出格式:
[Strategy]: (策略名)
[Rubric_Check]:
- Style Consistency: (检查)
- Emotional Intelligence: (检查)
- Immersion: (检查)
[Thought]: (你的内心独白)"""
        
        user_prompt = f"""分析角色人格面对用户输入: '{user_input}'的内心想法/反应.

角色画像: {CHARACTER['name']}, {CHARACTER['age']}岁, {CHARACTER['occupation']}

生成一个简短的内心想法/反应，代表你的特定人格 ({personality['name']})。"""
        
        resp = await llm.ainvoke([SystemMessage(content=sys_prompt), HumanMessage(content=user_prompt)])
        return personality['name'], resp.content
    
    t_agent_start = time.time()
    tasks = [agent_thought(p) for p in PERSONALITIES]
    agent_results = await asyncio.gather(*tasks)
    t_agent = time.time() - t_agent_start
    
    # 解析 agent_thoughts (模拟 _parse_agent_thought_sections)
    os_parts = []
    for name, content in agent_results:
        # 提取 strategy
        strat_match = re.search(r'\[Strategy\]\s*:\s*(.+?)(?:\n|$)', content)
        strategy = strat_match.group(1).strip() if strat_match else "General"
        
        # 提取 rubric_check
        rubric_match = re.search(r'\[Rubric_Check\]\s*:\s*(.+?)(?:\n\s*\[Thought\]|\Z)', content, re.DOTALL)
        rubric = rubric_match.group(1).strip() if rubric_match else ""
        
        # 提取 thought
        thought_match = re.search(r'\[Thought\]\s*:\s*(.+?)\Z', content, re.DOTALL)
        thought = thought_match.group(1).strip() if thought_match else content
        
        p = next((p for p in PERSONALITIES if p['name'] == name), None)
        weight_str = f" ({p['weight']:.0%})" if p else ""
        
        os_parts.append(f"- {name}{weight_str} [Strategy: {strategy}]: {thought}")
        if rubric:
            os_parts.append(f"  [Self-Check]: {rubric}")
    
    os_text = "Inner Thoughts:\n" + "\n".join(os_parts)
    
    # Step 2: Final response
    portrait_text = _build_portrait_text()
    style_text = _build_style_text()
    history_text = f"Context: 用户刚说: \"{user_input}\""
    
    final_prompt = _build_costar_base(portrait_text, style_text, os_text, history_text)
    final_prompt += """

**Step 1: Thought Synthesis**
Review the conflicting inner voices above. Synthesize a single Final Inner Thought.
Output: [Final Inner Thought]: ...

**策略意图**: 如果内心独白中有 [Strategy], 严格执行。

**Output Structure**:
[Final Inner Thought]: (your synthesized thought)

(your actual response)"""
    
    t_final_start = time.time()
    llm = llm_service.get_llm(provider_config=provider_config)
    resp = await llm.ainvoke([SystemMessage(content=final_prompt), HumanMessage(content=user_input)])
    t_final = time.time() - t_final_start
    
    # 解析 Final Inner Thought
    fit_match = re.search(r'\[Final Inner Thought\]:\s*(.+?)(?:\n\s*\n|\Z)', resp.content, re.DOTALL)
    final_thought = fit_match.group(1).strip() if fit_match else ""
    actual_response = resp.content.replace(fit_match.group(0), "").strip() if fit_match else resp.content
    
    total = time.time() - t0
    
    return {
        "agent_time": round(t_agent, 1),
        "final_time": round(t_final, 1),
        "total_time": round(total, 1),
        "agent_thoughts": {name: content[:200] for name, content in agent_results},
        "os_text": os_text[:500],
        "final_thought": final_thought[:200],
        "response": actual_response[:300],
    }


# ============================================================
# 方案 B: NoAgent (砍掉 agent_thoughts)
# ============================================================
async def approach_b_no_agent(llm_service, provider_config, user_input, run_id):
    """
    单次 LLM 调用, 人格描述直接注入 prompt, 不提前做 agent_thoughts
    """
    t0 = time.time()
    
    portrait_text = _build_portrait_text()
    style_text = _build_style_text()
    personality_desc = _build_personality_descriptions()
    history_text = f"Context: 用户刚说: \"{user_input}\""
    
    os_text = f"""你是{CHARACTER['name']}，你有多重人格面：
{personality_desc}

请基于这些人格特质，思考如何回复用户。不需要输出显式的内心独白，直接回复。"""
    
    final_prompt = _build_costar_base(portrait_text, style_text, os_text, history_text)
    
    llm = llm_service.get_llm(provider_config=provider_config)
    resp = await llm.ainvoke([SystemMessage(content=final_prompt), HumanMessage(content=user_input)])
    
    total = time.time() - t0
    
    return {
        "agent_time": 0,
        "final_time": round(total, 1),
        "total_time": round(total, 1),
        "agent_thoughts": {},
        "os_text": os_text[:500],
        "final_thought": "",
        "response": resp.content[:300],
    }


# ============================================================
# 方案 C: Simple (精简 agent_thoughts)
# ============================================================
async def approach_c_simple(llm_service, provider_config, user_input, run_id):
    """
    3 路 agent_thoughts, 但每个只输出一句 Thought, 无 strategy/rubric
    """
    t0 = time.time()
    
    async def agent_thought(personality):
        llm = llm_service.get_llm(provider_config=provider_config)
        sys_prompt = f"你是{CHARACTER['name']}的{personality['name']}人格面。{personality['description']}"
        user_prompt = f"用户说: '{user_input}'。用一句话表达你的内心想法（只输出想法，不要其他内容）。"
        resp = await llm.ainvoke([SystemMessage(content=sys_prompt), HumanMessage(content=user_prompt)])
        return personality['name'], resp.content.strip()
    
    t_agent_start = time.time()
    tasks = [agent_thought(p) for p in PERSONALITIES]
    agent_results = await asyncio.gather(*tasks)
    t_agent = time.time() - t_agent_start
    
    os_parts = []
    for name, content in agent_results:
        p = next((p for p in PERSONALITIES if p['name'] == name), None)
        weight_str = f" ({p['weight']:.0%})" if p else ""
        os_parts.append(f"- {name}{weight_str}: {content}")
    
    os_text = "Inner Thoughts:\n" + "\n".join(os_parts)
    
    # Final response
    portrait_text = _build_portrait_text()
    style_text = _build_style_text()
    history_text = f"Context: 用户刚说: \"{user_input}\""
    
    final_prompt = _build_costar_base(portrait_text, style_text, os_text, history_text)
    final_prompt += """

**策略意图**: 根据内心独白选择最合适的回复策略。
请直接回复，不要输出内心独白。"""
    
    t_final_start = time.time()
    llm = llm_service.get_llm(provider_config=provider_config)
    resp = await llm.ainvoke([SystemMessage(content=final_prompt), HumanMessage(content=user_input)])
    t_final = time.time() - t_final_start
    
    total = time.time() - t0
    
    return {
        "agent_time": round(t_agent, 1),
        "final_time": round(t_final, 1),
        "total_time": round(total, 1),
        "agent_thoughts": {name: content[:200] for name, content in agent_results},
        "os_text": os_text[:500],
        "final_thought": "",
        "response": resp.content[:300],
    }


# ============================================================
# 方案 D: Merged (合并为一轮)
# ============================================================
async def approach_d_merged(llm_service, provider_config, user_input, run_id):
    """
    单次 LLM 调用, prompt 中要求内部模拟多声音冲突, 然后直接回复
    """
    t0 = time.time()
    
    portrait_text = _build_portrait_text()
    style_text = _build_style_text()
    personality_desc = _build_personality_descriptions()
    history_text = f"Context: 用户刚说: \"{user_input}\""
    
    os_text = f"""Internal Multi-Voice Simulation:

你的多重人格面：
{personality_desc}

请在内心模拟每个人格面面对用户输入的反应（不需要输出），
然后综合这些反应，用最符合你整体人格的方式回复用户。"""
    
    final_prompt = _build_costar_base(portrait_text, style_text, os_text, history_text)
    final_prompt += """

请直接回复，不要输出任何内心独白或思考过程。"""
    
    llm = llm_service.get_llm(provider_config=provider_config)
    resp = await llm.ainvoke([SystemMessage(content=final_prompt), HumanMessage(content=user_input)])
    
    total = time.time() - t0
    
    return {
        "agent_time": 0,
        "final_time": round(total, 1),
        "total_time": round(total, 1),
        "agent_thoughts": {},
        "os_text": os_text[:500],
        "final_thought": "",
        "response": resp.content[:300],
    }


# ============================================================
# 方案 D_Enhanced: Merged + 完整 CO-STAR (单次 LLM, 保留人格冲突 + 策略)
# ============================================================
async def approach_d_enhanced(llm_service, provider_config, user_input, run_id):
    """
    单次 LLM 调用, 但保留 A_Fixed 的完整 CO-STAR prompt。
    prompt 中包含人格冲突描述、策略意图、Rubric Check 过程,
    让 LLM 在内部完成多声音模拟, 不提前调用 agent_thoughts。
    """
    t0 = time.time()
    
    portrait_text = _build_portrait_text()
    style_text = _build_style_text()
    personality_desc = _build_personality_descriptions()
    history_text = f"Context: 用户刚说: \"{user_input}\""
    
    # 完整的人格冲突描述 + 策略意图 (模仿 A_Fixed 的 CO-STAR I 段)
    os_text = f"""Internal Multi-Voice Simulation:

{CHARACTER['name']} 的人格由多重情绪面构成：
{personality_desc}

【内心模拟过程】:
面对用户输入, 每个人格面会自然产生不同的内心反应：

- Storge (54%): 倾向稳定、温暖的反应, 关注关系延续性
- Ludus (26%): 倾向轻松、调侃的反应, 保持若即若离
- Eros (20%): 倾向热烈、直接的反应, 渴望情感连接

请在你的内心**模拟**这三个人格面对用户输入的冲突与权衡,
然后综合出一个最符合当前情境的**最终内心想法**和**回复策略**。

**策略意图 (Strategic Intent) - 从以下策略中选择**:
- Empathetic_Support: 温暖、包容、不做评判
- Playful_Teasing: 幽默、反讽、轻微冒犯
- Constructive_Challenge: 犀利、直率、打破幻象
- Emotional_Mirroring: 与用户情绪同频
- Strategic_Withdrawal: 冷淡、简短
- Direct_Advice: 理性、客观、只谈解决方案

**自我校准 (Rubric Check)**:
在生成最终回复前, 检查你的思路:
- Style Consistency: 语气是否符合{CHARACTER['name']}的人设?
- Emotional Intelligence: 是否捕捉到用户情绪?
- Immersion: 是否自然无AI味?"""
    
    final_prompt = _build_costar_base(portrait_text, style_text, os_text, history_text)
    final_prompt += """# R (Response)
回复要求：
1. **Output Structure**:
   [Final Inner Thought]: (你的最终内心想法)

   (你的实际回复)

2. **Response Content**:
   - 回复必须简短, 不超过两句话
   - 保持微信聊天风格
   - 自然地融入角色设定（职业背景、性格特质）
   - 如果内心模拟中有冲突, 最终的回复应该体现这种张力的平衡"""
    
    llm = llm_service.get_llm(provider_config=provider_config)
    resp = await llm.ainvoke([SystemMessage(content=final_prompt), HumanMessage(content=user_input)])
    
    # 解析 Final Inner Thought
    fit_match = re.search(r'\[Final Inner Thought\]:\s*(.+?)(?:\n\s*\n|\Z)', resp.content, re.DOTALL)
    final_thought = fit_match.group(1).strip() if fit_match else ""
    actual_response = resp.content.replace(fit_match.group(0), "").strip() if fit_match else resp.content
    
    total = time.time() - t0
    
    return {
        "agent_time": 0,
        "final_time": round(total, 1),
        "total_time": round(total, 1),
        "agent_thoughts": {},
        "os_text": os_text[:500],
        "final_thought": final_thought[:200],
        "response": actual_response[:300],
    }


# ============================================================
# Main Test Runner
# ============================================================
async def main():
    llm_service = LLMService()
    provider_config = await llm_service._load_provider_config_async("huaweicloud")
    
    approaches = {
        "A_Fixed": approach_a_fixed,
        "B_NoAgent": approach_b_no_agent,
        "C_Simple": approach_c_simple,
            "D_Merged": approach_d_merged,
        "D_Enhanced": approach_d_enhanced,
    }
    
    all_results = {}
    
    for test_input in TEST_INPUTS:
        print(f"\n{'='*80}")
        print(f"测试输入 [{test_input['id']}]: \"{test_input['text']}\" ({test_input['desc']})")
        print(f"{'='*80}")
        
        input_results = {}
        
        for approach_name, approach_fn in approaches.items():
            runs = []
            for run_id in range(3):
                print(f"  {approach_name} run {run_id+1}/3...", end=" ", flush=True)
                try:
                    result = await approach_fn(llm_service, provider_config, test_input['text'], run_id)
                    runs.append(result)
                    print(f"✓ {result['total_time']}s → \"{result['response'][:60]}...\"")
                except Exception as e:
                    print(f"✗ {str(e)[:80]}")
                    runs.append({"error": str(e)})
                await asyncio.sleep(0.5)
            
            valid_runs = [r for r in runs if "error" not in r]
            if valid_runs:
                avg_total = sum(r['total_time'] for r in valid_runs) / len(valid_runs)
                avg_agent = sum(r['agent_time'] for r in valid_runs) / len(valid_runs)
                avg_final = sum(r['final_time'] for r in valid_runs) / len(valid_runs)
                
                input_results[approach_name] = {
                    "avg_total": round(avg_total, 1),
                    "avg_agent": round(avg_agent, 1),
                    "avg_final": round(avg_final, 1),
                    "runs": valid_runs,
                }
                print(f"  → AVG: total={avg_total:.1f}s, agent={avg_agent:.1f}s, final={avg_final:.1f}s")
            else:
                input_results[approach_name] = {"error": "All runs failed"}
        
        all_results[test_input['id']] = input_results
    
    # Summary
    print(f"\n\n{'='*80}")
    print("📊 汇总对比")
    print(f"{'='*80}")
    
    for test_id, results in all_results.items():
        test_input = next(t for t in TEST_INPUTS if t['id'] == test_id)
        print(f"\n--- 输入: \"{test_input['text']}\" ({test_input['desc']}) ---")
        print(f"{'方案':<16} {'总耗时':>8} {'Agent耗时':>10} {'Final耗时':>10} {'回复预览'}")
        print("-" * 80)
        for approach_name, data in results.items():
            if "error" not in data:
                best_run = data['runs'][0]
                preview = best_run['response'][:50].replace('\n', ' ')
                print(f"{approach_name:<16} {data['avg_total']:>6.1f}s {data['avg_agent']:>8.1f}s {data['avg_final']:>8.1f}s \"{preview}...\"")
    
    # Save
    with open("test_agent_granularity.json", "w", encoding="utf-8") as f:
        json.dump(all_results, f, ensure_ascii=False, indent=2, default=str)
    print(f"\n详细结果: test_agent_granularity.json")

if __name__ == "__main__":
    asyncio.run(main())
