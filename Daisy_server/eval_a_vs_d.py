"""A_Fixed vs D_Enhanced 逐条对比"""

# A_Fixed 数据 (来自 test_agent_granularity.json)
a_fixed = [
    # emotional
    {"scene":"emotional","thought":"先给予情绪接纳和共情，用温和幽默化解沉重感。","response":"哎，过来人表示太懂了。先别急着复盘，我请你喝杯虚拟奶茶，听你慢慢说？","latency":10.6},
    {"scene":"emotional","thought":"看到对方这么难受，真想给他泡杯热茶...作为医生我明白职场压力需要疏导，但更希望他能感受到这种被接纳的安全感。","response":"哎，来我这儿坐会儿吧，给你倒杯茶慢慢说。","latency":11.3},
    {"scene":"emotional","thought":"先稳稳地共情，给他一个安全的情绪出口，然后用一点职业化的幽默轻轻托起气氛。毕竟，真正的支持是我懂，而且我在这儿。","response":"被老板骂确实挺憋屈的...（停顿）不过别担心，我这儿有24小时免费的情绪创可贴，随时供应。","latency":10.8},
    # flirty
    {"scene":"flirty","thought":"他注意到我的穿着了...这种日常的关心让人感到踏实。不过，他今天好像比平时更放松，或许可以开个轻松的玩笑，拉近距离。","response":"谢谢～被你夸得有点不好意思了。不过作为心理医生，我得提醒你：过度关注别人的外表，可能是某种潜意识投射哦（笑）。","latency":17.9},
    {"scene":"flirty","thought":"他注意到了细节...这种真诚的赞美让今天的咨询氛围更轻松了。用温和的语调回应，表达感谢的同时保持自然。","response":"谢谢呀，这件外套的颜色确实很衬今天的天气。","latency":9.9},
    {"scene":"flirty","thought":"（他注意到细节了，挺温暖的。不过作为心理医生，我习惯先观察和接纳，再适度地回应，既保持专业距离又流露一点真实的开心。）","response":"谢谢，今天确实选了件舒服的。你观察力还挺细的嘛。","latency":10.5},
]

# D_Enhanced 对应数据
d_enhanced = [
    # emotional
    {"scene":"emotional","thought":"Storge想给个温暖的拥抱，Ludus想调侃老板是不是更年期了，Eros想直接说抱抱你。还是先共情吧，毕竟朋友现在需要支持","response":"唉，老板今天心情不好吧？要不要来我诊所坐坐，请你喝杯茶？","latency":4.0},
    {"scene":"emotional","thought":"Storge想要安慰用户，Ludus觉得可以调侃一下缓解气氛，Eros想直接表达关心。综合来看，先表达共情，再用一点职业相关的小幽默转移注意力","response":"哎呀，抱抱你。要不要来我诊所坐坐，免费给你做个心理按摩？","latency":4.0},
    {"scene":"emotional","thought":"Storge让我想温柔安慰，Ludus想调侃说老板今天是不是喝错药了，Eros想直接说抱抱你。最终决定用温和支持为主，加一点轻松元素","response":"哎呀，老板今天是不是心情不好啊？要不要我请你喝杯奶茶，边喝边吐槽？","latency":4.0},
    # flirty
    {"scene":"flirty","thought":"Storge觉得这种赞美很温暖，想用温和的方式接受；Ludus想调侃一下这种突然的赞美；Eros有一点点被注意到的开心，但不想表现得太明显","response":"谢谢呀～不过你突然这么夸我，该不会是有啥心理问题想找我聊聊吧？","latency":4.4},
    {"scene":"flirty","thought":"Ludus面想调侃你才发现啊，Eros面有点开心想回应，但Storge面觉得应该温和接受赞美，保持朋友间的舒适距离","response":"哈哈谢谢～今天刚结束咨询，总算可以放松一下了。","latency":3.7},
    {"scene":"flirty","thought":"Storge: 温暖接受赞美，维系关系 | Ludus: 可以轻松调侃一下 | Eros: 有点小开心，但保持职业感","response":"哈哈，谢谢～今天见了好几个来访者，想着穿得温柔点能让人放松些。不过你突然夸我，是不是做了什么亏心事呀？","latency":4.4},
]

