"""
src/agent – AI Agent Package

Contains the core LangGraph / LangChain agent orchestration logic.

Structure
---------
main.py         – Agent runner / entry-point
graph.py        – LangGraph state machine definition
state.py        – Shared agent state TypedDicts
nodes/          – Individual graph node functions (retrieve, reason, respond, …)
prompts/        – Prompt templates and system instructions
tools/          – Agent-callable tool wrappers
"""
