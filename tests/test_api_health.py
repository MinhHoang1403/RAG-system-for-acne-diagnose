"""
tests/test_api_health.py – API Health Endpoint Tests
"""

from __future__ import annotations

import pytest
from httpx import ASGITransport, AsyncClient

from src.api.app import app


@pytest.mark.asyncio
async def test_health_returns_ok(monkeypatch):
    async def fake_preflight():
        return {
            "status": "ok",
            "checks": {
                "postgres": {"status": "ok"},
                "qdrant": {"status": "ok"},
                "neo4j": {"status": "ok"},
                "redis": {"status": "ok"},
                "ollama": {"status": "ok"},
            },
        }

    monkeypatch.setattr("src.api.preflight.run_phase2_preflight", fake_preflight)

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        response = await client.get("/health")

    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"
    assert data["service"] == "acne-advisor-api"
