from __future__ import annotations

import json
import asyncio

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client


async def _list_tools():
    server_params = StdioServerParameters(
        command="python",
        args=["-u", "server.py"],
        env={
            "ADMIN_TOOLS_ENABLED": "true",
            "ADMIN_TOKENS": "test-token",
        },
    )
    async with stdio_client(server_params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            return await session.list_tools()


def test_tool_names_include_required():
    tools = asyncio.run(_list_tools())
    names = {tool.name for tool in tools.tools}
    required = {
        "emotion.analyze",
        "emotion.update_config",
        "memory.search",
        "memory.add",
        "memory.update_policy",
        "persona.select",
        "persona.update_strategy",
        "topic.summarize",
        "portrait.generate",
        "toolhub.search",
        "toolhub.calculate",
    }
    assert required.issubset(names)
