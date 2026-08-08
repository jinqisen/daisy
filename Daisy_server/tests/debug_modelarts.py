import os
import json
import sys
from dotenv import load_dotenv

# Load env from /app/.env if exists (Docker environment)
if os.path.exists("/app/.env"):
    load_dotenv("/app/.env")

# Add project root to sys.path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from langchain_openai import ChatOpenAI
from langchain_core.messages import HumanMessage

def normalize_api_key(api_key: str | None) -> str | None:
    if api_key is None:
        return None
    key = str(api_key).strip()
    if not key:
        return ""
    if (key.startswith('"') and key.endswith('"')) or (key.startswith("'") and key.endswith("'")):
        key = key[1:-1].strip()
    lower = key.lower()
    if lower.startswith("authorization:"):
        key = key.split(":", 1)[1].strip()
        lower = key.lower()
    if lower.startswith("bearer "):
        key = key[7:].strip()
    return key

def normalize_base_url(url: str | None) -> str | None:
    if not url:
        return url
    
    # 移除常见的包裹字符和末尾逗号
    return str(url).strip().strip("',`\" ").rstrip(",").strip("',`\" ")

def main():
    print("=== Debug ModelArts Connection ===")
    
    # 1. Check Env Var
    env_key = os.environ.get("MAAS_API_KEY")
    print(f"Env MAAS_API_KEY raw: {repr(env_key)}")
    normalized_key = normalize_api_key(env_key)
    print(f"Env MAAS_API_KEY normalized: {repr(normalized_key)}")

    # 2. Check Config File
    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    config_path = os.path.join(base_dir, "llm_providers.json")
    print(f"Config path: {config_path}")
    
    config_base_url = None
    config_model = None
    
    if os.path.exists(config_path):
        with open(config_path, "r", encoding="utf-8") as f:
            data = json.load(f)
            print(f"Config content: {json.dumps(data, indent=2)}")
            if "huaweicloud" in data:
                config_base_url = data["huaweicloud"].get("base_url")
                config_model = data["huaweicloud"].get("model")
    else:
        print("Config file not found!")

    print(f"Config Base URL raw: {repr(config_base_url)}")
    normalized_base_url = normalize_base_url(config_base_url)
    print(f"Config Base URL normalized: {repr(normalized_base_url)}")

    # 3. Test Connection
    if not normalized_key:
        print("Skipping connection test: No API Key")
        return

    print("\n--- Testing Connection ---")
    
    # Use config values or fallback to hardcoded for testing
    target_base_url = normalized_base_url or "https://api.modelarts-maas.com/v1"
    target_model = config_model or "deepseek-v3.2" # or qwen3-32b if that was the intention
    
    # Explicitly test the "bad" url if we suspect it
    # bad_url = "`https://api.modelarts-maas.com/v1,`"
    # print(f"Testing with suspected BAD URL first: {bad_url}")
    # try:
    #     llm_bad = ChatOpenAI(
    #         model=target_model,
    #         api_key=normalized_key,
    #         base_url=bad_url,
    #         temperature=0.1
    #     )
    #     llm_bad.invoke([HumanMessage(content="Hello")])
    #     print("BAD URL WORKED?!")
    # except Exception as e:
    #     print(f"BAD URL Failed as expected: {e}")

    print(f"\nTesting with NORMALIZED URL: {target_base_url}")
    try:
        llm = ChatOpenAI(
            model=target_model,
            api_key=normalized_key,
            base_url=target_base_url,
            temperature=0.1,
            max_retries=1,
            request_timeout=10
        )
        response = llm.invoke([HumanMessage(content="Hello, are you working?")])
        print(f"Success! Response: {response.content}")
    except Exception as e:
        print(f"Connection Failed: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    main()
