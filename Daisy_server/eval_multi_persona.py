"""
全方案评估：多人格体现 + 策略执行

评估维度：
1. 多人格体现：回复中能否感知到 Storge/Ludus/Eros 的冲突与权衡？
2. 策略执行：Final Inner Thought 中声明的策略是否在回复中真正落地？
3. Thought 质量：Final Inner Thought 本身是否展示了真实的人格冲突？

评估方法：基于关键词标记 + 人工判断（因为回复是自然语言，不是结构化数据）
"""
import json, re, sys

# 从 JSON 加载结果
with open("test_agent_granularity.json", "r") as f:
    data = json.load(f)

# 人格标记词
STORGE_MARKERS = ["温暖", "关心", "支持", "稳定", "陪伴", "温和", "认真", "务实", "问", "聊聊", "听你说", "我在这", "陪"]
LUDUS_MARKERS  = ["调侃", "笑", "幽默", "玩笑", "开玩笑", "轻松", "😄", "😅", "😏", "糊弄", "挂号费", "偷", "猜", "考验"]
EROS_MARKERS   = ["抱抱", "开心", "直接", "热烈", "感动", "想", "喜欢", "爱", "💕"]

# 策略信号词
STRATEGY_SIGNALS = {
    "Empathetic_Support":       ["温暖", "包容", "不评判", "抱抱", "理解", "支持", "陪你", "我在", "别难过", "辛苦了"],
    "Playful_Teasing":          ["调侃", "笑", "玩笑", "偷", "😄", "😅", "😏", "糊弄", "挂号费", "考验", "猜"],
    "Constructive_Challenge":   ["移情", "提醒", "底线", "不适合", "不能", "不行", "注意", "但是"],
    "Emotional_Mirroring":      ["开心", "恭喜", "替你", "太棒", "真好", "庆祝", "一起"],
    "Strategic_Withdrawal":     ["嗯", "哦", "好吧", "先忙", "再说"],
    "Direct_Advice":            ["建议", "应该", "可以试试", "不妨", "最好"],
}

def score_personas(response_text):
    """返回 (storge_score, ludus_score, eros_score)"""
    s = sum(1 for m in STORGE_MARKERS if m in response_text)
    l = sum(1 for m in LUDUS_MARKERS if m in response_text)
    e = sum(1 for m in EROS_MARKERS if m in response_text)
    return s, l, e

def check_strategy(response_text, thought_text):
    """检查策略是否在回复中执行"""
    # 从 thought 中提取策略
    strategy = "Unknown"
    for strat_name in STRATEGY_SIGNALS:
        if strat_name.lower() in thought_text.lower().replace("_", " "):
            strategy = strat_name
            break
    # 如果 thought 里没找到，尝试从 response 推断
    if strategy == "Unknown":
        for strat_name, signals in STRATEGY_SIGNALS.items():
            if any(sig in response_text for sig in signals):
                strategy = strat_name
                break
    
    # 检查策略是否执行
    signals = STRATEGY_SIGNALS.get(strategy, [])
    executed = any(sig in response_text for sig in signals)
    
    return strategy, executed

def analyze_thought_quality(thought_text):
    """分析 thought 是否展示了真实的人格冲突"""
    if not thought_text:
        return "no_thought"
    
    has_storge = any(w in thought_text for w in ["Storge", "storge", "稳定", "温暖"])
    has_ludus = any(w in thought_text for w in ["Ludus", "ludus", "轻松", "调侃", "幽默", "玩笑"])
    has_eros = any(w in thought_text for w in ["Eros", "eros", "热烈", "直接", "热情"])
    has_conflict = any(w in thought_text for w in ["冲突", "权衡", "平衡", "综合", "还是", "但", "不过", "最终"])
    
    if has_storge and has_ludus and has_eros and has_conflict:
        return "explicit_3way_conflict"
    elif (has_storge or has_ludus) and has_conflict:
        return "partial_conflict"
    elif has_storge or has_ludus or has_eros:
        return "single_persona"
    else:
        return "no_persona"


print("=" * 100)
print("全方案评估：多人格体现 + 策略执行 + Thought 质量")
print("=" * 100)

for test_id, approaches in data.items():
    print(f"\n{'─' * 100}")
    print(f"📝 输入: {test_id}")
    print(f"{'─' * 100}")
    
    for approach_name, approach_data in approaches.items():
        if "error" in approach_data:
            continue
        
        runs = approach_data.get("runs", [])
        if not runs:
            continue
        
        print(f"\n  🔹 {approach_name} ({approach_data['avg_total']}s avg)")
        
        for i, run in enumerate(runs):
            response = run.get("response", "")
            thought = run.get("final_thought", "")
            
            s, l, e = score_personas(response)
            strategy, executed = check_strategy(response, thought)
            thought_quality = analyze_thought_quality(thought)
            
            # 多人格评级
            if s > 0 and l > 0:
                multi_grade = "✓✓ 双人格感知"
            elif s > 0 or l > 0:
                multi_grade = "✓  单人格主导"
            else:
                multi_grade = "✗  无人格感知"
            
            # 策略评级
            if executed and strategy != "Unknown":
                strat_grade = f"✓  {strategy}"
            elif strategy != "Unknown":
                strat_grade = f"△  {strategy}(未执行)"
            else:
                strat_grade = "✗  无策略"
            
            # Thought 评级
            tq_map = {
                "explicit_3way_conflict": "✓✓ 三面冲突",
                "partial_conflict": "✓  部分冲突",
                "single_persona": "△  单面思考",
                "no_persona": "✗  无人格思考",
                "no_thought": "—  无Thought",
            }
            thought_grade = tq_map.get(thought_quality, "?")
            
            resp_preview = response[:60].replace('\n', ' ')
            thought_preview = thought[:60].replace('\n', ' ') if thought else "(无)"
            
            print(f"    run{i+1}: {multi_grade} | {strat_grade} | thought:{thought_grade}")
            print(f"           回复: {resp_preview}...")
            print(f"           thought: {thought_preview}...")

# 汇总
print(f"\n\n{'=' * 100}")
print("📊 汇总统计")
print(f"{'=' * 100}")

for test_id, approaches in data.items():
    print(f"\n--- {test_id} ---")
    print(f"{'方案':<16} {'延迟':>6} {'双人格率':>8} {'策略执行率':>10} {'Thought冲突率':>12}")
    print("-" * 60)
    
    for approach_name, approach_data in approaches.items():
        if "error" in approach_data:
            continue
        runs = approach_data.get("runs", [])
        if not runs:
            continue
        
        multi_ok = 0
        strat_ok = 0
        thought_ok = 0
        total = len(runs)
        
        for run in runs:
            response = run.get("response", "")
            thought = run.get("final_thought", "")
            s, l, e = score_personas(response)
            _, executed = check_strategy(response, thought)
            tq = analyze_thought_quality(thought)
            
            if s > 0 and l > 0:
                multi_ok += 1
            if executed:
                strat_ok += 1
            if tq in ("explicit_3way_conflict", "partial_conflict"):
                thought_ok += 1
        
        avg_lat = approach_data['avg_total']
        print(f"{approach_name:<16} {avg_lat:>4.1f}s {multi_ok}/{total} {strat_ok}/{total} {thought_ok}/{total}")