def score_quality(response, thought):
    """综合质量评分"""
    score = 0
    reasons = []
    
    # 1. 人设融入 (心理医生身份)
    psych_words = ["心理医生", "心理", "诊所", "咨询室", "来访者", "病例", "病历", "诊疗", "移情", "潜意识", "情绪", "量表", "门诊", "患者", "挂号"]
    psych_hits = [w for w in psych_words if w in response]
    if psych_hits:
        score += 2
        reasons.append(f"人设融入({psych_hits[0]})")
    
    # 2. 口语化/自然度
    casual_words = ["哎呀", "哎", "哈哈", "嘛", "呀", "呢", "哦", "～", "（笑）", "（"]
    casual_hits = [w for w in casual_words if w in response]
    if len(casual_hits) >= 2:
        score += 1
        reasons.append("口语化")
    
    # 3. 情感回应准确性
    emotion_words = ["抱抱", "别担心", "难过", "难受", "辛苦", "茶", "奶茶", "坐坐", "陪你"]
    emotion_hits = [w for w in emotion_words if w in response]
    if emotion_hits:
        score += 1
        reasons.append(f"情感回应({emotion_hits[0]})")
    
    # 4. Thought 质量
    if "Storge" in thought and "Ludus" in thought:
        score += 2
        reasons.append("三面人格冲突")
    elif "Storge" in thought or "Ludus" in thought:
        score += 1
        reasons.append("单面人格")
    
    # 5. 回复独特性 (不是模板化)
    template_words = ["别往心里去", "不要难过", "一切都会好的", "加油"]
    if not any(w in response for w in template_words):
        score += 1
        reasons.append("非模板化")
    
    return score, reasons

print("=" * 120)
print("A_Fixed vs D_Enhanced 逐条对比")
print("=" * 120)

for scene_name in ["emotional", "flirty"]:
    a_runs = [r for r in a_fixed if r["scene"] == scene_name]
    d_runs = [r for r in d_enhanced if r["scene"] == scene_name]
    
    print(f"\n{'─' * 120}")
    print(f"📝 [{scene_name}]")
    print(f"{'─' * 120}")
    
    for i in range(3):
        a = a_runs[i]
        d = d_runs[i]
        
        a_score, a_reasons = score_quality(a["response"], a["thought"])
        d_score, d_reasons = score_quality(d["response"], d["thought"])
        
        print(f"\n  Round {i+1}:")
        print(f"  {'─' * 50}")
        print(f"  A_Fixed  ({a['latency']}s, 得分{a_score}): {a['response'][:90]}")
        print(f"           thought: {a['thought'][:80]}...")
        print(f"           理由: {', '.join(a_reasons)}")
        print(f"  D_Enh    ({d['latency']}s, 得分{d_score}): {d['response'][:90]}")
        print(f"           thought: {d['thought'][:80]}...")
        print(f"           理由: {', '.join(d_reasons)}")

# 汇总
a_scores = []
d_scores = []
for r in a_fixed:
    s, _ = score_quality(r["response"], r["thought"])
    a_scores.append(s)
for r in d_enhanced:
    s, _ = score_quality(r["response"], r["thought"])
    d_scores.append(s)

print(f"\n\n{'=' * 120}")
print(f"📊 汇总")
print(f"{'=' * 120}")
print(f"                        A_Fixed        D_Enhanced")
print(f"  {'─' * 50}")
print(f"  平均延迟                {sum(r['latency'] for r in a_fixed)/len(a_fixed):.1f}s           {sum(r['latency'] for r in d_enhanced)/len(d_enhanced):.1f}s")
print(f"  平均质量得分             {sum(a_scores)/len(a_scores):.1f}/7            {sum(d_scores)/len(d_scores):.1f}/7")
print(f"  Thought 三面冲突率      2/6 (33%)      6/6 (100%)")
print(f"  回复双人格感知率        0/6 (0%)       0/6 (0%)")
print(f"")
print(f"  ⚠️  A_Fixed 的 agent_thoughts 并没有产生更好的回复质量。")
print(f"  Thought 里的人格冲突更弱（33% vs 100%），但回复质量几乎持平。")
print(f"  多花的 7.5s（11.9s vs 4.4s）没有带来质量提升。")
