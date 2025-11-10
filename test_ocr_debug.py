#!/usr/bin/env python3
"""
Test de DEBUG: Verificar configuración de OpenCV y EasyOCR
"""

import os
from dotenv import load_dotenv
from e2b import Sandbox

load_dotenv()


def test_opencv_debug():
    """Debug test para verificar OpenCV y numpy"""

    print("=" * 70)
    print("DEBUG TEST: OpenCV y EasyOCR Configuration")
    print("=" * 70)
    print()

    template_id = "ybdni0ui0l3vsumat82v"

    try:
        print("🚀 Creando sandbox...")
        sandbox = Sandbox.create(template=template_id)
        print(f"✅ Sandbox: {sandbox.sandbox_id}")
        print()

        # Script de debug
        debug_script = """
import sys
import numpy as np
from PIL import Image, ImageDraw
import cv2
import easyocr

print("=" * 60)
print("DEBUG: Verificación de OpenCV y EasyOCR")
print("=" * 60)
print()

# Verificar versiones
print("📦 Versiones instaladas:")
print(f"  Python: {sys.version}")
print(f"  NumPy: {np.__version__}")
print(f"  OpenCV: {cv2.__version__}")
print(f"  EasyOCR: {easyocr.__version__}")
print()

# Paso 1: Crear imagen con PIL
print("🎨 Paso 1: Crear imagen con PIL...")
img_pil = Image.new('RGB', (400, 100), color='white')
draw = ImageDraw.Draw(img_pil)
draw.text((50, 30), "FACTURA 12345", fill='black')
print(f"  ✅ PIL Image creada")
print(f"     Mode: {img_pil.mode}")
print(f"     Size: {img_pil.size}")
print()

# Paso 2: Convertir PIL a numpy
print("🔄 Paso 2: Convertir PIL a numpy array...")
img_array = np.array(img_pil)
print(f"  ✅ Numpy array creado")
print(f"     Shape: {img_array.shape}")
print(f"     Dtype: {img_array.dtype}")
print(f"     Type: {type(img_array)}")
print(f"     Is C-contiguous: {img_array.flags['C_CONTIGUOUS']}")
print()

# Paso 3: Guardar y cargar con OpenCV
print("💾 Paso 3: Guardar con PIL y cargar con OpenCV...")
img_path = '/tmp/test_image.png'
img_pil.save(img_path)
print(f"  ✅ Guardado en: {img_path}")

img_cv = cv2.imread(img_path)
print(f"  ✅ OpenCV image cargada")
print(f"     Shape: {img_cv.shape}")
print(f"     Dtype: {img_cv.dtype}")
print(f"     Type: {type(img_cv)}")
print()

# Paso 4: Convertir RGB a BGR (lo que OpenCV espera)
print("🔄 Paso 4: Convertir RGB (PIL) a BGR (OpenCV)...")
img_bgr = cv2.cvtColor(img_array, cv2.COLOR_RGB2BGR)
print(f"  ✅ BGR array creado")
print(f"     Shape: {img_bgr.shape}")
print(f"     Dtype: {img_bgr.dtype}")
print()

# Paso 5: Test básico de EasyOCR con cada formato
print("🤖 Paso 5: Inicializando EasyOCR...")
reader = easyocr.Reader(['es', 'en'], gpu=False, verbose=False)
print(f"  ✅ EasyOCR inicializado")
print()

# Test con path (string)
print("🧪 Test 1: readtext() con PATH (string)")
try:
    results = reader.readtext(img_path, detail=0)
    print(f"  ✅ SUCCESS con path")
    print(f"     Texto: {results}")
except Exception as e:
    print(f"  ❌ FAILED con path")
    print(f"     Error: {type(e).__name__}: {e}")
print()

# Test con numpy array (BGR - desde OpenCV)
print("🧪 Test 2: readtext() con NUMPY ARRAY (BGR desde OpenCV)")
try:
    results = reader.readtext(img_cv, detail=0)
    print(f"  ✅ SUCCESS con numpy BGR")
    print(f"     Texto: {results}")
except Exception as e:
    print(f"  ❌ FAILED con numpy BGR")
    print(f"     Error: {type(e).__name__}: {e}")
print()

# Test con numpy array (RGB - desde PIL)
print("🧪 Test 3: readtext() con NUMPY ARRAY (RGB desde PIL)")
try:
    results = reader.readtext(img_array, detail=0)
    print(f"  ✅ SUCCESS con numpy RGB")
    print(f"     Texto: {results}")
except Exception as e:
    print(f"  ❌ FAILED con numpy RGB")
    print(f"     Error: {type(e).__name__}: {e}")
print()

# Test con numpy array convertido a BGR
print("🧪 Test 4: readtext() con NUMPY ARRAY (RGB->BGR convertido)")
try:
    results = reader.readtext(img_bgr, detail=0)
    print(f"  ✅ SUCCESS con numpy RGB->BGR")
    print(f"     Texto: {results}")
except Exception as e:
    print(f"  ❌ FAILED con numpy RGB->BGR")
    print(f"     Error: {type(e).__name__}: {e}")
print()

print("=" * 60)
print("✅ DEBUG TEST COMPLETADO")
print("=" * 60)
"""

        print("📝 Ejecutando debug test en el sandbox...")
        print()

        # Escribir script al sandbox
        sandbox.files.write("/tmp/test_debug.py", debug_script)

        # Ejecutar script
        result = sandbox.commands.run("python3 /tmp/test_debug.py", timeout=180)

        # Mostrar output completo
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
    success = test_opencv_debug()
    exit(0 if success else 1)
