from typing import Any, Dict, List, Optional
from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field
import structlog

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from runtime import (
    SkillLoader,
    SkillDiscovery,
    SkillExecutor,
    SkillOrchestrator,
    DialogueFlowOrchestrator,
    DialogueFlowBuilder,
    PredefinedFlows,
    DialogueContext,
    FlowType,
    FlowStatus,
    StateManager,
    StateType
)
from ..workflow import AgentWorkflow
from app.flows.definitions import MAIN_DIALOGUE_FLOW

logger = structlog.get_logger()

router = APIRouter(prefix="/api/v1/skills", tags=["skills"])

skill_loader = SkillLoader()
skill_discovery = SkillDiscovery(skill_loader)
skill_executor = SkillExecutor(skill_loader)
skill_orchestrator = SkillOrchestrator(skill_loader, skill_discovery, skill_executor)
flow_orchestrator = DialogueFlowOrchestrator(skill_executor)
state_manager = StateManager()


class SkillListResponse(BaseModel):
    skills: List[Dict[str, Any]]
    total: int


class SkillDetailResponse(BaseModel):
    name: str
    version: str
    description: str
    author: str
    category: str
    tags: List[str]
    dependencies: List[str]
    allowed_tools: List[str]
    operations: List[Dict[str, Any]]


class SkillExecuteRequest(BaseModel):
    skill_name: str
    operation: str
    input_data: Dict[str, Any] = Field(default_factory=dict)
    context: Optional[Dict[str, Any]] = None
    timeout: float = 30.0


class SkillExecuteResponse(BaseModel):
    success: bool
    result: Optional[Dict[str, Any]] = None
    error: Optional[str] = None
    execution_time: float


class DialogueRequest(BaseModel):
    message: str
    user_id: str
    session_id: Optional[str] = None
    conversation_id: Optional[str] = None
    flow_type: str = "standard"
    context: Optional[Dict[str, Any]] = None


class DialogueResponse(BaseModel):
    success: bool
    response: Optional[str] = None
    flow_id: Optional[str] = None
    flow_status: Optional[str] = None
    steps: List[Dict[str, Any]] = Field(default_factory=list)
    error: Optional[str] = None
    execution_time: float


class ChatRequest(BaseModel):
    message: str
    user_id: str = "test_user"
    session_id: Optional[str] = None
    conversation_id: Optional[str] = None


class ChatResponse(BaseModel):
    response: str
    session_id: str
    conversation_id: str


class StateRequest(BaseModel):
    state_type: str
    identifier: str
    key: Optional[str] = None
    value: Optional[Any] = None


class StateResponse(BaseModel):
    success: bool
    data: Optional[Any] = None
    error: Optional[str] = None


@router.on_event("startup")
async def startup():
    logger.info("initializing_skill_runtime")
    await skill_loader.discover_skills("/Users/anykong/Daisy_Demo/Daisy_skills/app/skills")
    await skill_discovery.build_index()
    logger.info("skill_runtime_initialized", skills_count=skill_discovery.get_skill_count())


