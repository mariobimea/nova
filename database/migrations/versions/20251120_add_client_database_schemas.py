"""Add client_database_schemas table

Revision ID: 005
Revises: 89bcecaafdf6
Create Date: 2025-11-20

Stores database table schemas for client databases.
This allows NOVA to know which columns exist before generating SQL code.
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = '005'
down_revision = '89bcecaafdf6'
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Create client_database_schemas table"""

    op.create_table(
        'client_database_schemas',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('client_id', sa.Integer(), nullable=False),
        sa.Column('database_credential_id', sa.Integer(), nullable=False),
        sa.Column('table_name', sa.String(length=255), nullable=False),
        sa.Column('schema_definition', postgresql.JSON(astext_type=sa.Text()), nullable=False),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.text('NOW()')),
        sa.Column('updated_at', sa.DateTime(), nullable=False, server_default=sa.text('NOW()')),

        sa.PrimaryKeyConstraint('id'),
        sa.ForeignKeyConstraint(['client_id'], ['clients.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['database_credential_id'], ['client_database_credentials.id'], ondelete='CASCADE'),
        sa.UniqueConstraint('client_id', 'table_name', name='unique_client_table')
    )

    # Create indexes for frequent queries
    op.create_index('ix_client_database_schemas_client_id', 'client_database_schemas', ['client_id'])
    op.create_index('ix_client_database_schemas_table_name', 'client_database_schemas', ['table_name'])


def downgrade() -> None:
    """Drop client_database_schemas table"""
    op.drop_index('ix_client_database_schemas_table_name', table_name='client_database_schemas')
    op.drop_index('ix_client_database_schemas_client_id', table_name='client_database_schemas')
    op.drop_table('client_database_schemas')
