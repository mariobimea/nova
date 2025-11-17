#!/usr/bin/env python3
"""
Test de Truncamiento Inteligente

Verifica que el nuevo sistema de truncamiento:
1. Preserva dicts/listas normales completos
2. Trunca solo data "opaca" (PDFs base64, CSVs largos)
3. Detecta tipos específicos correctamente
"""

import json
from src.core.agents.data_analyzer import DataAnalyzerAgent
from src.core.agents.code_generator import CodeGeneratorAgent


def test_truncamiento():
    """Test del truncamiento inteligente"""

    print("=" * 80)
    print("TEST: Truncamiento Inteligente")
    print("=" * 80)
    print()

    # Crear instancia del DataAnalyzer (sin necesidad de clientes reales)
    analyzer = DataAnalyzerAgent(openai_client=None, e2b_executor=None)

    # Test 1: Dict/Lista normal - NO debe truncarse
    print("📦 TEST 1: Dict/Lista normal (debe mostrarse completo)")
    context_normal = {
        "products": [
            {"name": "Product A", "price": 100, "stock": 50},
            {"name": "Product B", "price": 200, "stock": 30},
            {"name": "Product C", "price": 300, "stock": 20}
        ],
        "customer": {
            "name": "John Doe",
            "email": "john@example.com",
            "address": {
                "street": "123 Main St",
                "city": "New York"
            }
        },
        "invoice_total": 600
    }

    schema = analyzer._summarize_value(context_normal)
    print(json.dumps(schema, indent=2, ensure_ascii=False))
    print()

    # Verificar que NO se truncó
    assert "products" in schema
    assert len(schema["products"]) == 3, f"❌ Lista truncada! Esperado 3, got {len(schema['products'])}"
    assert schema["products"][0]["name"] == "Product A", "❌ Contenido de lista truncado!"
    assert "customer" in schema
    assert schema["customer"]["name"] == "John Doe", "❌ Dict truncado!"
    assert "address" in schema["customer"], "❌ Dict anidado truncado!"
    print("✅ PASS: Dict/Lista normal preservado completo")
    print()

    # Test 2: PDF en base64 - SÍ debe truncarse
    print("📄 TEST 2: PDF en base64 (debe truncarse con metadata)")
    pdf_base64 = "JVBERi0xLjQKJeLjz9MKMyAwIG9iaiA8PC9..." + "x" * 50000  # PDF simulado
    context_pdf = {
        "email_subject": "Invoice #123",
        "attachments": [
            {
                "filename": "invoice.pdf",
                "data": pdf_base64
            }
        ]
    }

    schema_pdf = analyzer._summarize_value(context_pdf)
    print(json.dumps(schema_pdf, indent=2, ensure_ascii=False))
    print()

    # Verificar que SÍ se truncó el PDF pero NO el resto
    assert schema_pdf["email_subject"] == "Invoice #123", "❌ String corto truncado!"
    assert isinstance(schema_pdf["attachments"], list), "❌ Lista de attachments truncada!"
    assert schema_pdf["attachments"][0]["filename"] == "invoice.pdf", "❌ Filename truncado!"
    assert "<base64 PDF:" in schema_pdf["attachments"][0]["data"], f"❌ PDF no detectado! Got: {schema_pdf['attachments'][0]['data']}"
    assert "starts with JVBERi" in schema_pdf["attachments"][0]["data"], "❌ Metadata de PDF incompleta!"
    print("✅ PASS: PDF truncado con metadata, resto preservado")
    print()

    # Test 3: Lista muy grande (>100) - debe truncarse parcialmente
    print("📋 TEST 3: Lista muy grande (>100 items)")
    context_large_list = {
        "items": [{"id": i, "value": f"item_{i}"} for i in range(150)]
    }

    schema_large = analyzer._summarize_value(context_large_list)
    print(f"Lista de {len(context_large_list['items'])} items:")
    print(json.dumps(schema_large, indent=2, ensure_ascii=False))
    print()

    # Verificar que se truncó a 5 items + mensaje
    assert len(schema_large["items"]) == 6, f"❌ Lista grande mal truncada! Esperado 6 (5 items + mensaje), got {len(schema_large['items'])}"
    assert "... (+145 more items)" in str(schema_large["items"][-1]), "❌ Mensaje de truncamiento incorrecto!"
    print("✅ PASS: Lista grande truncada correctamente (5 items + mensaje)")
    print()

    # Test 4: CSV largo - debe detectarse y truncarse
    print("📊 TEST 4: CSV largo (debe detectarse y truncarse)")
    csv_data = "name,age,email\n" + "\n".join([f"user_{i},{20+i},user{i}@example.com" for i in range(500)])
    context_csv = {
        "csv_file": csv_data
    }

    schema_csv = analyzer._summarize_value(context_csv)
    print(json.dumps(schema_csv, indent=2, ensure_ascii=False))
    print()

    # Verificar que se detectó como CSV
    assert "<CSV data:" in schema_csv["csv_file"], f"❌ CSV no detectado! Got: {schema_csv['csv_file']}"
    assert "~500 lines" in schema_csv["csv_file"], "❌ Metadata de CSV incorrecta!"
    print("✅ PASS: CSV detectado y truncado con metadata")
    print()

    # Test 5: String mediano (500-1000 chars) - debe mostrarse preview
    print("📝 TEST 5: String mediano (500-1000 chars)")
    medium_string = "Lorem ipsum " * 60  # ~720 chars
    context_medium = {
        "description": medium_string
    }

    schema_medium = analyzer._summarize_value(context_medium)
    print(json.dumps(schema_medium, indent=2, ensure_ascii=False))
    print()

    # Verificar que tiene preview
    assert "<string:" in schema_medium["description"], f"❌ String mediano no truncado! Got: {schema_medium['description'][:100]}"
    assert "preview:" in schema_medium["description"], "❌ Preview no incluido!"
    print("✅ PASS: String mediano con preview")
    print()

    # Test 6: Valores falsy (0, False, [], {}) - deben preservarse
    print("⚖️ TEST 6: Valores falsy (deben preservarse)")
    context_falsy = {
        "pages": 0,
        "has_text": False,
        "attachments": [],
        "metadata": {},
        "price": None
    }

    schema_falsy = analyzer._summarize_value(context_falsy)
    print(json.dumps(schema_falsy, indent=2, ensure_ascii=False))
    print()

    # Verificar que los valores falsy NO se truncaron
    assert schema_falsy["pages"] == 0, "❌ Valor 0 truncado!"
    assert schema_falsy["has_text"] is False, "❌ Valor False truncado!"
    assert schema_falsy["attachments"] == [], "❌ Lista vacía truncada!"
    assert schema_falsy["metadata"] == {}, "❌ Dict vacío truncado!"
    assert schema_falsy["price"] is None, "❌ Valor None truncado!"
    print("✅ PASS: Valores falsy preservados correctamente")
    print()

    # Test 7: Depth profundo - debe limitarse a max_depth=4
    print("🌳 TEST 7: Depth profundo (max_depth=4)")
    context_deep = {
        "level1": {
            "level2": {
                "level3": {
                    "level4": {
                        "level5": {
                            "data": "too deep"
                        }
                    }
                }
            }
        }
    }

    schema_deep = analyzer._summarize_value(context_deep)
    print(json.dumps(schema_deep, indent=2, ensure_ascii=False))
    print()

    # Verificar que se limitó al depth 4
    level4 = schema_deep["level1"]["level2"]["level3"]["level4"]
    assert "<max depth reached:" in str(level4), f"❌ Depth no limitado! Got: {level4}"
    print("✅ PASS: Depth limitado correctamente a max_depth=4")
    print()

    print("=" * 80)
    print("✅ TODOS LOS TESTS PASARON")
    print("=" * 80)
    print()
    print("RESUMEN:")
    print("  ✅ Dicts/listas normales → Preservados completos")
    print("  ✅ PDFs base64 → Truncados con metadata")
    print("  ✅ Listas muy grandes (>100) → Truncadas a 5 items + mensaje")
    print("  ✅ CSVs largos → Detectados y truncados con metadata")
    print("  ✅ Strings medianos → Truncados con preview")
    print("  ✅ Valores falsy → Preservados correctamente")
    print("  ✅ Depth profundo → Limitado a max_depth=4")
    print()


if __name__ == "__main__":
    test_truncamiento()
