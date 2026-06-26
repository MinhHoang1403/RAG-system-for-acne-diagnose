"""
src/database/models/__init__.py
================================
Export the shared MetaData object used by init_schema.py and Alembic.
Import all model modules here so their tables are registered on metadata.
"""

from src.database.models.base import Base, metadata

# Import models so SQLAlchemy registers their tables on metadata.
# Uncomment as models are implemented:
# from src.database.models.conversation import Conversation, Message  # noqa: F401
# from src.database.models.document import Document                   # noqa: F401
# from src.database.models.embedding import Embedding                 # noqa: F401

__all__ = ["Base", "metadata"]
