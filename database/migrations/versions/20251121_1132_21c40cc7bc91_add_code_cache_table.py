"""add_code_cache_table

Revision ID: 21c40cc7bc91
Revises: 20251120_add_client_database_schemas
Create Date: 2025-11-21 11:32:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = '21c40cc7bc91'
down_revision: Union[str, None] = '005'  # Points to 20251120_add_client_database_schemas
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """
    Create code_cache table for storing AI-generated code.

    Cache Strategy:
        - cache_key = SHA256(prompt + context_schema)
        - Reuse code when prompt AND context structure are identical
        - Track usage statistics for performance monitoring
    """
    op.create_table(
        'code_cache',

        # Primary key
        sa.Column('id', sa.Integer(), nullable=False, primary_key=True),

        # Cache key (hash of prompt + context schema)
        sa.Column('cache_key', sa.String(length=64), nullable=False, unique=True, index=True),

        # Metadata del prompt (for analytics)
        sa.Column('task_hash', sa.String(length=64), nullable=False, index=True),
        sa.Column('context_schema_hash', sa.String(length=64), nullable=True),

        # Cached code
        sa.Column('generated_code', sa.Text(), nullable=False),

        # Metadata de generación original
        sa.Column('model', sa.String(length=100), nullable=False),
        sa.Column('original_prompt', sa.Text(), nullable=True),
        sa.Column('tokens_used', sa.Integer(), nullable=True),
        sa.Column('cost_usd', sa.Numeric(precision=10, scale=6), nullable=True),

        # Usage tracking
        sa.Column('times_reused', sa.Integer(), nullable=False, default=0),
        sa.Column('last_used_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('NOW()'), nullable=False),

        # Performance tracking
        sa.Column('success_count', sa.Integer(), nullable=False, default=0),
        sa.Column('failure_count', sa.Integer(), nullable=False, default=0),
        sa.Column('avg_execution_time_ms', sa.Float(), nullable=True),

        # Optional: Workflow context (for better analytics)
        sa.Column('workflow_id', sa.Integer(), nullable=True),
        sa.Column('node_id', sa.String(length=255), nullable=True),
    )

    # Create indexes for performance
    op.create_index('idx_code_cache_task_hash', 'code_cache', ['task_hash'])
    op.create_index('idx_code_cache_last_used', 'code_cache', ['last_used_at'])
    op.create_index('idx_code_cache_workflow', 'code_cache', ['workflow_id', 'node_id'])


def downgrade() -> None:
    """Drop code_cache table"""
    op.drop_index('idx_code_cache_workflow', table_name='code_cache')
    op.drop_index('idx_code_cache_last_used', table_name='code_cache')
    op.drop_index('idx_code_cache_task_hash', table_name='code_cache')
    op.drop_table('code_cache')
