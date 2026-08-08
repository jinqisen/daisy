from typing import Dict, Any
from runtime.models import SkillContext
from .intelligent_router import intelligent_router

async def execute(input_data: Dict[str, Any], context: SkillContext) -> Dict[str, Any]:
    return intelligent_router.get_route_info()
