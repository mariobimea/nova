"""
Tests for CachedExecutor - AI-powered code generation executor.

Tests cover:
1. Initialization (with/without API key)
2. Code cleaning (_clean_code_blocks)
3. Syntax validation (_validate_syntax)
4. Token estimation (_estimate_tokens)
5. Code generation (_generate_code) with OpenAI mock
6. Full execution flow (execute) with retry logic
7. Error handling and retry behavior
"""

import pytest
from unittest.mock import Mock, AsyncMock, patch, MagicMock
from src.core.executors import CachedExecutor
from src.core.exceptions import (
    ExecutorError,
    CodeExecutionError,
    E2BSandboxError,
    E2BTimeoutError
)


class TestCachedExecutorInit:
    """Test CachedExecutor initialization."""

    def test_init_without_api_key(self, monkeypatch):
        """Should raise ValueError if OPENAI_API_KEY not set."""
        monkeypatch.delenv("OPENAI_API_KEY", raising=False)

        with pytest.raises(ValueError, match="OPENAI_API_KEY"):
            CachedExecutor()

    def test_init_with_api_key(self, monkeypatch):
        """Should initialize successfully with API key."""
        monkeypatch.setenv("OPENAI_API_KEY", "sk-test123")
        monkeypatch.setenv("E2B_API_KEY", "e2b-test123")

        with patch('openai.OpenAI') as mock_openai_class:
            executor = CachedExecutor()

            assert executor.openai_client is not None
            assert executor.e2b_executor is not None
            assert executor.knowledge_manager is not None
            mock_openai_class.assert_called_once_with(api_key="sk-test123")

    def test_init_without_openai_library(self, monkeypatch):
        """Should raise ImportError if openai library not installed."""
        monkeypatch.setenv("OPENAI_API_KEY", "sk-test123")
        monkeypatch.setenv("E2B_API_KEY", "e2b-test123")

        # Mock the import to fail
        import sys
        with patch.dict(sys.modules, {'openai': None}):
            with pytest.raises((ImportError, AttributeError)):
                CachedExecutor()


class TestCleanCodeBlocks:
    """Test _clean_code_blocks method."""

    @pytest.fixture(autouse=True)
    def setup_executor(self, monkeypatch):
        """Setup executor for each test."""
        monkeypatch.setenv("OPENAI_API_KEY", "sk-test123")
        monkeypatch.setenv("E2B_API_KEY", "e2b-test123")

        with patch('openai.OpenAI'):
            self.executor = CachedExecutor()

    def test_clean_simple_code_block(self):
        """Should remove ```python markers."""
        code = "```python\nprint('hello')\n```"
        cleaned = self.executor._clean_code_blocks(code)
        assert cleaned == "print('hello')"

    def test_clean_code_block_without_language(self):
        """Should remove ``` markers without language."""
        code = "```\nprint('hello')\n```"
        cleaned = self.executor._clean_code_blocks(code)
        assert cleaned == "print('hello')"

    def test_clean_multiple_code_blocks(self):
        """Should take first code block if multiple present."""
        code = "```python\nprint('first')\n```\n```python\nprint('second')\n```"
        cleaned = self.executor._clean_code_blocks(code)
        assert cleaned == "print('first')"

    def test_clean_explanatory_text(self):
        """Should remove common explanatory phrases."""
        code = """Here's the code:
import json

print('hello')

Note: This code will print hello
"""
        cleaned = self.executor._clean_code_blocks(code)
        assert "Here's the code" not in cleaned
        assert "Note:" not in cleaned
        assert "import json" in cleaned
        assert "print('hello')" in cleaned

    def test_clean_no_markers(self):
        """Should return code as-is if no markers."""
        code = "print('hello')"
        cleaned = self.executor._clean_code_blocks(code)
        assert cleaned == "print('hello')"


