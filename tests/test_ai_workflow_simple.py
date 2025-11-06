"""
Simple test to validate AI-powered workflow nodes.

This test validates that CachedExecutor can:
1. Generate Python code from natural language prompts
2. Execute the generated code in E2B sandbox
3. Update context correctly
4. Handle retry logic if needed

Run with:
    pytest tests/test_ai_workflow_simple.py -v -s
"""

import pytest
import asyncio
import os
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

from src.core.executors import CachedExecutor


class TestAIWorkflowSimple:
    """Test AI-powered workflow nodes individually"""

    @pytest.fixture
    def executor(self):
        """Create CachedExecutor instance"""
        # No db_session needed for simple tests
        return CachedExecutor(db_session=None)

    @pytest.mark.asyncio
    async def test_find_total_amount_simple(self, executor):
        """Test AI can extract total amount from invoice text"""

        # Mock context with OCR text from a simple invoice
        context = {
            'ocr_text': """
            FACTURA #12345
            Proveedor: ACME Corp

            Subtotal: 500.00 €
            IVA (21%): 105.00 €

            TOTAL: 605.00 €

            Gracias por su compra.
            """
        }

        # Prompt from the workflow
        prompt = """Find the total invoice amount from the extracted text.

Input from context:
- context['ocr_text'] - text extracted from PDF invoice

Task:
Analyze the text and identify the total amount of the invoice.

Output to context:
- context['total_amount'] = extracted amount as float (e.g., 1234.56)

If you cannot find a clear total amount, set it to 0.0"""

        print("\n" + "="*80)
        print("TEST: Extract total amount from invoice")
        print("="*80)
        print(f"\nOCR Text:\n{context['ocr_text']}")
        print(f"\nPrompt:\n{prompt[:200]}...")

        # Execute with AI
        result = await executor.execute(
            code=prompt,  # CachedExecutor uses 'code' param for both code and prompts
            context=context,
            timeout=30
        )

        # Validate result
        print(f"\n{'='*80}")
        print("RESULT:")
        print(f"{'='*80}")
        print(f"Status: {result.get('status')}")
        print(f"Total amount extracted: {result.get('total_amount')}")

        # Check AI metadata
        if '_ai_metadata' in result:
            metadata = result['_ai_metadata']
            print(f"\nAI Metadata:")
            print(f"  Model: {metadata.get('model')}")
            print(f"  Tokens (input/output): {metadata.get('tokens_input')}/{metadata.get('tokens_output')}")
            print(f"  Cost: ${metadata.get('cost_usd', 0):.4f}")
            print(f"  Generation time: {metadata.get('generation_time_ms')}ms")
            print(f"  Execution time: {metadata.get('execution_time_ms')}ms")
            print(f"  Attempts: {metadata.get('attempts')}")

            print(f"\nGenerated Code:")
            print("-" * 80)
            print(metadata.get('generated_code'))
            print("-" * 80)

        # Assertions
        assert result.get('status') == 'success', f"Execution failed: {result.get('error')}"
        assert 'total_amount' in result, "total_amount not found in result"
        assert result['total_amount'] == 605.0, f"Expected 605.0, got {result['total_amount']}"

        print(f"\n✅ Test passed! Amount correctly extracted: €{result['total_amount']}")

    @pytest.mark.asyncio
    async def test_find_total_amount_complex(self, executor):
        """Test AI can handle different invoice formats"""

        # Mock context with a different format (comma as decimal separator)
        context = {
            'ocr_text': """
            INVOICE #ABC-789

            Item 1: Widget A .......... 1.200,50 EUR
            Item 2: Widget B .......... 850,00 EUR

            Subtotal .................. 2.050,50 EUR
            Tax (21%) ................. 430,61 EUR
            -------------------------------------------
            Total ..................... 2.481,11 EUR

            Payment due: 30 days
            """
        }

        prompt = """Find the total invoice amount from the extracted text.

Input from context:
- context['ocr_text'] - text extracted from PDF invoice

Task:
Analyze the text and identify the total amount of the invoice.

Output to context:
- context['total_amount'] = extracted amount as float (e.g., 1234.56)

If you cannot find a clear total amount, set it to 0.0"""

        print("\n" + "="*80)
        print("TEST: Extract amount with comma decimal separator")
        print("="*80)
        print(f"\nOCR Text:\n{context['ocr_text']}")

        # Execute
        result = await executor.execute(
            code=prompt,
            context=context,
            timeout=30
        )

        print(f"\nTotal amount extracted: {result.get('total_amount')}")

        # Assertions
        assert result.get('status') == 'success'
        assert 'total_amount' in result
        assert result['total_amount'] == 2481.11, f"Expected 2481.11, got {result['total_amount']}"

        print(f"✅ Test passed! Amount correctly extracted: €{result['total_amount']}")

    @pytest.mark.asyncio
    async def test_decision_node_ai(self, executor):
        """Test AI-powered decision node"""

        context = {
            'has_pdf': True
        }

        prompt = """Decide if the email has a PDF attachment.

Input from context:
- context['has_pdf'] - whether a PDF was found

Task:
Set context['branch_decision'] to True if a PDF was found, False otherwise.

Output to context:
- context['branch_decision'] = True/False"""

        print("\n" + "="*80)
        print("TEST: AI-powered decision node")
        print("="*80)
        print(f"\nContext: has_pdf = {context['has_pdf']}")

        # Execute
        result = await executor.execute(
            code=prompt,
            context=context,
            timeout=10
        )

        print(f"\nDecision result: branch_decision = {result.get('branch_decision')}")

        # Assertions
        assert result.get('status') == 'success'
        assert 'branch_decision' in result
        assert result['branch_decision'] is True

        print(f"✅ Test passed! Decision correctly made: {result['branch_decision']}")


if __name__ == "__main__":
    """Run tests directly with python"""
    import sys

    # Check for required env vars
    if not os.getenv('OPENAI_API_KEY'):
        print("❌ Error: OPENAI_API_KEY not found in environment")
        print("Please create a .env file with:")
        print("OPENAI_API_KEY=sk-...")
        sys.exit(1)

    # Run tests
    print("\n" + "="*80)
    print("RUNNING AI WORKFLOW TESTS")
    print("="*80)

    executor = CachedExecutor(db_session=None)

    # Test 1
    asyncio.run(TestAIWorkflowSimple().test_find_total_amount_simple(executor))

    # Test 2
    asyncio.run(TestAIWorkflowSimple().test_find_total_amount_complex(executor))

    # Test 3
    asyncio.run(TestAIWorkflowSimple().test_decision_node_ai(executor))

    print("\n" + "="*80)
    print("✅ ALL TESTS PASSED!")
    print("="*80)
