"""
Credentials Management Module

Funciones helper para acceder a credenciales de clientes desde workflows.

Este módulo abstrae el acceso a las tablas:
- clients
- client_database_credentials
- client_email_credentials

Usage en workflows:
    from src.models.credentials import get_database_connection, get_email_credentials

    # Conectar a BD del cliente
    conn = get_database_connection(context["client_slug"])

    # Obtener credenciales de email
    email_creds = get_email_credentials(context["client_slug"])
"""

import os
import psycopg2
from typing import Optional, Dict, Any
from dataclasses import dataclass


@dataclass
class DatabaseCredentials:
    """Database connection credentials"""
    client_id: int
    client_slug: str
    db_host: str
    db_port: int
    db_name: str
    db_user: str
    db_password: str
    label: str
    is_primary: bool


@dataclass
class EmailCredentials:
    """Email (IMAP/SMTP) credentials"""
    client_id: int
    client_slug: str
    email_provider: str
    imap_host: str
    imap_port: int
    smtp_host: str
    smtp_port: int
    email_user: str
    email_password: str
    sender_whitelist: Optional[str]
    label: str
    is_primary: bool


def _get_nova_db_connection():
    """
    Internal: Get connection to NOVA database.

    Returns:
        psycopg2 connection object

    Raises:
        ValueError: If DATABASE_URL not set
    """
    nova_db_url = os.getenv("DATABASE_URL")
    if not nova_db_url:
        raise ValueError("DATABASE_URL environment variable not set")

    return psycopg2.connect(nova_db_url)


def get_client_id(client_slug: str) -> int:
    """
    Get client ID from slug.

    Args:
        client_slug: Client identifier (e.g., "idom")

    Returns:
        Client ID

    Raises:
        ValueError: If client not found or inactive
    """
    conn = _get_nova_db_connection()
    cursor = conn.cursor()

    try:
        cursor.execute("""
            SELECT id FROM clients
            WHERE slug = %s AND is_active = true
        """, (client_slug,))

        result = cursor.fetchone()
        if not result:
            raise ValueError(f"Client '{client_slug}' not found or inactive")

        return result[0]

    finally:
        cursor.close()
        conn.close()


def get_database_credentials(client_slug: str, label: Optional[str] = None) -> DatabaseCredentials:
    """
    Get database credentials for a client.

    Args:
        client_slug: Client identifier (e.g., "idom")
        label: Optional label to get specific credentials (default: primary)

    Returns:
        DatabaseCredentials object

    Raises:
        ValueError: If client or credentials not found

    Example:
        db_creds = get_database_credentials("idom")
        conn = psycopg2.connect(
            host=db_creds.db_host,
            port=db_creds.db_port,
            database=db_creds.db_name,
            user=db_creds.db_user,
            password=db_creds.db_password
        )
    """
    conn = _get_nova_db_connection()
    cursor = conn.cursor()

    try:
        # Get client ID
        client_id = get_client_id(client_slug)

        # Get credentials
        if label:
            cursor.execute("""
                SELECT db_host, db_port, db_name, db_user, db_password_encrypted, label, is_primary
                FROM client_database_credentials
                WHERE client_id = %s AND label = %s
            """, (client_id, label))
        else:
            cursor.execute("""
                SELECT db_host, db_port, db_name, db_user, db_password_encrypted, label, is_primary
                FROM client_database_credentials
                WHERE client_id = %s AND is_primary = true
            """, (client_id,))

        result = cursor.fetchone()
        if not result:
            raise ValueError(f"Database credentials not found for client '{client_slug}'")

        db_host, db_port, db_name, db_user, db_password, lbl, is_primary = result

        return DatabaseCredentials(
            client_id=client_id,
            client_slug=client_slug,
            db_host=db_host,
            db_port=db_port,
            db_name=db_name,
            db_user=db_user,
            db_password=db_password,
            label=lbl,
            is_primary=is_primary
        )

    finally:
        cursor.close()
        conn.close()


def get_database_connection(client_slug: str, label: Optional[str] = None):
    """
    Get ready-to-use database connection for a client.

    This is a convenience function that combines get_database_credentials()
    and psycopg2.connect().

    Args:
        client_slug: Client identifier (e.g., "idom")
        label: Optional label to get specific credentials (default: primary)

    Returns:
        psycopg2 connection object (ready to use)

    Raises:
        ValueError: If client or credentials not found
        psycopg2.Error: If connection fails

    Example:
        # In workflow ActionNode:
        conn = get_database_connection(context["client_slug"])
        cursor = conn.cursor()
        cursor.execute("INSERT INTO invoices (...) VALUES (...)")
        conn.commit()
        cursor.close()
        conn.close()
    """
    creds = get_database_credentials(client_slug, label)

    return psycopg2.connect(
        host=creds.db_host,
        port=creds.db_port,
        database=creds.db_name,
        user=creds.db_user,
        password=creds.db_password
    )


