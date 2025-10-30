"""
Quick Setup Script - Multi-Client Architecture

Este script hace TODO automáticamente:
1. Ejecuta migración para crear tabla client_credentials
2. Crea tabla invoices en BD de IDOM
3. Inserta credenciales de IDOM
4. Verifica que todo funciona
"""

import os
import sys
from datetime import datetime
from dotenv import load_dotenv

# Cargar variables de entorno
load_dotenv()

# Add src to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

import psycopg2
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

print("="* 70)
print("🚀 NOVA Multi-Client Quick Setup")
print("=" * 70)

# Verificar variables de entorno
nova_db_url = os.getenv("DATABASE_URL")
client_db_url = os.getenv("CLIENT_DB_URL")

if not nova_db_url:
    print("\n❌ ERROR: DATABASE_URL no configurada")
    print("   Revisa tu archivo .env")
    sys.exit(1)

if not client_db_url:
    print("\n❌ ERROR: CLIENT_DB_URL no configurada")
    print("   Revisa tu archivo .env")
    sys.exit(1)

print(f"\n✅ NOVA DB: {nova_db_url[:40]}...")
print(f"✅ IDOM DB: {client_db_url[:40]}...")

# ==============================================================================
# PASO 1: Crear tabla client_credentials en NOVA DB
# ==============================================================================
print("\n" + "─" * 70)
print("📋 PASO 1: Crear tabla client_credentials en NOVA DB")
print("─" * 70)

try:
    conn = psycopg2.connect(nova_db_url)
    cursor = conn.cursor()

    # SQL para crear tabla
    create_table_sql = """
    CREATE TABLE IF NOT EXISTS client_credentials (
        id SERIAL PRIMARY KEY,
        client_name VARCHAR(255) NOT NULL,
        client_slug VARCHAR(100) NOT NULL UNIQUE,
        db_host VARCHAR(255) NOT NULL,
        db_port INTEGER NOT NULL DEFAULT 5432,
        db_name VARCHAR(255) NOT NULL,
        db_user VARCHAR(255) NOT NULL,
        db_password VARCHAR(255) NOT NULL,
        is_active BOOLEAN NOT NULL DEFAULT TRUE,
        created_at TIMESTAMP NOT NULL DEFAULT NOW(),
        updated_at TIMESTAMP NOT NULL DEFAULT NOW()
    );

    CREATE INDEX IF NOT EXISTS ix_client_credentials_id
        ON client_credentials(id);
    CREATE UNIQUE INDEX IF NOT EXISTS ix_client_credentials_client_slug
        ON client_credentials(client_slug);
    CREATE INDEX IF NOT EXISTS ix_client_credentials_is_active
        ON client_credentials(is_active);
    """

    cursor.execute(create_table_sql)
    conn.commit()

    print("✅ Tabla client_credentials creada correctamente")

    cursor.close()
    conn.close()

except Exception as e:
    print(f"❌ Error creando tabla client_credentials: {e}")
    sys.exit(1)

# ==============================================================================
# PASO 2: Insertar credenciales de IDOM
# ==============================================================================
print("\n" + "─" * 70)
print("📋 PASO 2: Insertar credenciales de IDOM en client_credentials")
print("─" * 70)

try:
    from urllib.parse import urlparse

    # Parsear CLIENT_DB_URL
    parsed = urlparse(client_db_url)

    conn = psycopg2.connect(nova_db_url)
    cursor = conn.cursor()

    # Check if already exists
    cursor.execute("SELECT id FROM client_credentials WHERE client_slug = 'idom'")
    existing = cursor.fetchone()

    if existing:
        print("⚠️  Cliente IDOM ya existe, actualizando...")
        cursor.execute("""
            UPDATE client_credentials
            SET db_host = %s,
                db_port = %s,
                db_name = %s,
                db_user = %s,
                db_password = %s,
                updated_at = NOW()
            WHERE client_slug = 'idom'
        """, (
            parsed.hostname,
            parsed.port or 5432,
            parsed.path.lstrip('/'),
            parsed.username,
            parsed.password
        ))
    else:
        print("✨ Creando nuevo cliente IDOM...")
        cursor.execute("""
            INSERT INTO client_credentials (
                client_name, client_slug,
                db_host, db_port, db_name, db_user, db_password,
                is_active, created_at, updated_at
            ) VALUES (
                %s, %s, %s, %s, %s, %s, %s, %s, NOW(), NOW()
            )
        """, (
            'IDOM',
            'idom',
            parsed.hostname,
            parsed.port or 5432,
            parsed.path.lstrip('/'),
            parsed.username,
            parsed.password,
            True
        ))

    conn.commit()

    print(f"✅ Credenciales de IDOM configuradas")
    print(f"   Host: {parsed.hostname}")
    print(f"   Port: {parsed.port or 5432}")
    print(f"   DB: {parsed.path.lstrip('/')}")

    cursor.close()
    conn.close()

