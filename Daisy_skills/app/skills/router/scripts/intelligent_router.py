from typing import Dict, List, Optional, Any
import re
from pydantic import BaseModel, Field
from app.skills.router.scripts.patterns import pattern_manager
from app.skills.router.scripts.route_judge import route_judge, RouteResult

class RouteConfig(BaseModel):
    standard_threshold: float = Field(default=0.6, ge=0.0, le=1.0)
    deep_threshold: float = Field(default=0.8, ge=0.0, le=1.0)

class IntelligentRouter:
    def __init__(self, config: Optional[RouteConfig] = None):
        self.config = config or RouteConfig()
        self._compile_patterns()
    
    def _compile_patterns(self):
        patterns = pattern_manager.get_patterns()
        self._compiled_patterns = [
            re.compile(p, re.IGNORECASE) for p in patterns
        ]
    
    async def route_input(
        self,
        user_input: str,
        user_id: str,
        session_id: str,
        context: Optional[Dict[str, Any]] = None
    ) -> RouteResult:
        context = context or {}
        
        # 1. FAST Path Check (Regex)
        fast_result = self._check_fast_path(user_input)
        if fast_result:
            return fast_result
        
        # 2. LLM Judge (STANDARD vs DEEP)
        llm_result = await route_judge.judge_route(
            user_input=user_input,
            context=context
        )
        
        return llm_result
    
    def _check_fast_path(self, user_input: str) -> Optional[RouteResult]:
        stripped_input = user_input.strip()
        for pattern in self._compiled_patterns:
            if pattern.match(stripped_input):
                return RouteResult(
                    route="FAST",
                    confidence=1.0,
                    reasoning=f"Matched FAST pattern: {pattern.pattern}"
                )
        return None
    
    def update_patterns(self, patterns: List[str]) -> Dict[str, Any]:
        count = pattern_manager.update_patterns(patterns)
        self._compile_patterns()
        return {
            "success": True,
            "count": count
        }
    
    def get_route_info(self) -> Dict[str, Any]:
        return {
            "routes": ["FAST", "STANDARD", "DEEP"],
            "fast_patterns": pattern_manager.get_patterns(),
            "thresholds": {
                "standard": self.config.standard_threshold,
                "deep": self.config.deep_threshold
            }
        }

intelligent_router = IntelligentRouter()