class TestValidateSyntax:
    """Test _validate_syntax method."""

    @pytest.fixture(autouse=True)
    def setup_executor(self, monkeypatch):
        """Setup executor for each test."""
        monkeypatch.setenv("OPENAI_API_KEY", "sk-test123")
        monkeypatch.setenv("E2B_API_KEY", "e2b-test123")

        with patch('openai.OpenAI'):
            self.executor = CachedExecutor()

    def test_validate_valid_syntax(self):
        """Should not raise for valid Python code."""
        code = "print('hello')\nx = 1 + 2"
        self.executor._validate_syntax(code)  # Should not raise

    def test_validate_invalid_syntax(self):
        """Should raise CodeExecutionError for invalid syntax."""
        code = "print('hello'\nx = 1 +"  # Missing closing parenthesis

        with pytest.raises(CodeExecutionError, match="invalid syntax"):
            self.executor._validate_syntax(code)

    def test_validate_empty_code(self):
        """Should not raise for empty code (valid Python)."""
        code = ""
        self.executor._validate_syntax(code)  # Should not raise


class TestEstimateTokens:
    """Test _estimate_tokens method."""

    @pytest.fixture(autouse=True)
    def setup_executor(self, monkeypatch):
        """Setup executor for each test."""
        monkeypatch.setenv("OPENAI_API_KEY", "sk-test123")
        monkeypatch.setenv("E2B_API_KEY", "e2b-test123")

        with patch('openai.OpenAI'):
            self.executor = CachedExecutor()

    def test_estimate_tokens_basic(self):
        """Should estimate tokens and cost correctly."""
        prompt = "a" * 4000  # ~1000 tokens
        code = "b" * 2000  # ~500 tokens

        result = self.executor._estimate_tokens(prompt, code)

        assert result["tokens_input"] == 1000
        assert result["tokens_output"] == 500
        assert result["tokens_total"] == 1500
        assert result["cost_usd"] > 0

    def test_estimate_tokens_cost_calculation(self):
        """Should calculate cost using correct pricing."""
        prompt = "x" * 40000  # ~10K tokens input
        code = "y" * 40000  # ~10K tokens output

        result = self.executor._estimate_tokens(prompt, code)

        # gpt-4o-mini pricing: $0.15/1M input, $0.60/1M output
        # 10K input = $0.0015, 10K output = $0.0060
        expected_cost = (10000 / 1_000_000) * 0.15 + (10000 / 1_000_000) * 0.60
        assert abs(result["cost_usd"] - expected_cost) < 0.000001


class TestGenerateCode:
    """Test _generate_code method."""

    @pytest.fixture
    def executor(self, monkeypatch):
        """Create executor with mocked OpenAI."""
        monkeypatch.setenv("OPENAI_API_KEY", "sk-test123")
        monkeypatch.setenv("E2B_API_KEY", "e2b-test123")

        with patch('openai.OpenAI'):
            executor = CachedExecutor()
            yield executor

    @pytest.mark.asyncio
    async def test_generate_code_success(self, executor):
        """Should generate and clean code successfully."""
        # Mock OpenAI response
        mock_response = Mock()
        mock_response.choices = [Mock(message=Mock(content="```python\nprint('hello')\n```"))]
        executor.openai_client.chat.completions.create = Mock(return_value=mock_response)

        code = await executor._generate_code("Test prompt")

        assert code == "print('hello')"
        executor.openai_client.chat.completions.create.assert_called_once()

    @pytest.mark.asyncio
    async def test_generate_code_with_explanations(self, executor):
        """Should clean explanatory text from response."""
        # Mock OpenAI response with explanations
        mock_response = Mock()
        mock_response.choices = [Mock(message=Mock(content="""
Here's the code to solve your problem:
```python
import json
print(json.dumps({"result": "success"}))
```
This code will output JSON.
"""))]
        executor.openai_client.chat.completions.create = Mock(return_value=mock_response)

        code = await executor._generate_code("Test prompt")

        assert "import json" in code
        assert "print(json.dumps" in code
        assert "Here's the code" not in code

    @pytest.mark.asyncio
    async def test_generate_code_empty_response(self, executor):
        """Should raise ExecutorError if OpenAI returns empty response."""
        # Mock empty response
        mock_response = Mock()
        mock_response.choices = [Mock(message=Mock(content=""))]
        executor.openai_client.chat.completions.create = Mock(return_value=mock_response)

        with pytest.raises(ExecutorError, match="empty response"):
            await executor._generate_code("Test prompt")

    @pytest.mark.asyncio
    async def test_generate_code_invalid_syntax(self, executor):
        """Should raise CodeExecutionError if generated code has invalid syntax."""
        # Mock response with invalid syntax
        mock_response = Mock()
        mock_response.choices = [Mock(message=Mock(content="print('hello'\nx = 1 +"))]
        executor.openai_client.chat.completions.create = Mock(return_value=mock_response)

        with pytest.raises(CodeExecutionError, match="invalid syntax"):
            await executor._generate_code("Test prompt")

    @pytest.mark.asyncio
    async def test_generate_code_openai_api_error(self, executor):
        """Should raise ExecutorError if OpenAI API fails."""
        # Mock API error
        executor.openai_client.chat.completions.create = Mock(
            side_effect=Exception("API rate limit exceeded")
        )

        with pytest.raises(ExecutorError, match="Failed to generate code"):
            await executor._generate_code("Test prompt")


