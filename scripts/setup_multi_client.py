"""
Setup Script for Multi-Client Architecture

This script helps you configure NOVA for multi-client support:
1. Runs Alembic migration to create client_credentials table
2. Inserts test client credentials
3. Verifies connection to client database
4. Creates invoices table in client database

Usage:
    python scripts/setup_multi_client.py
"""

import os
import sys
from datetime import datetime

# Add src to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker
from src.models.client_credentials import ClientCredentials, Base
import psycopg2


def run_alembic_migration():
    """Run Alembic migration to create client_credentials table"""
    print("\n🔧 Running Alembic migration...")
    os.system("cd /Users/marioferrer/automatizaciones/nova && alembic upgrade head")
    print("✅ Migration complete")


def insert_test_client(session, client_db_url: str):
    """Insert test client credentials"""
    print("\n📝 Inserting test client credentials...")

    # Parse client DB URL
    # Format: postgresql://user:password@host:port/dbname
    from urllib.parse import urlparse
    parsed = urlparse(client_db_url)

    client = ClientCredentials(
        client_name="Test Client",
        client_slug="test-client",
        db_host=parsed.hostname,
        db_port=parsed.port or 5432,
        db_name=parsed.path.lstrip('/'),
        db_user=parsed.username,
        db_password=parsed.password,
        is_active=True,
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow(),
    )

    # Check if already exists
    existing = session.query(ClientCredentials).filter(
        ClientCredentials.client_slug == "test-client"
    ).first()

    if existing:
        print("⚠️  Test client already exists, updating...")
        existing.db_host = parsed.hostname
        existing.db_port = parsed.port or 5432
        existing.db_name = parsed.path.lstrip('/')
        existing.db_user = parsed.username
        existing.db_password = parsed.password
        existing.updated_at = datetime.utcnow()
    else:
        session.add(client)

    session.commit()
    print(f"✅ Test client configured: {client.client_slug}")
    print(f"   DB: {client.db_host}:{client.db_port}/{client.db_name}")


def create_invoices_table(client_db_url: str):
    """Create invoices table in client database"""
    print("\n🗄️  Creating invoices table in client database...")

    try:
        conn = psycopg2.connect(client_db_url)
        cursor = conn.cursor()

        # Read SQL file
        sql_file = os.path.join(
            os.path.dirname(__file__),
            '../database/client_schemas/invoices.sql'
        )
        with open(sql_file, 'r') as f:
            sql = f.read()

        cursor.execute(sql)
        conn.commit()

        print("✅ Invoices table created successfully")

        cursor.close()
        conn.close()

    except Exception as e:
        print(f"❌ Error creating invoices table: {e}")
        raise


def verify_connection(client_db_url: str):
    """Verify connection to client database"""
    print("\n🔌 Verifying connection to client database...")

    try:
        conn = psycopg2.connect(client_db_url)
        cursor = conn.cursor()
        cursor.execute("SELECT version();")
        version = cursor.fetchone()[0]
        print(f"✅ Connected successfully!")
        print(f"   PostgreSQL version: {version[:50]}...")
        cursor.close()
        conn.close()
        return True
    except Exception as e:
        print(f"❌ Connection failed: {e}")
        return False


def main():
    print("=" * 60)
    print("NOVA Multi-Client Setup")
    print("=" * 60)

    # Get environment variables
    nova_db_url = os.getenv("DATABASE_URL")
    client_db_url = os.getenv("CLIENT_DB_URL")

    if not nova_db_url:
        print("\n❌ ERROR: DATABASE_URL not set (NOVA database)")
        print("   Set it in .env file or export it:")
        print("   export DATABASE_URL=postgresql://...")
        return

    if not client_db_url:
        print("\n❌ ERROR: CLIENT_DB_URL not set (Client database)")
        print("   Set it in .env file or export it:")
        print("   export CLIENT_DB_URL=postgresql://...")
        print("\n💡 To create a second PostgreSQL in Railway:")
        print("   1. Go to Railway dashboard")
        print("   2. Click 'New' → 'Database' → 'Add PostgreSQL'")
        print("   3. Name it 'client-db'")
        print("   4. Copy the DATABASE_URL and set as CLIENT_DB_URL")
        return

    print(f"\n📊 NOVA Database: {nova_db_url[:30]}...")
    print(f"📊 Client Database: {client_db_url[:30]}...")

    # Step 1: Run migration
    run_alembic_migration()

    # Step 2: Connect to NOVA DB
    print("\n🔌 Connecting to NOVA database...")
    engine = create_engine(nova_db_url)
    Session = sessionmaker(bind=engine)
    session = Session()

    # Step 3: Insert test client
    insert_test_client(session, client_db_url)

    # Step 4: Verify client DB connection
    if not verify_connection(client_db_url):
        print("\n❌ Setup incomplete due to connection error")
        return

    # Step 5: Create invoices table
    create_invoices_table(client_db_url)

    # Step 6: Test the helper function
    print("\n🧪 Testing get_client_db_connection()...")
    from src.models.client_credentials import get_client_db_connection

    try:
        conn = get_client_db_connection("test-client")
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM invoices;")
        count = cursor.fetchone()[0]
        print(f"✅ Helper function works! Invoices table has {count} rows")
        cursor.close()
        conn.close()
    except Exception as e:
        print(f"❌ Helper function failed: {e}")

    print("\n" + "=" * 60)
    print("✅ Multi-Client Setup Complete!")
    print("=" * 60)
    print("\nNext steps:")
    print("1. Create workflow JSON: fixtures/invoice_processing_workflow.json")
    print("2. Add Gmail credentials to .env:")
    print("   GMAIL_USER=your_email@gmail.com")
    print("   GMAIL_APP_PASSWORD=xxxx-xxxx-xxxx-xxxx")
    print("3. Run workflow test: python examples/run_invoice_workflow.py")
    print()

    session.close()


if __name__ == "__main__":
    main()
