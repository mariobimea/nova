"""
Agregar Credenciales de Email a un Cliente

Script interactivo para agregar credenciales de Gmail/IMAP a un cliente existente.

Usage:
    python scripts/add_email_credentials.py
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
print("📧 NOVA - Agregar Credenciales de Email")
print("=" * 70)

# Verificar DATABASE_URL
nova_db_url = os.getenv("DATABASE_URL")
if not nova_db_url:
    print("\n❌ ERROR: DATABASE_URL no configurada")
    sys.exit(1)

try:
    conn = psycopg2.connect(nova_db_url)
    cursor = conn.cursor()

    # ==============================================================================
    # Mostrar clientes disponibles
    # ==============================================================================
    print("\n📋 Clientes disponibles:")
    cursor.execute("SELECT id, slug, name FROM clients WHERE is_active = true ORDER BY slug")
    clients = cursor.fetchall()

    if not clients:
        print("\n❌ No hay clientes configurados.")
        print("   Primero crea un cliente con: python scripts/create_credentials_tables.py")
        sys.exit(1)

    for client_id, slug, name in clients:
        print(f"   - {slug} ({name})")

    # ==============================================================================
    # Input: Cliente
    # ==============================================================================
    print("\n" + "─" * 70)
    client_slug = input("Cliente (slug): ").strip() or "idom"

    cursor.execute("SELECT id, name FROM clients WHERE slug = %s", (client_slug,))
    client = cursor.fetchone()

    if not client:
        print(f"\n❌ Cliente '{client_slug}' no encontrado")
        sys.exit(1)

    client_id, client_name = client
    print(f"✅ Cliente seleccionado: {client_name} ({client_slug})")

    # ==============================================================================
    # Input: Credenciales de Email
    # ==============================================================================
    print("\n" + "─" * 70)
    print("📧 Credenciales de Email")
    print("─" * 70)

    print("\n💡 Para Gmail:")
    print("   1. Ir a: https://myaccount.google.com/security")
    print("   2. Activar 2-Step Verification")
    print("   3. Ir a 'App passwords'")
    print("   4. Generar password para 'Mail'")
    print("   5. Copiar el password de 16 caracteres\n")

    email_user = input("Email user (ej: facturas@idom.com): ").strip()
    if not email_user:
        print("❌ Email user es requerido")
        sys.exit(1)

    email_password = input("App Password (xxxx-xxxx-xxxx-xxxx): ").strip()
    if not email_password:
        print("❌ App Password es requerido")
        sys.exit(1)

    sender_whitelist = input("Sender whitelist (opcional, ej: proveedor@empresa.com): ").strip()

    label = input("Label (opcional, ej: 'Invoices'): ").strip() or "Primary Email"

    # ==============================================================================
    # Configuración del proveedor
    # ==============================================================================
    print("\n📮 Configuración del proveedor de email:")
    print("   1. Gmail (default)")
    print("   2. Outlook")
    print("   3. Custom IMAP")

    provider_choice = input("\nSeleccionar (1-3): ").strip() or "1"

    if provider_choice == "1":
        email_provider = "gmail"
        imap_host = "imap.gmail.com"
        imap_port = 993
        smtp_host = "smtp.gmail.com"
        smtp_port = 587
    elif provider_choice == "2":
        email_provider = "outlook"
        imap_host = "outlook.office365.com"
        imap_port = 993
        smtp_host = "smtp.office365.com"
        smtp_port = 587
    else:
        email_provider = "custom"
        imap_host = input("IMAP Host: ").strip()
        imap_port = int(input("IMAP Port (993): ").strip() or "993")
        smtp_host = input("SMTP Host: ").strip()
        smtp_port = int(input("SMTP Port (587): ").strip() or "587")

    # ==============================================================================
    # Confirmar
    # ==============================================================================
    print("\n" + "─" * 70)
    print("📋 Resumen:")
    print("─" * 70)
    print(f"  Cliente: {client_name} ({client_slug})")
    print(f"  Email: {email_user}")
    print(f"  Provider: {email_provider}")
    print(f"  IMAP: {imap_host}:{imap_port}")
    print(f"  SMTP: {smtp_host}:{smtp_port}")
    print(f"  Whitelist: {sender_whitelist or '(ninguno)'}")
    print(f"  Label: {label}")
    print("─" * 70)

    confirm = input("\n¿Continuar? (y/n): ").strip().lower()
    if confirm != 'y':
        print("❌ Cancelado")
        sys.exit(0)

    # ==============================================================================
    # Insertar credenciales
    # ==============================================================================
    print("\n💾 Guardando credenciales...")

    # Check if already exists
    cursor.execute("""
        SELECT id FROM client_email_credentials
        WHERE client_id = %s AND email_user = %s
    """, (client_id, email_user))

    existing = cursor.fetchone()

    if existing:
        print(f"\n⚠️  Ya existen credenciales para {email_user}")
        update = input("¿Actualizar? (y/n): ").strip().lower()

        if update == 'y':
            cursor.execute("""
                UPDATE client_email_credentials
                SET email_password_encrypted = %s,
                    sender_whitelist = %s,
                    email_provider = %s,
                    imap_host = %s,
                    imap_port = %s,
                    smtp_host = %s,
                    smtp_port = %s,
                    label = %s,
                    updated_at = NOW()
                WHERE id = %s
            """, (email_password, sender_whitelist, email_provider,
                  imap_host, imap_port, smtp_host, smtp_port, label, existing[0]))

            print("✅ Credenciales actualizadas")
        else:
            print("❌ Cancelado")
            sys.exit(0)
    else:
        # Check if this will be the primary email
        cursor.execute("""
            SELECT COUNT(*) FROM client_email_credentials
            WHERE client_id = %s
        """, (client_id,))

        email_count = cursor.fetchone()[0]
        is_primary = (email_count == 0)  # First email is primary

        cursor.execute("""
            INSERT INTO client_email_credentials (
                client_id, email_provider, imap_host, imap_port, smtp_host, smtp_port,
                email_user, email_password_encrypted, sender_whitelist,
                label, is_primary, created_at, updated_at
            ) VALUES (
                %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, NOW(), NOW()
            )
        """, (client_id, email_provider, imap_host, imap_port, smtp_host, smtp_port,
              email_user, email_password, sender_whitelist, label, is_primary))

        print(f"✅ Credenciales agregadas (Primary: {is_primary})")

    conn.commit()

    # ==============================================================================
    # Verificar
    # ==============================================================================
    print("\n" + "─" * 70)
    print("📊 Credenciales de email para este cliente:")
    print("─" * 70)

    cursor.execute("""
        SELECT email_user, email_provider, label, is_primary
        FROM client_email_credentials
        WHERE client_id = %s
        ORDER BY is_primary DESC, created_at
    """, (client_id,))

    for row in cursor.fetchall():
        email, provider, lbl, is_prim = row
        primary_mark = "⭐" if is_prim else "  "
        print(f"  {primary_mark} {email} ({provider}) - {lbl}")

    cursor.close()
    conn.close()

    # ==============================================================================
    # RESUMEN
    # ==============================================================================
    print("\n" + "=" * 70)
    print("✅ CREDENCIALES DE EMAIL CONFIGURADAS")
    print("=" * 70)

    print(f"\n✅ Cliente '{client_slug}' ahora puede:")
    print("  - Leer emails desde IMAP")
    print("  - Enviar emails vía SMTP")
    print(f"  - Filtrar por whitelist: {sender_whitelist or 'Sin filtro'}")

    print("\n🎯 Próximos pasos:")
    print("  1. Actualizar funciones helper en src/models/credentials.py")
    print("  2. Crear workflow de facturas que use estas credenciales")
    print("  3. Probar lectura de emails con: python examples/test_email_read.py")

    print("\n" + "=" * 70)
    print()

except Exception as e:
    print(f"\n❌ Error: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)
