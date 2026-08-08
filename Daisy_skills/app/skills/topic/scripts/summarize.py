from app.skills.topic.skill import summarize


async def execute(input_data, context):
    return await summarize(input_data, context)
