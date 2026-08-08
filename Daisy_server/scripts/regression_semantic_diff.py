#!/usr/bin/env python3
"""
黄金对话集语义回归工具(#6-min,重构安全网)。

两种模式:
  capture  对运行中的本地服务逐条发送黄金集输入,轮询收集回复,存为快照 JSON。
  compare  对比两份快照(基线 vs 改动后),用 Sentence-BERT 逐条算语义相似度,
           低于阈值的用例判为疑似回归。

用法:
  python3 scripts/regression_semantic_diff.py capture --token <JWT> --out baseline.json
  python3 scripts/regression_semantic_diff.py compare baseline.json candidate.json [--threshold 0.6]

说明:
  - capture 依赖本地服务(默认 http://127.0.0.1:30021)与有效登录 token,会产生真实 LLM 调用。
  - compare 完全离线,只需 sentence-transformers(与 app/services/reflexion/metrics.py 同款
    all-MiniLM-L6-v2 模型)。
  - 对话模型输出天然有随机性,阈值判断的是「语义是否还在同一意图/风格轨道上」,
    不是逐字一致;默认阈值 0.6 偏宽松,结果应人工复核低分项而不是盲目当作失败。
"""

import argparse
import json
import sys
import time
from pathlib import Path

GOLDEN_PATH = Path(__file__).resolve().parent.parent / "tests" / "golden" / "golden_dialogues.json"
DEFAULT_BASE_URL = "http://127.0.0.1:30021"
DEFAULT_THRESHOLD = 0.6


def load_golden() -> list[dict]:
    data = json.loads(GOLDEN_PATH.read_text(encoding="utf-8"))
    return data["cases"]


def capture(base_url: str, token: str, out_path: str, wait_secs: int) -> None:
    import requests

    headers = {"Authorization": f"Bearer {token}"}
    session_id = None
    resp = requests.get(f"{base_url}/api/session/current", headers=headers,
                        params={"create_if_missing": True}, timeout=15)
    resp.raise_for_status()
    session_id = resp.json().get("session_id")
    if not session_id:
        sys.exit("无法获取 session_id,请确认 token 有效、服务已启动")

    results = []
    for case in load_golden():
        print(f"[capture] {case['id']}: {case['input'][:30]}...")
        r = requests.post(f"{base_url}/api/chat", headers=headers,
                          json={"message": case["input"], "session_id": session_id}, timeout=30)
        r.raise_for_status()
        user_message_id = (r.json().get("data") or {}).get("user_message_id")

        # 轮询历史直到该消息的 AI 回复出现(worker 异步生成)
        reply_parts: list[str] = []
        deadline = time.time() + wait_secs
        while time.time() < deadline:
            time.sleep(3)
            h = requests.get(f"{base_url}/api/chat/history", headers=headers,
                             params={"mode": "count", "limit": 10, "session_id": session_id}, timeout=15)
            h.raise_for_status()
            items = h.json()
            # 找到该用户消息之后最近的 AI 回复
            seen_user = False
            for item in items:
                if item.get("id") == user_message_id:
                    seen_user = True
                    continue
                if seen_user and item.get("role") == "ai":
                    reply_parts = item.get("parts") or ([item.get("content")] if item.get("content") else [])
                    break
            if reply_parts:
                break
        results.append({
            "id": case["id"],
            "category": case["category"],
            "input": case["input"],
            "reply": "\n".join(p for p in reply_parts if p),
            "timed_out": not reply_parts,
        })

    snapshot = {"captured_at": time.strftime("%Y-%m-%dT%H:%M:%S"), "base_url": base_url, "results": results}
    Path(out_path).write_text(json.dumps(snapshot, ensure_ascii=False, indent=2), encoding="utf-8")
    timed_out = sum(1 for x in results if x["timed_out"])
    print(f"[capture] 完成:{len(results)} 条,超时 {timed_out} 条 → {out_path}")


def compare(baseline_path: str, candidate_path: str, threshold: float) -> int:
    from sentence_transformers import SentenceTransformer
    from sentence_transformers.util import cos_sim

    base = {r["id"]: r for r in json.loads(Path(baseline_path).read_text(encoding="utf-8"))["results"]}
    cand = {r["id"]: r for r in json.loads(Path(candidate_path).read_text(encoding="utf-8"))["results"]}
    model = SentenceTransformer("all-MiniLM-L6-v2")

    rows, failures = [], 0
    for case_id, b in base.items():
        c = cand.get(case_id)
        if c is None:
            rows.append((case_id, None, "候选快照缺少该用例"))
            failures += 1
            continue
        if b["timed_out"] or c["timed_out"]:
            rows.append((case_id, None, "存在超时,无法比较"))
            failures += 1
            continue
        emb = model.encode([b["reply"], c["reply"]])
        score = float(cos_sim(emb[0], emb[1])[0][0])
        verdict = "OK" if score >= threshold else "疑似回归"
        if score < threshold:
            failures += 1
        rows.append((case_id, score, verdict))

    print(f"\n{'用例':<20}{'相似度':<10}判定")
    print("-" * 44)
    for case_id, score, verdict in rows:
        score_str = f"{score:.3f}" if score is not None else "-"
        print(f"{case_id:<20}{score_str:<10}{verdict}")
    print("-" * 44)
    print(f"共 {len(rows)} 条,低于阈值({threshold}) / 异常 {failures} 条")
    if failures:
        print("提示:低分项请人工复核两侧回复内容,确认是语义漂移还是正常随机性。")
    return 1 if failures else 0


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="mode", required=True)

    p_cap = sub.add_parser("capture", help="采集当前服务对黄金集的回复快照")
    p_cap.add_argument("--base-url", default=DEFAULT_BASE_URL)
    p_cap.add_argument("--token", required=True, help="登录 JWT")
    p_cap.add_argument("--out", required=True, help="快照输出路径")
    p_cap.add_argument("--wait-secs", type=int, default=90, help="单条回复最长等待秒数")

    p_cmp = sub.add_parser("compare", help="对比两份快照的语义相似度")
    p_cmp.add_argument("baseline")
    p_cmp.add_argument("candidate")
    p_cmp.add_argument("--threshold", type=float, default=DEFAULT_THRESHOLD)

    args = parser.parse_args()
    if args.mode == "capture":
        capture(args.base_url, args.token, args.out, args.wait_secs)
    else:
        sys.exit(compare(args.baseline, args.candidate, args.threshold))


if __name__ == "__main__":
    main()
