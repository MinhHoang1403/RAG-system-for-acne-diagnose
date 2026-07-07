from __future__ import annotations

import pytest

from scripts import inspect_cache_versions


@pytest.mark.asyncio
async def test_inspect_cache_versions_graceful_without_backend(monkeypatch):
    async def fake_get_redis():
        return None

    monkeypatch.setattr(inspect_cache_versions, "get_redis", fake_get_redis)

    report = await inspect_cache_versions.inspect_cache_versions()

    assert report["passed"] is True
    assert report["cache_backend_detected"] is False
    assert report["legacy_entries_detected"] is None
    assert report["warnings"]
