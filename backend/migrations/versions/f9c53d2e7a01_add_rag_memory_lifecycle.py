"""add RAG versioning and memory lifecycle fields

Revision ID: f9c53d2e7a01
Revises: e8b42c1d6f90
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "f9c53d2e7a01"
down_revision: Union[str, None] = "e8b42c1d6f90"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    def columns(table: str) -> set[str]:
        return {item["name"] for item in inspector.get_columns(table)}

    def indexes(table: str) -> set[str]:
        return {item["name"] for item in inspector.get_indexes(table)}

    if "version" not in columns("knowledge_documents"):
        op.add_column(
        "knowledge_documents",
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        )
    if "content_hash" not in columns("knowledge_documents"):
        op.add_column(
        "knowledge_documents",
        sa.Column("content_hash", sa.String(64), nullable=True),
        )
    if "ix_knowledge_documents_content_hash" not in indexes("knowledge_documents"):
        op.create_index(
            "ix_knowledge_documents_content_hash",
            "knowledge_documents",
            ["content_hash"],
        )

    if "content_hash" not in columns("knowledge_chunks"):
        op.add_column(
        "knowledge_chunks",
        sa.Column("content_hash", sa.String(64), nullable=True),
        )
    if "token_count" not in columns("knowledge_chunks"):
        op.add_column(
        "knowledge_chunks",
        sa.Column("token_count", sa.Integer(), nullable=False, server_default="0"),
        )
    op.execute(
        "UPDATE knowledge_chunks SET content_hash = SHA2(content, 256), "
        "token_count = GREATEST(1, CHAR_LENGTH(content) DIV 2)"
    )
    op.alter_column(
        "knowledge_chunks",
        "content_hash",
        existing_type=sa.String(64),
        nullable=False,
    )
    if "ix_knowledge_chunks_content_hash" not in indexes("knowledge_chunks"):
        op.create_index(
            "ix_knowledge_chunks_content_hash",
            "knowledge_chunks",
            ["content_hash"],
        )

    if "memory_key" not in columns("user_memories"):
        op.add_column(
        "user_memories",
        sa.Column("memory_key", sa.String(100), nullable=True),
        )
    if "expires_at" not in columns("user_memories"):
        op.add_column(
        "user_memories",
        sa.Column("expires_at", sa.DateTime(), nullable=True),
        )
    if "last_accessed_at" not in columns("user_memories"):
        op.add_column(
        "user_memories",
        sa.Column("last_accessed_at", sa.DateTime(), nullable=True),
        )
    op.execute("UPDATE user_memories SET memory_key = fingerprint")
    op.alter_column(
        "user_memories",
        "memory_key",
        existing_type=sa.String(100),
        nullable=False,
    )
    if "ix_user_memories_memory_key" not in indexes("user_memories"):
        op.create_index(
            "ix_user_memories_memory_key",
            "user_memories",
            ["memory_key"],
        )
    if "ix_user_memories_expires_at" not in indexes("user_memories"):
        op.create_index(
            "ix_user_memories_expires_at",
            "user_memories",
            ["expires_at"],
        )


def downgrade() -> None:
    op.drop_index("ix_user_memories_expires_at", table_name="user_memories")
    op.drop_index("ix_user_memories_memory_key", table_name="user_memories")
    op.drop_column("user_memories", "last_accessed_at")
    op.drop_column("user_memories", "expires_at")
    op.drop_column("user_memories", "memory_key")
    op.drop_index(
        "ix_knowledge_chunks_content_hash", table_name="knowledge_chunks"
    )
    op.drop_column("knowledge_chunks", "token_count")
    op.drop_column("knowledge_chunks", "content_hash")
    op.drop_index(
        "ix_knowledge_documents_content_hash",
        table_name="knowledge_documents",
    )
    op.drop_column("knowledge_documents", "content_hash")
    op.drop_column("knowledge_documents", "version")
