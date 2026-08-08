from app.skills.persona.skill import build_system_prompt


async def execute(input_data, context):
    return await build_system_prompt(input_data, context)