def get_email_credentials(client_slug: str, label: Optional[str] = None) -> EmailCredentials:
    """
    Get email credentials for a client.

    Args:
        client_slug: Client identifier (e.g., "idom")
        label: Optional label to get specific credentials (default: primary)

    Returns:
        EmailCredentials object

    Raises:
        ValueError: If client or credentials not found

    Example:
        email_creds = get_email_credentials("idom")

        # Connect to IMAP
        import imaplib
        mail = imaplib.IMAP4_SSL(email_creds.imap_host, email_creds.imap_port)
        mail.login(email_creds.email_user, email_creds.email_password)

        # Connect to SMTP
        import smtplib
        smtp = smtplib.SMTP(email_creds.smtp_host, email_creds.smtp_port)
        smtp.starttls()
        smtp.login(email_creds.email_user, email_creds.email_password)
    """
    conn = _get_nova_db_connection()
    cursor = conn.cursor()

    try:
        # Get client ID
        client_id = get_client_id(client_slug)

        # Get credentials
        if label:
            cursor.execute("""
                SELECT email_provider, imap_host, imap_port, smtp_host, smtp_port,
                       email_user, email_password_encrypted, sender_whitelist, label, is_primary
                FROM client_email_credentials
                WHERE client_id = %s AND label = %s
            """, (client_id, label))
        else:
            cursor.execute("""
                SELECT email_provider, imap_host, imap_port, smtp_host, smtp_port,
                       email_user, email_password_encrypted, sender_whitelist, label, is_primary
                FROM client_email_credentials
                WHERE client_id = %s AND is_primary = true
            """, (client_id,))

        result = cursor.fetchone()
        if not result:
            raise ValueError(f"Email credentials not found for client '{client_slug}'")

        (email_provider, imap_host, imap_port, smtp_host, smtp_port,
         email_user, email_password, sender_whitelist, lbl, is_primary) = result

        return EmailCredentials(
            client_id=client_id,
            client_slug=client_slug,
            email_provider=email_provider,
            imap_host=imap_host,
            imap_port=imap_port,
            smtp_host=smtp_host,
            smtp_port=smtp_port,
            email_user=email_user,
            email_password=email_password,
            sender_whitelist=sender_whitelist,
            label=lbl,
            is_primary=is_primary
        )

    finally:
        cursor.close()
        conn.close()


def get_all_credentials(client_slug: str) -> Dict[str, Any]:
    """
    Get all credentials for a client (database + email).

    Convenience function to get everything at once.

    Args:
        client_slug: Client identifier (e.g., "idom")

    Returns:
        Dict with 'database' and 'email' keys

    Example:
        creds = get_all_credentials("idom")
        db_conn = psycopg2.connect(host=creds['database'].db_host, ...)
        mail = imaplib.IMAP4_SSL(creds['email'].imap_host, ...)
    """
    return {
        'database': get_database_credentials(client_slug),
        'email': get_email_credentials(client_slug)
    }


def get_database_schemas(client_slug: str) -> Dict[str, Any]:
    """
    Get database table schemas for a client.

    Returns schema definitions for all tables configured for this client.
    This allows code generators to know which columns exist before generating SQL.

    Args:
        client_slug: Client identifier (e.g., "idom")

    Returns:
        Dict mapping table names to their schema definitions:
        {
            "invoices": {
                "columns": ["id", "email_from", "total_amount", ...],
                "types": {"id": "SERIAL", "email_from": "VARCHAR(255)", ...},
                "nullable": {"id": False, "email_from": False, ...},
                "primary_key": ["id"],
                "defaults": {"currency": "EUR"}
            },
            "orders": {...}
        }

    Example:
        schemas = get_database_schemas("idom")

        # Check which columns exist before generating INSERT
        if "invoices" in schemas:
            available_columns = schemas["invoices"]["columns"]
            if "email_from" in available_columns:
                # Safe to insert into email_from column
                pass
    """
    conn = _get_nova_db_connection()
    cursor = conn.cursor()

    try:
        # Get client ID
        client_id = get_client_id(client_slug)

        # Get all schemas for this client
        cursor.execute("""
            SELECT table_name, schema_definition
            FROM client_database_schemas
            WHERE client_id = %s
            ORDER BY table_name
        """, (client_id,))

        results = cursor.fetchall()

        # Build dict of table_name -> schema_definition
        schemas = {}
        for table_name, schema_def in results:
            schemas[table_name] = schema_def

        return schemas

    finally:
        cursor.close()
        conn.close()


# Backward compatibility with old function name
def get_client_db_connection(client_slug: str):
    """
    DEPRECATED: Use get_database_connection() instead.

    Kept for backward compatibility with existing workflows.
    """
    return get_database_connection(client_slug)
