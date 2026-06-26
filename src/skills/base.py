"""
src/skills/base.py – BaseSkill Abstract Class
=============================================
All skills must inherit from BaseSkill and implement the `run` method.
"""

from __future__ import annotations

import abc
from dataclasses import dataclass, field
from typing import Any


@dataclass
class SkillResult:
    """Standardised return type from any skill invocation."""
    skill_name: str
    output: str
    metadata: dict[str, Any] = field(default_factory=dict)
    error: str | None = None

    @property
    def success(self) -> bool:
        return self.error is None


class BaseSkill(abc.ABC):
    """
    Abstract base class for all agent skills.

    Subclasses MUST implement:
    - name (class variable)
    - description (class variable) – shown to the LLM as tool description
    - run() – async method that executes the skill

    Example
    -------
    class PubMedSearchSkill(BaseSkill):
        name = "pubmed_search"
        description = "Search PubMed for scientific literature about acne treatments."

        async def run(self, query: str, **kwargs) -> SkillResult:
            ...
    """

    name: str = ""
    description: str = ""

    @abc.abstractmethod
    async def run(self, input: str, **kwargs) -> SkillResult:
        """Execute the skill and return a SkillResult."""
        ...

    def __repr__(self) -> str:
        return f"<Skill: {self.name}>"
