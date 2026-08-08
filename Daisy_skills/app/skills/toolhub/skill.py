from typing import Any, Dict, List, Optional
from datetime import datetime
import aiohttp


async def search(input_data: Dict[str, Any], context: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    query = input_data.get("query", "")
    top_k = input_data.get("top_k", 5)
    locale = input_data.get("locale", "zh")
    
    api_key = None
    endpoint = "https://cbs-ext.cn-southwest-2.myhuaweicloud.com/v1/ai-tools/web-search"
    
    results = []
    
    if api_key:
        try:
            async with aiohttp.ClientSession() as session:
                payload = {"query": query, "freshness": "noLimit", "count": top_k}
                headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json;charset=UTF-8"}
                async with session.post(endpoint, json=payload, headers=headers) as response:
                    if response.status == 200:
                        data = await response.json()
                        for page in data.get("web_pages", [])[:top_k]:
                            results.append({
                                "title": page.get("title", ""),
                                "summary": page.get("summary", ""),
                                "site_name": page.get("site_name", ""),
                                "url": page.get("url", ""),
                            })
        except Exception:
            pass
    
    if not results:
        results = [
            {
                "title": f"搜索结果: {query}",
                "summary": f"这是关于 '{query}' 的模拟搜索结果。实际搜索需要配置 API 密钥。",
                "site_name": "模拟结果",
                "url": f"https://example.com/search?q={query}",
            }
        ]
    
    return {
        "results": results,
        "query_used": query,
        "total_count": len(results),
        "metadata": {
            "top_k": top_k,
            "locale": locale,
            "timestamp": datetime.utcnow().isoformat()
        }
    }


async def calculate(input_data: Dict[str, Any], context: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    expression = input_data.get("expression", "")
    
    allowed = set("0123456789+-*/(). ")
    
    if not all(c in allowed for c in expression):
        return {
            "value": None,
            "expression": expression,
            "error": "Invalid characters in expression",
            "metadata": {
                "timestamp": datetime.utcnow().isoformat()
            }
        }
    
    try:
        result = eval(expression, {"__builtins__": None}, {})
        return {
            "value": str(result),
            "expression": expression,
            "metadata": {
                "timestamp": datetime.utcnow().isoformat()
            }
        }
    except Exception as e:
        return {
            "value": None,
            "expression": expression,
            "error": str(e),
            "metadata": {
                "timestamp": datetime.utcnow().isoformat()
            }
        }


async def weather(input_data: Dict[str, Any], context: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    location = input_data.get("location", "")
    days = input_data.get("days", 1)
    
    weather_data = {
        "location": location,
        "current": {
            "temperature": 25,
            "condition": "晴",
            "humidity": 60,
            "wind": "微风"
        },
        "forecast": [
            {
                "date": "今天",
                "temperature": "18-26°C",
                "condition": "晴"
            },
            {
                "date": "明天",
                "temperature": "17-25°C",
                "condition": "多云"
            }
        ][:days]
    }
    
    return {
        "weather": weather_data,
        "location": location,
        "metadata": {
            "days": days,
            "timestamp": datetime.utcnow().isoformat()
        }
    }


__all__ = ["search", "calculate", "weather"]
