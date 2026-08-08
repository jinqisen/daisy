"""
LLM 结构化输出的容错解析回归。

坑:深度角色卡生成走通了(不再超时),却栽在 JSON 解析上 ——
日志里是 "Expecting value: line 19 column 49",然后静默回落到默认卡,
用户永远拿不到为自己生成的人格。

实测两类稳定失败(deepseek-v3.2,2000~3000 tokens 的中文嵌套 JSON):
  1. 明确要求"不要输出 Markdown"仍加 ```json 围栏;
  2. 字符串里含中文弯引号「‘’」时,用中文右引号 ” 或 ASCII 单引号闭合 JSON 字符串。
加 response_format={"type":"json_object"} 两个毛病都还在,所以必须容错解析。

下面的样本都取自模型真实返回。
"""

import json

import pytest

from app.core.json_utils import parse_llm_json, strip_code_fence


class TestFenceStripping:

    @pytest.mark.parametrize("wrapped", [
        '```json\n{"a": 1}\n```',
        '```JSON\n{"a": 1}\n```',
        '```\n{"a": 1}\n```',
        '  ```json\n{"a": 1}\n```  ',
    ])
    def test_strips_all_fence_variants(self, wrapped):
        assert parse_llm_json(wrapped) == {"a": 1}

    def test_plain_json_untouched(self):
        assert strip_code_fence('{"a": 1}') == '{"a": 1}'


class TestMalformedRealWorldOutput:

    def test_ascii_single_quoted_string(self):
        """
        真实样本:数组里混入单引号字符串(值本身含中文弯引号,模型被带偏)。
        原始报错 "Expecting value: line 19 column 49"。
        """
        bad = (
            '{"behavior": {"push_behaviors": ["拒绝一切工作外的社交邀请", '
            "'当话题转向私人情感时，会生硬地转回‘事实’层面', "
            '"不透露自己的住址"]}}'
        )
        with pytest.raises(json.JSONDecodeError):
            json.loads(bad)
        data = parse_llm_json(bad)
        assert "behavior" in data
        assert len(data["behavior"]["push_behaviors"]) == 3

    def test_chinese_closing_quote_terminates_string(self):
        """
        真实样本:字符串以中文右引号 ” 而非 " 收尾。
        加了 json_object 模式也照样出现。
        """
        bad = '{"quirks": ["陈述事实时喜欢用‘数据显示…’开头”, "会整理袖口"]}'
        with pytest.raises(json.JSONDecodeError):
            json.loads(bad)
        data = parse_llm_json(bad)
        assert "quirks" in data

    def test_fence_plus_malformation_together(self):
        """两个毛病同时出现 —— 这才是线上实际形态。"""
        bad = "```json\n{\"a\": ['x', 'y']}\n```"
        data = parse_llm_json(bad)
        assert data["a"] == ["x", "y"]

    def test_trailing_comma(self):
        assert parse_llm_json('{"a": 1,}') == {"a": 1}


class TestFailureIsLoud:
    """修不动时必须抛错,不能返回空对象让上层误以为成功。"""

    def test_empty_content_raises(self):
        with pytest.raises(ValueError):
            parse_llm_json("")

    def test_fence_only_raises(self):
        with pytest.raises(ValueError):
            parse_llm_json("```json\n```")

    def test_prose_instead_of_json_raises(self):
        with pytest.raises(ValueError):
            parse_llm_json("抱歉，我无法完成这个请求。")


class TestGenerationUsesTolerantParser:

    def test_deep_card_does_not_use_raw_json_loads(self):
        import inspect
        from app.services.dialogue import generation
        src = inspect.getsource(generation.generate_deep_character_card)
        assert "parse_llm_json" in src
        assert "json.loads(" not in src, \
            "深度卡仍在用裸 json.loads —— 模型的引号毛病会让生成静默回落到默认卡"
