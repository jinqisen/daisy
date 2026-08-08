#!/usr/bin/env python3
"""
导出 (context, action, reward) 数据集,供 contextual bandit 离线评估使用。

用法:
  python3 scripts/export_rl_dataset.py                 # 概览统计
  python3 scripts/export_rl_dataset.py --out data.jsonl  # 导出样本

离线评估的意义:先用历史数据估计"如果换成 bandit 策略,期望回报会不会更高",
再决定要不要上线。若估计打不过现有 LLM 策略,就该停手 —— 这是设计好的止损点。
"""

import argparse
import json
import sqlite3
from collections import Counter, defaultdict
from pathlib import Path

DEFAULT_DB = Path(__file__).resolve().parent.parent / "sqlite.db"


def load(db_path: str, only_reliable: bool = False):
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    try:
        sql = "SELECT * FROM rl_samples"
        if only_reliable:
            sql += " WHERE reward_reliable = 1"
        sql += " ORDER BY id"
        return [dict(r) for r in conn.execute(sql)]
    except sqlite3.OperationalError as e:
        print(f"表不存在或不可读: {e}")
        print("提示:样本在对话发生后才会积累,需先运行应用并进行若干轮对话。")
        return []
    finally:
        conn.close()


def summarize(rows):
    if not rows:
        print("暂无样本。")
        print("\n数据积累说明:")
        print("  - 每轮对话在 strategy 节点记录 (context, action)")
        print("  - 下一轮用户回复后,Reflexion 算出 S 作为 reward 并配对落库")
        print("  - 故最后一轮没有奖励(尚无用户反馈),属正常")
        return

    print(f"=== 样本总览({len(rows)} 条)===\n")

    actions = Counter(r["action"] for r in rows)
    print("动作分布(人格选择):")
    for a, n in actions.most_common():
        print(f"  {a:<10}{n:>5}  ({n / len(rows):.0%})")

    policies = Counter(r["policy"] for r in rows)
    print(f"\n数据来源策略: {dict(policies)}")

    rewards = [r["reward"] for r in rows if r["reward"] is not None]
    if rewards:
        rewards_sorted = sorted(rewards)
        n = len(rewards_sorted)
        print(f"\n奖励(S)分布 n={n}:")
        print(f"  min={rewards_sorted[0]:.3f}  p50={rewards_sorted[n//2]:.3f}  max={rewards_sorted[-1]:.3f}")
        print(f"  mean={sum(rewards)/n:.3f}")
        reliable = sum(1 for r in rows if r["reward_reliable"])
        print(f"  其中 D_R 可信: {reliable}/{len(rows)}")

    print("\n各动作的平均回报(样本足够时才有参考意义):")
    by_action = defaultdict(list)
    for r in rows:
        if r["reward"] is not None:
            by_action[r["action"]].append(r["reward"])
    for a, vals in sorted(by_action.items(), key=lambda kv: -sum(kv[1]) / len(kv[1])):
        flag = "" if len(vals) >= 30 else "  ← 样本不足,勿据此下结论"
        print(f"  {a:<10}n={len(vals):<4} mean={sum(vals)/len(vals):.3f}{flag}")

    print("\n=== 是否可以进入离线评估 ===")
    if len(rows) < 100:
        print(f"  ✗ 样本 {len(rows)} 条,建议至少积累 200+ 再做离线评估")
        print("    (6 个动作臂,每臂需数十样本才能区分优劣)")
    else:
        print(f"  ✓ 样本 {len(rows)} 条,可尝试 IPS/DR 离线策略评估")


def export(rows, out_path: str):
    with open(out_path, "w", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps({
                "context": json.loads(r["context_json"]) if isinstance(r["context_json"], str) else r["context_json"],
                "action": r["action"],
                "action_weights": json.loads(r["action_weights_json"]) if isinstance(r["action_weights_json"], str) else r["action_weights_json"],
                "policy": r["policy"],
                "reward": r["reward"],
                "reward_reliable": bool(r["reward_reliable"]),
                "timestamp": r["timestamp"],
            }, ensure_ascii=False) + "\n")
    print(f"已导出 {len(rows)} 条 → {out_path}")


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--db", default=str(DEFAULT_DB))
    p.add_argument("--out", help="导出为 JSONL")
    p.add_argument("--reliable-only", action="store_true", help="仅导出 D_R 可信的样本")
    args = p.parse_args()

    rows = load(args.db, args.reliable_only)
    summarize(rows)
    if args.out and rows:
        export(rows, args.out)


if __name__ == "__main__":
    main()
