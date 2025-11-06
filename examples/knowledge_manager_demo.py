"""
Demo script showing how to use KnowledgeManager.

This demonstrates the complete flow of building prompts for AI code generation.
"""

import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.core.ai.knowledge_manager import KnowledgeManager


def demo_basic_usage():
    """Demonstrate basic KnowledgeManager usage."""
    print("=" * 80)
    print("DEMO 1: Basic Usage - Reading Emails")
    print("=" * 80)

    # Initialize manager
    manager = KnowledgeManager()

    # Define task and context
    task = "Read unread emails from inbox"
    context = {
        "client_slug": "acme_corp"
    }

    # Build prompt
    prompt = manager.build_prompt(task, context)

    print(f"\n📋 Task: {task}")
    print(f"📦 Context: {context}")
    print(f"\n📝 Generated Prompt ({len(prompt)} characters):\n")
    print("-" * 80)
    print(prompt[:1500])  # Print first 1500 chars
    print("\n... (truncated)")
    print("-" * 80)


def demo_multiple_integrations():
    """Demonstrate detection of multiple integrations."""
    print("\n\n" + "=" * 80)
    print("DEMO 2: Multiple Integrations - Email + PDF")
    print("=" * 80)

    manager = KnowledgeManager()

    task = "Read unread emails and extract invoice amount from PDF attachments"
    context = {
        "client_slug": "acme_corp",
        "pdf_data": b"fake pdf data" * 100,  # Fake binary data
        "email_from": "vendor@example.com"
    }

    # Detect integrations
    integrations = manager.detect_integrations(task, context)

    print(f"\n📋 Task: {task}")
    print(f"\n🔍 Detected Integrations: {integrations}")

    # Show context summary
    summary = manager.summarize_context(context)
    print(f"\n📊 Context Summary:\n{summary}")


def demo_with_error_history():
    """Demonstrate retry with error history."""
    print("\n\n" + "=" * 80)
    print("DEMO 3: Retry with Error History")
    print("=" * 80)

    manager = KnowledgeManager()

    task = "Extract total amount from PDF invoice"
    context = {
        "pdf_data": b"fake pdf" * 50,
        "pdf_filename": "invoice_123.pdf"
    }

    # Simulate previous failed attempt
    error_history = [
        {
            "attempt": 1,
            "error": "AttributeError: 'NoneType' object has no attribute 'get_text'",
            "code": "doc = fitz.open(None)\ntext = doc.get_text()"
        }
    ]

    prompt = manager.build_prompt(task, context, error_history)

    print(f"\n📋 Task: {task}")
    print(f"⚠️  Previous Attempts Failed: {len(error_history)}")

    # Show error history section
    error_section_start = prompt.find("PREVIOUS ATTEMPTS")
    if error_section_start > 0:
        error_section = prompt[error_section_start:error_section_start + 500]
        print(f"\n🔄 Error History Section:\n{error_section}...")


def demo_cache_performance():
    """Demonstrate file caching performance."""
    print("\n\n" + "=" * 80)
    print("DEMO 4: File Caching Performance")
    print("=" * 80)

    manager = KnowledgeManager()

    import time

    # First load (from disk)
    start = time.time()
    content1 = manager.load_file("main.md")
    first_load_time = (time.time() - start) * 1000

    # Second load (from cache)
    start = time.time()
    content2 = manager.load_file("main.md")
    cached_load_time = (time.time() - start) * 1000

    print(f"\n📂 Loading main.md:")
    print(f"  First load (disk):  {first_load_time:.2f}ms")
    print(f"  Cached load:        {cached_load_time:.2f}ms")
    if cached_load_time > 0:
        print(f"  Speedup:            {first_load_time/cached_load_time:.1f}x")
    else:
        print(f"  Speedup:            >1000x (cached load too fast to measure)")

    print(f"\n💾 Cache Status:")
    print(f"  Files in cache: {len(manager._cache)}")
    print(f"  Cached files: {list(manager._cache.keys())}")


def demo_integration_detection_rules():
    """Show integration detection rules."""
    print("\n\n" + "=" * 80)
    print("DEMO 5: Integration Detection Rules")
    print("=" * 80)

    manager = KnowledgeManager()

    test_cases = [
        ("Read emails", {}),
        ("Send notification email", {}),
        ("Extract PDF text", {}),
        ("Save invoice to database", {}),
        ("Read email, extract PDF, save to DB", {}),
        ("Process document", {"pdf_data": b"..."}),
        ("Handle submission", {"email_from": "test@example.com", "pdf_filename": "inv.pdf"}),
    ]

    print("\n🔍 Detection Test Cases:\n")
    for task, context in test_cases:
        integrations = manager.detect_integrations(task, context)
        print(f"  Task: '{task[:40]}'")
        print(f"  Context keys: {list(context.keys())}")
        print(f"  → Detected: {integrations}")
        print()


if __name__ == "__main__":
    try:
        demo_basic_usage()
        demo_multiple_integrations()
        demo_with_error_history()
        demo_cache_performance()
        demo_integration_detection_rules()

        print("\n\n" + "=" * 80)
        print("✅ All demos completed successfully!")
        print("=" * 80)

    except FileNotFoundError as e:
        print(f"\n❌ Error: Knowledge base not found.")
        print(f"   Make sure you run this from the nova directory.")
        print(f"   Details: {e}")
    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback
        traceback.print_exc()
