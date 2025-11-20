"""
Database Schema Model

Stores database table schemas for client databases.
NOVA workflows use this to know which columns exist in client tables
before generating SQL code.

Purpose:
- Prevent SQL errors from non-existent columns
- Guide code generation to use only available columns
- Document client database structure

Example:
    # Client "idom" has table "invoices" with columns:
    # id, email_from, email_subject, total_amount, currency

    # When generating code to save invoice:
    # CodeGenerator checks context['database_schemas']['invoices']['columns']
    # Only uses columns that actually exist
"""

from sqlalchemy import Column, Integer, String, Text, DateTime, ForeignKey, UniqueConstraint, JSON
from sqlalchemy.orm import relationship
from datetime import datetime
from . import Base


class ClientDatabaseSchema(Base):
    """
    Database table schema definition for a client.

    Each record defines the structure of one table in a client's database.
    Multiple clients can have tables with the same name but different schemas.

    Attributes:
        id: Primary key
        client_id: Foreign key to clients table
        database_credential_id: Foreign key to client_database_credentials
        table_name: Name of the table (e.g., "invoices", "orders")
        schema_definition: JSON with columns, types, nullable, etc.
        description: Optional human-readable description
        created_at: When this schema was created
        updated_at: When this schema was last modified

    Schema Definition Structure:
        {
            "columns": ["id", "email_from", "total_amount", "currency"],
            "types": {
                "id": "SERIAL",
                "email_from": "VARCHAR(255)",
                "total_amount": "DECIMAL(10,2)",
                "currency": "VARCHAR(3)"
            },
            "nullable": {
                "id": false,
                "email_from": false,
                "total_amount": false,
                "currency": true
            },
            "primary_key": ["id"],
            "defaults": {
                "currency": "EUR"
            }
        }

    Usage in Workflows:
        # GraphEngine loads schemas into context:
        context['database_schemas'] = {
            'invoices': {
                'columns': ['id', 'email_from', ...],
                'types': {...},
                ...
            }
        }

        # CodeGenerator uses this to generate valid SQL:
        if 'database_schemas' in context:
            schema = context['database_schemas']['invoices']
            available_columns = schema['columns']
            # Only INSERT into columns that exist
    """

    __tablename__ = "client_database_schemas"

    id = Column(Integer, primary_key=True, autoincrement=True)

    # Foreign keys
    client_id = Column(Integer, ForeignKey('clients.id', ondelete='CASCADE'), nullable=False, index=True)
    database_credential_id = Column(Integer, ForeignKey('client_database_credentials.id', ondelete='CASCADE'), nullable=False)

    # Table information
    table_name = Column(String(255), nullable=False, index=True)
    schema_definition = Column(JSON, nullable=False)
    description = Column(Text, nullable=True)

    # Metadata
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at = Column(DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships (defined in models/__init__.py to avoid circular imports)
    # client = relationship("Client", back_populates="database_schemas")
    # database_credential = relationship("ClientDatabaseCredentials", back_populates="schemas")

    # Constraints
    __table_args__ = (
        UniqueConstraint('client_id', 'table_name', name='unique_client_table'),
    )

    def __repr__(self):
        columns = self.schema_definition.get('columns', []) if self.schema_definition else []
        return f"<ClientDatabaseSchema(table='{self.table_name}', columns={len(columns)})>"

    def to_dict(self):
        """Convert to dictionary for API responses"""
        return {
            "id": self.id,
            "client_id": self.client_id,
            "database_credential_id": self.database_credential_id,
            "table_name": self.table_name,
            "schema_definition": self.schema_definition,
            "description": self.description,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }
