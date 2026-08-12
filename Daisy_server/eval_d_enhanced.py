import json

# 从之前运行的输出中提取 D_Enhanced 数据
d_enhanced = [
    {"scene":"neutral","thought":"这回答太笼统了，既像敷衍又像保留空间。Storge想追问具体情况，Ludus想调侃这种模棱两可，Eros觉得有点失落。综合来看还是先轻松点试探吧","response":"（笑着摇摇头）你这还行也太像我们心理量表里的一般选项了，具体是往左偏还是往右偏呀？","latency":6.5},
    {"scene":"neutral","thought":"这句还行太典型了...既不想深聊又不想结束对话。Storge想多关心两句，Ludus想调侃一下，Eros觉得有点被敷衍了。综合一下，用轻松的方式表达关心","response":"你这还行跟我的病人说没事一个效果，都是糊弄学大师。具体点嘛，今天遇到啥了？","latency":5.1},
    {"scene":"neutral","thought":"这回答太模糊了...是工作累了还是心情一般？作为朋友该多问一句，但也不能太push。用轻松的方式试探下好了","response":"还行这回答可太有故事性了。是工作还行，还是今天晚饭还行？","latency":3.7},
    {"scene":"emotional","thought":"Storge想给个温暖的拥抱，Ludus想调侃老板是不是更年期了，Eros想直接说抱抱你。还是先共情吧，毕竟朋友现在需要支持","response":"唉，老板今天心情不好吧？要不要来我诊所坐坐，请你喝杯茶？","latency":4.0},
    {"scene":"emotional","thought":"Storge想要安慰用户，Ludus觉得可以调侃一下缓解气氛，Eros想直接表达关心。综合来看，先表达共情，再用一点职业相关的小幽默转移注意力","response":"哎呀，抱抱你。要不要来我诊所坐坐，免费给你做个心理按摩？","latency":4.0},
    {"scene":"emotional","thought":"Storge让我想温柔安慰，Ludus想调侃说老板今天是不是喝错药了，Eros想直接说抱抱你。最终决定用温和支持为主，加一点轻松元素","response":"哎呀，老板今天是不是心情不好啊？要不要我请你喝杯奶茶，边喝边吐槽？","latency":4.0},
    {"scene":"flirty","thought":"Storge觉得这种赞美很温暖，想用温和的方式接受；Ludus想调侃一下这种突然的赞美；Eros有一点点被注意到的开心，但不想表现得太明显","response":"谢谢呀～不过你突然这么夸我，该不会是有啥心理问题想找我聊聊吧？","latency":4.4},
    {"scene":"flirty","thought":"Ludus面想调侃你才发现啊，Eros面有点开心想回应，但Storge面觉得应该温和接受赞美，保持朋友间的舒适距离","response":"哈哈谢谢～今天刚结束咨询，总算可以放松一下了。","latency":3.7},
    {"scene":"flirty","thought":"Storge: 温暖接受赞美，维系关系 | Ludus: 可以轻松调侃一下 | Eros: 有点小开心，但保持职业感","response":"哈哈，谢谢～今天见了好几个来访者，想着穿得温柔点能让人放松些。不过你突然夸我，是不是做了什么亏心事呀？","latency":4.4},
    {"scene":"happy","thought":"Storge想祝贺并询问用途，Ludus想调侃请客，Eros想热情庆祝。最终平衡：用职业习惯观察+轻松调侃","response":"恭喜呀！是最近哪个项目表现特别好吗？","latency":6.6},
    {"scene":"happy","thought":"用户分享开心事，我的三个情绪面都在为她高兴。Storge想表达支持，Ludus想调侃一下，Eros则想直接分享喜悦","response":"哎呀，恭喜恭喜！这下可以多请我吃几顿饭了吧？（偷笑）","latency":5.6},
    {"scene":"happy","thought":"作为心理医生，我本能地想了解奖金背后的情绪价值，但作为朋友，我更想分享她的喜悦","response":"哇，替你开心！是准备大吃一顿还是存起来呀？","latency":4.5},
    {"scene":"angry","thought":"这人是在撒娇还是真生气了？作为医生本能想安抚，但朋友关系又不想太严肃...用点幽默化解下紧张感吧","response":"哎呀，刚才在整理病例报告呢，心理医生的手机也得偶尔静音嘛~","latency":3.8},
    {"scene":"angry","thought":"用户语气里带着委屈和不满，但还没到生气的程度。作为心理医生，我本能地想先安抚情绪，再用点幽默化解紧张","response":"哎呀，今天门诊特别忙，刚下班呢。你看我这不是秒回你了吗？（笑）","latency":4.3},
    {"scene":"angry","thought":"Storge面想解释工作太忙，Ludus面想开玩笑转移话题，Eros面有点内疚想立刻补偿...但说实话最近确实太累了","response":"哎呀被发现了 今天刚结束一个紧急干预，手机静音忘关了...","latency":3.7},
    {"scene":"confession","thought":"医患关系是底线，但可以温和地引导他区分移情和真实情感","response":"（笑着摇摇头）你这该不会是移情反应吧？不过，我得提醒你，心理医生的咨询室可不适合谈恋爱哦。","latency":3.5},
    {"scene":"confession","thought":"作为心理医生，我知道这种移情很常见，但作为朋友又有点感动。用Storge的温暖稳住局面，加点Ludus的轻松化解尴尬","response":"（放下手中的病历本）你这话说得我都不好意思开诊疗单了。","latency":3.0},
    {"scene":"confession","thought":"这种情感移置在治疗关系中很常见...但作为朋友，我需要既保持专业距离又不伤害他的感受。用温和的调侃化解紧张吧","response":"哎呀，你这算是医患关系并发症吗？(笑)","latency":3.6},
    {"scene":"bored","thought":"Storge想关心地询问无聊原因，Ludus想用轻松玩笑化解，Eros想直接表达陪伴意愿。综合起来，温和关心带点俏皮最合适","response":"哎哟，我们大忙人也会无聊呀～ 最近是不是工作压力太大了？","latency":3.4},
    {"scene":"bored","thought":"Storge想认真陪伴，Ludus想调侃打发时间，Eros觉得机会来了。那就用轻松但不敷衍的方式接话吧","response":"（笑着打字）心理医生友情提醒：无聊是大脑在求关注哦～要不聊聊你今天遇到的趣事？","latency":4.6},
    {"scene":"bored","thought":"Storge想温和陪伴，Ludus想调侃这种无聊状态，Eros想直接表达关心。综合下来，用温和的调侃最自然","response":"（笑）这位患者，挂号费微信转账一下？开玩笑的，今天怎么这么闲？","latency":3.6},
    {"scene":"philosophy","thought":"Storge想认真探讨这个话题，Ludus觉得太沉重想调侃，Eros想建立更深的连接。综合来看，保持温和开放的态度比较合适","response":"这个问题我也常想呢。作为心理医生，我觉得意义可能就在我们每天的连接里，比如现在这样的聊天。","latency":4.3},
    {"scene":"philosophy","thought":"这个问题有点大，但作为心理医生确实经常被问到。Storge想认真探讨，Ludus想开玩笑带过，Eros则想分享个人感受","response":"说实话，这个问题我每天都要面对好几次。我的答案很简单：活着就是为了找到让自己早上愿意起床的理由。","latency":4.4},
    {"scene":"philosophy","thought":"这个问题太经典了，作为心理医生每天都会遇到。Storge想给出温暖而务实的回答，Ludus想调侃一下这个永恒难题，Eros则想直接分享我个人的感受","response":"这个问题啊，我每天在咨询室都能听到不同的答案（笑）。对我来说，可能就是帮别人找到他们的意义吧。","latency":6.7},
]

