#!/usr/bin/env python3
"""
Local Workflow Execution - Test workflows without Railway deployment

This script executes complete workflows locally using the GraphEngine.
No API server, no Celery, just pure workflow execution.

Usage:
    python3 test_workflow_local.py <workflow_file> [--context-file <file>]

Examples:
    # Run with workflow fixture
    python3 test_workflow_local.py fixtures/invoice_workflow_improved.json

    # Run with custom context
    python3 test_workflow_local.py fixtures/invoice_workflow_improved.json --context '{"pdf_data": "..."}'
"""

import asyncio
import json
import sys
import os
from pathlib import Path
from dotenv import load_dotenv
import argparse
import base64
from datetime import datetime

# Load environment
env_path = Path(__file__).parent / ".env"
load_dotenv(env_path)

# Add src to path
sys.path.insert(0, str(Path(__file__).parent / "src"))

from core.engine import GraphEngine
from core.executors import get_executor
import logging

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def load_workflow(workflow_path: str) -> dict:
    """Load workflow definition from JSON file."""
    with open(workflow_path, 'r') as f:
        return json.load(f)


def load_pdf_as_base64(pdf_path: str) -> str:
    """Load PDF file and convert to base64."""
    with open(pdf_path, 'rb') as f:
        pdf_bytes = f.read()
    return base64.b64encode(pdf_bytes).decode('utf-8')


def prepare_context(workflow: dict, custom_context: dict = None) -> dict:
    """
    Prepare initial context for workflow execution.

    Merges workflow's initial_context with custom_context.
    """
    # Get workflow's initial context
    context = workflow.get('initial_context', {}).copy()

    # Merge custom context if provided
    if custom_context:
        context.update(custom_context)

    # Add execution metadata
    context['_execution'] = {
        'timestamp': datetime.utcnow().isoformat(),
        'mode': 'local_test',
        'workflow_id': workflow.get('id', 'unknown')
    }

    return context


async def execute_workflow_local(
    workflow: dict,
    context: dict,
    executor_type: str = "cached"
) -> dict:
    """
    Execute workflow locally without database.

    Args:
        workflow: Workflow definition dict
        context: Initial context
        executor_type: "e2b" (hardcoded) or "cached" (AI-powered) - Note: Currently not used, GraphEngine creates executor internally

    Returns:
        Final context after execution
    """
    print("\n" + "="*80)
    print("🚀 LOCAL WORKFLOW EXECUTION")
    print("="*80)

    # Create graph engine (without DB session)
    # GraphEngine creates executor internally based on node configuration
    engine = GraphEngine(api_key=None, db_session=None)
    print(f"📊 Workflow: {workflow.get('name', 'Unnamed')}")
    print(f"📦 Initial context keys: {list(context.keys())}")

    # Execute workflow
    print("\n⏳ Starting execution...\n")

    try:
        result = await engine.execute_workflow(workflow, context)

        print("\n" + "="*80)
        print("✅ WORKFLOW COMPLETED SUCCESSFULLY")
        print("="*80)

        return result

    except Exception as e:
        print("\n" + "="*80)
        print("❌ WORKFLOW FAILED")
        print("="*80)
        print(f"\nError: {e}")
        logger.exception("Workflow execution failed")
        raise


