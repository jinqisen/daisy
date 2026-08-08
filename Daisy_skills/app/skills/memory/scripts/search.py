from app.skills.memory.skill import search


async def execute(input_data, context):
    return await search(input_data, context)
