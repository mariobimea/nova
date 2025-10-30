"""
Crear Tablas de Credenciales Separadas por Servicio

Este script crea:
1. clients - Información del cliente
2. client_database_credentials - Credenciales de PostgreSQL
3. client_email_credentials - Credenciales de Gmail/IMAP

Luego migra los datos de la tabla antigua client_credentials a las nuevas.
"""

import os
import sys
from dotenv import load_dotenv

# Cargar variables de entorno
load_dotenv()

# Add src to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

import psycopg2

print("="* 70)
print("🔐 NOVA - Crear Tablas de Credenciales (Multi-Servicio)")
print("=" * 70)

# Verificar DATABASE_URL
nova_db_url = os.getenv("DATABASE_URL")
if not nova_db_url:
    print("\n❌ ERROR: DATABASE_URL no configurada")
    sys.exit(1)

print(f"\n✅ NOVA DB: {nova_db_url[:40]}...")

try:
    conn = psycopg2.connect(nova_db_url)
    cursor = conn.cursor()

    # ==============================================================================
    # TABLA 1: clients
    # ==============================================================================
    print("\n" + "─" * 70)
    print("📋 Creando tabla: clients")
    print("─" * 70)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS clients (
            id SERIAL PRIMARY KEY,
            name VARCHAR(255) NOT NULL,
            slug VARCHAR(100) NOT NULL UNIQUE,
            description TEXT,
            is_active BOOLEAN DEFAULT true,
            created_at TIMESTAMP NOT NULL DEFAULT NOW(),
            updated_at TIMESTAMP NOT NULL DEFAULT NOW()
        );

        CREATE INDEX IF NOT EXISTS idx_clients_id ON clients(id);
        CREATE UNIQUE INDEX IF NOT EXISTS idx_clients_slug ON clients(slug);
        CREATE INDEX IF NOT EXISTS idx_clients_is_active ON clients(is_active);
    """)

    print("✅ Tabla 'clients' creada")

    # ==============================================================================
    # TABLA 2: client_database_credentials
    # ==============================================================================
    print("\n" + "─" * 70)
    print("📋 Creando tabla: client_database_credentials")
    print("─" * 70)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS client_database_credentials (
            id SERIAL PRIMARY KEY,
            client_id INTEGER NOT NULL REFERENCES clients(id) ON DELETE CASCADE,

            -- Connection info
            db_host VARCHAR(255) NOT NULL,
            db_port INTEGER NOT NULL DEFAULT 5432,
            db_name VARCHAR(255) NOT NULL,
            db_user VARCHAR(255) NOT NULL,
            db_password_encrypted TEXT NOT NULL,

            -- Metadata
            label VARCHAR(100),
            is_primary BOOLEAN DEFAULT true,

            created_at TIMESTAMP NOT NULL DEFAULT NOW(),
            updated_at TIMESTAMP NOT NULL DEFAULT NOW()
        );

        CREATE INDEX IF NOT EXISTS idx_client_db_creds_id ON client_database_credentials(id);
        CREATE INDEX IF NOT EXISTS idx_client_db_creds_client_id ON client_database_credentials(client_id);
        CREATE INDEX IF NOT EXISTS idx_client_db_creds_is_primary ON client_database_credentials(is_primary);
    """)

    print("✅ Tabla 'client_database_credentials' creada")

    # ==============================================================================
    # TABLA 3: client_email_credentials
    # ==============================================================================
    print("\n" + "─" * 70)
    print("📋 Creando tabla: client_email_credentials")
    print("─" * 70)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS client_email_credentials (
            id SERIAL PRIMARY KEY,
            client_id INTEGER NOT NULL REFERENCES clients(id) ON DELETE CASCADE,

            -- Email provider info
            email_provider VARCHAR(50) DEFAULT 'gmail',
            imap_host VARCHAR(255) DEFAULT 'imap.gmail.com',
            imap_port INTEGER DEFAULT 993,
            smtp_host VARCHAR(255) DEFAULT 'smtp.gmail.com',
            smtp_port INTEGER DEFAULT 587,

            -- Credentials
            email_user VARCHAR(255) NOT NULL,
            email_password_encrypted TEXT NOT NULL,

            -- Whitelist (comma-separated emails)
            sender_whitelist TEXT,

            -- Metadata
            label VARCHAR(100),
            is_primary BOOLEAN DEFAULT true,

            created_at TIMESTAMP NOT NULL DEFAULT NOW(),
            updated_at TIMESTAMP NOT NULL DEFAULT NOW()
        );

        CREATE INDEX IF NOT EXISTS idx_client_email_creds_id ON client_email_credentials(id);
        CREATE INDEX IF NOT EXISTS idx_client_email_creds_client_id ON client_email_credentials(client_id);
        CREATE INDEX IF NOT EXISTS idx_client_email_creds_is_primary ON client_email_credentials(is_primary);
    """)

    print("✅ Tabla 'client_email_credentials' creada")

    conn.commit()

    # ==============================================================================
    # MIGRACIÓN: De client_credentials antigua a nuevas tablas
    # ==============================================================================
    print("\n" + "─" * 70)
    print("🔄 Migrando datos de client_credentials a nuevas tablas")
    print("─" * 70)

    # Check if old table exists
    cursor.execute("""
        SELECT EXISTS (
            SELECT FROM information_schema.tables
            WHERE table_schema = 'public'
            AND table_name = 'client_credentials'
        )
    """)
    old_table_exists = cursor.fetchone()[0]

    if old_table_exists:
        # Get data from old table
        cursor.execute("SELECT * FROM client_credentials")
        old_creds = cursor.fetchall()

        if old_creds:
            print(f"\n✨ Encontrados {len(old_creds)} clientes en tabla antigua")

            for row in old_creds:
                # Old table columns: id, client_name, client_slug, db_host, db_port, db_name, db_user, db_password, is_active, created_at, updated_at
                old_id, client_name, client_slug, db_host, db_port, db_name, db_user, db_password, is_active, created_at, updated_at = row

                print(f"\n   Migrando cliente: {client_slug}")

                # Check if already migrated
                cursor.execute("SELECT id FROM clients WHERE slug = %s", (client_slug,))
                existing = cursor.fetchone()

                if existing:
                    print(f"   ⚠️  Cliente '{client_slug}' ya existe, saltando...")
                    continue

                # 1. Insert into clients
                cursor.execute("""
                    INSERT INTO clients (name, slug, is_active, created_at, updated_at)
                    VALUES (%s, %s, %s, %s, %s)
                    RETURNING id
                """, (client_name, client_slug, is_active, created_at, updated_at))

                new_client_id = cursor.fetchone()[0]

                # 2. Insert into client_database_credentials
                cursor.execute("""
                    INSERT INTO client_database_credentials (
                        client_id, db_host, db_port, db_name, db_user, db_password_encrypted,
                        label, is_primary, created_at, updated_at
                    ) VALUES (
                        %s, %s, %s, %s, %s, %s, %s, %s, %s, %s
                    )
                """, (new_client_id, db_host, db_port, db_name, db_user, db_password,
                      'Main DB', True, created_at, updated_at))

                print(f"   ✅ Cliente '{client_slug}' migrado exitosamente")

            conn.commit()
            print(f"\n✅ Migración completada: {len(old_creds)} clientes")

            # Ask if user wants to drop old table
            print("\n⚠️  NOTA: La tabla antigua 'client_credentials' todavía existe.")
            print("   Puedes eliminarla manualmente cuando estés seguro:")
            print("   DROP TABLE client_credentials CASCADE;")

        else:
            print("\n⚠️  Tabla antigua 'client_credentials' está vacía, nada que migrar")
    else:
        print("\n✅ No existe tabla antigua 'client_credentials', nada que migrar")

    # ==============================================================================
    # Verificar tablas creadas
    # ==============================================================================
    print("\n" + "─" * 70)
    print("📊 Verificando estructura")
    print("─" * 70)

    # Count clients
    cursor.execute("SELECT COUNT(*) FROM clients")
    client_count = cursor.fetchone()[0]

    # Count database credentials
    cursor.execute("SELECT COUNT(*) FROM client_database_credentials")
    db_creds_count = cursor.fetchone()[0]

    # Count email credentials
    cursor.execute("SELECT COUNT(*) FROM client_email_credentials")
    email_creds_count = cursor.fetchone()[0]

    print(f"\n✅ Estructura creada:")
    print(f"   - Clientes: {client_count}")
    print(f"   - Credenciales de BD: {db_creds_count}")
    print(f"   - Credenciales de Email: {email_creds_count}")

    # Show clients
    if client_count > 0:
        cursor.execute("""
            SELECT c.slug, c.name, c.is_active,
                   COUNT(DISTINCT db.id) as db_count,
                   COUNT(DISTINCT em.id) as email_count
            FROM clients c
            LEFT JOIN client_database_credentials db ON c.id = db.client_id
            LEFT JOIN client_email_credentials em ON c.id = em.client_id
            GROUP BY c.id, c.slug, c.name, c.is_active
        """)

        print("\n📋 Clientes configurados:")
        for row in cursor.fetchall():
            slug, name, is_active, db_count, email_count = row
            status = "✅" if is_active else "❌"
            print(f"   {status} {slug} ({name})")
            print(f"      - BDs configuradas: {db_count}")
            print(f"      - Emails configurados: {email_count}")

    cursor.close()
    conn.close()

    # ==============================================================================
    # RESUMEN
    # ==============================================================================
    print("\n" + "=" * 70)
    print("✅ TABLAS DE CREDENCIALES CREADAS EXITOSAMENTE")
    print("=" * 70)

    print("\n📊 Nueva Estructura:")
    print("  ✅ clients                      - Información del cliente")
    print("  ✅ client_database_credentials  - Credenciales de PostgreSQL")
    print("  ✅ client_email_credentials     - Credenciales de Gmail/IMAP")

    print("\n🎯 Próximos pasos:")
    print("  1. Agregar credenciales de email para cliente IDOM:")
    print("     python scripts/add_idom_email.py")
    print("  2. Actualizar funciones helper en src/models/")
    print("  3. Crear workflow de facturas")

    print("\n💡 Nota: Para Phase 2, considera migrar a AWS Secrets Manager")
    print("   Ver: documentacion/futuro/AWS-SECRETS-MANAGER.md")

    print("\n" + "=" * 70)
    print()

except Exception as e:
    print(f"\n❌ Error: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)
