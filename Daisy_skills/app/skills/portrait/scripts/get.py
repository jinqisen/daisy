import sys
from pathlib import Path

skill_dir = Path(__file__).parent.parent
sys.path.insert(0, str(skill_dir))

from skill import get


async def execute(input_data, context):
    return await get(input_data, context)
