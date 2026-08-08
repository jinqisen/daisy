import asyncio
import httpx
import json
from typing import List, Dict, Any
from datetime import datetime


class DialogueTestClient:
    def __init__(self, base_url: str):
        self.base_url = base_url
        self.client = httpx.AsyncClient(timeout=60.0)

    async def close(self):
        await self.client.aclose()


class DaisyServerClient(DialogueTestClient):
    def __init__(self, base_url: str, username: str = "jinqisen", password: str = "Hello!2025"):
        super().__init__(base_url)
        self.username = username
        self.password = password
        self._token = None

    async def _get_token(self) -> str:
        if self._token:
            return self._token
        
        url = f"{self.base_url}/api/auth/login"
        payload = {
            "username": self.username,
            "password": self.password
        }
        
        response = await self.client.post(url, data=payload)
        data = response.json()
        self._token = data.get("access_token")
        return self._token

    async def _get_headers(self, token: str | None = None) -> Dict[str, str]:
        headers = {}
        auth_token = token or await self._get_token()
        if auth_token:
            headers["Authorization"] = f"Bearer {auth_token}"
        return headers

    async def get_history(self, limit: int = 50, mode: str = "count") -> List[Dict[str, Any]]:
        url = f"{self.base_url}/api/chat/history"
        headers = await self._get_headers()
        response = await self.client.get(url, params={"limit": limit, "mode": mode}, headers=headers)
        return response.json()

    async def get_ai_response_after(self, user_message_id: int, retries: int = 20, delay_seconds: float = 2.0) -> str | None:
        for _ in range(retries):
            history = await self.get_history(limit=100, mode="count")
            target = next((item for item in history if item.get("id") == user_message_id), None)
            session_id = target.get("session_id") if target else None
            candidates = [
                item
                for item in history
                if item.get("role") == "ai"
                and item.get("id", 0) > user_message_id
                and (session_id is None or item.get("session_id") == session_id)
            ]
            candidates.sort(key=lambda item: item.get("id", 0))
            if candidates:
                return candidates[0].get("content")
            await asyncio.sleep(delay_seconds)
        return None

    async def chat(self, message: str, user_id: str = "test_user", token: str = None) -> Dict[str, Any]:
        url = f"{self.base_url}/api/chat"
        headers = await self._get_headers(token)
        
        payload = {
            "message": message
        }
        
        response = await self.client.post(url, json=payload, headers=headers)
        return response.json()


class DaisySkillsClient(DialogueTestClient):
    async def chat(self, message: str, user_id: str = "test_user", session_id: str = None, conversation_id: str = None) -> Dict[str, Any]:
        url = f"{self.base_url}/api/v1/skills/chat"
        
        payload = {
            "message": message,
            "user_id": user_id
        }
        
        if session_id:
            payload["session_id"] = session_id
        if conversation_id:
            payload["conversation_id"] = conversation_id
        
        response = await self.client.post(url, json=payload)
        return response.json()


