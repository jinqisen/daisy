import asyncio
import datetime
import hashlib
import structlog
from typing import Any, Dict
from ...core.database import SessionLocal
from ...core.cache import cache_result
from ...models import WorkflowTraceDB, UserDB, CommonSettingsDB, ChatHistoryDB, RoleProfileDB
from ...prompts import CommonSettings, RoleProfile
from ...services.memory.chat_history import history_service
from .state import AgentState
from typing import List

import time
import functools

logger = structlog.get_logger()

_REDACTED_TRACE_FIELDS = {"system_prompt", "system_instructions", "full_context"}


def _build_redacted_text_payload(field_name: str, value: str) -> Dict[str, Any]:
    normalized = value or ""
    return {
        "redacted": True,
        "field": field_name,
        "length": len(normalized),
        "line_count": normalized.count("\n") + (1 if normalized else 0),
        "sha256_prefix": hashlib.sha256(normalized.encode("utf-8", errors="ignore")).hexdigest()[:16],
    }


def sanitize_trace_payload(payload: Any) -> Any:
    if isinstance(payload, dict):
        sanitized: Dict[str, Any] = {}
        for key, value in payload.items():
            if key in _REDACTED_TRACE_FIELDS and isinstance(value, str):
                sanitized[key] = _build_redacted_text_payload(key, value)
            else:
                sanitized[key] = sanitize_trace_payload(value)
        return sanitized

    if isinstance(payload, list):
        return [sanitize_trace_payload(item) for item in payload]

    return payload

def monitor_execution_time(func):
    """
    装饰器：监控异步函数的执行时间并记录日志
    """
    @functools.wraps(func)
    async def wrapper(*args, **kwargs):
        start_time = time.time()
        func_name = func.__name__
        logger.info(f"START_NODE: {func_name}")
        
        try:
            result = await func(*args, **kwargs)
            end_time = time.time()
            duration = end_time - start_time
            logger.info("CHARACTER_PERFORMANCE", 
                        node=func_name, 
                        duration_seconds=round(duration, 4),
                        status="success")
            return result
        except Exception as e:
            end_time = time.time()
            duration = end_time - start_time
            logger.error("CHARACTER_PERFORMANCE", 
                         node=func_name, 
                         duration_seconds=round(duration, 4), 
                         status="error",
                         error=str(e))
            raise e
            
    return wrapper

async def add_trace(state: AgentState, node_id: str, input_data: Any, output_data: Any) -> Dict[str, Dict[str, Any]]:
    """
    辅助函数：更新工作流追踪信息 (Trace)
    用于可视化展示每个节点的处理过程
    同时将追踪数据持久化到数据库
    """
    sanitized_input_data = sanitize_trace_payload(input_data)
    sanitized_output_data = sanitize_trace_payload(output_data)

    # 1. 持久化到数据库 (Async Wrapper)
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        loop = asyncio.get_event_loop()
    
    def _persist_trace():
        try:
            history_service.persist_workflow_trace(
                session_id=state["session_id"],
                user_id=state.get("user_id"),
                execution_id=state.get("execution_id"),
                node_id=node_id,
                input_data=sanitized_input_data,
                output_data=sanitized_output_data,
                timestamp=datetime.datetime.now().strftime("%H:%M:%S"),
            )
        except Exception as e:
            logger.error(f"持久化 Trace 到数据库失败: {e}")

    await loop.run_in_executor(None, _persist_trace)

    # 2. 更新内存中的 trace (保持向后兼容，或用于不需要查询 DB 的场景)
    trace = state.get("workflow_trace", {})
    if trace is None: trace = {}
    else: trace = trace.copy() # 确保操作副本，避免副作用
    
    # 记录节点信息
    trace[node_id] = {
        "input": sanitized_input_data,
        "output": sanitized_output_data,
        "timestamp": datetime.datetime.now().strftime("%H:%M:%S")
    }
    logger.debug("Trace Update", node_id=node_id, trace_keys=list(trace.keys()))
    return trace

# --- 异步数据库辅助函数 ---

from typing import Union

def _get_active_profiles_sync(user_identifier: Union[str, int]) -> List[RoleProfile]:
    """同步获取所有角色 Profile"""
    try:
        with SessionLocal() as db:
            if isinstance(user_identifier, int):
                user = db.query(UserDB).filter(UserDB.id == user_identifier).first()
            else:
                user = db.query(UserDB).filter(UserDB.username == str(user_identifier)).first()

            if user:
                profiles = db.query(RoleProfileDB).filter(RoleProfileDB.user_id == user.id).all()
                return [
                    RoleProfile(
                        name=p.name,
                        description=p.description,
                        style=p.style,
                        constraints=p.constraints,
                    ) for p in profiles
                ]
    except Exception as e:
        logger.error(f"Failed to fetch profiles: {e}")
    return []

async def get_active_profiles_async(user_identifier: Union[str, int]) -> List[RoleProfile]:
    """异步获取所有角色 Profile"""
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, _get_active_profiles_sync, user_identifier)

def _get_common_settings_sync(user_identifier: Union[str, int]):
    """同步获取通用设置"""
    try:
        with SessionLocal() as db:
            if isinstance(user_identifier, int):
                user = db.query(UserDB).filter(UserDB.id == user_identifier).first()
            else:
                user = db.query(UserDB).filter(UserDB.username == str(user_identifier)).first()

            if user:
                common_db = db.query(CommonSettingsDB).filter(CommonSettingsDB.user_id == user.id).first()
                if common_db:
                    return CommonSettings(
                        name=common_db.name,
                        gender=common_db.gender,
                        age=common_db.age,
                        occupation=common_db.occupation,
                        relationship=common_db.relationship,
                        backstory=common_db.backstory,
                        portrait=common_db.portrait,
                        world_setting=common_db.world_setting,
                        system_prompt_template=common_db.system_prompt_template,
                        core_system_prompt=common_db.core_system_prompt,
                        character_card_json=common_db.character_card_json, # Populate character card
                        llm_provider=common_db.llm_provider,
                        llm_api_key=common_db.llm_api_key,
                        llm_base_url=common_db.llm_base_url,
                        llm_model_name=common_db.llm_model_name
                    )
    except Exception as e:
        logger.error(f"Failed to load user settings: {e}")
    return None

@cache_result(ttl=300, key_prefix="common_settings_dict")
async def _get_common_settings_dict_async(user_identifier: Union[str, int]) -> Dict[str, Any]:
    """
    Internal helper to get settings as dict with caching.
    Separated because cache_result uses JSON which doesn't support Pydantic objects directly.
    """
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        loop = asyncio.get_event_loop()
    
    settings_obj = await loop.run_in_executor(None, _get_common_settings_sync, user_identifier)
    if settings_obj:
        # Support both Pydantic v1 and v2
        if hasattr(settings_obj, "model_dump"):
            return settings_obj.model_dump()
        if hasattr(settings_obj, "dict"):
            return settings_obj.dict()
        return settings_obj.__dict__
    return None

async def get_common_settings_async(user_identifier: Union[str, int]):
    """异步获取通用设置 (Cached)"""
    data = await _get_common_settings_dict_async(user_identifier)
    if data:
        return CommonSettings(**data)
    return None

