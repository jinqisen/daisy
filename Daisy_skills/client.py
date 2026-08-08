import asyncio
import sys
import os
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

async def run():
    # 获取当前 Python 解释器路径
    python_executable = sys.executable
    server_script = os.path.join(os.path.dirname(__file__), "server.py")

    print(f"Connecting to MCP Server at: {server_script}...")

    # 定义 Server 启动参数 (Stdio 模式)
    server_params = StdioServerParameters(
        command=python_executable,
        args=[server_script],
        env=None
    )

    try:
        async with stdio_client(server_params) as (read, write):
            async with ClientSession(read, write) as session:
                # 1. 初始化连接
                await session.initialize()
                print("✅ Connected to MCP Server")

                # 2. 列出可用工具
                tools_response = await session.list_tools()
                print("\n📋 Available Tools:")
                for tool in tools_response.tools:
                    print(f"  - {tool.name}: {tool.description}")

                # 3. 调用工具: add
                print("\n🧪 Testing Tool: add(10, 5)")
                result_add = await session.call_tool("add", arguments={"a": 10, "b": 5})
                # MCP 返回的是 Content 列表
                print(f"  Result: {result_add.content[0].text}")

                # 4. 调用工具: calculate_bmi
                print("\n🧪 Testing Tool: calculate_bmi(70, 1.75)")
                result_bmi = await session.call_tool("calculate_bmi", arguments={"weight_kg": 70.0, "height_m": 1.75})
                print(f"  Result: {result_bmi.content[0].text}")
                
    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(run())
