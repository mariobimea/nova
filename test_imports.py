"""
Test all critical imports to find what's failing in production
"""

print("=" * 60)
print("TESTING CRITICAL IMPORTS")
print("=" * 60)

try:
    print("\n1. Testing FastAPI app import...")
    from src.api.main import app
    print("   ✅ FastAPI app imported")
except Exception as e:
    print(f"   ❌ FAILED: {e}")
    import traceback
    traceback.print_exc()
    exit(1)

try:
    print("\n2. Testing Celery app import...")
    from src.workers.celery_app import celery_app
    print("   ✅ Celery app imported")
except Exception as e:
    print(f"   ❌ FAILED: {e}")
    import traceback
    traceback.print_exc()
    exit(1)

try:
    print("\n3. Testing Celery tasks import...")
    from src.workers.tasks import execute_workflow_task
    print("   ✅ Celery tasks imported")
except Exception as e:
    print(f"   ❌ FAILED: {e}")
    import traceback
    traceback.print_exc()
    exit(1)

try:
    print("\n4. Testing GraphEngine import...")
    from src.core.engine import GraphEngine
    print("   ✅ GraphEngine imported")
except Exception as e:
    print(f"   ❌ FAILED: {e}")
    import traceback
    traceback.print_exc()
    exit(1)

try:
    print("\n5. Testing CachedExecutor import...")
    from src.core.executors import CachedExecutor
    print("   ✅ CachedExecutor imported")
except Exception as e:
    print(f"   ❌ FAILED: {e}")
    import traceback
    traceback.print_exc()
    exit(1)

try:
    print("\n6. Testing agents import...")
    from src.core.agents import MultiAgentOrchestrator
    print("   ✅ Agents imported")
except Exception as e:
    print(f"   ❌ FAILED: {e}")
    import traceback
    traceback.print_exc()
    exit(1)

try:
    print("\n7. Testing E2B executor import...")
    from src.core.e2b.executor import E2BExecutor
    print("   ✅ E2B executor imported")
except Exception as e:
    print(f"   ❌ FAILED: {e}")
    import traceback
    traceback.print_exc()
    exit(1)

print("\n" + "=" * 60)
print("✅ ALL IMPORTS SUCCESSFUL!")
print("=" * 60)
