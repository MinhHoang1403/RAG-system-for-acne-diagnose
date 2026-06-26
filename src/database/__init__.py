"""
src/database – Database Access Layer

Manages all persistent storage: SQL (PostgreSQL + pgvector) and vector DB.

Structure
---------
connection.py       – Engine and session factory (SQLAlchemy async)
models/             – SQLAlchemy ORM model definitions
  __init__.py       – Exports `metadata` (MetaData) for schema creation
  base.py           – Declarative base and shared mixins
  conversation.py   – Conversation and message models
  document.py       – Ingested document metadata models
  embedding.py      – pgvector embedding table (when VECTOR_DB_PROVIDER=pgvector)
repositories/       – Repository pattern: thin data-access wrappers
  conversation.py
  document.py
vector_store.py     – VectorStore abstraction (Qdrant / pgvector backend)
migrations/         – Alembic migration scripts
"""