class DialogueComparisonTest:
    def __init__(self, daisy_server_url: str, daisy_skills_url: str):
        self.daisy_server = DaisyServerClient(daisy_server_url)
        self.daisy_skills = DaisySkillsClient(daisy_skills_url)
        self.results = []

    async def close(self):
        await self.daisy_server.close()
        await self.daisy_skills.close()

    async def test_single_message(self, test_case: Dict[str, Any]) -> Dict[str, Any]:
        message = test_case["message"]
        user_id = test_case.get("user_id", "test_user")
        expected_type = test_case.get("expected_type", "standard")
        
        print(f"\n{'='*60}")
        print(f"测试用例: {test_case.get('name', '未命名')}")
        print(f"消息: {message}")
        print(f"期望类型: {expected_type}")
        print(f"{'='*60}")
        
        result = {
            "test_case": test_case,
            "timestamp": datetime.now().isoformat(),
            "daisy_server": None,
            "daisy_skills": None,
            "comparison": None
        }
        
        try:
            print("\n[Daisy Server] 发送请求...")
            server_response = await self.daisy_server.chat(message, user_id)
            print(f"[Daisy Server] 响应: {json.dumps(server_response, ensure_ascii=False, indent=2)}")
            user_message_id = server_response.get("data", {}).get("user_message_id")
            final_response = None
            if user_message_id:
                final_response = await self.daisy_server.get_ai_response_after(user_message_id)
            if final_response:
                print(f"[Daisy Server] 最终回复: {final_response}")
            result["daisy_server"] = {
                "success": True,
                "response": server_response,
                "final_response": final_response
            }
        except Exception as e:
            print(f"[Daisy Server] 错误: {e}")
            result["daisy_server"] = {
                "success": False,
                "error": str(e)
            }
        
        try:
            print("\n[Daisy Skills] 发送请求...")
            skills_response = await self.daisy_skills.chat(message, user_id)
            print(f"[Daisy Skills] 响应: {json.dumps(skills_response, ensure_ascii=False, indent=2)}")
            result["daisy_skills"] = {
                "success": True,
                "response": skills_response
            }
        except Exception as e:
            print(f"[Daisy Skills] 错误: {e}")
            result["daisy_skills"] = {
                "success": False,
                "error": str(e)
            }
        
        result["comparison"] = self._compare_responses(result["daisy_server"], result["daisy_skills"])
        
        print(f"\n[对比结果] {result['comparison']['summary']}")
        
        return result

    async def test_conversation_flow(self, test_case: Dict[str, Any]) -> Dict[str, Any]:
        messages = test_case["messages"]
        user_id = test_case.get("user_id", "test_user")
        
        print(f"\n{'='*60}")
        print(f"对话流测试: {test_case.get('name', '未命名')}")
        print(f"消息数: {len(messages)}")
        print(f"{'='*60}")
        
        result = {
            "test_case": test_case,
            "timestamp": datetime.now().isoformat(),
            "daisy_server": [],
            "daisy_skills": [],
            "comparison": None
        }
        
        session_id = f"{user_id}_test_{datetime.now().timestamp()}"
        conversation_id = f"{session_id}_conv"
        
        for i, message in enumerate(messages):
            print(f"\n--- 消息 {i+1}/{len(messages)}: {message} ---")
            
            try:
                print("[Daisy Server] 发送请求...")
                server_response = await self.daisy_server.chat(message, user_id)
                print(f"[Daisy Server] 响应: {json.dumps(server_response, ensure_ascii=False, indent=2)}")
                user_message_id = server_response.get("data", {}).get("user_message_id")
                final_response = None
                if user_message_id:
                    final_response = await self.daisy_server.get_ai_response_after(user_message_id)
                if final_response:
                    print(f"[Daisy Server] 最终回复: {final_response}")
                result["daisy_server"].append({
                    "message": message,
                    "success": True,
                    "response": server_response,
                    "final_response": final_response
                })
            except Exception as e:
                print(f"[Daisy Server] 错误: {e}")
                result["daisy_server"].append({
                    "message": message,
                    "success": False,
                    "error": str(e)
                })
            
            try:
                print("[Daisy Skills] 发送请求...")
                skills_response = await self.daisy_skills.chat(message, user_id, session_id, conversation_id)
                print(f"[Daisy Skills] 响应: {json.dumps(skills_response, ensure_ascii=False, indent=2)}")
                result["daisy_skills"].append({
                    "message": message,
                    "success": True,
                    "response": skills_response
                })
            except Exception as e:
                print(f"[Daisy Skills] 错误: {e}")
                result["daisy_skills"].append({
                    "message": message,
                    "success": False,
                    "error": str(e)
                })
        
        result["comparison"] = self._compare_conversation_flows(result["daisy_server"], result["daisy_skills"])
        
        print(f"\n[对话流对比结果] {result['comparison']['summary']}")
        
        return result

    def _compare_responses(self, server_result: Dict, skills_result: Dict) -> Dict[str, Any]:
        comparison = {
            "both_success": False,
            "both_failed": False,
            "server_success": False,
            "skills_success": False,
            "summary": ""
        }
        
        server_success = server_result.get("success", False)
        skills_success = skills_result.get("success", False)
        
        comparison["server_success"] = server_success
        comparison["skills_success"] = skills_success
        comparison["both_success"] = server_success and skills_success
        comparison["both_failed"] = not server_success and not skills_success
        
        if comparison["both_success"]:
            comparison["summary"] = "两个服务都成功响应"
        elif comparison["both_failed"]:
            comparison["summary"] = "两个服务都失败"
        elif server_success:
            comparison["summary"] = "仅 Daisy Server 成功"
        else:
            comparison["summary"] = "仅 Daisy Skills 成功"
        
        return comparison

    def _compare_conversation_flows(self, server_flow: List, skills_flow: List) -> Dict[str, Any]:
        comparison = {
            "total_messages": len(server_flow),
            "server_success_count": sum(1 for r in server_flow if r.get("success", False)),
            "skills_success_count": sum(1 for r in skills_flow if r.get("success", False)),
            "summary": ""
        }
        
        if comparison["server_success_count"] == comparison["skills_success_count"] == len(server_flow):
            comparison["summary"] = "两个服务在所有消息上都成功响应"
        elif comparison["skills_success_count"] > comparison["server_success_count"]:
            comparison["summary"] = f"Daisy Skills 成功率更高 ({comparison['skills_success_count']}/{len(server_flow)} vs {comparison['server_success_count']}/{len(server_flow)})"
        elif comparison["server_success_count"] > comparison["skills_success_count"]:
            comparison["summary"] = f"Daisy Server 成功率更高 ({comparison['server_success_count']}/{len(server_flow)} vs {comparison['skills_success_count']}/{len(server_flow)})"
        else:
            comparison["summary"] = f"两个服务成功率相同 ({comparison['skills_success_count']}/{len(server_flow)})"
        
        return comparison

    async def run_all_tests(self, test_cases: List[Dict[str, Any]]) -> Dict[str, Any]:
        print(f"\n{'#'*60}")
        print(f"# 开始对话能力对比测试")
        print(f"# Daisy Server: {self.daisy_server.base_url}")
        print(f"# Daisy Skills: {self.daisy_skills.base_url}")
        print(f"# 测试用例数: {len(test_cases)}")
        print(f"{'#'*60}")
        
        all_results = []
        
        for test_case in test_cases:
            if "messages" in test_case:
                result = await self.test_conversation_flow(test_case)
            else:
                result = await self.test_single_message(test_case)
            all_results.append(result)
        
        summary = self._generate_summary(all_results)
        
        print(f"\n{'#'*60}")
        print(f"# 测试总结")
        print(f"{'#'*60}")
        print(json.dumps(summary, ensure_ascii=False, indent=2))
        
        return {
            "results": all_results,
            "summary": summary
        }

    def _generate_summary(self, results: List[Dict]) -> Dict[str, Any]:
        total_tests = len(results)

        def is_success(entry: Any) -> bool:
            if isinstance(entry, list):
                return all(item.get("success", False) for item in entry)
            if isinstance(entry, dict):
                return entry.get("success", False)
            return False

        server_success_count = sum(1 for r in results if is_success(r.get("daisy_server")))
        skills_success_count = sum(1 for r in results if is_success(r.get("daisy_skills")))
        
        return {
            "total_tests": total_tests,
            "server_success_count": server_success_count,
            "skills_success_count": skills_success_count,
            "server_success_rate": f"{(server_success_count/total_tests*100):.1f}%" if total_tests > 0 else "0%",
            "skills_success_rate": f"{(skills_success_count/total_tests*100):.1f}%" if total_tests > 0 else "0%",
            "conclusion": "Daisy Skills 对话能力未退化" if skills_success_count >= server_success_count else "Daisy Skills 对话能力可能退化"
        }


