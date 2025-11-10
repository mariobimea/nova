#!/usr/bin/env python3
from e2b import Sandbox
import os
from dotenv import load_dotenv

load_dotenv()

sandbox = Sandbox.create(template='ybdni0ui0l3vsumat82v')
print('Checking installed packages...')

# Check what opencv packages are installed
result = sandbox.commands.run('pip list | grep opencv', timeout=30)
print("OpenCV packages:")
print(result.stdout)

# Check numpy
result = sandbox.commands.run('pip list | grep numpy', timeout=30)
print("\nNumPy packages:")
print(result.stdout)

# Try importing
test_code = """
import sys
print("Python:", sys.version)
print()

try:
    import cv2
    print(f"✅ cv2 imported: {cv2.__version__}")
except Exception as e:
    print(f"❌ cv2 import failed: {e}")

try:
    import numpy as np
    print(f"✅ numpy imported: {np.__version__}")

    # Test numpy array creation
    arr = np.array([[1, 2], [3, 4]])
    print(f"✅ numpy array created: {arr.shape}, dtype={arr.dtype}")
    print(f"   Array type: {type(arr)}")
    print(f"   Is ndarray: {isinstance(arr, np.ndarray)}")
except Exception as e:
    print(f"❌ numpy test failed: {e}")
"""

result = sandbox.commands.run(f'python3 -c "{test_code}"', timeout=30)
print("\nPackage import test:")
print(result.stdout)
if result.stderr:
    print("Errors:")
    print(result.stderr)

sandbox.kill()
