import structlog
import aiohttp
import json
from typing import Dict, Any, Optional
from app.core.config import settings

logger = structlog.get_logger()

class BaseTool:
    name: str
    description: str

    async def run(self, query: str) -> str:
        raise NotImplementedError

class SearchTool(BaseTool):
    name = "search"
    description = "Use this tool to search for real-time information, such as weather, news, or movie ratings. Input should be a search query."

    async def run(self, query: str) -> str:
        logger.info(f"Executing SearchTool (Huawei Cloud) with query: {query}")
        
        # 优先使用配置的 HUAWEI_SEARCH_API_KEY
        api_key = settings.HUAWEI_SEARCH_API_KEY
        endpoint = settings.HUAWEI_SEARCH_ENDPOINT or "https://cbs-ext.cn-southwest-2.myhuaweicloud.com/v1/ai-tools/web-search"
        
        if not api_key:
            logger.error("HUAWEI_SEARCH_API_KEY not configured. Search functionality is disabled.")
            raise ValueError("HUAWEI_SEARCH_API_KEY not configured.")

        try:
            async with aiohttp.ClientSession() as session:
                payload = {
                    "query": query,
                    "freshness": "noLimit",
                    "count": 3
                }
                headers = {
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json;charset=UTF-8"
                }
                
                async with session.post(endpoint, json=payload, headers=headers) as response:
                    if response.status == 200:
                        data = await response.json()
                        return self._format_results(data)
                    else:
                        error_text = await response.text()
                        logger.error(f"Huawei Search API Error: {response.status} - {error_text}")
                        return f"Error: Search API returned status {response.status}"
                        
        except Exception as e:
            logger.error(f"Huawei Search Tool execution failed: {e}")
            return f"Error executing search: {e}"

    def _format_results(self, data: Dict[str, Any]) -> str:
        """Format Huawei Search results into a readable string."""
        # 1. Check for box_result (Direct Answer)
        box_result = data.get("box_result")
        formatted = ""
        
        if box_result:
            formatted += f"**Direct Answer**: {box_result}\n\n"
            
        # 2. Process web_pages
        web_pages = data.get("web_pages", [])
        if web_pages:
            formatted += "**Web Results**:\n"
            for i, page in enumerate(web_pages[:3], 1):
                title = page.get("title", "No Title")
                summary = page.get("summary", "No Summary")
                site_name = page.get("site_name", "")
                
                formatted += f"{i}. [{site_name}] {title}\n"
                formatted += f"   Summary: {summary}\n"
        
        if not formatted:
            return "No relevant search results found."
            
        return formatted

class CalculatorTool(BaseTool):
    name = "calculator"
    description = "Use this tool for mathematical calculations. Input should be a mathematical expression."

    async def run(self, query: str) -> str:
        logger.info(f"Executing CalculatorTool with query: {query}")
        try:
            # Safe evaluation is hard, using simple eval for demo but restrict chars
            allowed = set("0123456789+-*/(). ")
            if not all(c in allowed for c in query):
                return "Error: Invalid characters in expression."
            return str(eval(query, {"__builtins__": None}, {}))
        except Exception as e:
            return f"Error calculating: {e}"

# Tool Registry
AVAILABLE_TOOLS = {
    "search": SearchTool(),
    "calculator": CalculatorTool()
}

def get_tool_descriptions() -> str:
    desc = []
    for tool in AVAILABLE_TOOLS.values():
        desc.append(f"- {tool.name}: {tool.description}")
    return "\n".join(desc)