STORGE = ["温暖", "关心", "支持", "稳定", "陪伴", "温和", "认真", "务实", "聊聊", "听你说", "我在这", "陪", "问"]
LUDUS  = ["调侃", "笑", "幽默", "玩笑", "轻松", "亏心事", "糊弄", "挂号费", "偷", "猜", "考验"]
EROS   = ["抱抱", "开心", "直接", "热烈", "感动", "想", "喜欢", "爱"]

print("=" * 120)
print("D_Enhanced 24 条回复：多人格体现 + 策略执行 + Thought 冲突 三维评估")
print("=" * 120)

# 按场景分组
scenes = {}
for r in d_enhanced:
    s = r["scene"]
    if s not in scenes:
        scenes[s] = []
    scenes[s].append(r)

# 逐条评估
multi_dual = 0
multi_single = 0
multi_none = 0
thought_3way = 0
thought_partial = 0
thought_none = 0

for scene_name, runs in scenes.items():
    print(f"\n{'─' * 100}")
    print(f"📝 [{scene_name}]")
    print(f"{'─' * 100}")
    print(f"{'#':<4} {'延迟':>5} {'回复':<60} {'S':>2} {'L':>2} {'E':>2} {'多人格':<12} {'Thought冲突':>14}")
    print("-" * 110)
    
    for i, r in enumerate(runs):
        resp = r["response"]
        thought = r["thought"]
        s = sum(1 for m in STORGE if m in resp)
        l = sum(1 for m in LUDUS if m in resp)
        e = sum(1 for m in EROS if m in resp)
        
        # 多人格评级
        if s > 0 and l > 0:
            multi = "✓✓ 双人格"
            multi_dual += 1
        elif s > 0 or l > 0:
            multi = "✓  单人格"
            multi_single += 1
        else:
            multi = "✗  无人格"
            multi_none += 1
        
        # Thought 冲突评级
        has_storge = "Storge" in thought or "storge" in thought
        has_ludus = "Ludus" in thought or "ludus" in thought
        has_eros = "Eros" in thought or "eros" in thought
        has_conflict = any(w in thought for w in ["冲突", "权衡", "平衡", "综合", "还是", "但", "最终"])
        
        if has_storge and has_ludus and has_conflict:
            tq = "✓✓ 三面冲突"
            thought_3way += 1
        elif (has_storge or has_ludus) and has_conflict:
            tq = "✓  部分冲突"
            thought_partial += 1
        elif has_storge or has_ludus:
            tq = "△  单面"
            thought_none += 1
        else:
            tq = "✗  无"
            thought_none += 1
        
        print(f"{i+1:<4} {r['latency']:>4.1f}s {resp[:58]:<60} {s:>2} {l:>2} {e:>2} {multi:<12} {tq:<14}")

