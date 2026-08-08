from app.skills.persona.skill import select


async def execute(input_data, context):
    return await select(input_data, context)