def print_results(result: dict):
    """Print workflow execution results in a readable format."""
    print("\n📤 FINAL CONTEXT:")
    print("─" * 80)

    # Separate metadata from actual results
    metadata_keys = [k for k in result.keys() if k.startswith('_')]
    result_keys = [k for k in result.keys() if not k.startswith('_')]

    # Print results (non-metadata)
    if result_keys:
        print("\n🎯 Results:")
        for key in sorted(result_keys):
            value = result[key]

            # Smart formatting based on type
            if isinstance(value, str) and len(value) > 100:
                print(f"   {key}: <string, {len(value)} chars>")
            elif isinstance(value, bytes):
                print(f"   {key}: <bytes, {len(value)} bytes>")
            elif isinstance(value, dict):
                print(f"   {key}:")
                for k, v in value.items():
                    if isinstance(v, str) and len(v) > 50:
                        print(f"      {k}: <string, {len(v)} chars>")
                    else:
                        print(f"      {k}: {v}")
            else:
                print(f"   {key}: {value}")
    else:
        print("\n⚠️  No results (only metadata)")

    # Print metadata summary
    if '_ai_metadata' in result:
        print("\n🤖 AI Metadata Summary:")
        metadata = result['_ai_metadata']
        print(f"   Model: {metadata.get('model')}")
        print(f"   Attempts: {metadata.get('attempts')}")
        print(f"   Cost: ${metadata.get('cost_usd_estimated', 0):.6f}")
        print(f"   Generation time: {metadata.get('generation_time_ms')}ms")
        print(f"   Execution time: {metadata.get('execution_time_ms')}ms")
        print(f"   Total time: {metadata.get('total_time_ms')}ms")
        print(f"   Tool calls: {metadata.get('total_tool_calls', 0)}")
        print(f"   Stages: {metadata.get('stages_used', 1)}")

        # Show generated code (truncated)
        if 'generated_code' in metadata:
            code = metadata['generated_code']
            code_lines = code.split('\n')
            print(f"\n📜 Generated Code ({len(code)} chars):")
            print("   " + "─" * 76)
            for line in code_lines[:15]:  # First 15 lines
                print(f"   {line}")
            if len(code_lines) > 15:
                remaining_lines = len(code_lines) - 15
                print(f"   ... ({remaining_lines} more lines)")

    print("\n" + "─" * 80)


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Execute NOVA workflows locally without deployment",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Simple execution with workflow defaults
  python3 test_workflow_local.py fixtures/invoice_workflow_improved.json

  # With custom context (JSON string)
  python3 test_workflow_local.py fixtures/invoice_workflow_improved.json \\
    --context '{"client_name": "ACME Corp"}'

  # With PDF file
  python3 test_workflow_local.py fixtures/invoice_workflow_improved.json \\
    --pdf examples/sample_invoice.pdf

  # Use hardcoded executor (no AI)
  python3 test_workflow_local.py fixtures/simple_workflow.json \\
    --executor e2b
        """
    )

    parser.add_argument(
        'workflow_file',
        help='Path to workflow JSON file'
    )

    parser.add_argument(
        '--context',
        help='Custom context as JSON string',
        default=None
    )

    parser.add_argument(
        '--context-file',
        help='Load context from JSON file',
        default=None
    )

    parser.add_argument(
        '--pdf',
        help='Load PDF file and add to context as pdf_data (base64)',
        default=None
    )

    parser.add_argument(
        '--executor',
        choices=['e2b', 'cached'],
        default='cached',
        help='Executor type: e2b (hardcoded) or cached (AI-powered)'
    )

    parser.add_argument(
        '--save-result',
        help='Save final context to JSON file',
        default=None
    )

    args = parser.parse_args()

    # Check environment
    print("\n📋 Environment Check:")
    print(f"   E2B_API_KEY: {'✅ Set' if os.getenv('E2B_API_KEY') else '❌ Missing'}")
    print(f"   OPENAI_API_KEY: {'✅ Set' if os.getenv('OPENAI_API_KEY') else '⚠️  Not set'}")

    if args.executor == 'cached' and not os.getenv('OPENAI_API_KEY'):
        print("\n❌ Error: OPENAI_API_KEY required for 'cached' executor")
        print("   Either:")
        print("   1. Add OPENAI_API_KEY to .env")
        print("   2. Use --executor e2b for hardcoded execution")
        sys.exit(1)

    try:
        # Load workflow
        print(f"\n📂 Loading workflow: {args.workflow_file}")
        workflow = load_workflow(args.workflow_file)

        # Prepare context
        custom_context = {}

        if args.context:
            custom_context = json.loads(args.context)

        if args.context_file:
            with open(args.context_file, 'r') as f:
                custom_context.update(json.load(f))

        if args.pdf:
            print(f"📄 Loading PDF: {args.pdf}")
            custom_context['pdf_data'] = load_pdf_as_base64(args.pdf)
            print(f"   PDF loaded: {len(custom_context['pdf_data'])} base64 chars")

        context = prepare_context(workflow, custom_context)

        # Execute workflow
        result = asyncio.run(execute_workflow_local(
            workflow=workflow,
            context=context,
            executor_type=args.executor
        ))

        # Print results
        print_results(result)

        # Save result if requested
        if args.save_result:
            with open(args.save_result, 'w') as f:
                json.dump(result, f, indent=2, default=str)
            print(f"\n💾 Result saved to: {args.save_result}")

        print("\n✅ Local execution completed successfully!")
        sys.exit(0)

    except FileNotFoundError as e:
        print(f"\n❌ File not found: {e}")
        sys.exit(1)
    except json.JSONDecodeError as e:
        print(f"\n❌ Invalid JSON: {e}")
        sys.exit(1)
    except Exception as e:
        print(f"\n❌ Execution failed: {e}")
        logger.exception("Fatal error")
        sys.exit(1)


if __name__ == "__main__":
    main()