@router.get("/list", response_model=SkillListResponse)
async def list_skills():
    try:
        skills = skill_discovery.get_all_skills()
        skill_list = []
        for metadata in skills:
            skill_list.append({
                "name": metadata.name,
                "version": metadata.version,
                "description": metadata.description,
                "category": metadata.category,
                "tags": metadata.tags,
                "author": metadata.author
            })
        return SkillListResponse(skills=skill_list, total=len(skill_list))
    except Exception as e:
        logger.error("list_skills_error", error=str(e))
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{skill_name}", response_model=SkillDetailResponse)
async def get_skill(skill_name: str):
    try:
        metadata = skill_discovery.get_skill(skill_name)
        if not metadata:
            raise HTTPException(status_code=404, detail=f"Skill {skill_name} not found")
        
        return SkillDetailResponse(
            name=metadata.name,
            version=metadata.version,
            description=metadata.description,
            author=metadata.author,
            category=metadata.category,
            tags=metadata.tags,
            dependencies=metadata.dependencies,
            allowed_tools=metadata.allowed_tools,
            operations=[
                {
                    "name": op.name,
                    "description": op.description,
                    "input_schema": op.input_schema,
                    "output_schema": op.output_schema
                }
                for op in metadata.instructions
            ]
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error("get_skill_error", skill_name=skill_name, error=str(e))
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/execute", response_model=SkillExecuteResponse)
async def execute_skill(request: SkillExecuteRequest):
    try:
        import time
        start_time = time.time()
        
        result = await skill_executor.execute(
            skill_name=request.skill_name,
            operation=request.operation,
            input_data=request.input_data,
            context=request.context or {}
        )
        
        execution_time = time.time() - start_time
        
        return SkillExecuteResponse(
            success=True,
            result=result,
            execution_time=execution_time
        )
    except Exception as e:
        logger.error("execute_skill_error", skill_name=request.skill_name, operation=request.operation, error=str(e))
        return SkillExecuteResponse(
            success=False,
            error=str(e),
            execution_time=0.0
        )


@router.post("/dialogue", response_model=DialogueResponse)
async def process_dialogue(request: DialogueRequest):
    try:
        import time
        import uuid
        start_time = time.time()
        
        session_id = request.session_id or str(uuid.uuid4())
        conversation_id = request.conversation_id or str(uuid.uuid4())
        flow_id = str(uuid.uuid4())
        
        await state_manager.create_session(session_id, request.user_id)
        await state_manager.create_conversation(conversation_id, session_id, request.user_id)
        
        await state_manager.add_message(conversation_id, "user", request.message)
        
        context_data = request.context or {}
        conversation = await state_manager.get_conversation(conversation_id)
        history_limit = context_data.get("history_limit", 8)
        history = conversation.get_recent_messages(history_limit) if conversation else []

        initial_input = {
            "user_input": request.message,
            "user_id": request.user_id,
            "session_id": session_id,
            "conversation_id": conversation_id,
            "context": context_data,
            "history": history,
            "latest_message": request.message,
            "language_hint": context_data.get("language_hint", "zh")
        }

        # Execute flow using SkillOrchestrator
        # We currently default to MAIN_DIALOGUE_FLOW regardless of request.flow_type
        # In the future we can select different flows based on request.flow_type
        
        final_state = await skill_orchestrator.execute_flow(
            MAIN_DIALOGUE_FLOW, 
            initial_input
        )
        
        response_data = final_state.get("response")
        response_content = ""
        if isinstance(response_data, dict):
            response_content = response_data.get("content", "")
        elif response_data:
            response_content = str(response_data)
        
        await state_manager.add_message(conversation_id, "assistant", response_content)
        
        execution_time = time.time() - start_time
        
        return DialogueResponse(
            success=True,
            response=response_content,
            flow_id=flow_id,
            flow_status="completed",
            steps=[], # SkillOrchestrator currently does not return execution trace
            execution_time=execution_time
        )
    except Exception as e:
        logger.error("process_dialogue_error", error=str(e))
        return DialogueResponse(
            success=False,
            error=str(e),
            execution_time=0.0
        )


@router.get("/flow/{flow_id}")
async def get_flow_status(flow_id: str):
    try:
        flow_result = flow_orchestrator.get_flow_status(flow_id)
        if not flow_result:
            raise HTTPException(status_code=404, detail=f"Flow {flow_id} not found")
        
        return {
            "flow_id": flow_result.flow_id,
            "status": flow_result.status.value,
            "steps": [
                {
                    "step_id": step.step_id,
                    "skill_name": step.skill_name,
                    "operation": step.operation,
                    "status": step.status.value,
                    "result": step.result,
                    "error": step.error
                }
                for step in flow_result.steps
            ],
            "final_result": flow_result.final_result,
            "error": flow_result.error,
            "execution_time": flow_result.execution_time
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error("get_flow_status_error", flow_id=flow_id, error=str(e))
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/state/get", response_model=StateResponse)
async def get_state(request: StateRequest):
    try:
        state_type = StateType(request.state_type)
        data = await state_manager.get_state(state_type, request.identifier, request.key)
        return StateResponse(success=True, data=data)
    except ValueError:
        raise HTTPException(status_code=400, detail=f"Invalid state type: {request.state_type}")
    except Exception as e:
        logger.error("get_state_error", error=str(e))
        return StateResponse(success=False, error=str(e))


@router.post("/state/set", response_model=StateResponse)
async def set_state(request: StateRequest):
    try:
        if request.key is None or request.value is None:
            raise HTTPException(status_code=400, detail="key and value are required")
        
        state_type = StateType(request.state_type)
        success = await state_manager.set_state(state_type, request.identifier, request.key, request.value)
        return StateResponse(success=success)
    except ValueError:
        raise HTTPException(status_code=400, detail=f"Invalid state type: {request.state_type}")
    except Exception as e:
        logger.error("set_state_error", error=str(e))
        return StateResponse(success=False, error=str(e))


@router.get("/session/{session_id}")
async def get_session(session_id: str):
    try:
        session = await state_manager.get_session(session_id)
        if not session:
            raise HTTPException(status_code=404, detail=f"Session {session_id} not found")
        
        return {
            "session_id": session.session_id,
            "user_id": session.user_id,
            "state": session.state,
            "created_at": session.created_at.isoformat(),
            "updated_at": session.updated_at.isoformat(),
            "last_activity": session.last_activity.isoformat()
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error("get_session_error", session_id=session_id, error=str(e))
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/conversation/{conversation_id}")
async def get_conversation(conversation_id: str):
    try:
        conversation = await state_manager.get_conversation(conversation_id)
        if not conversation:
            raise HTTPException(status_code=404, detail=f"Conversation {conversation_id} not found")
        
        return {
            "conversation_id": conversation.conversation_id,
            "session_id": conversation.session_id,
            "user_id": conversation.user_id,
            "messages": conversation.messages,
            "state": conversation.state,
            "created_at": conversation.created_at.isoformat(),
            "updated_at": conversation.updated_at.isoformat()
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error("get_conversation_error", conversation_id=conversation_id, error=str(e))
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/chat", response_model=ChatResponse)
async def chat_endpoint(request: ChatRequest):
    """
    Chat endpoint that uses LangGraph workflow with Agent Skills.
    """
    try:
        import time
        start_time = time.time()
        
        workflow = AgentWorkflow()
        result = await workflow.run(
            request.message,
            user_id=request.user_id,
            session_id=request.session_id,
            conversation_id=request.conversation_id
        )
        
        session_id = request.session_id or f"{request.user_id}_default"
        conversation_id = request.conversation_id or f"{session_id}_conv"
        
        return ChatResponse(
            response=result,
            session_id=session_id,
            conversation_id=conversation_id
        )
    except Exception as e:
        logger.error("chat_endpoint_error", error=str(e))
        raise HTTPException(status_code=500, detail=str(e))


__all__ = ["router"]