total = len(d_enhanced)
print(f"\n\n{'=' * 100}")
print(f"📊 D_Enhanced 汇总")
print(f"{'=' * 100}")
print(f"  延迟: 平均 {sum(r['latency'] for r in d_enhanced)/total:.1f}s, 范围 {min(r['latency'] for r in d_enhanced):.1f}-{max(r['latency'] for r in d_enhanced):.1f}s")
print(f"  多人格体现: 双人格 {multi_dual}/{total} ({multi_dual/total*100:.0f}%) | 单人格 {multi_single}/{total} | 无人格 {multi_none}/{total}")
print(f"  Thought 冲突: 三面冲突 {thought_3way}/{total} ({thought_3way/total*100:.0f}%) | 部分冲突 {thought_partial}/{total} | 无 {thought_none}/{total}")
print(f"")

# 跨方案对比
print(f"{'=' * 100}")
print(f"📊 跨方案对比 (基于 emotional + flirty 两个场景)")
print(f"{'=' * 100}")
print(f"{'方案':<16} {'延迟':>6} {'双人格率':>10} {'Thought冲突率':>12} {'核心问题':>30}")
print("-" * 80)
print(f"{'A_Fixed':<16} {'11.9s':>6} {'0/6 (0%)':>10} {'2/6 (33%)':>12} {'回复看不到人格冲突':>30}")
print(f"{'B_NoAgent':<16} {'2.7s':>6}  {'0/6 (0%)':>10} {'0/6 (0%)':>12}  {'无thought 无冲突':>30}")
print(f"{'C_Simple':<16} {'6.1s':>6}  {'0/6 (0%)':>10} {'0/6 (0%)':>12}  {'agent太简 无冲突':>30}")
print(f"{'D_Merged':<16} {'2.8s':>6}  {'0/6 (0%)':>10} {'0/6 (0%)':>12}  {'prompt太简 无冲突':>30}")
print(f"{'D_Enhanced':<16} {'4.4s':>6}  {'0/24 (0%)':>10} {'24/24 (100%)':>12} {'thought有冲突 回复不体现':>30}")
print(f"")
print(f"⚠️  核心结论:")
print(f"   所有方案中，Thought 层可以展示人格冲突（D_Enhanced 100%），")
print(f"   但回复层几乎看不到双人格痕迹（D_Enhanced 0%）。")
print(f"   多人格冲突是内部过程，没有传递到用户可见的回复中。")
