"""
Reflexion 演化触发阈值测试(F2:补丁分支从「不可达」修复为「可配置且可达」)。

用 fake patcher/storage 验证 _trigger_evolution 的三个分支按 settings 阈值分派。
"""

import asyncio
from types import SimpleNamespace

import pytest

from app.core.config import settings
from app.services.learning.reflexion.service import ReflexionService


@pytest.fixture
def service_with_spies(monkeypatch):
    svc = ReflexionService()
    calls = {"patch": 0, "exemplar": 0}

    async def fake_generate_patch(**kwargs):
        calls["patch"] += 1
        return {"patch": "p", "scope": "PERSONAL", "reasoning": ""}

    async def fake_store_exemplar(**kwargs):
        calls["exemplar"] += 1

    monkeypatch.setattr(svc, "patcher", SimpleNamespace(generate_patch=fake_generate_patch))
    monkeypatch.setattr(svc, "storage", SimpleNamespace(store_exemplar=fake_store_exemplar))
    return svc, calls


def _trigger(svc, score):
    asyncio.run(svc._trigger_evolution(
        user_id=1, user_input_context="ctx", agent_response="resp",
        user_feedback="fb", score=score, metrics={},
    ))


def test_low_score_triggers_patch(service_with_spies):
    svc, calls = service_with_spies
    _trigger(svc, settings.REFLEXION_PATCH_THRESHOLD - 0.01)
    assert calls == {"patch": 1, "exemplar": 0}


def test_high_score_triggers_exemplar(service_with_spies):
    svc, calls = service_with_spies
    _trigger(svc, settings.REFLEXION_EXEMPLAR_THRESHOLD + 0.01)
    assert calls == {"patch": 0, "exemplar": 1}


def test_mid_score_triggers_nothing(service_with_spies):
    svc, calls = service_with_spies
    mid = (settings.REFLEXION_PATCH_THRESHOLD + settings.REFLEXION_EXEMPLAR_THRESHOLD) / 2
    _trigger(svc, mid)
    assert calls == {"patch": 0, "exemplar": 0}


def test_default_thresholds_are_reachable_for_observed_distribution():
    """
    校准断言:实测 S 分布为 [0.49, 0.86](2026-07,n=82)。
    默认阈值必须落在该区间内,保证两个分支都实际可达——
    这是 F2 的根因(旧补丁阈值 0.40 低于分布下限,永不触发)。
    """
    assert 0.49 < settings.REFLEXION_PATCH_THRESHOLD < 0.86
    assert 0.49 < settings.REFLEXION_EXEMPLAR_THRESHOLD < 0.86
    assert settings.REFLEXION_PATCH_THRESHOLD < settings.REFLEXION_EXEMPLAR_THRESHOLD
