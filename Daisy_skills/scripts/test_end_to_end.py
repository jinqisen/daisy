import asyncio
import json
import os
import time
from typing import Any, Dict, List

import aiohttp
from dotenv import load_dotenv

load_dotenv("/Users/anykong/Daisy_Demo/Daisy_server/.env")

EMPATHY_KEYWORDS = [
    "我理解",
    "理解你",
    "听起来",
    "很抱歉",
    "难过",
    "心疼",
    "抱抱",
    "辛苦",
    "我在",
    "陪你",
    "不容易",
    "我能感受",
    "理解你的感受",
    "I'm sorry",
    "I understand",
    "That sounds",
]

SUPPORT_KEYWORDS = [
    "可以",
    "建议",
    "要不要",
    "不妨",
    "如果你愿意",
    "我们可以",
    "一起",
    "尝试",
]

DEFAULT_TEST_CASES = [
    {
        "user_input": "你好，我今天有点低落，感觉没人理解我。",
        "session_id": "session_emotion_1",
    },
    {
        "user_input": "我最近总是睡不好，心里有点慌。",
        "session_id": "session_emotion_1",
    },
    {
        "user_input": "我和朋友闹别扭了，很难受。",
        "session_id": "session_emotion_2",
    },
]


def analyze_response(text: str) -> Dict[str, Any]:
    length = len(text)
    empathy_hits = [kw for kw in EMPATHY_KEYWORDS if kw in text]
    support_hits = [kw for kw in SUPPORT_KEYWORDS if kw in text]
    question_count = text.count("?") + text.count("？")
    warmth_score = len(empathy_hits) * 2 + len(support_hits) + min(question_count, 2)
    return {
        "length": length,
        "empathy_hits": empathy_hits,
        "support_hits": support_hits,
        "question_count": question_count,
        "warmth_score": warmth_score,
    }


async def fetch_daisy_server_token(
    session: aiohttp.ClientSession,
    base_url: str,
    username: str,
    password: str,
) -> str:
    login_url = f"{base_url}/api/auth/login"
    register_url = f"{base_url}/api/auth/register"

    def variants(pw: str) -> List[str]:
        v = [pw]
        if "！" in pw:
            v.append(pw.replace("！", "!"))
        return list(dict.fromkeys(v))

    # Try login with variants
    for pw in variants(password):
        async with session.post(login_url, data={"username": username, "password": pw}) as resp:
            if resp.status == 200:
                payload = await resp.json()
                token = payload.get("access_token")
                if token:
                    return token

    # Try register with a complexity-safe variant
    reg_pw = password
    if "！" in reg_pw:
        reg_pw = reg_pw.replace("！", "!")
    async with session.post(register_url, json={"username": username, "password": reg_pw}) as resp:
        if resp.status == 200:
            payload = await resp.json()
            token = payload.get("access_token")
            if token:
                return token

    # Final attempt: login with variant used for register
    async with session.post(login_url, data={"username": username, "password": reg_pw}) as resp:
        payload = await resp.text()
        raise RuntimeError(f"Daisy_server login failed: {resp.status} {payload}")


async def read_sse_response(
    session: aiohttp.ClientSession,
    stream_url: str,
    timeout_sec: int = 60,
) -> Dict[str, Any]:
    timeout = aiohttp.ClientTimeout(total=timeout_sec)
    async with session.get(stream_url, timeout=timeout) as resp:
        async for raw_line in resp.content:
            line = raw_line.decode("utf-8").strip()
            if not line:
                continue
            if not line.startswith("data:"):
                continue
            payload = line[5:].strip()
            if not payload:
                continue
            try:
                data = json.loads(payload)
            except json.JSONDecodeError:
                continue
            if isinstance(data, dict) and "response" in data:
                return data
    raise RuntimeError("No SSE response received")


async def call_daisy_server(
    session: aiohttp.ClientSession,
    base_url: str,
    token: str,
    message: str,
    session_id: str,
) -> Dict[str, Any]:
    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
    chat_url = f"{base_url}/api/chat"
    payload = {"message": message, "session_id": session_id}
    async with session.post(chat_url, json=payload, headers=headers) as resp:
        if resp.status not in (200, 202):
            text = await resp.text()
            raise RuntimeError(f"Daisy_server chat failed: {resp.status} {text}")

    stream_url = f"{base_url}/api/chat/stream?token={token}"
    return await read_sse_response(session, stream_url)


