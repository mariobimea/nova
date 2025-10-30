"""Add client_credentials table for multi-client support

Revision ID: 002
Revises: 001
Create Date: 2025-10-30

This table stores encrypted credentials for connecting to client databases.
NOVA workflows can read credentials from here to connect to external databases.
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = '002'
down_revision = '001'
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Create client_credentials table"""

    op.create_table(
        'client_credentials',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('client_name', sa.String(length=255), nullable=False),
        sa.Column('client_slug', sa.String(length=100), nullable=False, unique=True),

        # Database connection details (encrypted in production)
        sa.Column('db_host', sa.String(length=255), nullable=False),
        sa.Column('db_port', sa.Integer(), nullable=False, default=5432),
        sa.Column('db_name', sa.String(length=255), nullable=False),
        sa.Column('db_user', sa.String(length=255), nullable=False),
        sa.Column('db_password', sa.String(length=255), nullable=False),  # TODO: Encrypt in Phase 2

        # Metadata
        sa.Column('is_active', sa.Boolean(), nullable=False, default=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),

        sa.PrimaryKeyConstraint('id')
    )

    op.create_index(op.f('ix_client_credentials_id'), 'client_credentials', ['id'], unique=False)
    op.create_index(op.f('ix_client_credentials_client_slug'), 'client_credentials', ['client_slug'], unique=True)
    op.create_index(op.f('ix_client_credentials_is_active'), 'client_credentials', ['is_active'], unique=False)


def downgrade() -> None:
    """Drop client_credentials table"""
    op.drop_index(op.f('ix_client_credentials_is_active'), table_name='client_credentials')
    op.drop_index(op.f('ix_client_credentials_client_slug'), table_name='client_credentials')
    op.drop_index(op.f('ix_client_credentials_id'), table_name='client_credentials')
    op.drop_table('client_credentials')
