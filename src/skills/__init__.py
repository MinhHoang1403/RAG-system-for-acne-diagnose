"""
src/skills – Reusable Skill Modules

Each sub-module is a self-contained skill that the agent can invoke.
Skills are registered in the agent's tool registry and must expose
a `run(input: str, **kwargs) -> str` coroutine or callable.

Structure
---------
base.py             – BaseSkill abstract class
registry.py         – SkillRegistry: register and look up skills
pubmed/             – PubMed literature search skill
clinical_trials/    – ClinicalTrials.gov search skill
dermatology/        – Domain-specific dermatology knowledge skill
web_search/         – General web search skill
"""