async def call_daisy_skills(
    session: aiohttp.ClientSession,
    base_url: str,
    message: str,
    user_id: str,
    session_id: str,
) -> Dict[str, Any]:
    chat_url = f"{base_url}/api/v1/skills/chat"
    payload = {"message": message, "user_id": user_id, "session_id": session_id}
    async with session.post(chat_url, json=payload) as resp:
        if resp.status != 200:
            text = await resp.text()
            raise RuntimeError(f"Daisy_skills chat failed: {resp.status} {text}")
        return await resp.json()


def build_comparison(
    user_input: str,
    server_data: Dict[str, Any],
    skills_data: Dict[str, Any],
) -> Dict[str, Any]:
    server_text = server_data.get("response", "") or ""
    skills_text = skills_data.get("response", "") or ""
    server_analysis = analyze_response(server_text)
    skills_analysis = analyze_response(skills_text)
    return {
        "input": user_input,
        "daisy_server": {
            "response": server_text,
            "emotion_analysis": server_data.get("emotion_analysis", {}),
            "personality": server_data.get("personality"),
            "engagement_score": server_data.get("engagement_score"),
            "analysis": server_analysis,
        },
        "daisy_skills": {
            "response": skills_text,
            "analysis": skills_analysis,
        },
        "delta": {
            "length": server_analysis["length"] - skills_analysis["length"],
            "warmth_score": server_analysis["warmth_score"] - skills_analysis["warmth_score"],
            "question_count": server_analysis["question_count"] - skills_analysis["question_count"],
        },
    }


def summarize(results: List[Dict[str, Any]]) -> Dict[str, Any]:
    if not results:
        return {}
    server_scores = [r["daisy_server"]["analysis"]["warmth_score"] for r in results]
    skills_scores = [r["daisy_skills"]["analysis"]["warmth_score"] for r in results]
    server_lengths = [r["daisy_server"]["analysis"]["length"] for r in results]
    skills_lengths = [r["daisy_skills"]["analysis"]["length"] for r in results]
    return {
        "daisy_server": {
            "avg_warmth_score": sum(server_scores) / len(server_scores),
            "avg_length": sum(server_lengths) / len(server_lengths),
        },
        "daisy_skills": {
            "avg_warmth_score": sum(skills_scores) / len(skills_scores),
            "avg_length": sum(skills_lengths) / len(skills_lengths),
        },
    }


def select_whitelist_user() -> str:
    whitelist_path = os.path.join(
        os.path.dirname(os.path.dirname(__file__)),
        "..",
        "Daisy_server",
        "whitelist.json",
    )
    whitelist_path = os.path.abspath(whitelist_path)
    if not os.path.exists(whitelist_path):
        return "verify_user"
    try:
        with open(whitelist_path, "r", encoding="utf-8") as handle:
            data = json.load(handle)
        users = data.get("users", []) if isinstance(data, dict) else data
        for user in users:
            if isinstance(user, str):
                return user
            if isinstance(user, dict) and user.get("username"):
                return user["username"]
    except Exception:
        return "verify_user"
    return "verify_user"


async def main():
    daisy_server_base = os.getenv("DAISY_SERVER_BASE_URL", "http://localhost:30021")
    daisy_skills_base = os.getenv("DAISY_SKILLS_BASE_URL", "http://localhost:8001")
    username = os.getenv("DAISY_SERVER_USER") or select_whitelist_user()
    password = os.getenv("DAISY_SERVER_PASSWORD", "Password123!")
    preset_token = os.getenv("DAISY_SERVER_TOKEN")
    test_cases = [{**case, "user_id": username} for case in DEFAULT_TEST_CASES]

    async with aiohttp.ClientSession() as session:
        token = preset_token or await fetch_daisy_server_token(session, daisy_server_base, username, password)
        results = []
        for idx, case in enumerate(test_cases, start=1):
            session_id = f"compare_{case['session_id']}_{int(time.time() * 1000)}"
            server_data = await call_daisy_server(
                session,
                daisy_server_base,
                token,
                case["user_input"],
                session_id,
            )
            skills_data = await call_daisy_skills(
                session,
                daisy_skills_base,
                case["user_input"],
                case["user_id"],
                session_id,
            )
            comparison = build_comparison(case["user_input"], server_data, skills_data)
            comparison["case_id"] = idx
            results.append(comparison)

    output = {
        "summary": summarize(results),
        "cases": results,
    }
    print(json.dumps(output, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    asyncio.run(main())