class TestExecute:
    """Test execute method (full flow)."""

    @pytest.fixture
    def executor(self, monkeypatch):
        """Create executor with mocked dependencies."""
        monkeypatch.setenv("OPENAI_API_KEY", "sk-test123")
        monkeypatch.setenv("E2B_API_KEY", "e2b-test123")

        with patch('openai.OpenAI'):
            executor = CachedExecutor()

            # Mock KnowledgeManager
            executor.knowledge_manager.build_prompt = Mock(
                return_value="Complete prompt with docs"
            )

            yield executor

    @pytest.mark.asyncio
    async def test_execute_success_first_attempt(self, executor):
        """Should succeed on first attempt and return result with metadata."""
        # Mock code generation
        executor._generate_code = AsyncMock(return_value="print('test')")

        # Mock E2B execution
        executor.e2b_executor.execute = AsyncMock(return_value={
            "result": "success"
        })

        result = await executor.execute(
            code="Test task prompt",
            context={"key": "value"},
            timeout=30
        )

        assert result["result"] == "success"
        assert "_ai_metadata" in result
        assert result["_ai_metadata"]["model"] == "gpt-4o-mini"
        assert result["_ai_metadata"]["prompt"] == "Test task prompt"
        assert result["_ai_metadata"]["generated_code"] == "print('test')"
        assert result["_ai_metadata"]["attempts"] == 1
        assert result["_ai_metadata"]["cost_usd"] > 0

    @pytest.mark.asyncio
    async def test_execute_retry_on_execution_error(self, executor):
        """Should retry with error feedback if execution fails."""
        # Mock code generation (different code each time)
        generated_codes = ["print('attempt1')", "print('attempt2')"]
        executor._generate_code = AsyncMock(side_effect=generated_codes)

        # Mock E2B execution (fail first, succeed second)
        executor.e2b_executor.execute = AsyncMock(
            side_effect=[
                CodeExecutionError("First attempt failed", code="", error_details=""),
                {"result": "success"}
            ]
        )

        result = await executor.execute(
            code="Test task",
            context={},
            timeout=30
        )

        assert result["result"] == "success"
        assert result["_ai_metadata"]["attempts"] == 2
        assert executor._generate_code.call_count == 2

        # Verify error history was passed to build_prompt on second attempt
        second_call = executor.knowledge_manager.build_prompt.call_args_list[1]
        assert second_call[1]["error_history"] is not None
        assert len(second_call[1]["error_history"]) == 1

    @pytest.mark.asyncio
    async def test_execute_fail_after_max_retries(self, executor):
        """Should raise ExecutorError after 3 failed attempts."""
        # Mock code generation (always returns code)
        executor._generate_code = AsyncMock(return_value="print('test')")

        # Mock E2B execution (always fails)
        executor.e2b_executor.execute = AsyncMock(
            side_effect=CodeExecutionError("Persistent error", code="", error_details="")
        )

        with pytest.raises(ExecutorError, match="Failed to generate and execute code after 3 attempts"):
            await executor.execute(
                code="Test task",
                context={},
                timeout=30
            )

        assert executor._generate_code.call_count == 3

    @pytest.mark.asyncio
    async def test_execute_timeout_error_retry(self, executor):
        """Should retry on E2B timeout errors."""
        executor._generate_code = AsyncMock(
            side_effect=["print('attempt1')", "print('attempt2')"]
        )

        # Timeout on first attempt, success on second
        executor.e2b_executor.execute = AsyncMock(
            side_effect=[
                E2BTimeoutError("Timeout", timeout_seconds=30),
                {"result": "success"}
            ]
        )

        result = await executor.execute(
            code="Test task",
            context={},
            timeout=30
        )

        assert result["result"] == "success"
        assert result["_ai_metadata"]["attempts"] == 2

    @pytest.mark.asyncio
    async def test_execute_sandbox_error_retry(self, executor):
        """Should retry on E2B sandbox errors."""
        executor._generate_code = AsyncMock(
            side_effect=["print('attempt1')", "print('attempt2')"]
        )

        # Sandbox error on first attempt, success on second
        executor.e2b_executor.execute = AsyncMock(
            side_effect=[
                E2BSandboxError("Sandbox crashed", sandbox_id="test123"),
                {"result": "success"}
            ]
        )

        result = await executor.execute(
            code="Test task",
            context={},
            timeout=30
        )

        assert result["result"] == "success"
        assert result["_ai_metadata"]["attempts"] == 2

    @pytest.mark.asyncio
    async def test_execute_unexpected_error_no_retry(self, executor):
        """Should fail immediately on unexpected errors (not retry)."""
        executor._generate_code = AsyncMock(return_value="print('test')")

        # Unexpected error (not a known retry-able error)
        executor.e2b_executor.execute = AsyncMock(
            side_effect=RuntimeError("Unexpected error")
        )

        with pytest.raises(ExecutorError, match="CachedExecutor unexpected error"):
            await executor.execute(
                code="Test task",
                context={},
                timeout=30
            )

        # Should fail on first attempt (no retries for unexpected errors)
        assert executor._generate_code.call_count == 1

    @pytest.mark.asyncio
    async def test_execute_builds_prompt_correctly(self, executor):
        """Should build prompt with task and context."""
        executor._generate_code = AsyncMock(return_value="print('test')")
        executor.e2b_executor.execute = AsyncMock(return_value={"result": "ok"})

        await executor.execute(
            code="Extract invoice total",
            context={"pdf_path": "/tmp/invoice.pdf"},
            timeout=30
        )

        # Verify build_prompt was called with correct arguments
        executor.knowledge_manager.build_prompt.assert_called()
        call_args = executor.knowledge_manager.build_prompt.call_args[1]
        assert call_args["task"] == "Extract invoice total"
        assert call_args["context"] == {"pdf_path": "/tmp/invoice.pdf"}
        assert call_args["error_history"] is None  # First attempt


class TestIntegration:
    """Integration tests with real KnowledgeManager (no mocks)."""

    @pytest.mark.asyncio
    async def test_full_flow_with_knowledge_manager(self, monkeypatch, tmp_path):
        """Test full flow with real KnowledgeManager."""
        monkeypatch.setenv("OPENAI_API_KEY", "sk-test123")
        monkeypatch.setenv("E2B_API_KEY", "e2b-test123")

        # Create mock knowledge base
        knowledge_dir = tmp_path / "knowledge"
        knowledge_dir.mkdir()

        (knowledge_dir / "main.md").write_text("""
# NOVA Code Generator
Generate Python code based on task and context.
""")

        with patch('openai.OpenAI'):
            executor = CachedExecutor()

            # Override knowledge base path
            executor.knowledge_manager.knowledge_base_path = str(knowledge_dir)

            # Mock code generation and execution
            executor._generate_code = AsyncMock(return_value="result = 42")
            executor.e2b_executor.execute = AsyncMock(return_value={"result": 42})

            result = await executor.execute(
                code="Calculate something",
                context={},
                timeout=30
            )

            assert result["result"] == 42
            assert "_ai_metadata" in result
