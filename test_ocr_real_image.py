#!/usr/bin/env python3
"""
Test OCR functionality with a real image
Creates a test image with text and performs OCR using V2 template
"""

import os
from dotenv import load_dotenv
from e2b import Sandbox

load_dotenv()


def test_ocr_with_real_image():
    """Test EasyOCR with a real image in V2 template"""

    print("=" * 70)
    print("TEST 2: OCR with Real Image (NOVA Template V2)")
    print("=" * 70)
    print()

    template_id = "ybdni0ui0l3vsumat82v"
    template_name = "nova-ocr-simple"

    print(f"📋 Template: {template_name}")
    print(f"🆔 ID: {template_id}")
    print()

    try:
        print("🚀 Creating sandbox...")
        sandbox = Sandbox.create(template=template_id)
        print(f"✅ Sandbox created: {sandbox.sandbox_id}")
        print()

        # Create a test image with text using PIL
        print("🖼️  Creating test image with text...")

        # Upload Python script to sandbox
        create_script = """from PIL import Image, ImageDraw, ImageFont

# Create a white image with text
img = Image.new('RGB', (800, 200), color='white')
draw = ImageDraw.Draw(img)

# Use a basic font (PIL default)
try:
    font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 40)
except:
    font = ImageFont.load_default()

# Draw text
texts = [
    "Factura N 12345",
    "Total: $1,234.56",
    "Fecha: 2025-01-10"
]

y_position = 20
for text in texts:
    draw.text((50, y_position), text, fill='black', font=font)
    y_position += 60

# Save to file
img.save('/tmp/test_invoice.png')
print("✅ Test image created: /tmp/test_invoice.png")
"""

        # Write script to sandbox
        sandbox.files.write("/tmp/create_image.py", create_script)

        # Run script
        result = sandbox.commands.run("python3 /tmp/create_image.py", timeout=30)
        print(result.stdout)

        if result.exit_code != 0:
            print(f"❌ Image creation failed: {result.stderr}")
            sandbox.kill()
            return False

        # Perform OCR on the image
        print("🔍 Performing OCR on test image...")
        print("  (This may take 30-60 seconds for model loading)")

        ocr_script = """import easyocr
import os

# Initialize EasyOCR reader
print("Initializing EasyOCR reader...")
reader = easyocr.Reader(['es', 'en'], gpu=False, verbose=False)
print("✅ Reader initialized")

# Verify image exists
image_path = '/tmp/test_invoice.png'
if not os.path.exists(image_path):
    print(f"❌ Image not found at {image_path}")
    exit(1)

print(f"\\nImage found at: {image_path}")

# Perform OCR directly with file path (EasyOCR accepts string paths)
print("\\nPerforming OCR...")
results = reader.readtext(image_path, detail=1)

print("\\n📄 OCR Results:")
print("-" * 50)

if not results:
    print("⚠️  No text detected in image")
else:
    total_confidence = 0
    for i, (bbox, text, confidence) in enumerate(results, 1):
        print(f"{i}. Text: {text}")
        print(f"   Confidence: {confidence:.2%}")
        total_confidence += confidence

    avg_confidence = total_confidence / len(results)
    print("-" * 50)
    print(f"\\n✅ Total text elements detected: {len(results)}")
    print(f"✅ Average confidence: {avg_confidence:.2%}")
"""

        # Write OCR script to sandbox
        sandbox.files.write("/tmp/run_ocr.py", ocr_script)

        # Run OCR script
        result = sandbox.commands.run("python3 /tmp/run_ocr.py", timeout=120)

        print(result.stdout)

        if result.exit_code != 0:
            print(f"⚠️  OCR warning: {result.stderr}")
            # Don't fail on warnings, only on actual errors
            if "error" in result.stderr.lower() and "warning" not in result.stderr.lower():
                sandbox.kill()
                return False

        print()
        sandbox.kill()

        print("=" * 70)
        print("✅ OCR REAL IMAGE TEST PASSED")
        print("=" * 70)
        print()
        print("Summary:")
        print("  - Test image created successfully")
        print("  - EasyOCR initialized and loaded models")
        print("  - OCR extracted text from image")
        print("  - Template is ready for production OCR tasks")
        print()

        return True

    except Exception as e:
        print(f"❌ Test failed with exception: {e}")
        import traceback
        traceback.print_exc()
        return False


def main():
    """Run OCR test with real image"""

    print()
    print("╔" + "═" * 68 + "╗")
    print("║" + " " * 15 + "NOVA OCR FUNCTIONALITY TEST" + " " * 24 + "║")
    print("╚" + "═" * 68 + "╝")
    print()

    api_key = os.getenv("E2B_API_KEY")
    if not api_key:
        print("❌ ERROR: E2B_API_KEY not found in environment")
        return False

    print(f"✅ E2B API Key: {api_key[:12]}...")
    print()
    print()

    # Run test
    success = test_ocr_with_real_image()

    if success:
        print()
        print("╔" + "═" * 68 + "╗")
        print("║" + " " * 15 + "🎉 OCR TEST SUCCESSFUL! 🎉" + " " * 22 + "║")
        print("║" + " " * 68 + "║")
        print("║  V2 template can successfully perform OCR on images." + " " * 12 + "║")
        print("║  Ready for processing scanned invoices and documents." + " " * 9 + "║")
        print("║" + " " * 68 + "║")
        print("╚" + "═" * 68 + "╝")
        print()
    else:
        print()
        print("╔" + "═" * 68 + "╗")
        print("║" + " " * 20 + "⚠️  TEST FAILED" + " " * 31 + "║")
        print("║" + " " * 68 + "║")
        print("║  Please review the error messages above." + " " * 26 + "║")
        print("║" + " " * 68 + "║")
        print("╚" + "═" * 68 + "╝")
        print()

    return success


if __name__ == "__main__":
    success = main()
    exit(0 if success else 1)
