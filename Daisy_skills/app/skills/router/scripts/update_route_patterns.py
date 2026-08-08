from typing import Dict, Any, List
from runtime.models import SkillContext
from .intelligent_router import intelligent_router

async def execute(input_data: Dict[str, Any], context: SkillContext) -> Dict[str, Any]:
    patterns = input_data.get("patterns")
    
    if not isinstance(patterns, list):
        return {
            "error": "patterns must be a list of strings"
        }
        
    return intelligent_router.update_patterns(patterns)
