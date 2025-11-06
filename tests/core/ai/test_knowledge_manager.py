"""
Unit tests for KnowledgeManager.
"""

import pytest
import tempfile
import os
from pathlib import Path

from src.core.ai.knowledge_manager import KnowledgeManager


class TestKnowledgeManager:
    """Test suite for KnowledgeManager class."""

    @pytest.fixture
    def temp_knowledge_base(self):
        """Create a temporary knowledge base directory with test files."""
        with tempfile.TemporaryDirectory() as temp_dir:
            # Create main.md
            main_content = """# NOVA AI Code Generation

Generate Python code for NOVA workflows.

## Environment
- Python 3.11
- E2B Sandbox
"""
            with open(os.path.join(temp_dir, "main.md"), 'w') as f:
                f.write(main_content)

            # Create integrations directory
            integrations_dir = os.path.join(temp_dir, "integrations")
            os.makedirs(integrations_dir)

            # Create imap.md
            imap_content = """# IMAP - Reading Emails

Read emails using imaplib.
"""
            with open(os.path.join(integrations_dir, "imap.md"), 'w') as f:
                f.write(imap_content)

            # Create pdf.md
            pdf_content = """# PDF Processing

Extract text from PDFs using PyMuPDF.
"""
            with open(os.path.join(integrations_dir, "pdf.md"), 'w') as f:
                f.write(pdf_content)

            yield temp_dir

    @pytest.fixture
    def manager(self, temp_knowledge_base):
        """Create KnowledgeManager with temp knowledge base."""
        return KnowledgeManager(knowledge_base_path=temp_knowledge_base)

    # Test __init__
    def test_init_with_custom_path(self, temp_knowledge_base):
        """Test initialization with custom knowledge base path."""
        manager = KnowledgeManager(knowledge_base_path=temp_knowledge_base)
        assert manager.knowledge_base_path == temp_knowledge_base
        assert manager._cache == {}

    def test_init_with_default_path(self):
        """Test initialization with default knowledge base path."""
        manager = KnowledgeManager()
        # Should default to /nova/knowledge
        assert manager.knowledge_base_path.endswith("knowledge")
        assert manager._cache == {}

    # Test load_file()
    def test_load_file_success(self, manager):
        """Test loading an existing file."""
        content = manager.load_file("main.md")
        assert "NOVA AI Code Generation" in content
        assert "Python 3.11" in content

    def test_load_file_caching(self, manager):
        """Test that files are cached after first load."""
        # Load file first time
        content1 = manager.load_file("main.md")

        # Check it's in cache
        assert "main.md" in manager._cache

        # Load again (should come from cache)
        content2 = manager.load_file("main.md")

        # Same content
        assert content1 == content2

    def test_load_file_not_found(self, manager):
        """Test loading a non-existent file raises FileNotFoundError."""
        with pytest.raises(FileNotFoundError):
            manager.load_file("nonexistent.md")

    def test_load_file_integration_doc(self, manager):
        """Test loading integration documentation."""
        content = manager.load_file("integrations/imap.md")
        assert "IMAP" in content
        assert "imaplib" in content

    # Test detect_integrations()
    def test_detect_integrations_from_task_email(self, manager):
        """Test detecting IMAP from email-related task."""
        task = "Read unread emails from inbox"
        context = {}

        integrations = manager.detect_integrations(task, context)

        assert "imap" in integrations

    def test_detect_integrations_from_task_pdf(self, manager):
        """Test detecting PDF from pdf-related task."""
        task = "Extract invoice amount from PDF"
        context = {}

        integrations = manager.detect_integrations(task, context)

        assert "pdf" in integrations

    def test_detect_integrations_from_context_keys(self, manager):
        """Test detecting integrations from context keys."""
        task = "Process document"
        context = {
            "pdf_data": b"...",
            "pdf_filename": "invoice.pdf"
        }

        integrations = manager.detect_integrations(task, context)

        assert "pdf" in integrations

    def test_detect_integrations_multiple(self, manager):
        """Test detecting multiple integrations."""
        task = "Read email and extract PDF attachment"
        context = {
            "email_from": "test@example.com",
            "pdf_data": b"..."
        }

        integrations = manager.detect_integrations(task, context)

        assert "imap" in integrations
        assert "pdf" in integrations

    def test_detect_integrations_no_matches(self, manager):
        """Test when no integrations match."""
        task = "Do something generic"
        context = {"some_key": "some_value"}

        integrations = manager.detect_integrations(task, context)

        # Should return empty list or minimal matches
        assert isinstance(integrations, list)

    def test_detect_integrations_sorted(self, manager):
        """Test that integrations are returned sorted."""
        task = "Send email with PDF attachment from database"
        context = {}

        integrations = manager.detect_integrations(task, context)

        # Should be sorted alphabetically
        assert integrations == sorted(integrations)

    # Test summarize_context()
    def test_summarize_context_empty(self, manager):
        """Test summarizing empty context."""
        context = {}
        summary = manager.summarize_context(context)

        assert "CONTEXT AVAILABLE" in summary
        assert "empty" in summary

    def test_summarize_context_with_string(self, manager):
        """Test summarizing context with string value."""
        context = {"email_from": "test@example.com"}
        summary = manager.summarize_context(context)

        assert "email_from" in summary
        assert "test@example.com" in summary
        assert "str" in summary

    def test_summarize_context_with_bytes(self, manager):
        """Test summarizing context with binary data."""
        context = {"pdf_data": b"a" * 5000}  # 5KB
        summary = manager.summarize_context(context)

        assert "pdf_data" in summary
        assert "binary data" in summary
        assert "4KB" in summary or "5KB" in summary
        assert "bytes" in summary

    def test_summarize_context_with_numbers(self, manager):
        """Test summarizing context with numbers."""
        context = {
            "total_amount": 1500.50,
            "invoice_id": 123,
            "is_valid": True
        }
        summary = manager.summarize_context(context)

        assert "total_amount: 1500.5" in summary
        assert "invoice_id: 123" in summary
        assert "is_valid: True" in summary

    def test_summarize_context_truncates_long_strings(self, manager):
        """Test that long strings are truncated."""
        long_text = "a" * 100
        context = {"long_field": long_text}
        summary = manager.summarize_context(context)

        assert "long_field" in summary
        assert "..." in summary  # Truncation indicator
        assert len(long_text) > summary.count("a")  # Should be truncated

    def test_summarize_context_with_collections(self, manager):
        """Test summarizing context with lists and dicts."""
        context = {
            "items": [1, 2, 3, 4, 5],
            "metadata": {"key1": "value1", "key2": "value2"}
        }
        summary = manager.summarize_context(context)

        assert "items" in summary
        assert "list with 5 items" in summary
        assert "metadata" in summary
        assert "dict with 2 keys" in summary

    # Test build_prompt()
    def test_build_prompt_basic(self, manager):
        """Test building a basic prompt without error history."""
        task = "Read unread emails"
        context = {"client_slug": "test_client"}

        prompt = manager.build_prompt(task, context)

        # Should include main.md content
        assert "NOVA AI Code Generation" in prompt

        # Should include task
        assert "TASK" in prompt
        assert "Read unread emails" in prompt

        # Should include context summary
        assert "CONTEXT AVAILABLE" in prompt
        assert "client_slug" in prompt

        # Should include detected integrations
        assert "IMAP" in prompt or "imap" in prompt

        # Should include final instruction
        assert "GENERATE PYTHON CODE" in prompt

    def test_build_prompt_with_multiple_integrations(self, manager):
        """Test prompt with multiple integrations."""
        task = "Read email and extract PDF"
        context = {
            "client_slug": "test",
            "pdf_data": b"..."
        }

        prompt = manager.build_prompt(task, context)

        # Should include both IMAP and PDF docs
        assert "IMAP" in prompt or "imap" in prompt
        assert "PDF" in prompt or "pdf" in prompt

    def test_build_prompt_with_error_history(self, manager):
        """Test prompt with retry error history."""
        task = "Extract amount"
        context = {"pdf_data": b"..."}
        error_history = [
            {
                "attempt": 1,
                "error": "AttributeError: 'NoneType' object has no attribute 'get_text'",
                "code": "doc = None\ntext = doc.get_text()"
            }
        ]

        prompt = manager.build_prompt(task, context, error_history)

        # Should include error history section
        assert "PREVIOUS ATTEMPTS" in prompt
        assert "Attempt 1" in prompt
        assert "AttributeError" in prompt
        assert "doc.get_text()" in prompt

    def test_build_prompt_without_main_md(self):
        """Test prompt building when main.md doesn't exist."""
        # Create manager with empty temp dir
        with tempfile.TemporaryDirectory() as temp_dir:
            manager = KnowledgeManager(knowledge_base_path=temp_dir)

            task = "Test task"
            context = {}

            # Should not crash, should use fallback
            prompt = manager.build_prompt(task, context)

            assert "TASK" in prompt
            assert prompt is not None

    def test_build_prompt_structure(self, manager):
        """Test that prompt has correct structure."""
        task = "Test task"
        context = {"key": "value"}

        prompt = manager.build_prompt(task, context)

        # Check sections appear in correct order
        task_pos = prompt.find("TASK")
        context_pos = prompt.find("CONTEXT AVAILABLE")
        generate_pos = prompt.find("GENERATE PYTHON CODE")

        assert task_pos > 0
        assert context_pos > task_pos
        assert generate_pos > context_pos


# Integration test
class TestKnowledgeManagerIntegration:
    """Integration tests with real knowledge base."""

    def test_with_real_knowledge_base(self):
        """Test KnowledgeManager with actual knowledge base if it exists."""
        # Try to use real knowledge base
        base_dir = Path(__file__).parent.parent.parent.parent
        knowledge_path = base_dir / "knowledge"

        if not knowledge_path.exists():
            pytest.skip("Real knowledge base not found")

        manager = KnowledgeManager(knowledge_base_path=str(knowledge_path))

        # Test loading real main.md
        try:
            main_content = manager.load_file("main.md")
            assert len(main_content) > 0
        except FileNotFoundError:
            pytest.skip("main.md not found in real knowledge base")

        # Test detecting integrations
        task = "Read emails and extract PDF invoices"
        context = {"client_slug": "test"}

        integrations = manager.detect_integrations(task, context)
        assert isinstance(integrations, list)

        # Test building full prompt
        prompt = manager.build_prompt(task, context)
        assert len(prompt) > 1000  # Should be substantial
