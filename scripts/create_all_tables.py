"""
Crear TODAS las tablas de NOVA en la base de datos

Este script crea:
1. workflows
2. executions
3. chain_of_work
4. client_credentials (si no existe ya)
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
print("🗄️  NOVA - Crear Todas las Tablas")
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
    # TABLA 1: workflows
    # ==============================================================================
    print("\n" + "─" * 70)
    print("📋 Creando tabla: workflows")
    print("─" * 70)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS workflows (
            id SERIAL PRIMARY KEY,
            name VARCHAR(255) NOT NULL,
            description TEXT,
            graph_definition JSON NOT NULL,
            created_at TIMESTAMP NOT NULL DEFAULT NOW(),
            updated_at TIMESTAMP NOT NULL DEFAULT NOW()
        );

        CREATE INDEX IF NOT EXISTS ix_workflows_id ON workflows(id);
        CREATE INDEX IF NOT EXISTS ix_workflows_name ON workflows(name);
    """)

    print("✅ Tabla 'workflows' creada")

    # ==============================================================================
    # TABLA 2: executions
    # ==============================================================================
    print("\n" + "─" * 70)
    print("📋 Creando tabla: executions")
    print("─" * 70)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS executions (
            id SERIAL PRIMARY KEY,
            workflow_id INTEGER NOT NULL REFERENCES workflows(id),
            status VARCHAR(50) NOT NULL DEFAULT 'pending',
            started_at TIMESTAMP,
            completed_at TIMESTAMP,
            result JSON,
            error TEXT,
            created_at TIMESTAMP NOT NULL DEFAULT NOW()
        );

        CREATE INDEX IF NOT EXISTS ix_executions_id ON executions(id);
        CREATE INDEX IF NOT EXISTS ix_executions_workflow_id ON executions(workflow_id);
        CREATE INDEX IF NOT EXISTS ix_executions_status ON executions(status);
    """)

    print("✅ Tabla 'executions' creada")

    # ==============================================================================
    # TABLA 3: chain_of_work
    # ==============================================================================
    print("\n" + "─" * 70)
    print("📋 Creando tabla: chain_of_work")
    print("─" * 70)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS chain_of_work (
            id SERIAL PRIMARY KEY,
            execution_id INTEGER NOT NULL REFERENCES executions(id),
            node_id VARCHAR(255) NOT NULL,
            node_type VARCHAR(50) NOT NULL,
            code_executed TEXT,
            input_context JSON,
            output_result JSON,
            execution_time FLOAT,
            status VARCHAR(50) NOT NULL DEFAULT 'success',
            error_message TEXT,
            decision_result VARCHAR(10),
            path_taken VARCHAR(255),
            timestamp TIMESTAMP NOT NULL DEFAULT NOW()
        );

        CREATE INDEX IF NOT EXISTS ix_chain_of_work_id ON chain_of_work(id);
        CREATE INDEX IF NOT EXISTS ix_chain_of_work_execution_id ON chain_of_work(execution_id);
        CREATE INDEX IF NOT EXISTS ix_chain_of_work_node_id ON chain_of_work(node_id);
    """)

    print("✅ Tabla 'chain_of_work' creada")

    # ==============================================================================
    # TABLA 4: client_credentials (si no existe ya)
    # ==============================================================================
    print("\n" + "─" * 70)
    print("📋 Creando tabla: client_credentials (si no existe)")
    print("─" * 70)

    cursor.execute("""
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

        CREATE INDEX IF NOT EXISTS ix_client_credentials_id ON client_credentials(id);
        CREATE UNIQUE INDEX IF NOT EXISTS ix_client_credentials_client_slug ON client_credentials(client_slug);
        CREATE INDEX IF NOT EXISTS ix_client_credentials_is_active ON client_credentials(is_active);
    """)

    print("✅ Tabla 'client_credentials' verificada")

    # Commit all changes
    conn.commit()

    # ==============================================================================
    # Verificar tablas creadas
    # ==============================================================================
    print("\n" + "─" * 70)
    print("📊 Verificando tablas creadas")
    print("─" * 70)

    cursor.execute("""
        SELECT table_name
        FROM information_schema.tables
        WHERE table_schema = 'public'
        ORDER BY table_name
    """)

    tables = cursor.fetchall()

    print("\n✅ Tablas en NOVA DB:")
    for table in tables:
        print(f"   - {table[0]}")

    cursor.close()
    conn.close()

    # ==============================================================================
    # RESUMEN
    # ==============================================================================
    print("\n" + "=" * 70)
    print("✅ TODAS LAS TABLAS CREADAS EXITOSAMENTE")
    print("=" * 70)

    print("\n📊 Estructura de NOVA DB:")
    print("  ✅ workflows          - Definiciones de workflows")
    print("  ✅ executions         - Historial de ejecuciones")
    print("  ✅ chain_of_work      - Auditoría detallada paso a paso")
    print("  ✅ client_credentials - Credenciales de clientes")

    print("\n🎯 Sistema listo para:")
    print("  1. Crear workflows via API o scripts")
    print("  2. Ejecutar workflows con GraphEngine")
    print("  3. Guardar resultados en BD de clientes")
    print("  4. Auditar cada paso con Chain of Work")

    print("\n" + "=" * 70)
    print()

except Exception as e:
    print(f"\n❌ Error: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)
