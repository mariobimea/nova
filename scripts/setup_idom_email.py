"""
Setup Email Credentials for IDOM

Configura automáticamente las credenciales de Gmail para el cliente IDOM.
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
print("📧 NOVA - Configurar Email de IDOM")
print("=" * 70)

# Verificar DATABASE_URL
nova_db_url = os.getenv("DATABASE_URL")
if not nova_db_url:
    print("\n❌ ERROR: DATABASE_URL no configurada")
    sys.exit(1)

# Credenciales de IDOM
CLIENT_SLUG = "idom"
EMAIL_USER = "ferrermarinmario@gmail.com"
EMAIL_PASSWORD = "uxqo ijfo lpig udev"
SENDER_WHITELIST = "mario@bimea.es"
LABEL = "Facturas IDOM"

try:
    conn = psycopg2.connect(nova_db_url)
    cursor = conn.cursor()

    print(f"\n✅ Configurando email para cliente: {CLIENT_SLUG}")
    print(f"   Email: {EMAIL_USER}")
    print(f"   Whitelist: {SENDER_WHITELIST}")

    # Get client ID
    cursor.execute("SELECT id, name FROM clients WHERE slug = %s", (CLIENT_SLUG,))
    client = cursor.fetchone()

    if not client:
        print(f"\n❌ Cliente '{CLIENT_SLUG}' no encontrado")
        sys.exit(1)

    client_id, client_name = client

    # Check if email already exists
    cursor.execute("""
        SELECT id FROM client_email_credentials
        WHERE client_id = %s AND email_user = %s
    """, (client_id, EMAIL_USER))

    existing = cursor.fetchone()

    if existing:
        print(f"\n⚠️  Credenciales ya existen, actualizando...")
        cursor.execute("""
            UPDATE client_email_credentials
            SET email_password_encrypted = %s,
                sender_whitelist = %s,
                label = %s,
                updated_at = NOW()
            WHERE id = %s
        """, (EMAIL_PASSWORD, SENDER_WHITELIST, LABEL, existing[0]))
        print("✅ Credenciales actualizadas")
    else:
        # Check if this will be the primary email
        cursor.execute("""
            SELECT COUNT(*) FROM client_email_credentials
            WHERE client_id = %s
        """, (client_id,))
        email_count = cursor.fetchone()[0]
        is_primary = (email_count == 0)

        print(f"\n💾 Insertando credenciales (Primary: {is_primary})...")
        cursor.execute("""
            INSERT INTO client_email_credentials (
                client_id, email_provider, imap_host, imap_port, smtp_host, smtp_port,
                email_user, email_password_encrypted, sender_whitelist,
                label, is_primary, created_at, updated_at
            ) VALUES (
                %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, NOW(), NOW()
            )
        """, (client_id, 'gmail', 'imap.gmail.com', 993, 'smtp.gmail.com', 587,
              EMAIL_USER, EMAIL_PASSWORD, SENDER_WHITELIST, LABEL, is_primary))
        print("✅ Credenciales insertadas")

    conn.commit()

    # Verify
    print("\n" + "─" * 70)
    print("📊 Credenciales configuradas para IDOM:")
    print("─" * 70)

    cursor.execute("""
        SELECT email_user, email_provider, label, is_primary, sender_whitelist
        FROM client_email_credentials
        WHERE client_id = %s
        ORDER BY is_primary DESC
    """, (client_id,))

    for row in cursor.fetchall():
        email, provider, lbl, is_prim, whitelist = row
        primary_mark = "⭐" if is_prim else "  "
        print(f"  {primary_mark} {email}")
        print(f"     Provider: {provider}")
        print(f"     Label: {lbl}")
        print(f"     Whitelist: {whitelist or '(sin filtro)'}")

    cursor.close()
    conn.close()

    print("\n" + "=" * 70)
    print("✅ EMAIL CONFIGURADO EXITOSAMENTE")
    print("=" * 70)

    print(f"\n✅ Cliente IDOM ahora puede:")
    print(f"  - Leer emails desde: {EMAIL_USER}")
    print(f"  - Filtrar solo emails de: {SENDER_WHITELIST}")
    print(f"  - Enviar respuestas vía SMTP")

    print("\n🎯 Próximos pasos:")
    print("  1. Actualizar funciones helper (src/models/credentials.py)")
    print("  2. Crear workflow de facturas")
    print("  3. Probar lectura de emails")

    print("\n" + "=" * 70)
    print()

except Exception as e:
    print(f"\n❌ Error: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)
