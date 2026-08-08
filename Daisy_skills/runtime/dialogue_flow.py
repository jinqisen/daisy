from typing import Any, Dict, List, Optional, Callable, Union
from enum import Enum
from dataclasses import dataclass, field
from datetime import datetime
import asyncio


class FlowType(Enum):
    SEQUENTIAL = "sequential"
    PARALLEL = "parallel"
    CONDITIONAL = "conditional"
    LOOP = "loop"


class FlowStatus(Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


@dataclass
class FlowStep:
    step_id: str
    skill_name: str
    operation: str
    input_data: Dict[str, Any] = field(default_factory=dict)
    condition: Optional[str] = None
    timeout: float = 30.0
    retry_count: int = 0
    max_retries: int = 3
    status: FlowStatus = FlowStatus.PENDING
    result: Optional[Dict[str, Any]] = None
    error: Optional[str] = None
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None


@dataclass
class DialogueContext:
    session_id: str
    user_id: str
    message: str
    history: List[Dict[str, Any]] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)
    state: Dict[str, Any] = field(default_factory=dict)
    created_at: datetime = field(default_factory=datetime.utcnow)


@dataclass
class FlowResult:
    flow_id: str
    status: FlowStatus
    steps: List[FlowStep]
    final_result: Optional[Dict[str, Any]] = None
    error: Optional[str] = None
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    execution_time: float = 0.0


class DialogueFlowOrchestrator:
    def __init__(self, skill_executor: Any):
        self.skill_executor = skill_executor
        self.flows: Dict[str, FlowResult] = {}
        self.flow_templates: Dict[str, Dict[str, Any]] = {}
        
    def register_flow_template(self, template_id: str, template: Dict[str, Any]) -> None:
        self.flow_templates[template_id] = template
        
    def get_flow_template(self, template_id: str) -> Optional[Dict[str, Any]]:
        return self.flow_templates.get(template_id)
        
    def create_flow(
        self,
        flow_id: str,
        flow_type: FlowType,
        steps: List[FlowStep],
        context: DialogueContext
    ) -> FlowResult:
        flow_result = FlowResult(
            flow_id=flow_id,
            status=FlowStatus.PENDING,
            steps=steps,
            started_at=datetime.utcnow()
        )
        self.flows[flow_id] = flow_result
        return flow_result
        
    async def execute_flow(
        self,
        flow_id: str,
        context: DialogueContext
    ) -> FlowResult:
        flow = self.flows.get(flow_id)
        if not flow:
            raise ValueError(f"Flow {flow_id} not found")
            
        flow.status = FlowStatus.RUNNING
        flow.started_at = datetime.utcnow()
        
        try:
            for step in flow.steps:
                if step.status == FlowStatus.COMPLETED:
                    continue
                    
                await self._execute_step(step, context)
                
                if step.status == FlowStatus.FAILED and step.retry_count < step.max_retries:
                    step.retry_count += 1
                    step.status = FlowStatus.PENDING
                    await self._execute_step(step, context)
                    
                if step.status == FlowStatus.FAILED:
                    flow.status = FlowStatus.FAILED
                    flow.error = f"Step {step.step_id} failed: {step.error}"
                    break
                    
            if flow.status != FlowStatus.FAILED:
                flow.status = FlowStatus.COMPLETED
                flow.final_result = self._aggregate_results(flow.steps)
                
        except Exception as e:
            flow.status = FlowStatus.FAILED
            flow.error = str(e)
            
        finally:
            flow.completed_at = datetime.utcnow()
            if flow.started_at:
                flow.execution_time = (flow.completed_at - flow.started_at).total_seconds()
                
        return flow
        
    async def _execute_step(self, step: FlowStep, context: DialogueContext) -> None:
        step.status = FlowStatus.RUNNING
        step.started_at = datetime.utcnow()
        
        try:
            input_data = self._prepare_step_input(step, context)
            
            result = await asyncio.wait_for(
                self.skill_executor.execute(
                    skill_name=step.skill_name,
                    operation=step.operation,
                    input_data=input_data,
                    context=context.metadata
                ),
                timeout=step.timeout
            )
            
            step.result = result
            step.status = FlowStatus.COMPLETED
            
            self._update_context_from_result(context, result)
            
        except asyncio.TimeoutError:
            step.status = FlowStatus.FAILED
            step.error = f"Step timeout after {step.timeout}s"
            
        except Exception as e:
            step.status = FlowStatus.FAILED
            step.error = str(e)
            
        finally:
            step.completed_at = datetime.utcnow()
            
    def _prepare_step_input(self, step: FlowStep, context: DialogueContext) -> Dict[str, Any]:
        input_data = step.input_data.copy()
        input_data["session_id"] = context.session_id
        input_data["user_id"] = context.user_id
        
        if "message" not in input_data:
            input_data["message"] = context.message
            
        if "history" not in input_data:
            input_data["history"] = context.history

        if step.skill_name == "emotion" and "text" not in input_data:
            input_data["text"] = context.message
        if step.skill_name == "emotion" and "context_history" not in input_data:
            input_data["context_history"] = context.history

        if step.skill_name == "memory" and step.operation == "search":
            if not input_data.get("query"):
                topic_summary = context.state.get("topic_summary", "")
                input_data["query"] = topic_summary or context.message
            if "limit" not in input_data:
                input_data["limit"] = 5

        if step.skill_name == "topic" and step.operation == "summarize":
            if "latest_message" not in input_data:
                input_data["latest_message"] = context.message
            
        input_data.update(context.state)
        
        return input_data
        
    def _update_context_from_result(self, context: DialogueContext, result: Dict[str, Any]) -> None:
        if result:
            for key, value in result.items():
                if key not in ["metadata", "timestamp"]:
                    context.state[key] = value
                    
    def _aggregate_results(self, steps: List[FlowStep]) -> Dict[str, Any]:
        aggregated = {}
        for step in steps:
            if step.result:
                aggregated[step.step_id] = step.result
        return aggregated
        
    def get_flow_status(self, flow_id: str) -> Optional[FlowResult]:
        return self.flows.get(flow_id)
        
    def cancel_flow(self, flow_id: str) -> bool:
        flow = self.flows.get(flow_id)
        if flow and flow.status == FlowStatus.RUNNING:
            flow.status = FlowStatus.CANCELLED
            flow.completed_at = datetime.utcnow()
            return True
        return False


