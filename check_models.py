#!/usr/bin/env python3
from e2b import Sandbox
import os
from dotenv import load_dotenv

load_dotenv()

print("Checking if EasyOCR models are pre-downloaded...")
print()

sandbox = Sandbox.create(template='ybdni0ui0l3vsumat82v')

# Check where EasyOCR stores models
check_script = """
import os
import easyocr

# Check default model directory
model_dir = os.path.expanduser('~/.EasyOCR/model')
print(f"Default model directory: {model_dir}")
print(f"Directory exists: {os.path.exists(model_dir)}")

if os.path.exists(model_dir):
    print("\\nFiles in model directory:")
    for file in os.listdir(model_dir):
        file_path = os.path.join(model_dir, file)
        size_mb = os.path.getsize(file_path) / (1024*1024)
        print(f"  - {file} ({size_mb:.1f} MB)")
else:
    print("\\n❌ Model directory does not exist - models not pre-downloaded")
"""

sandbox.files.write("/tmp/check_models.py", check_script)
result = sandbox.commands.run("python3 /tmp/check_models.py", timeout=120)

print(result.stdout)
if result.stderr:
    print("Stderr:")
    print(result.stderr)

sandbox.kill()
print()
print("Done")
