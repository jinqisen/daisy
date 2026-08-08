"""
跨路由统一 system prompt 装配层测试(prompt_base.py)。

不触达 LLM;角色卡按测试环境实际可得性降级(builder 对加载失败本就静默降级)。
"""

from app.workflow.nodes.prompt_base import (
    build_base_system_prompt,
    OFFLINE_MEETUP_CONSTRAINT,
    FALLBACK_SYSTEM_PROMPT,
)
from app.prompts import CommonSettings, get_core_system_instructions


def test_none_common_falls_back_to_minimal_prompt():
    prompt = build_base_system_prompt(None, user_id=999999, channel="FAST", user_input="好的")
    assert prompt.startswith(FALLBACK_SYSTEM_PROMPT)


def test_core_instructions_and_template_are_included():
    common = CommonSettings(name="AI", system_prompt_template="模板追加内容XYZ")
    prompt = build_base_system_prompt(common, user_id=999999, channel="STANDARD", user_input="早")
    # builder 与旧实现一致会 strip 首尾空白,比较时对齐
    assert get_core_system_instructions(common).strip() in prompt
    assert "模板追加内容XYZ" in prompt


def test_offline_meetup_intent_injects_constraint_on_both_channels():
    common = CommonSettings(name="AI")
    meetup_input = "周四我们江滩见面吧,把地址发我"
    for channel in ("FAST", "STANDARD"):
        prompt = build_base_system_prompt(common, user_id=999999, channel=channel, user_input=meetup_input)
        assert OFFLINE_MEETUP_CONSTRAINT in prompt, f"{channel} 路由缺少线下见面硬约束"


def test_trivial_input_has_no_meetup_constraint():
    common = CommonSettings(name="AI")
    prompt = build_base_system_prompt(common, user_id=999999, channel="FAST", user_input="谢谢")
    assert OFFLINE_MEETUP_CONSTRAINT not in prompt
