"""
Add Invoice Schema for Client

This script creates the database schema definition for the 'invoices' table.
NOVA will use this to know which columns exist before generating SQL INSERT statements.

Usage:
    python fixtures/add_invoice_schema.py
"""

import sys
import os

# Add parent directory to path to import modules
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from src.database import SessionLocal
from src.models.database_schema import ClientDatabaseSchema


def add_invoice_schema():
    """Add schema definition for invoices table"""

    db = SessionLocal()

    try:
        # Get client ID 1 (assuming it exists from previous fixtures)
        # You can change this to match your client_id
        client_id = 1

        # Get database_credential_id for this client
        # Assuming it's 1, change if needed
        database_credential_id = 1

        # Check if schema already exists
        existing = db.query(ClientDatabaseSchema).filter(
            ClientDatabaseSchema.client_id == client_id,
            ClientDatabaseSchema.table_name == "invoices"
        ).first()

        if existing:
            print(f"⚠️  Schema for 'invoices' already exists (ID: {existing.id})")
            print(f"   Current columns: {existing.schema_definition.get('columns', [])}")
            response = input("   Do you want to update it? (y/N): ")

            if response.lower() != 'y':
                print("❌ Aborted")
                return

            # Update existing schema
            existing.schema_definition = {
                "columns": [
                    "id",
                    "email_from",
                    "email_subject",
                    "total_amount",
                    "currency",
                    "created_at"
                ],
                "types": {
                    "id": "SERIAL",
                    "email_from": "VARCHAR(255)",
                    "email_subject": "VARCHAR(500)",
                    "total_amount": "DECIMAL(10,2)",
                    "currency": "VARCHAR(3)",
                    "created_at": "TIMESTAMP"
                },
                "nullable": {
                    "id": False,
                    "email_from": False,
                    "email_subject": True,
                    "total_amount": False,
                    "currency": True,
                    "created_at": False
                },
                "primary_key": ["id"],
                "defaults": {
                    "currency": "EUR",
                    "created_at": "NOW()"
                }
            }
            existing.description = "Invoice table schema - stores processed invoice data from emails"

            db.commit()

            print("✅ Schema 'invoices' updated successfully")
            print(f"   Columns: {', '.join(existing.schema_definition['columns'])}")

        else:
            # Create new schema
            schema = ClientDatabaseSchema(
                client_id=client_id,
                database_credential_id=database_credential_id,
                table_name="invoices",
                schema_definition={
                    "columns": [
                        "id",
                        "email_from",
                        "email_subject",
                        "total_amount",
                        "currency",
                        "created_at"
                    ],
                    "types": {
                        "id": "SERIAL",
                        "email_from": "VARCHAR(255)",
                        "email_subject": "VARCHAR(500)",
                        "total_amount": "DECIMAL(10,2)",
                        "currency": "VARCHAR(3)",
                        "created_at": "TIMESTAMP"
                    },
                    "nullable": {
                        "id": False,
                        "email_from": False,
                        "email_subject": True,
                        "total_amount": False,
                        "currency": True,
                        "created_at": False
                    },
                    "primary_key": ["id"],
                    "defaults": {
                        "currency": "EUR",
                        "created_at": "NOW()"
                    }
                },
                description="Invoice table schema - stores processed invoice data from emails"
            )

            db.add(schema)
            db.commit()
            db.refresh(schema)

            print("✅ Schema 'invoices' created successfully")
            print(f"   Schema ID: {schema.id}")
            print(f"   Client ID: {schema.client_id}")
            print(f"   Table: {schema.table_name}")
            print(f"   Columns: {', '.join(schema.schema_definition['columns'])}")

    except Exception as e:
        print(f"❌ Error: {e}")
        db.rollback()
        raise

    finally:
        db.close()


if __name__ == "__main__":
    print("=" * 60)
    print("Adding Invoice Schema to NOVA")
    print("=" * 60)
    add_invoice_schema()
    print("=" * 60)
