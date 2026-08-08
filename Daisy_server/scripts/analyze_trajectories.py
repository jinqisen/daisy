#!/usr/bin/env python3
"""
轨迹评估脚本(深改点 #6-full 首切片,书 ch19「trajectory evaluation」)。

只读消费已持久化的 workflow_traces 表(chat_history.persist_workflow_trace 写入),
不触碰主链路。输出:

  1. 路由分布           —— 每次执行走了哪条路(FAST/STANDARD/DEEP)
  2. 执行完成率         —— 到达 save 的比例;DEEP 中 generate 缺失(跳过/失败)的比例
  3. 端到端耗时         —— 每次执行首末节点时间差的分布(秒级粒度)
  4. 补丁注入命中率     —— DEEP 生成上下文中包含 Reflexion patches 的比例
  5. 工具使用率         —— tool_check 实际产出 tool_results 的比例

用法:
  python3 scripts/analyze_trajectories.py [--db sqlite.db] [--days N]
"""

import argparse
import json
import sqlite3
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path

DEFAULT_DB = Path(__file__).resolve().parent.parent / "sqlite.db"


def parse_ts(value: str):
    """trace 时间戳是 HH:MM:SS 字符串;解析失败返回 None。"""
    if not value:
        return None
    try:
        return datetime.strptime(value.strip(), "%H:%M:%S")
    except ValueError:
        return None


def load_rows(db_path: str, days: int | None):
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    sql = "SELECT execution_id, node_id, input_data, output_data, timestamp FROM workflow_traces WHERE execution_id IS NOT NULL"
    rows = conn.execute(sql).fetchall()
    conn.close()
    return rows


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--db", default=str(DEFAULT_DB))
    parser.add_argument("--days", type=int, default=None, help="预留:按天过滤(当前 trace 时间戳无日期,忽略)")
    args = parser.parse_args()

    rows = load_rows(args.db, args.days)
    if not rows:
        print("workflow_traces 表无数据")
        return

    executions: dict[str, list] = defaultdict(list)
    for r in rows:
        executions[r["execution_id"]].append(r)

    route_counter = Counter()
    completed = 0
    deep_total = 0
    deep_generate_missing = 0
    durations = []
    patch_hits = 0
    patch_checked = 0
    tool_used = 0
    tool_checked = 0

    for exec_id, nodes in executions.items():
        node_ids = {n["node_id"] for n in nodes}

        # 1. 路由判定:按实际走过的节点回推
        if "fast_generate" in node_ids:
            route = "FAST"
        elif "standard_generate" in node_ids:
            route = "STANDARD"
        elif "analyze" in node_ids:
            route = "DEEP"
        else:
            route = "UNKNOWN"
        route_counter[route] += 1

        # 2. 完成率
        if "save" in node_ids:
            completed += 1
        if route == "DEEP":
            deep_total += 1
            if "generate" not in node_ids:
                deep_generate_missing += 1

        # 3. 端到端耗时(秒级,同一天内;跨天/异常样本丢弃)
        stamps = [parse_ts(n["timestamp"]) for n in nodes]
        stamps = [s for s in stamps if s is not None]
        if len(stamps) >= 2:
            span = (max(stamps) - min(stamps)).total_seconds()
            if 0 <= span < 3600:
                durations.append(span)

        # 4/5. generate 上下文中的补丁注入 & 工具使用
        for n in nodes:
            if n["node_id"] == "generate":
                patch_checked += 1
                try:
                    input_data = json.loads(n["input_data"]) if isinstance(n["input_data"], str) else (n["input_data"] or {})
                    full_context = str(input_data.get("full_context", ""))
                    if "REFLEXION INTELLIGENCE" in full_context:
                        patch_hits += 1
                except (json.JSONDecodeError, AttributeError):
                    pass
            if n["node_id"] == "tool_check":
                tool_checked += 1
                try:
                    output_data = json.loads(n["output_data"]) if isinstance(n["output_data"], str) else (n["output_data"] or {})
                    if output_data.get("tool_results"):
                        tool_used += 1
                except (json.JSONDecodeError, AttributeError):
                    pass

    total = len(executions)
    print(f"=== 轨迹评估报告(workflow_traces,共 {len(rows)} 行 / {total} 次执行)===\n")

    print("1) 路由分布")
    for route, count in route_counter.most_common():
        print(f"   {route:<10}{count:>6}  ({count / total:.1%})")

    print(f"\n2) 完成率")
    print(f"   到达 save 节点:      {completed}/{total}  ({completed / total:.1%})")
    if deep_total:
        print(f"   DEEP 中 generate 缺失: {deep_generate_missing}/{deep_total}  ({deep_generate_missing / deep_total:.1%})  ← 跳过或中途失败")

    if durations:
        durations.sort()
        p50 = durations[len(durations) // 2]
        p95 = durations[int(len(durations) * 0.95)]
        print(f"\n3) 端到端耗时(有效样本 {len(durations)})")
        print(f"   p50: {p50:.0f}s   p95: {p95:.0f}s   max: {durations[-1]:.0f}s")

    if patch_checked:
        print(f"\n4) Reflexion 补丁注入命中率(generate 上下文)")
        print(f"   {patch_hits}/{patch_checked}  ({patch_hits / patch_checked:.1%})")

    if tool_checked:
        print(f"\n5) 工具使用率(tool_check 有产出)")
        print(f"   {tool_used}/{tool_checked}  ({tool_used / tool_checked:.1%})")


if __name__ == "__main__":
    main()
