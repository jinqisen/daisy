import asyncio
from typing import Any, Dict, List, Optional, Callable
from datetime import datetime
import json

from .loader import SkillLoader
from .discovery import SkillDiscovery
from .executor import SkillExecutor
from .models import (
    SkillContext,
    SkillResult,
    ExecutionConfig
)
from .errors import (
    SkillNotFoundError,
    SkillExecutionError
)


class SkillOrchestrator:
    def __init__(
        self,
        loader: SkillLoader,
        discovery: SkillDiscovery,
        executor: SkillExecutor
    ):
        self.loader = loader
        self.discovery = discovery
        self.executor = executor

    async def execute_flow(
        self,
        flow_definition: Dict[str, Any],
        initial_input: Dict[str, Any],
        context: Optional[SkillContext] = None
    ) -> Dict[str, Any]:
        """
        Executes a complex flow defined by a dictionary.
        
        Args:
            flow_definition: Dict defining the flow structure
            initial_input: Initial input data
            context: SkillContext
            
        Returns:
            Final state dictionary
        """
        current_state = initial_input.copy()
        
        flow_type = flow_definition.get("type", "chain")
        
        try:
            if flow_type == "chain":
                steps = flow_definition.get("steps", [])
                await self._execute_chain_steps(steps, current_state, context)
                
            elif flow_type == "parallel":
                tasks = flow_definition.get("tasks", [])
                await self._execute_parallel_tasks(tasks, current_state, context)
                
            elif flow_type == "switch":
                router_step = flow_definition.get("router")
                if not router_step:
                    raise ValueError("Switch flow requires a 'router' definition")
                
                # Execute router step first
                await self._execute_step(router_step, current_state, context)
                
                # Get route key from state
                route_key = router_step.get("output_key", "route")
                route_value = current_state.get(route_key)
                
                if isinstance(route_value, dict):
                    # Handle case where route output is a dict (e.g. from Router Skill)
                    route_value = route_value.get("route")
                
                # Find matching branch
                cases = flow_definition.get("cases", {})
                branch = cases.get(route_value) or flow_definition.get("default")
                
                if branch:
                    branch_result = await self.execute_flow(branch, current_state, context)
                    current_state.update(branch_result)
                    
            elif flow_type == "skill":
                await self._execute_step(flow_definition, current_state, context)
                
            else:
                raise ValueError(f"Unknown flow type: {flow_type}")
                
            return current_state
            
        except Exception as e:
            # Log error
            print(f"Flow execution error: {e}")
            current_state["error"] = str(e)
            return current_state

    async def _execute_chain_steps(
        self, 
        steps: List[Dict[str, Any]], 
        state: Dict[str, Any], 
        context: Optional[SkillContext]
    ):
        for step in steps:
            # Check if step is a nested flow
            if "type" in step and step["type"] != "skill":
                step_result = await self.execute_flow(step, state, context)
                state.update(step_result)
            else:
                # It's a skill step
                await self._execute_step(step, state, context)
                
            # Check for stop condition
            if state.get("_stop_flow"):
                break

    async def _execute_parallel_tasks(
        self,
        tasks: List[Dict[str, Any]],
        state: Dict[str, Any],
        context: Optional[SkillContext]
    ):
        async def run_task(task):
            # Create a localized state copy for the parallel task to avoid race conditions
            # Note: This means parallel tasks can't easily modify shared state 
            # effectively without a merge strategy.
            # For simplicity, we assume they return distinct outputs.
            local_state = state.copy()
            if "type" in task and task["type"] != "skill":
                return await self.execute_flow(task, local_state, context)
            else:
                await self._execute_step(task, local_state, context)
                return local_state

        results = await asyncio.gather(*[run_task(task) for task in tasks])
        
        # Merge results back into main state
        # Simple merge: overwrite keys. Last one wins if conflicts.
        for result_state in results:
            for k, v in result_state.items():
                if k not in state or state[k] != v:
                    state[k] = v

    async def _execute_step(
        self,
        step: Dict[str, Any],
        state: Dict[str, Any],
        context: Optional[SkillContext]
    ):
        skill_name = step.get("skill")
        operation = step.get("operation")
        
        # Map inputs from state
        input_mapping = step.get("inputs", {})
        input_data = {}
        
        # 1. Copy explicit constant inputs
        if "params" in step:
            input_data.update(step["params"])
            
        # 2. Map from state variables
        for param_name, state_key in input_mapping.items():
            if state_key in state:
                input_data[param_name] = state[state_key]
            # Handle nested keys with dot notation (e.g. "user.id")
            elif "." in state_key:
                parts = state_key.split(".")
                value = state
                found = True
                for part in parts:
                    if isinstance(value, dict) and part in value:
                        value = value[part]
                    else:
                        found = False
                        break
                if found:
                    input_data[param_name] = value

        # 3. If no mapping provided, pass all state (optional, can be risky)
        if not input_mapping and not step.get("params"):
             input_data.update(state)

        # Execute
        result = await self.executor.execute(
            skill_name,
            operation,
            input_data,
            context
        )
        
        if not result.success:
            print(f"ERROR: Skill {skill_name}.{operation} failed: {result.error}")
        
        # Handle Output
        if result.success:
            output_key = step.get("output_key")
            if output_key:
                state[output_key] = result.data
            elif isinstance(result.data, dict):
                # If no specific key, merge dict output into state
                state.update(result.data)
        else:
            if step.get("stop_on_error", False):
                state["_stop_flow"] = True
                state["error"] = result.error
            # Else continue? Usually we want to at least log.
