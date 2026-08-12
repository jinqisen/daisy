"""
MAAS API 响应基线测试
1. 测试不同输入/输出 token 量对延迟的影响
2. 测试优化 prompt 前后的速度对比
3. 建立 deepseek-v3.2 的响应基线
"""
import asyncio
import time
import json
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from dotenv import load_dotenv
load_dotenv(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env"))

from app.core.llm_config import llm_config_manager
from app.core.llm import LLMService
from app.core.config import settings
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
# Test 1: Token vs Latency Baseline
# ============================================================
async def test_token_latency():
    """测试不同 prompt 长度下的延迟"""
    print("=" * 80)
    print("Test 1: Token vs Latency 基线 (deepseek-v3.2 @ MAAS)")
    print("=" * 80)
    
    llm_service = LLMService()
    provider_config = await llm_service._load_provider_config_async("huaweicloud")
    llm = llm_service.get_llm(provider_config=provider_config)
    
    # 不同长度的 user prompt
    short_input = "你好，今天天气不错"
    medium_input = "我今天工作上遇到了一些麻烦，老板对我的方案不太满意，让我重新修改。我已经花了很多时间在这个项目上，感觉很沮丧。你能给我一些建议吗？"
    long_input = """我今天工作上遇到了一些麻烦，老板对我的方案不太满意，让我重新修改。我已经花了很多时间在这个项目上，感觉很沮丧。你能给我一些建议吗？

其实这个项目我已经做了两个月了，从需求分析到原型设计，再到现在的详细方案，每一步都付出了很多心血。但是老板今天突然说这个方向不对，要重新做市场调研，我感觉之前的努力都白费了。

而且团队里其他同事似乎也不太理解我的设计思路，我觉得自己很孤立。有时候我在想，是不是我自己的能力不够，不适合做这份工作。

你能帮我分析一下现在的情况吗？我应该怎么跟老板沟通？怎么调整自己的心态？"""
    
    # 不同输出长度要求
    outputs = [
        ("极短输出", "请用一句话回复（不超过20字）。"),
        ("短输出", "请用2-3句话回复（不超过60字）。"),
        ("中输出", "请用一段话回复（100-150字），给出具体建议。"),
        ("长输出", "请详细回复（200-300字），从多个角度分析并给出建议。"),
    ]
    
    results = []
    
    for input_name, user_input in [("短输入", short_input), ("中输入", medium_input), ("长输入", long_input)]:
        for output_name, output_instruction in outputs:
            prompt = f"{output_instruction}\n\n用户说：{user_input}"
            
            # 跑 3 次取平均
            latencies = []
            for run in range(3):
                start = time.time()
                input_tokens_est = 0
                output_tokens_est = 0
                output_chars = 0
                try:
                    response = await llm.ainvoke([
                        SystemMessage(content="你是一个友好的助手。"),
                        HumanMessage(content=prompt)
                    ])
                    elapsed = time.time() - start
                    latencies.append(elapsed)
                    content = response.content
                    # 估算 token
                    input_chars = len(prompt) + 30  # +system
                    output_chars = len(content)
                    input_tokens_est = int(input_chars * 0.6)  # 中文 ~0.6 token/char
                    output_tokens_est = int(output_chars * 0.6)
                except Exception as e:
                    latencies.append(None)
                    input_tokens_est = 0
                    output_tokens_est = 0
                    print(f"  ❌ {input_name}/{output_name} run{run+1}: {str(e)[:80]}")
                
                await asyncio.sleep(0.5)
            
            valid = [l for l in latencies if l is not None]
            avg_lat = sum(valid) / len(valid) if valid else 0
            min_lat = min(valid) if valid else 0
            max_lat = max(valid) if valid else 0
            
            results.append({
                "input": input_name,
                "output": output_name,
                "input_chars": len(prompt) + 30,
                "output_chars": output_chars,
                "input_tokens_est": input_tokens_est,
                "output_tokens_est": output_tokens_est,
                "avg_latency": avg_lat,
                "min_latency": min_lat,
                "max_latency": max_lat,
                "runs": len(valid),
            })
            
            print(f"  {input_name}/{output_name}: avg={avg_lat:.1f}s, "
                  f"in~{input_tokens_est}tk, out~{output_tokens_est}tk, "
                  f"({min_lat:.1f}-{max_lat:.1f}s, {len(valid)}/3 runs)")
    
    return results


# ============================================================
# Test 2: Prompt Optimization (精简 vs 原文)
# ============================================================
async def test_prompt_optimization():
    """测试精简 prompt 是否提升速度"""
    print("\n" + "=" * 80)
    print("Test 2: Prompt 优化对比 (精简 vs 原始)")
    print("=" * 80)
    
    llm_service = LLMService()
    provider_config = await llm_service._load_provider_config_async("huaweicloud")
    llm = llm_service.get_llm(provider_config=provider_config)
    
    user_input = "我今天好难过，工作上的事让我很沮丧"
    
    # 原始风格（类似 Daisy 当前 prompt 风格）
    verbose_system = """你是一个名为 Daisy 的 AI 角色。你需要根据以下设定来扮演这个角色。

## 角色设定
- 姓名：静雯
- 性别：女
- 年龄：24岁
- 职业：独立插画师
- 与用户关系：暧昧期的朋友
- 性格：温柔体贴，但有自己的小脾气，偶尔会撒娇

## 语言风格指导
- 口语化，像真人聊天一样
- 可以适当使用语气词（呢、吧、哦、嘛）
- 不要过于正式，保持轻松自然的聊天氛围
- 回复要简短，通常不超过两句话

## 行为指导
- 当用户难过时要给予温暖的安慰
- 保持适当的暧昧感，但不要过于直白
- 可以用自己的经历来共情

## 情感基调
- 当前处于温暖、关心的状态
- 用温柔的语气回应"""

    concise_system = """你是静雯，24岁独立插画师，和用户是暧昧期的朋友。回复要口语化、简短（≤2句）、温柔。当前：用户难过，你需要温暖安慰。"""

    results = []
    
    for name, system_prompt in [("原始长prompt", verbose_system), ("精简prompt", concise_system)]:
        latencies = []
        output_lens = []
        for run in range(5):
            start = time.time()
            try:
                response = await llm.ainvoke([
                    SystemMessage(content=system_prompt),
                    HumanMessage(content=user_input)
                ])
                elapsed = time.time() - start
                latencies.append(elapsed)
                output_lens.append(len(response.content))
            except Exception as e:
                latencies.append(None)
                print(f"  ❌ {name} run{run+1}: {e[:80]}")
            
            await asyncio.sleep(0.3)
        
        valid = [l for l in latencies if l is not None]
        avg_lat = sum(valid) / len(valid) if valid else 0
        avg_out = sum(output_lens) / len(output_lens) if output_lens else 0
        
        sys_len = len(system_prompt)
        sys_tokens = int(sys_len * 0.6)
        
        results.append({
            "name": name,
            "system_chars": sys_len,
            "system_tokens_est": sys_tokens,
            "avg_latency": avg_lat,
            "min_latency": min(valid) if valid else 0,
            "max_latency": max(valid) if valid else 0,
            "avg_output_chars": avg_out,
            "runs": len(valid),
        })
        
        print(f"  {name}: avg={avg_lat:.1f}s, sys~{sys_tokens}tk, "
              f"out~{int(avg_out*0.6)}tk ({min(valid) if valid else 0:.1f}-{max(valid) if valid else 0:.1f}s)")
    
    return results


# ============================================================
# Test 3: 并发 vs 串行
# ============================================================
async def test_concurrent_vs_serial():
    """测试并发调用 vs 串行调用的延迟"""
    print("\n" + "=" * 80)
    print("Test 3: 并发 vs 串行 (模拟 multi_agent 3 路)")
    print("=" * 80)
    
    llm_service = LLMService()
    provider_config = await llm_service._load_provider_config_async("huaweicloud")
    
    prompts = [
        ("Eros", "你是Eros，热情浪漫。用户说：早啊，今天心情不错。请用一句话表达你的内心想法。"),
        ("Ludus", "你是Ludus，幽默玩世不恭。用户说：早啊，今天心情不错。请用一句话表达你的内心想法。"),
        ("Storge", "你是Storge，温和可靠。用户说：早啊，今天心情不错。请用一句话表达你的内心想法。"),
    ]
    
    # 串行
    print("--- 串行 (3 calls sequentially) ---")
    serial_start = time.time()
    for name, prompt in prompts:
        llm = llm_service.get_llm(provider_config=provider_config)
        t0 = time.time()
        await llm.ainvoke([
            SystemMessage(content="用一句话回复。"),
            HumanMessage(content=prompt)
        ])
        print(f"  {name}: {time.time()-t0:.1f}s")
    serial_total = time.time() - serial_start
    print(f"  串行总耗时: {serial_total:.1f}s")
    
    await asyncio.sleep(1)
    
    # 并发
    print("--- 并发 (3 calls concurrently) ---")
    async def single_call(name, prompt):
        llm = llm_service.get_llm(provider_config=provider_config)
        t0 = time.time()
        await llm.ainvoke([
            SystemMessage(content="用一句话回复。"),
            HumanMessage(content=prompt)
        ])
        elapsed = time.time() - t0
        print(f"  {name}: {elapsed:.1f}s")
        return elapsed
    
    concurrent_start = time.time()
    tasks = [single_call(name, prompt) for name, prompt in prompts]
    latencies = await asyncio.gather(*tasks)
    concurrent_total = time.time() - concurrent_start
    print(f"  并发总耗时: {concurrent_total:.1f}s (max single: {max(latencies):.1f}s)")
    
    return {
        "serial_total": serial_total,
        "concurrent_total": concurrent_total,
        "concurrent_max_single": max(latencies),
        "speedup": serial_total / concurrent_total if concurrent_total > 0 else 0,
    }


# ============================================================
# Test 4: system prompt 长度对延迟的影响
# ============================================================
async def test_system_prompt_length():
    """测试 system prompt 长度对延迟的精确影响"""
    print("\n" + "=" * 80)
    print("Test 4: System Prompt 长度 vs 延迟")
    print("=" * 80)
    
    llm_service = LLMService()
    provider_config = await llm_service._load_provider_config_async("huaweicloud")
    llm = llm_service.get_llm(provider_config=provider_config)
    
    user_input = "今天心情不错"
    
    # 不同长度的 system prompt
    base = "你是静雯，温柔体贴。"
    fill = "你是一个很好的倾听者，善于理解他人的感受。"
    
    prompts = [
        ("极简 (20字)", base),
        ("短 (80字)", base + fill),
        ("中 (200字)", base + fill * 3),
        ("长 (500字)", base + fill * 10),
        ("超长 (1000字)", base + fill * 20),
    ]
    
    results = []
    for name, sys_prompt in prompts:
        latencies = []
        for run in range(3):
            start = time.time()
            try:
                response = await llm.ainvoke([
                    SystemMessage(content=sys_prompt),
                    HumanMessage(content=user_input)
                ])
                latencies.append(time.time() - start)
            except Exception as e:
                latencies.append(None)
            await asyncio.sleep(0.3)
        
        valid = [l for l in latencies if l is not None]
        avg = sum(valid) / len(valid) if valid else 0
        sys_tokens = int(len(sys_prompt) * 0.6)
        total_tokens = sys_tokens + int(len(user_input) * 0.6) + 30  # ~30 output
        
        results.append({
            "name": name,
            "sys_chars": len(sys_prompt),
            "sys_tokens_est": sys_tokens,
            "total_tokens_est": total_tokens,
            "avg_latency": avg,
            "latencies": valid,
        })
        print(f"  {name}: sys~{sys_tokens}tk, avg={avg:.1f}s ({valid[0]:.1f}, {valid[1]:.1f}, {valid[2]:.1f})")
    
    return results


# ============================================================
# Main
# ============================================================
async def main():
    all_results = {}
    
    # Test 1
    t1 = await test_token_latency()
    all_results["token_latency"] = t1
    
    # Test 2
    t2 = await test_prompt_optimization()
    all_results["prompt_optimization"] = t2
    
    # Test 3
    t3 = await test_concurrent_vs_serial()
    all_results["concurrent_vs_serial"] = t3
    
    # Test 4
    t4 = await test_system_prompt_length()
    all_results["system_prompt_length"] = t4
    
    # Summary
    print("\n\n" + "=" * 80)
    print("📊 汇总报告")
    print("=" * 80)
    
    print("\n--- Token vs Latency ---")
    print(f"{'场景':<16} {'avg':>6} {'in_tk':>6} {'out_tk':>6}")
    print("-" * 36)
    for r in t1:
        if r["runs"] >= 2:
            print(f"{r['input']+'/'+r['output']:<16} {r['avg_latency']:>5.1f}s {r['input_tokens_est']:>5} {r['output_tokens_est']:>5}")
    
    print("\n--- Prompt 优化 ---")
    for r in t2:
        print(f"  {r['name']}: avg={r['avg_latency']:.1f}s, sys_tk={r['system_tokens_est']}")
    
    print("\n--- 并发 vs 串行 ---")
    print(f"  串行: {t3['serial_total']:.1f}s, 并发: {t3['concurrent_total']:.1f}s, 加速比: {t3['speedup']:.1f}x")
    
    print("\n--- System Prompt 长度 ---")
    for r in t4:
        print(f"  {r['name']}: sys={r['sys_tokens_est']}tk, avg={r['avg_latency']:.1f}s")
    
    with open("test_maas_baseline.json", "w", encoding="utf-8") as f:
        json.dump(all_results, f, ensure_ascii=False, indent=2, default=str)
    print("\n详细结果: test_maas_baseline.json")

if __name__ == "__main__":
    asyncio.run(main())
