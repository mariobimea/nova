#!/usr/bin/env python3
"""
Test de DEBUG: Investigar conflicto de NumPy
"""

import os
from dotenv import load_dotenv
from e2b import Sandbox

load_dotenv()


def test_numpy_conflict():
    """Debug test para identificar conflicto de NumPy"""

    print("=" * 70)
    print("DEBUG TEST: Conflicto de NumPy")
    print("=" * 70)
    print()

    template_id = "ybdni0ui0l3vsumat82v"

    try:
        print("🚀 Creando sandbox...")
        sandbox = Sandbox.create(template=template_id)
        print(f"✅ Sandbox: {sandbox.sandbox_id}")
        print()

        # Script de debug más profundo
        debug_script = """
import sys
import importlib.metadata

print("=" * 60)
print("DEBUG: Análisis profundo de NumPy")
print("=" * 60)
print()

# Ver todos los paquetes instalados relacionados con numpy
print("📦 Paquetes relacionados con NumPy:")
try:
    for dist in importlib.metadata.distributions():
        if 'numpy' in dist.name.lower():
            print(f"  {dist.name} == {dist.version}")
except:
    pass
print()

# Importar numpy y verificar
print("🔍 Importando numpy...")
import numpy as np
print(f"  ✅ NumPy importado: {np.__version__}")
print(f"  📁 Location: {np.__file__}")
print()

# Verificar que tipo de ndarray está disponible
print("🧪 Verificando np.ndarray:")
print(f"  Type: {type(np.ndarray)}")
print(f"  Module: {np.ndarray.__module__}")
print()

# Crear un array simple
print("✏️  Creando array de prueba...")
arr = np.array([1, 2, 3])
print(f"  Array: {arr}")
print(f"  Type: {type(arr)}")
print(f"  Type name: {type(arr).__name__}")
print(f"  Module: {type(arr).__module__}")
print(f"  isinstance(arr, np.ndarray): {isinstance(arr, np.ndarray)}")
print()

# Ahora importar PIL y opencv
print("🎨 Importando PIL...")
from PIL import Image
print(f"  ✅ PIL importado: {Image.__version__}")
print()

print("📷 Importando OpenCV...")
import cv2
print(f"  ✅ OpenCV importado: {cv2.__version__}")
print()

# Crear imagen con PIL y convertir a numpy
print("🔄 Crear imagen PIL y convertir a numpy...")
img_pil = Image.new('RGB', (100, 100), color='white')
img_array = np.array(img_pil)
print(f"  Array shape: {img_array.shape}")
print(f"  Array dtype: {img_array.dtype}")
print(f"  Array type: {type(img_array)}")
print(f"  Type name: {type(img_array).__name__}")
print(f"  Module: {type(img_array).__module__}")
print(f"  isinstance(img_array, np.ndarray): {isinstance(img_array, np.ndarray)}")
print()

# Intentar con OpenCV
print("📷 Crear imagen con OpenCV...")
img_cv = np.zeros((100, 100, 3), dtype=np.uint8)
img_cv[:] = [255, 255, 255]
print(f"  Array shape: {img_cv.shape}")
print(f"  Array dtype: {img_cv.dtype}")
print(f"  Array type: {type(img_cv)}")
print(f"  Type name: {type(img_cv).__name__}")
print(f"  Module: {type(img_cv).__module__}")
print(f"  isinstance(img_cv, np.ndarray): {isinstance(img_cv, np.ndarray)}")
print()

# Ahora importar easyocr
print("🤖 Importando EasyOCR...")
import easyocr
print(f"  ✅ EasyOCR importado: {easyocr.__version__}")
print()

# Ver qué numpy usa internamente easyocr
print("🔍 Verificando numpy en EasyOCR...")
import easyocr.utils as easyocr_utils
import inspect
source_file = inspect.getfile(easyocr_utils.reformat_input)
print(f"  EasyOCR utils location: {source_file}")
print()

# Ver importaciones de easyocr
print("📦 Verificando imports de easyocr.utils...")
import easyocr.utils
print(f"  numpy en easyocr.utils.__dict__: {'numpy' in dir(easyocr.utils)}")
if hasattr(easyocr.utils, 'np'):
    easyocr_np = easyocr.utils.np
    print(f"  easyocr.utils.np: {easyocr_np}")
    print(f"  easyocr.utils.np.__version__: {easyocr_np.__version__}")
    print(f"  easyocr.utils.np.__file__: {easyocr_np.__file__}")
    print(f"  ¿Es el mismo numpy? {easyocr_np is np}")
print()

print("=" * 60)
print("✅ ANÁLISIS COMPLETADO")
print("=" * 60)
"""

        print("📝 Ejecutando análisis de NumPy en el sandbox...")
        print()

        # Escribir script al sandbox
        sandbox.files.write("/tmp/test_numpy.py", debug_script)

        # Ejecutar script
        result = sandbox.commands.run("python3 /tmp/test_numpy.py", timeout=180)

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
    success = test_numpy_conflict()
    exit(0 if success else 1)
