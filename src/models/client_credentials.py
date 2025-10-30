"""
Client Credentials Model

Stores database connection information for client databases.
NOVA workflows use this to connect to external client databases.

Security Notes:
- Phase 1: Passwords stored in plaintext (acceptable for MVP)
- Phase 2: Encrypt passwords with Fernet or use HashiCorp Vault
- Production: Use secrets manager (AWS Secrets Manager, Railway Secrets, etc.)
"""

from sqlalchemy import Column, Integer, String, Boolean, DateTime
from sqlalchemy.orm import declarative_base
from datetime import datetime

Base = declarative_base()


class ClientCredentials(Base):
    """
    Client database credentials for multi-tenant workflows.

    Each client has their own database where NOVA writes results.
    Workflows read credentials from this table to connect.

    Example:
        # In workflow ActionNode:
        from src.models.client_credentials import get_client_db_connection

        conn = get_client_db_connection(context["client_slug"])
        cursor = conn.cursor()
        cursor.execute("INSERT INTO invoices (...) VALUES (...)")
        conn.commit()
    """

    __tablename__ = "client_credentials"

    id = Column(Integer, primary_key=True, index=True)

    # Client identification
    client_name = Column(String(255), nullable=False)  # e.g., "ACME Corp"
    client_slug = Column(String(100), nullable=False, unique=True, index=True)  # e.g., "acme"

    # Database connection details
    db_host = Column(String(255), nullable=False)  # e.g., "postgres.railway.internal"
    db_port = Column(Integer, nullable=False, default=5432)
    db_name = Column(String(255), nullable=False)  # e.g., "railway"
    db_user = Column(String(255), nullable=False)  # e.g., "postgres"
    db_password = Column(String(255), nullable=False)  # TODO: Encrypt in Phase 2

    # Metadata
    is_active = Column(Boolean, nullable=False, default=True, index=True)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at = Column(DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)

    def __repr__(self):
        return f"<ClientCredentials(client_slug='{self.client_slug}', db_host='{self.db_host}')>"

    def to_dict(self):
        """Convert to dictionary (excludes password for security)"""
        return {
            "id": self.id,
            "client_name": self.client_name,
            "client_slug": self.client_slug,
            "db_host": self.db_host,
            "db_port": self.db_port,
            "db_name": self.db_name,
            "db_user": self.db_user,
            # "db_password": NOT INCLUDED for security
            "is_active": self.is_active,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
        }


# Helper function for workflows
def get_client_db_connection(client_slug: str):
    """
    Get database connection for a specific client.

    This function is imported and used by workflow ActionNodes
    to connect to client databases.

    Args:
        client_slug: Client identifier (e.g., "acme", "test-client")

    Returns:
        psycopg2 connection object

    Raises:
        ValueError: If client not found or inactive
        psycopg2.Error: If connection fails

    Example:
        # In workflow ActionNode code:
        conn = get_client_db_connection(context["client_slug"])
        cursor = conn.cursor()
        cursor.execute("INSERT INTO invoices (amount) VALUES (%s)", (1000,))
        conn.commit()
        cursor.close()
        conn.close()
    """
    import os
    import psycopg2
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker

    # Connect to NOVA database to fetch credentials
    nova_db_url = os.getenv("DATABASE_URL")
    if not nova_db_url:
        raise ValueError("DATABASE_URL not set (NOVA database)")

    engine = create_engine(nova_db_url)
    Session = sessionmaker(bind=engine)
    session = Session()

    try:
        # Fetch client credentials
        creds = session.query(ClientCredentials).filter(
            ClientCredentials.client_slug == client_slug,
            ClientCredentials.is_active == True
        ).first()

        if not creds:
            raise ValueError(f"Client '{client_slug}' not found or inactive")

        # Connect to client database
        conn = psycopg2.connect(
            host=creds.db_host,
            port=creds.db_port,
            database=creds.db_name,
            user=creds.db_user,
            password=creds.db_password,
        )

        return conn

    finally:
        session.close()