async def main():
    daisy_server_url = "http://127.0.0.1:30021"
    daisy_skills_url = "http://localhost:8001"
    
    test_cases = [
        {
            "name": "简单问候",
            "message": "你好",
            "user_id": "test_user_1",
            "expected_type": "quick"
        },
        {
            "name": "情感表达 - 快乐",
            "message": "我今天心情特别好，因为考试通过了！",
            "user_id": "test_user_2",
            "expected_type": "context_aware"
        },
        {
            "name": "情感表达 - 悲伤",
            "message": "我很难过，我的宠物去世了",
            "user_id": "test_user_3",
            "expected_type": "context_aware"
        },
        {
            "name": "工具调用 - 搜索",
            "message": "帮我搜索一下人工智能的最新发展",
            "user_id": "test_user_4",
            "expected_type": "tool_required"
        },
        {
            "name": "工具调用 - 记忆",
            "message": "记住我喜欢喝咖啡",
            "user_id": "test_user_5",
            "expected_type": "tool_required"
        },
        {
            "name": "普通问题",
            "message": "什么是机器学习？",
            "user_id": "test_user_6",
            "expected_type": "standard"
        },
        {
            "name": "多轮对话",
            "messages": [
                "你好",
                "我想了解人工智能",
                "人工智能有哪些应用？",
                "谢谢你的解释"
            ],
            "user_id": "test_user_7"
        }
    ]
    
    tester = DialogueComparisonTest(daisy_server_url, daisy_skills_url)
    
    try:
        results = await tester.run_all_tests(test_cases)
        
        output_file = "/Users/anykong/Daisy_Demo/test_results.json"
        with open(output_file, "w", encoding="utf-8") as f:
            json.dump(results, f, ensure_ascii=False, indent=2)
        
        print(f"\n测试结果已保存到: {output_file}")
        
    finally:
        await tester.close()


if __name__ == "__main__":
    asyncio.run(main())
