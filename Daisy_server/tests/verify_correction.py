import sys
import os
import asyncio
import json
from unittest.mock import MagicMock, patch

# Add project root to path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.workflow.nodes.correction import correct_typo
from app.workflow.nodes.state import AgentState
from app.core.llm_config import llm_config_manager

async def setup_llm_config():
    """Manually setup LLM config for testing"""
    # 1. Load llm_providers.json
    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    config_path = os.path.join(base_dir, "llm_providers.json")
    
    if os.path.exists(config_path):
        with open(config_path, "r", encoding="utf-8") as f:
            providers = json.load(f)
            
        # 2. Inject env vars
        for key, config in providers.items():
            api_key_env = config.get("api_key_env")
            if api_key_env:
                env_key = os.environ.get(api_key_env)
                if env_key:
                    config["api_key"] = env_key
            
            # Set to manager
            llm_config_manager.set_provider_config(key, config)
            print(f"Loaded config for provider: {key}")
            
        # 3. Set default provider
        default_provider = os.environ.get("DEFAULT_LLM_PROVIDER", "huaweicloud")
        llm_config_manager.set_current_provider(default_provider)
        print(f"Set current provider to: {default_provider}")
    else:
        print(f"WARNING: llm_providers.json not found at {config_path}")

async def test_correction():
    print("=== Testing Context-Aware Typo Correction (Real LLM) ===")
    
    # Setup LLM Config first
    await setup_llm_config()
    
    # 1. Mock DB and History Service (We only mock the Context fetching part)
    # We want to test if the LLM can fix "像你" to "想你" given the context.
    mock_history = [
        MagicMock(role="ai", content="这么晚了还没睡呀，是有心事，还是单纯在享受安静的夜晚呢？", id=1),
        # Current message: "有没有可能，像你呢？"
    ]
    
    # We patch SessionLocal and history_service to avoid real DB hits
    with patch("app.workflow.nodes.correction.SessionLocal") as MockSession:
        with patch("app.workflow.nodes.correction.history_service") as MockHistoryService:
            # Setup Mock behavior
            session_instance = MockSession.return_value.__enter__.return_value
            MockHistoryService.get_recent_history_limit.return_value = mock_history
            
            # 2. Define State
            state = AgentState(
                user_input="有没有可能，像你呢？",
                user_id=123,
                user_message_id=2,
                # ... other fields
            )
            
            # 3. Run Node
            print(f"Input: {state['user_input']}")
            print("Context: AI: 这么晚了还没睡呀... (implying flirting context)")
            
            try:
                # This will call the real LLM configured in .env
                result = await correct_typo(state)
                
                if "user_input" in result:
                    print(f"✅ Correction Result: {result['user_input']}")
                    if "想你" in result['user_input']:
                        print("SUCCESS: Typo corrected correctly!")
                    else:
                        print(f"WARNING: Corrected but not matching expected. Got: {result['user_input']}")
                else:
                    print("❌ Result empty (No correction made). LLM might have thought it's correct.")
                    
            except Exception as e:
                print(f"ERROR: {e}")
                import traceback
                traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(test_correction())
