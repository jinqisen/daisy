import asyncio
import importlib.util
import sys
from pathlib import Path
from typing import Any, Dict, Optional, Callable, List
from datetime import datetime
import time

from .loader import SkillLoader
from .models import (
    Skill,
    SkillContext,
    SkillResult,
    ExecutionConfig,
    SkillResource,
    ResourceType
)
from .errors import (
    SkillNotFoundError,
    SkillExecutionError,
    SkillTimeoutError,
    SkillResourceError
)
from .state_manager import StateManager, StateType


class SkillExecutor:
    def __init__(
        self,
        loader: SkillLoader,
        config: Optional[ExecutionConfig] = None,
        state_manager: Optional[StateManager] = None
    ):
        self.loader = loader
        self.config = config or ExecutionConfig()
        self.state_manager = state_manager
        self._script_cache: Dict[str, Callable] = {}
        self._pre_execution_hooks: List[Callable] = []
        self._post_execution_hooks: List[Callable] = []

    async def execute(
        self,
        skill_name: str,
        operation: str,
        input_data: Dict[str, Any],
        context: Optional[SkillContext] = None
    ) -> SkillResult:
        start_time = time.time()

        try:
            skill = self.loader.load_skill(skill_name)

            script_func = self._load_script_function(skill, operation)

            if context is None:
                context = SkillContext(
                    user_id=input_data.get('user_id', 'anonymous'),
                    session_id=input_data.get('session_id', 'default'),
                    conversation_id=input_data.get('conversation_id')
                )

            await self._call_pre_execution_hooks(skill_name, operation, input_data, context)

            result = await self._execute_with_timeout(
                script_func,
                input_data,
                context
            )

            execution_time = time.time() - start_time

            skill_result = SkillResult(
                success=True,
                data=result,
                execution_time=execution_time,
                metadata={
                    "skill_name": skill_name,
                    "operation": operation,
                    "timestamp": datetime.utcnow().isoformat()
                }
            )

            await self._call_post_execution_hooks(skill_name, operation, skill_result, context)

            if self.state_manager and context.session_id:
                await self.state_manager.update_session(
                    context.session_id,
                    {
                        f"last_skill_execution": {
                            "skill": skill_name,
                            "operation": operation,
                            "success": True,
                            "timestamp": datetime.utcnow().isoformat()
                        }
                    }
                )

            return skill_result

        except asyncio.TimeoutError:
            execution_time = time.time() - start_time
            error_result = SkillResult(
                success=False,
                data=None,
                error=f"Operation '{operation}' on skill '{skill_name}' timed out after {self.config.timeout_sec} seconds",
                execution_time=execution_time,
                metadata={
                    "skill_name": skill_name,
                    "operation": operation,
                    "timeout_sec": self.config.timeout_sec
                }
            )
            await self._call_post_execution_hooks(skill_name, operation, error_result, context)
            return error_result

        except SkillNotFoundError as e:
            execution_time = time.time() - start_time
            error_result = SkillResult(
                success=False,
                data=None,
                error=e.message,
                metadata={"code": e.code, "details": e.details}
            )
            await self._call_post_execution_hooks(skill_name, operation, error_result, context)
            return error_result

        except Exception as e:
            execution_time = time.time() - start_time
            error_result = SkillResult(
                success=False,
                data=None,
                error=str(e),
                execution_time=execution_time,
                metadata={
                    "skill_name": skill_name,
                    "operation": operation,
                    "error_type": type(e).__name__
                }
            )
            await self._call_post_execution_hooks(skill_name, operation, error_result, context)
            return error_result

    def _load_script_function(self, skill: Skill, operation: str) -> Callable:
        cache_key = f"{skill.metadata.name}:{operation}"

        if cache_key in self._script_cache:
            return self._script_cache[cache_key]

        script_path = None
        for resource in skill.resources:
            if resource.type == ResourceType.SCRIPT and resource.name == operation:
                script_path = Path(resource.path)
                break

        if not script_path or not script_path.exists():
            raise SkillResourceError(
                skill.metadata.name,
                f"scripts/{operation}.py",
                f"Script for operation '{operation}' not found"
            )

        spec = importlib.util.spec_from_file_location(
            f"{skill.metadata.name}_{operation}",
            script_path
        )

        if spec is None or spec.loader is None:
            raise SkillResourceError(
                skill.metadata.name,
                str(script_path),
                "Failed to load script module"
            )

        module = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = module
        spec.loader.exec_module(module)

        if not hasattr(module, 'execute'):
            raise SkillExecutionError(
                skill.metadata.name,
                operation,
                "Script module must have an 'execute' function"
            )

        execute_func = getattr(module, 'execute')
        self._script_cache[cache_key] = execute_func

        return execute_func

    async def _execute_with_timeout(
        self,
        func: Callable,
        input_data: Dict[str, Any],
        context: SkillContext
    ) -> Any:
        try:
            if asyncio.iscoroutinefunction(func):
                result = await asyncio.wait_for(
                    func(input_data, context),
                    timeout=self.config.timeout_sec
                )
            else:
                result = await asyncio.get_event_loop().run_in_executor(
                    None,
                    lambda: func(input_data, context)
                )

            return result

        except asyncio.TimeoutError:
            raise SkillTimeoutError(
                context.metadata.get("skill_name", "unknown"),
                context.metadata.get("operation", "unknown"),
                self.config.timeout_sec
            )

    def execute_sync(
        self,
        skill_name: str,
        operation: str,
        input_data: Dict[str, Any],
        context: Optional[SkillContext] = None
    ) -> SkillResult:
        return asyncio.run(self.execute(skill_name, operation, input_data, context))

    def clear_cache(self):
        self._script_cache.clear()

    def get_cached_operations(self, skill_name: str) -> list:
        operations = []
        prefix = f"{skill_name}:"
        for key in self._script_cache:
            if key.startswith(prefix):
                operations.append(key[len(prefix):])
        return operations

    def register_pre_execution_hook(self, hook: Callable) -> None:
        self._pre_execution_hooks.append(hook)

    def register_post_execution_hook(self, hook: Callable) -> None:
        self._post_execution_hooks.append(hook)

    async def _call_pre_execution_hooks(
        self,
        skill_name: str,
        operation: str,
        input_data: Dict[str, Any],
        context: SkillContext
    ) -> None:
        for hook in self._pre_execution_hooks:
            try:
                if asyncio.iscoroutinefunction(hook):
                    await hook(skill_name, operation, input_data, context)
                else:
                    hook(skill_name, operation, input_data, context)
            except Exception:
                pass

    async def _call_post_execution_hooks(
        self,
        skill_name: str,
        operation: str,
        result: SkillResult,
        context: Optional[SkillContext] = None
    ) -> None:
        for hook in self._post_execution_hooks:
            try:
                if asyncio.iscoroutinefunction(hook):
                    await hook(skill_name, operation, result, context)
                else:
                    hook(skill_name, operation, result, context)
            except Exception:
                pass

    async def get_state(
        self,
        state_type: StateType,
        identifier: str,
        key: Optional[str] = None,
        default: Any = None
    ) -> Any:
        if self.state_manager:
            return await self.state_manager.get_state(state_type, identifier, key, default)
        return default

    async def set_state(
        self,
        state_type: StateType,
        identifier: str,
        key: str,
        value: Any
    ) -> bool:
        if self.state_manager:
            return await self.state_manager.set_state(state_type, identifier, key, value)
        return False
