from app.skills.portrait.skill import generate


async def execute(input_data, context):
    return await generate(input_data, context)
