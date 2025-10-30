"""Initial schema - workflows, executions, chain_of_work

Revision ID: 001
Revises:
Create Date: 2025-10-27

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = '001'
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Create initial tables for NOVA workflow engine"""

    # Create workflows table
    op.create_table(
        'workflows',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('name', sa.String(length=255), nullable=False),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('graph_definition', postgresql.JSON(astext_type=sa.Text()), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_workflows_id'), 'workflows', ['id'], unique=False)
    op.create_index(op.f('ix_workflows_name'), 'workflows', ['name'], unique=False)

    # Create executions table
    op.create_table(
        'executions',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('workflow_id', sa.Integer(), nullable=False),
        sa.Column('status', sa.String(length=50), nullable=False),
        sa.Column('started_at', sa.DateTime(), nullable=True),
        sa.Column('completed_at', sa.DateTime(), nullable=True),
        sa.Column('result', postgresql.JSON(astext_type=sa.Text()), nullable=True),
        sa.Column('error', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['workflow_id'], ['workflows.id'], ),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_executions_id'), 'executions', ['id'], unique=False)
    op.create_index(op.f('ix_executions_workflow_id'), 'executions', ['workflow_id'], unique=False)
    op.create_index(op.f('ix_executions_status'), 'executions', ['status'], unique=False)

    # Create chain_of_work table
    op.create_table(
        'chain_of_work',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('execution_id', sa.Integer(), nullable=False),
        sa.Column('node_id', sa.String(length=255), nullable=False),
        sa.Column('node_type', sa.String(length=50), nullable=False),
        sa.Column('code_executed', sa.Text(), nullable=True),
        sa.Column('input_context', postgresql.JSON(astext_type=sa.Text()), nullable=True),
        sa.Column('output_result', postgresql.JSON(astext_type=sa.Text()), nullable=True),
        sa.Column('execution_time', sa.Float(), nullable=True),
        sa.Column('status', sa.String(length=50), nullable=False),
        sa.Column('error_message', sa.Text(), nullable=True),
        sa.Column('timestamp', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['execution_id'], ['executions.id'], ),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_chain_of_work_id'), 'chain_of_work', ['id'], unique=False)
    op.create_index(op.f('ix_chain_of_work_execution_id'), 'chain_of_work', ['execution_id'], unique=False)
    op.create_index(op.f('ix_chain_of_work_node_id'), 'chain_of_work', ['node_id'], unique=False)


def downgrade() -> None:
    """Drop all tables"""
    op.drop_index(op.f('ix_chain_of_work_node_id'), table_name='chain_of_work')
    op.drop_index(op.f('ix_chain_of_work_execution_id'), table_name='chain_of_work')
    op.drop_index(op.f('ix_chain_of_work_id'), table_name='chain_of_work')
    op.drop_table('chain_of_work')

    op.drop_index(op.f('ix_executions_status'), table_name='executions')
    op.drop_index(op.f('ix_executions_workflow_id'), table_name='executions')
    op.drop_index(op.f('ix_executions_id'), table_name='executions')
    op.drop_table('executions')

    op.drop_index(op.f('ix_workflows_name'), table_name='workflows')
    op.drop_index(op.f('ix_workflows_id'), table_name='workflows')
    op.drop_table('workflows')
