"""
记忆检索查询的清洗。

这条测试来自对**真实运行数据**的度量,而不是设想:统计 158 次记忆检索的
`workflow_traces`,发现 5% 的检索查询被污染,最典型的是这种 ——

    ```json
    {"search_query": "文本理解和分析的含义与定义"}
    ```

提示词明确写了"仅输出搜索查询字符串",但模型并不总是听话。原实现只做
`.strip()`,于是整段 markdown 连同反引号和 JSON 包装被当作查询文本送去向量检索。

**它不会报错**,只是悄悄检索了一串无意义的字符,对用户表现为
"这次怎么什么都没想起来" —— 这类静默劣化最难被发现,因为日志一切正常。

项目里本来就有 `core/json_utils` 处理 LLM 的 JSON 脏输出,只是这条路径没接上。
"""

import pytest

from app.workflow.nodes.memory import _clean_search_query


class TestJsonWrappedOutput:
    """实测出现过的形态。"""

    def test_json_code_fence(self):
        raw = '```json\n{\n  "search_query": "文本理解和分析的含义与定义"\n}\n```'
        assert _clean_search_query(raw) == "文本理解和分析的含义与定义"

    def test_bare_json_object(self):
        assert _clean_search_query('{"search_query": "咖啡偏好"}') == "咖啡偏好"

    def test_alternative_key_names(self):
        assert _clean_search_query('{"query": "宠物"}') == "宠物"

    def test_plain_code_fence(self):
        assert _clean_search_query("```\n纯代码块包裹\n```") == "纯代码块包裹"

    def test_json_without_usable_field_is_rejected(self):
        """
        取不出查询就返回空,让调用方回落用户原句 ——
        原句总比一串 JSON 字面量更接近用户想找的东西。
        """
        assert _clean_search_query('{"unrelated": 1}') == ""


class TestUnrenderedPlaceholders:
    """
    历史数据里出现过字面量 `{text}` 作为检索查询 —— 模板占位符没被替换。
    同样不会报错,同样只是静默劣化。
    """

    @pytest.mark.parametrize("raw", ["{text}", "{{text}}", "{ text }"])
    def test_placeholder_rejected(self, raw):
        assert _clean_search_query(raw) == ""

    def test_normal_braces_in_text_not_rejected(self):
        """别误伤正常内容 —— 只有"整条就是一个占位符"才算污染。"""
        assert _clean_search_query("用户提到 {config} 配置项") == "用户提到 {config} 配置项"


class TestNormalQueriesPassThrough:

    def test_plain_query_kept(self):
        assert _clean_search_query("  用户的咖啡偏好  ") == "用户的咖啡偏好"

    def test_empty_returns_empty(self):
        assert _clean_search_query("") == ""
        assert _clean_search_query(None) == ""


class TestNodeFallsBackOnBadQuery:
    """
    清洗失败必须回落到用户原句,而不是拿空串去检索 ——
    空查询在向量库里会返回一堆不相关的东西,比不检索更糟。
    """

    def test_node_uses_cleaner_and_falls_back(self):
        import inspect

        from app.workflow.nodes import memory

        src = inspect.getsource(memory.retrieve_memory)
        assert "_clean_search_query" in src, "检索节点没有清洗 LLM 生成的查询"
        # 清洗失败时不能把 search_query 覆盖成空
        assert "if cleaned:" in src, "清洗返回空时仍然覆盖了原句"
