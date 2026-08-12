from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import Field, ConfigDict
from typing import Optional, List, Union, Dict, Any
import os
import json
import logging
from dotenv import load_dotenv

# Path Setup
_base_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))) # Daisy_skills/
_server_dir = os.path.join(os.path.dirname(_base_dir), "Daisy_server") # Daisy_server/

# Try to load .env from Daisy_server if not in Daisy_skills
_env_path = os.path.join(_base_dir, ".env")
if not os.path.exists(_env_path):
    _env_path = os.path.join(_server_dir, ".env")

load_dotenv(_env_path)

def load_whitelist() -> dict:
    try:
        # Try Daisy_skills/whitelist.json
        whitelist_path = os.path.join(_base_dir, "whitelist.json")
        if not os.path.exists(whitelist_path):
            # Try Daisy_server/whitelist.json
            whitelist_path = os.path.join(_server_dir, "whitelist.json")
        
        if os.path.exists(whitelist_path):
            with open(whitelist_path, "r", encoding="utf-8") as f:
                data = json.load(f)
                if isinstance(data, list):
                    return {"users": data, "admins": ["admin"]}
                return data
        return {"users": ["admin", "test_user"], "admins": ["admin"]}
    except Exception as e:
        logging.warning(f"Failed to load whitelist.json: {e}")
        return {"users": ["admin", "test_user"], "admins": ["admin"]}

def load_default_settings(user_gender: str = "male") -> dict:
    try:
        settings_path = os.path.join(_base_dir, "default_settings.json")
        if not os.path.exists(settings_path):
            settings_path = os.path.join(_server_dir, "default_settings.json")
        
        if os.path.exists(settings_path):
            with open(settings_path, "r", encoding="utf-8") as f:
                data = json.load(f)
                if user_gender in data:
                    return data[user_gender]
                if "name" in data:
                     return data
                if "male" in data:
                    return data["male"]
    except Exception as e:
        logging.warning(f"Failed to load default_settings.json: {e}")
    
    return {
        "name": "Default",
        "gender": "Unknown",
        "core_system_prompt": "Please configure default_settings.json"
    }

class Settings(BaseSettings):
    PROJECT_NAME: str = "Daisy Skills Backend"
    API_V1_STR: str = "/api"
    
    # MCP Configuration
    MCP_SERVER_SCRIPT: str = "server.py"
    
    # LLM Configuration (Defaulting to what's likely in .env)
    EMBEDDING_PROVIDER: str = Field("siliconflow")
    EMBEDDING_MODEL_NAME: str = Field("BAAI/bge-large-zh-v1.5")
    DEFAULT_LLM_PROVIDER: str = Field("huaweicloud")
    DEFAULT_LLM_BASE_URL: str = Field("https://api.modelarts-maas.com/v1")
    DEFAULT_LLM_MODEL_NAME: str = Field("deepseek-v3.2")
    
    # Lightweight/Deep Config
    LIGHTWEIGHT_LLM_MODEL_NAME: Optional[str] = Field(None)
    DEEP_LLM_MODEL_NAME: Optional[str] = Field(None)
    DEEP_FINAL_TIMEOUT_SEC: int = Field(25)
    DEEP_TOOL_MAX_STEPS: int = Field(3)
    DEEP_TOOL_STEP_TIMEOUT_SEC: int = Field(10)
    TOOL_RESULT_MAX_CHARS: int = Field(1200)
    DEEP_ALLOWED_TOOLS: List[str] = Field(default_factory=lambda: ["search", "calculator"])
    
    # Storage
    VECTOR_DB_PATH: str = Field("./chroma_db")
    QDRANT_HOST: Optional[str] = Field(None)
    QDRANT_PORT: int = Field(6333)
    
    # Model Paths
    # Assuming models are in Daisy_server/model or Daisy_skills/model
    EMOTION_MODEL_NAME: str = Field("bert-base-cased-goemotions-original") # Will resolve path later if needed
    
    EMOTION_CONTEXT_TURNS: int = Field(2)
    EMOTION_CONTEXT_MAX_CHARS: int = Field(300)
    PERSONALITY_SELECTION_MODE: str = Field("llm")
    TOPIC_SUMMARY_HISTORY_LIMIT: int = Field(20)
    LOG_LEVEL: str = Field("INFO")
    ADMIN_TOOLS_ENABLED: bool = Field(False)
    ADMIN_TOKENS: str = Field("")
    
    # Security
    SECRET_KEY: str = Field("")  # 首次启动时自动生成随机密钥;生产环境请通过环境变量 SECRET_KEY 设置)
    ALGORITHM: str = Field("HS256")
    ACCESS_TOKEN_EXPIRE_MINUTES: int = Field(30)
    
    _whitelist_config: dict = load_whitelist()
    ALLOWED_USERS: List[Union[str, Dict]] = _whitelist_config.get("users", [])
    SUPERUSERS: List[str] = _whitelist_config.get("admins", [])
    
    # Redis
    REDIS_HOST: str = Field("localhost")
    REDIS_PORT: int = Field(6379)
    REDIS_DB: int = Field(0)
    REDIS_PASSWORD: Optional[str] = Field(None)
    ARQ_REDIS_SETTINGS: Optional[Dict[str, Any]] = None
    
    # API Keys
    SILICONFLOW_API_KEY: Optional[str] = Field(None)
    MAAS_API_KEY: Optional[str] = Field(None)
    OPENAI_API_KEY: Optional[str] = Field(None)
    HUAWEI_SEARCH_API_KEY: Optional[str] = Field(None)
    HUAWEI_SEARCH_ENDPOINT: Optional[str] = Field(None)
    
    def get_redis_settings(self):
        from arq.connections import RedisSettings
        return RedisSettings(
            host=self.REDIS_HOST,
            port=self.REDIS_PORT,
            database=self.REDIS_DB,
            password=self.REDIS_PASSWORD
        )

    # Kling (可灵) Video Generation
    KLING_API_KEY: Optional[str] = Field(None)
    KLING_ACCESS_KEY: Optional[str] = Field(None)
    KLING_SECRET_KEY: Optional[str] = Field(None)

    # ──────────────────────────────────────────────
    # 响应优化开关（速度 vs 质量权衡）
    # 设为 False 可跳过对应的 LLM 调用，显著降低延迟。
    # 经 2026-08 对比测试，关闭后回复质量无明显下降，
    # 故默认关闭。如需恢复，设为 True 或设环境变量即可。
    # 详见 docs/RESPONSE_OPTIMIZATION.md
    # ──────────────────────────────────────────────
    ENABLE_DYNAMIC_STYLE_ANALYSIS: bool = Field(
        True,
        description="启用 _analyze_style + _agent_thoughts（动态沟通风格分析，每次请求 +2-6s）"
    )
    ENABLE_REFINE_RESPONSE: bool = Field(
        False,
        description="启用 _refine_response（主 LLM 后的二次润色，每次请求 +2-5s）"
    )
    ENABLE_COMPRESS_RESPONSE: bool = Field(
        False,
        description="启用 _compress_response_to_limit（条件触发，超2句时压缩，+1-2s）"
    )

    model_config = SettingsConfigDict(
        env_file=_env_path,
        env_file_encoding='utf-8',
        extra='ignore'
    )


settings = Settings()
