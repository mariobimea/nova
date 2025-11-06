"""add_ai_metadata_to_chain_of_work

Revision ID: d17c971a5e1c
Revises: 002
Create Date: 2025-11-06 12:07:21.550318

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = 'd17c971a5e1c'
down_revision = '002'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Add ai_metadata column to chain_of_work table
    # This stores AI generation metadata when executor_type == "cached"
    op.add_column('chain_of_work', sa.Column('ai_metadata', sa.JSON(), nullable=True))


def downgrade() -> None:
    # Remove ai_metadata column from chain_of_work table
    op.drop_column('chain_of_work', 'ai_metadata')
