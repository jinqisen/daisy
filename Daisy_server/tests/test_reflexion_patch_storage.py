"""
Reflexion 补丁存储迁移测试(深改点 #3:JSONL → Redis)。

覆盖:Redis 读写往返、存量 JSONL 一次性迁移、Redis 不可用时回退 JSONL、
GLOBAL 补丁的缓存失效。集成用例在本地 Redis 不可达时跳过。
"""

import asyncio
import json
import uuid

import pytest

from app.services.learning.reflexion.patching import ReflexionPatcher


from tests.redis_test_utils import probe_redis, fresh_redis

REDIS_UP = probe_redis()


def _make_patcher(tmp_path, suffix: str) -> ReflexionPatcher:
    """构造使用独立 Redis 键与临时 JSONL 的 patcher,避免污染真实数据。"""
    patcher = ReflexionPatcher.__new__(ReflexionPatcher)
    patcher.patches_file = str(tmp_path / "patches.jsonl")
    patcher.GLOBAL_KEY = f"test:reflexion:{suffix}:global"
    patcher.PERSONAL_KEY_PREFIX = f"test:reflexion:{suffix}:personal:"
    patcher.MIGRATION_FLAG_KEY = f"test:reflexion:{suffix}:migrated"
    patcher._cache = {}
    patcher._migration_checked = False
    patcher._ensure_file_exists()
    return patcher


async def _cleanup(patcher: ReflexionPatcher, user_ids):
    from app.core.cache import redis_client
    keys = [patcher.GLOBAL_KEY, patcher.MIGRATION_FLAG_KEY]
    keys += [patcher._personal_key(u) for u in user_ids]
    await redis_client.redis.delete(*keys)


@pytest.mark.skipif(not REDIS_UP, reason="本地 Redis 不可达")
def test_store_and_read_roundtrip_via_redis(tmp_path):
    patcher = _make_patcher(tmp_path, uuid.uuid4().hex[:8])

    async def _run():
        async with fresh_redis():
            await patcher._store_patch(7, "对用户7回复要更简短", "PERSONAL", "r", 0.2, {})
            await patcher._store_patch(7, "禁止使用翻译腔", "GLOBAL", "r", 0.1, {})
            got_u7 = await patcher.get_active_patches(7)
            got_u8 = await patcher.get_active_patches(8)
            await _cleanup(patcher, [7, 8])
            return got_u7, got_u8

    got_u7, got_u8 = asyncio.run(_run())
    assert got_u7 == {"global": ["禁止使用翻译腔"], "personal": ["对用户7回复要更简短"]}
    # 其他用户只看到全局补丁
    assert got_u8 == {"global": ["禁止使用翻译腔"], "personal": []}
    # JSONL 双写仍在(备份)
    lines = (tmp_path / "patches.jsonl").read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == 2


@pytest.mark.skipif(not REDIS_UP, reason="本地 Redis 不可达")
def test_legacy_jsonl_migrated_once(tmp_path):
    patcher = _make_patcher(tmp_path, uuid.uuid4().hex[:8])
    legacy = [
        {"user_id": 7, "patch": "旧个人补丁", "scope": "PERSONAL", "status": "active"},
        {"user_id": 1, "patch": "旧全局补丁", "scope": "GLOBAL", "status": "active"},
        {"user_id": 7, "patch": "已归档不该出现", "scope": "PERSONAL", "status": "archived"},
    ]
    (tmp_path / "patches.jsonl").write_text(
        "\n".join(json.dumps(e, ensure_ascii=False) for e in legacy) + "\n", encoding="utf-8"
    )

    async def _run():
        async with fresh_redis():
            got = await patcher.get_active_patches(7)
            # 第二次读取应命中已迁移的 Redis 数据(且不重复迁移)
            patcher._cache.clear()
            got_again = await patcher.get_active_patches(7)
            await _cleanup(patcher, [7])
            return got, got_again

    got, got_again = asyncio.run(_run())
    assert got == {"global": ["旧全局补丁"], "personal": ["旧个人补丁"]}
    assert got_again == got  # 无重复条目 → 迁移只执行了一次


def test_fallback_to_jsonl_when_redis_unavailable(tmp_path, monkeypatch):
    patcher = _make_patcher(tmp_path, uuid.uuid4().hex[:8])
    (tmp_path / "patches.jsonl").write_text(
        json.dumps({"user_id": 9, "patch": "文件回退补丁", "scope": "PERSONAL", "status": "active"},
                   ensure_ascii=False) + "\n", encoding="utf-8"
    )

    async def _no_redis(self):
        return None
    monkeypatch.setattr(ReflexionPatcher, "_get_redis", _no_redis)

    got = asyncio.run(patcher.get_active_patches(9))
    assert got == {"global": [], "personal": ["文件回退补丁"]}


@pytest.mark.skipif(not REDIS_UP, reason="本地 Redis 不可达")
def test_global_patch_invalidates_all_cache(tmp_path):
    patcher = _make_patcher(tmp_path, uuid.uuid4().hex[:8])

    async def _run():
        async with fresh_redis():
            first = await patcher.get_active_patches(7)   # 建立缓存(空)
            await patcher._store_patch(1, "新全局规则", "GLOBAL", "r", 0.1, {})
            second = await patcher.get_active_patches(7)  # GLOBAL 存储应已清缓存
            await _cleanup(patcher, [1, 7])
            return first, second

    first, second = asyncio.run(_run())
    assert first["global"] == []
    assert second["global"] == ["新全局规则"]