except Exception as e:
    print(f"❌ Error insertando credenciales: {e}")
    sys.exit(1)

# ==============================================================================
# PASO 3: Crear tabla invoices en BD de IDOM
# ==============================================================================
print("\n" + "─" * 70)
print("📋 PASO 3: Crear tabla invoices en BD de IDOM")
print("─" * 70)

try:
    conn = psycopg2.connect(client_db_url)
    cursor = conn.cursor()

    # SQL para crear tabla invoices
    create_invoices_sql = """
    CREATE TABLE IF NOT EXISTS invoices (
        id SERIAL PRIMARY KEY,
        email_from VARCHAR(255) NOT NULL,
        email_subject TEXT,
        email_date TIMESTAMP,
        pdf_filename VARCHAR(255),
        pdf_content BYTEA,
        pdf_size_bytes INTEGER,
        ocr_text TEXT,
        ocr_method VARCHAR(50),
        total_amount DECIMAL(10,2),
        currency VARCHAR(10) DEFAULT 'EUR',
        processed_by_workflow_id INTEGER,
        processed_by_execution_id INTEGER,
        created_at TIMESTAMP DEFAULT NOW(),
        updated_at TIMESTAMP DEFAULT NOW()
    );

    CREATE INDEX IF NOT EXISTS idx_invoices_email_from
        ON invoices(email_from);
    CREATE INDEX IF NOT EXISTS idx_invoices_total_amount
        ON invoices(total_amount);
    CREATE INDEX IF NOT EXISTS idx_invoices_created_at
        ON invoices(created_at);
    """

    cursor.execute(create_invoices_sql)
    conn.commit()

    # Verificar cuántas facturas hay
    cursor.execute("SELECT COUNT(*) FROM invoices")
    count = cursor.fetchone()[0]

    print(f"✅ Tabla invoices creada correctamente")
    print(f"   Facturas existentes: {count}")

    cursor.close()
    conn.close()

except Exception as e:
    print(f"❌ Error creando tabla invoices: {e}")
    sys.exit(1)

# ==============================================================================
# PASO 4: Verificar función get_client_db_connection()
# ==============================================================================
print("\n" + "─" * 70)
print("📋 PASO 4: Verificar función get_client_db_connection()")
print("─" * 70)

try:
    from src.models.client_credentials import get_client_db_connection

    # Intentar conectar usando la función
    conn = get_client_db_connection("idom")
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) FROM invoices")
    count = cursor.fetchone()[0]

    print(f"✅ Función get_client_db_connection() funciona correctamente")
    print(f"   Conexión exitosa a BD de IDOM")
    print(f"   Facturas en tabla: {count}")

    cursor.close()
    conn.close()

except Exception as e:
    print(f"❌ Error verificando función: {e}")
    sys.exit(1)

# ==============================================================================
# RESUMEN FINAL
# ==============================================================================
print("\n" + "=" * 70)
print("✅ SETUP COMPLETADO EXITOSAMENTE")
print("=" * 70)

print("\n📊 Resumen:")
print("  ✅ Tabla client_credentials creada en NOVA DB")
print("  ✅ Credenciales de IDOM insertadas")
print("  ✅ Tabla invoices creada en BD de IDOM")
print("  ✅ Función get_client_db_connection() funciona")

print("\n🎯 Próximos pasos:")
print("  1. Configurar credenciales de Gmail en .env:")
print("     GMAIL_USER=tu_email@gmail.com")
print("     GMAIL_APP_PASSWORD=xxxx-xxxx-xxxx-xxxx")
print("  2. Crear workflow JSON de facturas")
print("  3. Ejecutar workflow de prueba")

print("\n" + "=" * 70)
print()
