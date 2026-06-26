"""
tests/test_skills_registry.py – Skill Registry Unit Tests
"""

from __future__ import annotations

import pytest

from src.skills.base import BaseSkill, SkillResult
from src.skills.registry import SkillRegistry


class _DummySkill(BaseSkill):
    name = "dummy"
    description = "A dummy skill for testing."

    async def run(self, input: str, **kwargs) -> SkillResult:
        return SkillResult(skill_name=self.name, output=f"echo: {input}")


def test_register_and_get():
    registry = SkillRegistry()
    registry.register(_DummySkill)
    skill = registry.get("dummy")
    assert isinstance(skill, _DummySkill)


def test_list_skills():
    registry = SkillRegistry()
    registry.register(_DummySkill)
    assert "dummy" in registry.list()


def test_get_unknown_skill_raises():
    registry = SkillRegistry()
    with pytest.raises(KeyError):
        registry.get("nonexistent")


@pytest.mark.asyncio
async def test_skill_run_returns_result():
    skill = _DummySkill()
    result = await skill.run("hello")
    assert result.success
    assert result.output == "echo: hello"
