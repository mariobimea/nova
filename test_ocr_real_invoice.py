#!/usr/bin/env python3
"""
Test con factura realista para medir confianza real de EasyOCR
"""

import os
from dotenv import load_dotenv
from e2b import Sandbox

load_dotenv()


def test_real_invoice():
    """Test con factura más realista"""

    print("=" * 70)
    print("TEST: EasyOCR con Factura Realista")
    print("=" * 70)
    print()

    template_id = "ybdni0ui0l3vsumat82v"

    try:
        print("🚀 Creando sandbox...")
        sandbox = Sandbox.create(template=template_id)
        print(f"✅ Sandbox: {sandbox.sandbox_id}")
        print()

        # Script que crea una factura más realista
        invoice_script = """
import numpy as np
from PIL import Image, ImageDraw, ImageFont
import easyocr

print("=" * 60)
print("PRUEBA CON FACTURA REALISTA")
print("=" * 60)
print()

# Crear imagen más grande y realista
print("📝 Creando factura simulada...")
width, height = 800, 1000
img = Image.new('RGB', (width, height), color='white')
draw = ImageDraw.Draw(img)

# Simular estructura de factura
# ENCABEZADO
draw.rectangle([50, 50, 750, 150], outline='black', width=2)
draw.text((60, 60), "FACTURA", fill='black')
draw.text((60, 90), "Numero: F-2024-001234", fill='black')
draw.text((60, 120), "Fecha: 10/01/2024", fill='black')

# DATOS EMPRESA
draw.rectangle([50, 170, 750, 270], outline='black', width=2)
draw.text((60, 180), "EMPRESA DEMO S.A.", fill='black')
draw.text((60, 210), "CIF: B12345678", fill='black')
draw.text((60, 240), "Direccion: Calle Principal 123", fill='black')

# DATOS CLIENTE
draw.rectangle([50, 290, 750, 390], outline='black', width=2)
draw.text((60, 300), "CLIENTE:", fill='black')
draw.text((60, 330), "Juan Perez Martinez", fill='black')
draw.text((60, 360), "DNI: 12345678A", fill='black')

# CONCEPTOS
draw.rectangle([50, 410, 750, 560], outline='black', width=2)
draw.text((60, 420), "CONCEPTO", fill='black')
draw.text((400, 420), "CANTIDAD", fill='black')
draw.text((600, 420), "PRECIO", fill='black')
draw.line([50, 450, 750, 450], fill='black', width=1)
draw.text((60, 460), "Producto A", fill='black')
draw.text((420, 460), "10", fill='black')
draw.text((610, 460), "25.00 EUR", fill='black')
draw.text((60, 500), "Producto B", fill='black')
draw.text((420, 500), "5", fill='black')
draw.text((610, 500), "50.00 EUR", fill='black')

# TOTALES
draw.rectangle([50, 580, 750, 700], outline='black', width=2)
draw.text((60, 590), "SUBTOTAL:", fill='black')
draw.text((610, 590), "500.00 EUR", fill='black')
draw.text((60, 630), "IVA (21%):", fill='black')
draw.text((610, 630), "105.00 EUR", fill='black')
draw.line([50, 660, 750, 660], fill='black', width=2)
draw.text((60, 670), "TOTAL:", fill='black')
draw.text((610, 670), "605.00 EUR", fill='black')

print(f"   ✅ Factura creada: {width}x{height} pixels")
print()

# Guardar imagen
img_path = '/tmp/factura_realista.png'
img.save(img_path)
print(f"💾 Factura guardada en: {img_path}")
print()

# Inicializar EasyOCR
print("🤖 Inicializando EasyOCR...")
reader = easyocr.Reader(['es', 'en'], gpu=False, verbose=False)
print("   ✅ EasyOCR inicializado")
print()

# Ejecutar OCR
print("🔍 Ejecutando OCR sobre factura...")
results = reader.readtext(img_path, detail=1)
print(f"   ✅ OCR completado: {len(results)} elementos detectados")
print()

# Mostrar resultados
print("📄 RESULTADOS DETALLADOS:")
print("=" * 60)

if not results:
    print("❌ No se detectó texto")
else:
    # Ordenar por confianza (mayor a menor)
    results_sorted = sorted(results, key=lambda x: x[2], reverse=True)

    print(f"\\n{'Texto':<40} {'Confianza':>10}")
    print("-" * 60)

    total_confidence = 0
    for bbox, text, confidence in results_sorted:
        print(f"{text:<40} {confidence:>9.2%}")
        total_confidence += confidence

    avg_confidence = total_confidence / len(results)

    print("-" * 60)
    print(f"{'PROMEDIO':<40} {avg_confidence:>9.2%}")
    print()

    # Verificar elementos clave
    all_text = ' '.join([text for (bbox, text, conf) in results]).upper()

    print("✅ VERIFICACIÓN DE CAMPOS CLAVE:")
    print("-" * 60)
    checks = [
        ("FACTURA", "FACTURA" in all_text),
        ("Número de factura", any("001234" in t or "F-2024" in t for (_, t, _) in results)),
        ("Fecha", any("10/01/2024" in t or "2024" in t for (_, t, _) in results)),
        ("CIF/NIF", any("B12345678" in t or "12345678A" in t for (_, t, _) in results)),
        ("Cantidades", any("25.00" in t or "50.00" in t or "605.00" in t for (_, t, _) in results)),
        ("IVA", "IVA" in all_text or "21%" in all_text),
        ("TOTAL", "TOTAL" in all_text)
    ]

    passed = 0
    for check_name, result in checks:
        status = "✅" if result else "❌"
        print(f"  {status} {check_name}")
        if result:
            passed += 1

    print("-" * 60)
    print(f"Campos detectados: {passed}/{len(checks)}")
    print()

    if avg_confidence >= 0.80:
        print("🎉 EXCELENTE: Confianza promedio > 80%")
    elif avg_confidence >= 0.70:
        print("✅ BUENO: Confianza promedio > 70%")
    elif avg_confidence >= 0.60:
        print("⚠️  ACEPTABLE: Confianza promedio > 60%")
    else:
        print("❌ BAJO: Confianza promedio < 60%")

print()
print("=" * 60)
print("✅ PRUEBA COMPLETADA")
print("=" * 60)
"""

        print("📝 Ejecutando prueba con factura realista...")
        print("   (Esto puede tardar 60-90 segundos)")
        print()

        # Escribir script al sandbox
        sandbox.files.write("/tmp/test_invoice.py", invoice_script)

        # Ejecutar script
        result = sandbox.commands.run("python3 /tmp/test_invoice.py", timeout=180)

        # Mostrar output
        print(result.stdout)

        if result.stderr:
            print("⚠️  Stderr:")
            print(result.stderr)

        sandbox.kill()

        return result.exit_code == 0

    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()
        return False


if __name__ == "__main__":
    print()
    print("╔" + "═" * 68 + "╗")
    print("║" + " " * 15 + "TEST DE FACTURA REALISTA" + " " * 28 + "║")
    print("╚" + "═" * 68 + "╝")
    print()

    success = test_real_invoice()
    exit(0 if success else 1)
