#!/usr/bin/env python3
"""
Daisy Skills MCP Server
提供 Agent Skills 工具的 MCP Server 实现
"""
from __future__ import annotations

import asyncio
import sys
import os
from pathlib import Path
from typing import Any

from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import Tool, TextContent

sys.path.insert(0, str(Path(__file__).parent))

from app.core.registry import registry
from app.core.config import settings
from app.core.logging import init_logging

init_logging(settings.LOG_LEVEL)

app = Server("daisy-skills-server")


async def register_all_tools():
    """注册所有 Agent Skills 工具到 MCP Server"""
    from app.skills.emotion.tool import register_emotion_tools
    from app.skills.memory.tool import register_memory_tools
    from app.skills.persona.tool import register_persona_tools
    from app.skills.topic.tool import register_topic_tools
    from app.skills.portrait.tool import register_portrait_tools
    from app.skills.toolhub.tool import register_toolhub_tools

    register_emotion_tools(registry)
    register_memory_tools(registry)
    register_persona_tools(registry)
    register_topic_tools(registry)
    register_portrait_tools(registry)
    register_toolhub_tools(registry)


def tool_spec_to_mcp_tool(spec: Any) -> Tool:
    """将 ToolSpec 转换为 MCP Tool"""
    return Tool(
        name=spec.name,
        description=spec.description,
        inputSchema=spec.input_model.model_json_schema()
    )


@app.list_tools()
async def list_tools() -> list[Tool]:
    """列出所有可用工具"""
    await register_all_tools()
    return [tool_spec_to_mcp_tool(spec) for spec in registry.list()]


@app.call_tool()
async def call_tool(name: str, arguments: dict[str, Any]) -> list[TextContent]:
    """调用指定工具"""
    await register_all_tools()
    
    tool_spec = None
    for spec in registry.list():
        if spec.name == name:
            tool_spec = spec
            break
    
    if tool_spec is None:
        raise ValueError(f"Tool not found: {name}")
    
    if tool_spec.admin and not settings.ADMIN_TOOLS_ENABLED:
        raise ValueError(f"Admin tool {name} is not enabled")
    
    result = await tool_spec.handler(arguments)
    
    return [TextContent(
        type="text",
        text=str(result)
    )]


async def main():
    """启动 MCP Server"""
    async with stdio_server() as (read_stream, write_stream):
        await app.run(
            read_stream,
            write_stream,
            app.create_initialization_options()
        )


if __name__ == "__main__":
    asyncio.run(main())
