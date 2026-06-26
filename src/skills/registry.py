"""
src/skills/registry.py – Skill Registry
========================================
Central registry for discovering and looking up skills.
"""

from __future__ import annotations

import logging
from typing import Type

from src.skills.base import BaseSkill

logger = logging.getLogger(__name__)


class SkillRegistry:
    """
    Registry that maps skill names to their class definitions.

    Usage
    -----
    registry = SkillRegistry()
    registry.register(PubMedSearchSkill)
    skill = registry.get("pubmed_search")
    result = await skill.run("acne treatment retinoids")
    """

    def __init__(self) -> None:
        self._registry: dict[str, Type[BaseSkill]] = {}

    def register(self, skill_class: Type[BaseSkill]) -> None:
        if not skill_class.name:
            raise ValueError(f"{skill_class.__name__} must define a non-empty `name`.")
        if skill_class.name in self._registry:
            logger.warning("Skill '%s' is already registered – overwriting.", skill_class.name)
        self._registry[skill_class.name] = skill_class
        logger.debug("Registered skill: %s", skill_class.name)

    def get(self, name: str) -> BaseSkill:
        if name not in self._registry:
            raise KeyError(f"Skill '{name}' is not registered. Available: {self.list()}")
        return self._registry[name]()

    def list(self) -> list[str]:
        return sorted(self._registry.keys())

    def __len__(self) -> int:
        return len(self._registry)


# Singleton registry
_registry = SkillRegistry()


def get_registry() -> SkillRegistry:
    return _registry


def register_skill(skill_class: Type[BaseSkill]) -> Type[BaseSkill]:
    """Decorator to auto-register a skill class."""
    _registry.register(skill_class)
    return skill_class
