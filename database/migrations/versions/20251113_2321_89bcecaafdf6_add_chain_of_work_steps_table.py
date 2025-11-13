"""add_chain_of_work_steps_table

Adds granular execution trace table for Mark I multi-agent system.

Each row in chain_of_work_steps represents ONE agent execution within a workflow node.
A single ActionNode with CachedExecutor may generate 4-14 steps depending on retries.

Example:
- 1 row in chain_of_work (node summary)
- 9 rows in chain_of_work_steps (InputAnalyzer, DataAnalyzer, CodeGenerator x2, etc.)

Revision ID: 89bcecaafdf6
Revises: d17c971a5e1c
Create Date: 2025-11-13 23:21:19.651609
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision = '89bcecaafdf6'
down_revision = 'd17c971a5e1c'
branch_labels = None
depends_on = None


def upgrade() -> None:
    """
    Create chain_of_work_steps table with indexes.

    This table provides complete traceability of what happens INSIDE a workflow node
    when using CachedExecutor (Mark I multi-agent system).

    Features:
    - Foreign key to chain_of_work with CASCADE delete
    - Composite indexes for common queries
    - JSON columns for flexible metadata storage
    """

    # Create table
    op.create_table(
        'chain_of_work_steps',

        # Primary key
        sa.Column('id', sa.Integer(), nullable=False),

        # Foreign key (cascade delete when parent chain_of_work is deleted)
        sa.Column(
            'chain_of_work_id',
            sa.Integer(),
            nullable=False
        ),

        # Step identification
        sa.Column('step_number', sa.Integer(), nullable=False),
        sa.Column('step_name', sa.String(length=100), nullable=False),
        sa.Column('agent_name', sa.String(length=100), nullable=False),
        sa.Column('attempt_number', sa.Integer(), nullable=True, server_default='1'),

        # Input/Output (JSON for flexibility)
        sa.Column('input_data', postgresql.JSON(astext_type=sa.Text()), nullable=True),
        sa.Column('output_data', postgresql.JSON(astext_type=sa.Text()), nullable=True),

        # Code generation
        sa.Column('generated_code', sa.Text(), nullable=True),

        # E2B execution
        sa.Column('sandbox_id', sa.String(length=255), nullable=True),

        # AI metadata
        sa.Column('model_used', sa.String(length=50), nullable=True),
        sa.Column('tokens_input', sa.Integer(), nullable=True),
        sa.Column('tokens_output', sa.Integer(), nullable=True),
        sa.Column('cost_usd', sa.Float(), nullable=True),

        # Tool calling (RAG)
        sa.Column('tool_calls', postgresql.JSON(astext_type=sa.Text()), nullable=True),

        # Execution status
        sa.Column('status', sa.String(length=50), nullable=False),
        sa.Column('error_message', sa.Text(), nullable=True),
        sa.Column('execution_time_ms', sa.Float(), nullable=False),
        sa.Column(
            'timestamp',
            sa.DateTime(),
            nullable=False,
            server_default=sa.text('now()')
        ),

        # Constraints
        sa.ForeignKeyConstraint(
            ['chain_of_work_id'],
            ['chain_of_work.id'],
            ondelete='CASCADE'  # Delete steps when chain_of_work is deleted
        ),
        sa.PrimaryKeyConstraint('id')
    )

    # Create indexes for common queries

    # 1. Primary lookup: Get all steps for a chain_of_work, ordered
    op.create_index(
        'idx_chain_steps_chain_order',
        'chain_of_work_steps',
        ['chain_of_work_id', 'step_number', 'attempt_number']
    )

    # 2. Foreign key index (required for efficient joins)
    op.create_index(
        'idx_chain_steps_chain_id',
        'chain_of_work_steps',
        ['chain_of_work_id']
    )

    # 3. Analytics: Find all failed steps
    op.create_index(
        'idx_chain_steps_status',
        'chain_of_work_steps',
        ['status']
    )

    # 4. Analytics: Find steps by agent
    op.create_index(
        'idx_chain_steps_agent',
        'chain_of_work_steps',
        ['agent_name']
    )

    # 5. Time-based queries
    op.create_index(
        'idx_chain_steps_timestamp',
        'chain_of_work_steps',
        ['timestamp']
    )

    # 6. Retry analysis: Find steps with multiple attempts
    op.create_index(
        'idx_chain_steps_attempt',
        'chain_of_work_steps',
        ['attempt_number']
    )

    # 7. Step name lookup
    op.create_index(
        'idx_chain_steps_step_name',
        'chain_of_work_steps',
        ['step_name']
    )

    # 8. Cost analysis (partial index - only rows with cost)
    op.execute(
        """
        CREATE INDEX idx_chain_steps_cost
        ON chain_of_work_steps (agent_name, cost_usd)
        WHERE cost_usd IS NOT NULL
        """
    )


def downgrade() -> None:
    """
    Drop chain_of_work_steps table and all indexes.

    Note: Indexes are dropped automatically with the table due to CASCADE,
    but we explicitly drop the partial index first to be safe.
    """

    # Drop partial index explicitly
    op.drop_index('idx_chain_steps_cost', table_name='chain_of_work_steps')

    # Drop other indexes
    op.drop_index('idx_chain_steps_step_name', table_name='chain_of_work_steps')
    op.drop_index('idx_chain_steps_attempt', table_name='chain_of_work_steps')
    op.drop_index('idx_chain_steps_timestamp', table_name='chain_of_work_steps')
    op.drop_index('idx_chain_steps_agent', table_name='chain_of_work_steps')
    op.drop_index('idx_chain_steps_status', table_name='chain_of_work_steps')
    op.drop_index('idx_chain_steps_chain_id', table_name='chain_of_work_steps')
    op.drop_index('idx_chain_steps_chain_order', table_name='chain_of_work_steps')

    # Drop table (this will also drop foreign key constraint)
    op.drop_table('chain_of_work_steps')
