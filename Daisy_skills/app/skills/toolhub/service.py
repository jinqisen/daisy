from __future__ import annotations

from typing import Any, Dict, List
import aiohttp

from ...core.config import settings


async def search_web(query: str, top_k: int) -> List[Dict[str, Any]]:
    api_key = settings.HUAWEI_SEARCH_API_KEY
    endpoint = settings.HUAWEI_SEARCH_ENDPOINT or "https://cbs-ext.cn-southwest-2.myhuaweicloud.com/v1/ai-tools/web-search"
    if not api_key:
        return []
    async with aiohttp.ClientSession() as session:
        payload = {"query": query, "freshness": "noLimit", "count": top_k}
        headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json;charset=UTF-8"}
        async with session.post(endpoint, json=payload, headers=headers) as response:
            if response.status != 200:
                return []
            data = await response.json()
            results = []
            for page in data.get("web_pages", [])[:top_k]:
                results.append(
                    {
                        "title": page.get("title", ""),
                        "summary": page.get("summary", ""),
                        "site_name": page.get("site_name", ""),
                        "url": page.get("url"),
                    }
                )
            return results


def calculate_expression(expression: str) -> str:
    allowed = set("0123456789+-*/(). ")
    if not all(c in allowed for c in expression):
        raise ValueError("Invalid characters in expression")
    return str(eval(expression, {"__builtins__": None}, {}))
