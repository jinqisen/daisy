import sqlite3
import os
import argparse
from datetime import datetime, timedelta

def detect_db_path():
    candidates = [
        "/Users/anykong/Daisy_Demo/Daisy_server/sqlite.db",
        "/app/Daisy_server/sqlite.db"
    ]
    for p in candidates:
        if os.path.exists(p):
            return p
    return candidates[0]

def connect_db(db_path):
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    return conn

def find_user_message_by_text(cur, text):
    cur.execute(
        "SELECT id, user_id, role, session_id, timestamp, content FROM chat_history WHERE role='user' AND content LIKE ? ORDER BY timestamp DESC LIMIT 1",
        (f"%{text}%",)
    )
    row = cur.fetchone()
    return row

def find_user_messages_by_text(cur, text, limit=20):
    cur.execute(
        "SELECT id, user_id, role, session_id, timestamp, content FROM chat_history WHERE role='user' AND content LIKE ? ORDER BY timestamp DESC LIMIT ?",
        (f"%{text}%", limit)
    )
    return cur.fetchall()

def find_next_ai_by_id(cur, session_id, user_id, message_id):
    cur.execute(
        "SELECT id, role, timestamp, content FROM chat_history WHERE session_id=? AND user_id=? AND role='ai' AND id>? ORDER BY id ASC LIMIT 1",
        (session_id, user_id, message_id)
    )
    return cur.fetchone()

def find_ai_reply_after_message(cur, session_id, user_id, message_id):
    cur.execute(
        "SELECT id, role, timestamp, content FROM chat_history WHERE session_id=? AND user_id=? AND role='ai' AND id>? ORDER BY id ASC LIMIT 1",
        (session_id, user_id, message_id)
    )
    return cur.fetchone()

def list_session_messages(cur, session_id, user_id, limit=50):
    cur.execute(
        "SELECT id, role, timestamp, content FROM chat_history WHERE session_id=? AND user_id=? ORDER BY id ASC LIMIT ?",
        (session_id, user_id, limit)
    )
    return cur.fetchall()

def get_ai_replies_near_time(cur, user_id, base_time, window_mins=10):
    start = (base_time - timedelta(minutes=window_mins)).isoformat(sep=" ")
    end = (base_time + timedelta(minutes=window_mins)).isoformat(sep=" ")
    cur.execute(
        "SELECT id, role, session_id, timestamp, content FROM chat_history WHERE role='ai' AND user_id=? AND timestamp BETWEEN ? AND ? ORDER BY timestamp ASC",
        (user_id, start, end)
    )
    return cur.fetchall()

def has_workflow_traces(cur, session_id):
    cur.execute(
        "SELECT COUNT(1) AS c FROM workflow_traces WHERE session_id=?",
        (session_id,)
    )
    row = cur.fetchone()
    return (row["c"] or 0) > 0

def llm_traces_by_trigger(cur, text, limit=20):
    cur.execute(
        "SELECT id, timestamp, agent_name, trigger_message, response FROM llm_traces WHERE trigger_message LIKE ? ORDER BY timestamp DESC LIMIT ?",
        (f"%{text}%", limit)
    )
    return cur.fetchall()

def llm_prompts_by_trigger(cur, text, limit=50):
    cur.execute(
        "SELECT id, timestamp, agent_name, trigger_message, system_prompt, user_input, response, error FROM llm_traces WHERE trigger_message LIKE ? ORDER BY timestamp DESC LIMIT ?",
        (f"%{text}%", limit)
    )
    return cur.fetchall()

def pick_llm_trace(rows, agent_prefix=None, exclude_prefix=None):
    for row in rows:
        agent_name = row["agent_name"] or ""
        if agent_prefix and not agent_name.startswith(agent_prefix):
            continue
        if exclude_prefix and agent_name.startswith(exclude_prefix):
            continue
        if row["system_prompt"] or row["response"]:
            return row
    return None

def score_colloquial(text):
    particles = ["呢", "呀", "吧", "哦", "嘛", "呀呀", "欸", "唉", "哟", "哈"]
    count = sum(text.count(p) for p in particles)
    punctuation = sum(text.count(ch) for ch in ["～", "~", "!", "！", "?", "？", "…"])
    return count + punctuation

