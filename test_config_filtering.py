#!/usr/bin/env python3
"""
Test rápido para verificar que el filtrado de CONFIG_KEYS funciona.

Este test simula el contexto que entra al InputAnalyzer/DataAnalyzer
y verifica que solo reciben data relevante (no configuración).
"""

from src.core.agents.config_keys import CONFIG_KEYS, filter_config_keys

# Contexto de ejemplo (el mismo que mostraste)
context_example = {
    # ❌ Configuración (se debe filtrar)
    "client_slug": "idom",
    "email_user": "ferrermarinmario@gmail.com",
    "email_password": "uxqo ijfo lpig udev",
    "imap_host": "imap.gmail.com",
    "imap_port": 993,
    "smtp_host": "smtp.gmail.com",
    "smtp_port": 587,
    "sender_whitelist": "mario@bimea.es",
    "db_host": "metro.proxy.rlwy.net",
    "db_port": 19822,
    "db_name": "railway",
    "db_user": "postgres",
    "db_password": "pWBOqTDVxeUkJgztLsXWIGgrDVnwNdHb",
    "database_schemas": {
        "invoices": {
            "columns": ["id", "email_from", "email_subject", "total_amount", "currency", "created_at"],
        }
    },
    "GCP_SERVICE_ACCOUNT_JSON": "<string: 2354 chars>",
    "_analyzed_keys": [],

    # ✅ Data real (NO se debe filtrar)
    "email_data": {
        "subject": "Invoice #123",
        "body": "Please find attached...",
        "attachments": [
            {
                "filename": "invoice.pdf",
                "data": "<base64 PDF: 50000 chars>"  # Data opaca que SÍ necesita análisis
            }
        ]
    },
    "extracted_text": "Invoice total: $1,234.56"
}

print("=" * 80)
print("TEST: Filtrado de CONFIG_KEYS")
print("=" * 80)

print("\n1️⃣ Contexto ORIGINAL:")
print(f"   Total keys: {len(context_example)}")
print(f"   Keys: {list(context_example.keys())}")

print("\n2️⃣ CONFIG_KEYS que se filtran:")
print(f"   Total: {len(CONFIG_KEYS)}")
print(f"   Keys: {sorted(CONFIG_KEYS)}")

print("\n3️⃣ Aplicando filtro...")
filtered = filter_config_keys(context_example)

print("\n4️⃣ Contexto FILTRADO (lo que reciben InputAnalyzer/DataAnalyzer):")
print(f"   Total keys: {len(filtered)}")
print(f"   Keys: {list(filtered.keys())}")

print("\n5️⃣ Keys que se FILTRARON (config):")
removed_keys = set(context_example.keys()) - set(filtered.keys())
print(f"   Total: {len(removed_keys)}")
print(f"   Keys: {sorted(removed_keys)}")

print("\n6️⃣ Verificación:")
# Todas las config keys deben haber sido filtradas
config_keys_in_original = set(context_example.keys()) & CONFIG_KEYS
config_keys_in_filtered = set(filtered.keys()) & CONFIG_KEYS

if config_keys_in_filtered:
    print(f"   ❌ FALLO: Quedan config keys en el contexto filtrado: {config_keys_in_filtered}")
else:
    print(f"   ✅ ÉXITO: Todas las config keys fueron filtradas ({len(config_keys_in_original)} keys)")

# Solo deben quedar las data keys
expected_data_keys = {"email_data", "extracted_text"}
if set(filtered.keys()) == expected_data_keys:
    print(f"   ✅ ÉXITO: Solo quedan data keys: {expected_data_keys}")
else:
    print(f"   ⚠️ WARNING: Keys inesperadas en contexto filtrado: {set(filtered.keys()) - expected_data_keys}")

print("\n" + "=" * 80)
print("Ahorro de tokens estimado:")
print("=" * 80)

# Estimar tokens (aproximado: 1 token ≈ 4 chars)
def estimate_tokens(data):
    import json
    json_str = json.dumps(data, ensure_ascii=False)
    return len(json_str) // 4

tokens_original = estimate_tokens(context_example)
tokens_filtered = estimate_tokens(filtered)
tokens_saved = tokens_original - tokens_filtered
savings_pct = (tokens_saved / tokens_original) * 100

print(f"   Tokens originales: ~{tokens_original}")
print(f"   Tokens filtrados:  ~{tokens_filtered}")
print(f"   Tokens ahorrados:  ~{tokens_saved} ({savings_pct:.1f}%)")
print(f"\n   💸 Ahorro en InputAnalyzer: ~{tokens_saved} tokens menos por ejecución")
print(f"   💸 Ahorro en DataAnalyzer:  ~{tokens_saved} tokens menos por ejecución")

print("\n" + "=" * 80)