class DialogueFlowBuilder:
    def __init__(self, flow_id: str, flow_type: FlowType = FlowType.SEQUENTIAL):
        self.flow_id = flow_id
        self.flow_type = flow_type
        self.steps: List[FlowStep] = []
        self._step_counter = 0
        
    def add_step(
        self,
        skill_name: str,
        operation: str,
        input_data: Optional[Dict[str, Any]] = None,
        condition: Optional[str] = None,
        timeout: float = 30.0,
        max_retries: int = 3
    ) -> "DialogueFlowBuilder":
        self._step_counter += 1
        step = FlowStep(
            step_id=f"step_{self._step_counter}",
            skill_name=skill_name,
            operation=operation,
            input_data=input_data or {},
            condition=condition,
            timeout=timeout,
            max_retries=max_retries
        )
        self.steps.append(step)
        return self
        
    def build(self) -> List[FlowStep]:
        return self.steps


class PredefinedFlows:
    @staticmethod
    def create_standard_dialogue_flow(flow_id: str) -> DialogueFlowBuilder:
        builder = DialogueFlowBuilder(flow_id, FlowType.SEQUENTIAL)
        builder.add_step("emotion", "analyze", timeout=10.0)
        builder.add_step("memory", "search", timeout=15.0)
        builder.add_step("persona", "select", timeout=10.0)
        builder.add_step("topic", "summarize", timeout=10.0)
        builder.add_step("portrait", "generate", timeout=10.0)
        return builder
        
    @staticmethod
    def create_quick_response_flow(flow_id: str) -> DialogueFlowBuilder:
        builder = DialogueFlowBuilder(flow_id, FlowType.SEQUENTIAL)
        builder.add_step("emotion", "analyze", timeout=10.0)
        builder.add_step("persona", "select", timeout=10.0)
        return builder
        
    @staticmethod
    def create_context_aware_flow(flow_id: str) -> DialogueFlowBuilder:
        builder = DialogueFlowBuilder(flow_id, FlowType.SEQUENTIAL)
        builder.add_step("memory", "search", timeout=15.0)
        builder.add_step("emotion", "analyze", timeout=10.0)
        builder.add_step("topic", "summarize", timeout=10.0)
        builder.add_step("persona", "select", timeout=10.0)
        builder.add_step("portrait", "generate", timeout=10.0)
        return builder


__all__ = [
    "FlowType",
    "FlowStatus",
    "FlowStep",
    "DialogueContext",
    "FlowResult",
    "DialogueFlowOrchestrator",
    "DialogueFlowBuilder",
    "PredefinedFlows"
]
