from __future__ import annotations

import asyncio

import pytest

from src.api import preflight


@pytest.mark.asyncio
async def test_bounded_preflight_check_reports_timeout(monkeypatch):
    monkeypatch.setattr(preflight, "PREFLIGHT_CHECK_TIMEOUT_SECONDS", 0.001)

    async def slow_check():
        await asyncio.sleep(1)
        return preflight.CheckResult("ok")

    result = await preflight._bounded_check("slow", slow_check())

    assert result.status == "timeout"
    assert "slow health check exceeded" in result.detail