def sentence_count(text):
    seps = ["。", ".", "！", "!", "？", "?"]
    c = 0
    i = 0
    while i < len(text):
        if text[i] in seps:
            c += 1
        i += 1
    return max(1, c)

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--db", default=None)
    parser.add_argument("--message", default=None)
    parser.add_argument("--session", default=None)
    parser.add_argument("--user-id", type=int, default=None)
    parser.add_argument("--window-mins", type=int, default=10)
    parser.add_argument("--limit", type=int, default=50)
    parser.add_argument("--print-llm-traces", action="store_true")
    parser.add_argument("--prompt-compare", action="store_true")
    args = parser.parse_args()

    db_path = args.db or detect_db_path()
    print(f"DB: {db_path}")
    conn = connect_db(db_path)
    cur = conn.cursor()

    user_msg = None
    session_id = args.session
    user_id = args.user_id

    if args.message:
        pairs = find_user_messages_by_text(cur, args.message, limit=20)
        if pairs:
            print(f"MatchedPairs count={len(pairs)}")
            for p in pairs:
                ai = find_next_ai_by_id(cur, p["session_id"], int(p["user_id"]), int(p["id"]))
                label = "server" if has_workflow_traces(cur, p["session_id"]) else "skills_or_unknown"
                print(f"- user_id={p['user_id']} session={p['session_id']} ts={p['timestamp']} label={label}")
                print(f"  user={p['content']}")
                if ai:
                    sc = score_colloquial(ai["content"] or "")
                    sn = sentence_count(ai["content"] or "")
                    print(f"  ai_ts={ai['timestamp']} score={sc} sentences={sn} len={len(ai['content'] or '')}")
                    print(f"  ai={ai['content']}")
                else:
                    print("  ai=None")

        user_msg = find_user_message_by_text(cur, args.message)
        if user_msg:
            session_id = user_msg["session_id"]
            user_id = user_id or int(user_msg["user_id"])
            print(f"UserMessage id={user_msg['id']} uid={user_id} session={session_id} ts={user_msg['timestamp']}")
            print(f"UserContent: {user_msg['content']}")
        else:
            print("No user message matched.")

    if not session_id or not user_id:
        print("Missing session_id or user_id. Provide --session and --user-id if --message not found.")
        conn.close()
        return

    ai_after = None
    if user_msg:
        ai_after = find_ai_reply_after_message(cur, session_id, user_id, int(user_msg["id"]))
        if ai_after:
            print("NextAIReply:")
            print(f"  ts={ai_after['timestamp']}")
            print(f"  content={ai_after['content']}")
            sc = score_colloquial(ai_after["content"] or "")
            sn = sentence_count(ai_after["content"] or "")
            print(f"  metrics: colloquial_score={sc} sentence_count={sn} length={len(ai_after['content'] or '')}")

    rows = list_session_messages(cur, session_id, user_id, args.limit)
    print(f"SessionMessages count={len(rows)}")
    has_traces = has_workflow_traces(cur, session_id)
    print(f"WorkflowTracesPresent={has_traces} label={'server' if has_traces else 'skills_or_unknown'}")

    if user_msg:
        try:
            base_time = datetime.fromisoformat(user_msg["timestamp"])
        except Exception:
            base_time = datetime.utcnow()
        near_ai = get_ai_replies_near_time(cur, user_id, base_time, args.window_mins)
        print(f"NearbyAIReplies count={len(near_ai)}")
        for r in near_ai:
            sc = score_colloquial(r["content"] or "")
            sn = sentence_count(r["content"] or "")
            label = "server" if has_workflow_traces(cur, r["session_id"]) else "skills_or_unknown"
            print(f"- session={r['session_id']} ts={r['timestamp']} label={label} score={sc} sentences={sn} len={len(r['content'] or '')}")
            print(f"  {r['content']}")

    if args.print_llm_traces and args.message:
        traces = llm_traces_by_trigger(cur, args.message, limit=20)
        print(f"LLMTraces count={len(traces)}")
        for t in traces:
            print(f"- ts={t['timestamp']} agent={t['agent_name']}")
            print(f"  trigger={t['trigger_message']}")
            print(f"  response={t['response']}")

    if args.prompt_compare and args.message:
        prompts = llm_prompts_by_trigger(cur, args.message, limit=80)
        skills_prompt = pick_llm_trace(prompts, agent_prefix="SkillsGeneration")
        server_prompt = pick_llm_trace(prompts, exclude_prefix="SkillsGeneration")
        print("PromptCompare")
        if server_prompt:
            print(f"ServerPrompt ts={server_prompt['timestamp']} agent={server_prompt['agent_name']}")
            print(server_prompt["system_prompt"])
            if server_prompt["response"]:
                print("ServerResponse")
                print(server_prompt["response"])
            if server_prompt["error"]:
                print("ServerError")
                print(server_prompt["error"])
        else:
            print("ServerPrompt not found")
        if skills_prompt:
            print(f"SkillsPrompt ts={skills_prompt['timestamp']} agent={skills_prompt['agent_name']}")
            print(skills_prompt["system_prompt"])
            if skills_prompt["response"]:
                print("SkillsResponse")
                print(skills_prompt["response"])
            if skills_prompt["error"]:
                print("SkillsError")
                print(skills_prompt["error"])
        else:
            print("SkillsPrompt not found")

    conn.close()

if __name__ == "__main__":
    main()
