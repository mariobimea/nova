#!/usr/bin/env python3
"""
Benchmark: EasyOCR vs Tesseract vs PaddleOCR
Comparar precisión y velocidad en factura realista
"""

import os
from dotenv import load_dotenv
from e2b import Sandbox

load_dotenv()


def benchmark_ocr():
    """Comparar diferentes engines de OCR"""

    print("=" * 70)
    print("BENCHMARK: Comparación de Engines OCR")
    print("=" * 70)
    print()

    template_id = "ybdni0ui0l3vsumat82v"

    try:
        print("🚀 Creando sandbox...")
        sandbox = Sandbox.create(template=template_id)
        print(f"✅ Sandbox: {sandbox.sandbox_id}")
        print()

        # Script de benchmark
        benchmark_script = """
import numpy as np
from PIL import Image, ImageDraw
import time

print("=" * 70)
print("BENCHMARK: EasyOCR vs Tesseract vs PaddleOCR")
print("=" * 70)
print()

# ============================================================
# CREAR FACTURA DE PRUEBA
# ============================================================
print("📝 Creando factura de prueba...")
width, height = 800, 600
img = Image.new('RGB', (width, height), color='white')
draw = ImageDraw.Draw(img)

# Texto limpio y claro para testing
test_texts = [
    (100, 50, "FACTURA N° 2024-001234"),
    (100, 100, "Fecha: 10 de Enero 2024"),
    (100, 150, "EMPRESA DEMO S.A."),
    (100, 200, "CIF: B-12345678"),
    (100, 250, "Cliente: Juan Perez Martinez"),
    (100, 300, "DNI: 12345678-A"),
    (100, 350, "Concepto: Servicios profesionales"),
    (100, 400, "Importe: 1,250.50 EUR"),
    (100, 450, "IVA (21%): 262.61 EUR"),
    (100, 500, "TOTAL: 1,513.11 EUR"),
]

for x, y, text in test_texts:
    draw.text((x, y), text, fill='black')

img_path = '/tmp/factura_test.png'
img.save(img_path)
print(f"✅ Factura guardada: {img_path}")
print()

# Textos esperados para validación
expected_keywords = [
    "FACTURA", "2024-001234", "Enero", "2024",
    "EMPRESA", "DEMO", "B-12345678",
    "Juan", "Perez", "Martinez", "12345678",
    "1250", "262", "1513", "EUR", "IVA", "TOTAL"
]

# ============================================================
# TEST 1: EasyOCR (ya instalado)
# ============================================================
print("=" * 70)
print("TEST 1: EasyOCR")
print("=" * 70)

try:
    import easyocr

    print("🔧 Inicializando EasyOCR...")
    start_time = time.time()
    reader_easy = easyocr.Reader(['es', 'en'], gpu=False, verbose=False)
    init_time = time.time() - start_time
    print(f"   ✅ Inicializado en {init_time:.2f}s")

    print("🔍 Ejecutando OCR...")
    start_time = time.time()
    results_easy = reader_easy.readtext(img_path, detail=1)
    ocr_time = time.time() - start_time

    # Analizar resultados
    texts_easy = [text for (bbox, text, conf) in results_easy]
    confidences_easy = [conf for (bbox, text, conf) in results_easy]
    avg_conf_easy = sum(confidences_easy) / len(confidences_easy) if confidences_easy else 0

    # Verificar keywords detectadas
    all_text_easy = ' '.join(texts_easy).upper()
    detected_easy = sum(1 for kw in expected_keywords if kw.upper() in all_text_easy)

    print(f"   ✅ OCR completado en {ocr_time:.2f}s")
    print(f"   📊 Elementos detectados: {len(results_easy)}")
    print(f"   📈 Confianza promedio: {avg_conf_easy:.2%}")
    print(f"   ✓  Keywords detectadas: {detected_easy}/{len(expected_keywords)}")
    print()

except Exception as e:
    print(f"   ❌ Error: {e}")
    results_easy = []
    avg_conf_easy = 0
    detected_easy = 0
    init_time = 0
    ocr_time = 0

# ============================================================
# TEST 2: Tesseract OCR
# ============================================================
print("=" * 70)
print("TEST 2: Tesseract OCR")
print("=" * 70)

try:
    # Instalar pytesseract
    print("📦 Instalando pytesseract...")
    import subprocess
    subprocess.run(['pip', 'install', '-q', 'pytesseract'], check=True)

    # Instalar tesseract binary
    print("📦 Instalando tesseract-ocr...")
    subprocess.run(['apt-get', 'update', '-qq'], check=True, capture_output=True)
    subprocess.run(['apt-get', 'install', '-y', '-qq', 'tesseract-ocr', 'tesseract-ocr-spa'],
                   check=True, capture_output=True)

    import pytesseract

    print("🔧 Tesseract instalado")

    print("🔍 Ejecutando OCR...")
    start_time = time.time()

    # OCR con Tesseract
    text_tess = pytesseract.image_to_string(img_path, lang='spa+eng')

    # OCR con datos de confianza
    data_tess = pytesseract.image_to_data(img_path, lang='spa+eng', output_type=pytesseract.Output.DICT)

    ocr_time_tess = time.time() - start_time

    # Analizar resultados
    confidences_tess = [int(conf) for conf in data_tess['conf'] if conf != '-1']
    avg_conf_tess = sum(confidences_tess) / len(confidences_tess) if confidences_tess else 0

    # Verificar keywords
    all_text_tess = text_tess.upper()
    detected_tess = sum(1 for kw in expected_keywords if kw.upper() in all_text_tess)

    print(f"   ✅ OCR completado en {ocr_time_tess:.2f}s")
    print(f"   📊 Palabras detectadas: {len([w for w in data_tess['text'] if w.strip()])}")
    print(f"   📈 Confianza promedio: {avg_conf_tess:.2%}")
    print(f"   ✓  Keywords detectadas: {detected_tess}/{len(expected_keywords)}")
    print()

except Exception as e:
    print(f"   ❌ Error: {e}")
    import traceback
    traceback.print_exc()
    avg_conf_tess = 0
    detected_tess = 0
    ocr_time_tess = 0

# ============================================================
# TEST 3: PaddleOCR
# ============================================================
print("=" * 70)
print("TEST 3: PaddleOCR")
print("=" * 70)

try:
    # Instalar PaddleOCR
    print("📦 Instalando PaddleOCR...")
    import subprocess
    subprocess.run(['pip', 'install', '-q', 'paddlepaddle', 'paddleocr'], check=True)

    from paddleocr import PaddleOCR

    print("🔧 Inicializando PaddleOCR...")
    start_time = time.time()
    ocr_paddle = PaddleOCR(use_angle_cls=True, lang='es', show_log=False)
    init_time_paddle = time.time() - start_time
    print(f"   ✅ Inicializado en {init_time_paddle:.2f}s")

    print("🔍 Ejecutando OCR...")
    start_time = time.time()
    results_paddle = ocr_paddle.ocr(img_path, cls=True)
    ocr_time_paddle = time.time() - start_time

    # Analizar resultados
    texts_paddle = []
    confidences_paddle = []

    if results_paddle and results_paddle[0]:
        for line in results_paddle[0]:
            if line:
                texts_paddle.append(line[1][0])
                confidences_paddle.append(line[1][1])

    avg_conf_paddle = sum(confidences_paddle) / len(confidences_paddle) if confidences_paddle else 0

    # Verificar keywords
    all_text_paddle = ' '.join(texts_paddle).upper()
    detected_paddle = sum(1 for kw in expected_keywords if kw.upper() in all_text_paddle)

    print(f"   ✅ OCR completado en {ocr_time_paddle:.2f}s")
    print(f"   📊 Líneas detectadas: {len(texts_paddle)}")
    print(f"   📈 Confianza promedio: {avg_conf_paddle:.2%}")
    print(f"   ✓  Keywords detectadas: {detected_paddle}/{len(expected_keywords)}")
    print()

except Exception as e:
    print(f"   ❌ Error: {e}")
    import traceback
    traceback.print_exc()
    avg_conf_paddle = 0
    detected_paddle = 0
    init_time_paddle = 0
    ocr_time_paddle = 0

# ============================================================
# COMPARACIÓN FINAL
# ============================================================
print("=" * 70)
print("📊 COMPARACIÓN FINAL")
print("=" * 70)
print()

print(f"{'Engine':<15} {'Confianza':<12} {'Keywords':<12} {'Tiempo OCR':<12}")
print("-" * 70)
print(f"{'EasyOCR':<15} {avg_conf_easy:>10.2%} {detected_easy:>5}/{len(expected_keywords):<5} {ocr_time:>10.2f}s")
print(f"{'Tesseract':<15} {avg_conf_tess:>10.2%} {detected_tess:>5}/{len(expected_keywords):<5} {ocr_time_tess:>10.2f}s")
print(f"{'PaddleOCR':<15} {avg_conf_paddle:>10.2%} {detected_paddle:>5}/{len(expected_keywords):<5} {ocr_time_paddle:>10.2f}s")
print()

# Determinar ganador
scores = [
    ('EasyOCR', avg_conf_easy * 0.6 + (detected_easy/len(expected_keywords)) * 0.4),
    ('Tesseract', avg_conf_tess * 0.6 + (detected_tess/len(expected_keywords)) * 0.4),
    ('PaddleOCR', avg_conf_paddle * 0.6 + (detected_paddle/len(expected_keywords)) * 0.4),
]

winner = max(scores, key=lambda x: x[1])
print(f"🏆 GANADOR: {winner[0]} (score: {winner[1]:.2%})")
print()

print("=" * 70)
print("✅ BENCHMARK COMPLETADO")
print("=" * 70)
"""

        print("📝 Ejecutando benchmark...")
        print("   (Esto puede tardar 2-3 minutos)")
        print()

        # Escribir script al sandbox
        sandbox.files.write("/tmp/benchmark.py", benchmark_script)

        # Ejecutar script con timeout largo
        result = sandbox.commands.run("python3 /tmp/benchmark.py", timeout=300)

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
    print("║" + " " * 15 + "BENCHMARK OCR ENGINES" + " " * 30 + "║")
    print("╚" + "═" * 68 + "╝")
    print()

    success = benchmark_ocr()
    exit(0 if success else 1)
