"""
Add Invoice Schema for Client

Simple SQL-based script that doesn't rely on SQLAlchemy ORM.
"""

import os
import psycopg2
import json

def add_invoice_schema():
    """Add schema definition for invoices table"""

    # Connect directly to database
    DATABASE_URL = os.getenv("DATABASE_URL")
    if not DATABASE_URL:
        raise ValueError("DATABASE_URL not set")

    conn = psycopg2.connect(DATABASE_URL)
    cursor = conn.cursor()

    try:
        # Get client ID 1
        client_id = 1

        # Get database_credential_id for this client
        cursor.execute("SELECT id FROM client_database_credentials WHERE client_id = %s LIMIT 1", (client_id,))
        result = cursor.fetchone()
        if not result:
            print(f"❌ No database credentials found for client_id {client_id}")
            return

        database_credential_id = result[0]
        print(f"✅ Found database credentials (ID: {database_credential_id})")

        # Check if schema already exists
        cursor.execute(
            "SELECT id FROM client_database_schemas WHERE client_id = %s AND table_name = %s",
            (client_id, "invoices")
        )
        existing = cursor.fetchone()

        schema_definition = {
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

        if existing:
            schema_id = existing[0]
            print(f"⚠️  Schema for 'invoices' already exists (ID: {schema_id})")
            print(f"   Updating schema...")

            # Update
            cursor.execute("""
                UPDATE client_database_schemas
                SET schema_definition = %s,
                    description = %s,
                    updated_at = NOW()
                WHERE id = %s
            """, (
                json.dumps(schema_definition),
                "Invoice table schema - stores processed invoice data from emails",
                schema_id
            ))

            conn.commit()
            print("✅ Schema 'invoices' updated successfully")

        else:
            # Insert new schema
            cursor.execute("""
                INSERT INTO client_database_schemas
                (client_id, database_credential_id, table_name, schema_definition, description, created_at, updated_at)
                VALUES (%s, %s, %s, %s, %s, NOW(), NOW())
                RETURNING id
            """, (
                client_id,
                database_credential_id,
                "invoices",
                json.dumps(schema_definition),
                "Invoice table schema - stores processed invoice data from emails"
            ))

            schema_id = cursor.fetchone()[0]
            conn.commit()

            print("✅ Schema 'invoices' created successfully")
            print(f"   Schema ID: {schema_id}")

        print(f"   Client ID: {client_id}")
        print(f"   Table: invoices")
        print(f"   Columns: {', '.join(schema_definition['columns'])}")

    except Exception as e:
        print(f"❌ Error: {e}")
        conn.rollback()
        raise

    finally:
        cursor.close()
        conn.close()


if __name__ == "__main__":
    print("=" * 60)
    print("Adding Invoice Schema to NOVA")
    print("=" * 60)
    add_invoice_schema()
    print("=" * 60)
