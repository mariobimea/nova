"""
KnowledgeManager - Manages knowledge base documentation for AI code generation.

This component:
1. Loads markdown documentation files with caching
2. Detects which integrations are needed based on task and context
3. Summarizes context for AI prompts
4. Builds complete prompts for code generation
"""

import os
from typing import Dict, List, Optional
from pathlib import Path


class KnowledgeManager:
    """Manages knowledge base documentation for AI-powered code generation."""

    def __init__(self, knowledge_base_path: Optional[str] = None):
        """
        Initialize KnowledgeManager.

        Args:
            knowledge_base_path: Path to knowledge base directory.
                                Defaults to /nova/knowledge
        """
        if knowledge_base_path is None:
            # Default to /nova/knowledge (absolute path)
            base_dir = Path(__file__).parent.parent.parent.parent
            knowledge_base_path = str(base_dir / "knowledge")

        self.knowledge_base_path = knowledge_base_path
        self._cache: Dict[str, str] = {}  # In-memory cache for loaded files

    def load_file(self, relative_path: str) -> str:
        """
        Load a markdown file from the knowledge base with caching.

        Args:
            relative_path: Path relative to knowledge_base_path
                          (e.g., "main.md" or "integrations/imap.md")

        Returns:
            File contents as string

        Raises:
            FileNotFoundError: If file doesn't exist
            IOError: If file can't be read
        """
        # Check cache first
        if relative_path in self._cache:
            return self._cache[relative_path]

        # Construct full path
        full_path = os.path.join(self.knowledge_base_path, relative_path)

        # Read file
        if not os.path.exists(full_path):
            raise FileNotFoundError(f"Knowledge file not found: {full_path}")

        try:
            with open(full_path, 'r', encoding='utf-8') as f:
                content = f.read()

            # Cache it
            self._cache[relative_path] = content

            return content

        except Exception as e:
            raise IOError(f"Failed to read knowledge file {full_path}: {str(e)}")

    def detect_integrations(self, task: str, context: Dict) -> List[str]:
        """
        Detect which integration documentation files are needed.

        Uses keyword-based detection from task string and context keys.
        No limit on number of integrations.

        Args:
            task: Task description/prompt from user
            context: Context dictionary available to the code

        Returns:
            List of integration doc filenames (e.g., ["imap", "pdf"])
        """
        detected = set()  # Use set to avoid duplicates

        task_lower = task.lower()

        # Keyword-based detection from task
        integration_keywords = {
            'imap': ['email', 'imap', 'inbox', 'read email', 'unread', 'fetch email'],
            'smtp': ['send email', 'smtp', 'reply', 'notification', 'send mail'],
            'pdf': ['pdf', 'invoice', 'extract', 'document'],
            'postgres': ['database', 'db', 'save', 'store', 'query', 'insert', 'update', 'postgres', 'sql']
        }

        for integration, keywords in integration_keywords.items():
            for keyword in keywords:
                if keyword in task_lower:
                    detected.add(integration)
                    break

        # Context-key-based detection
        context_key_hints = {
            'imap': ['email_subject', 'email_from', 'email_date', 'has_emails'],
            'smtp': ['smtp_host', 'smtp_port', 'rejection_reason'],
            'pdf': ['pdf_data', 'pdf_filename', 'pdf_text'],
            'postgres': ['invoice_id', 'db_table', 'sql_query']
        }

        for integration, hint_keys in context_key_hints.items():
            for hint_key in hint_keys:
                if hint_key in context:
                    detected.add(integration)
                    break

        return sorted(list(detected))  # Sort for consistency

    def summarize_context(self, context: Dict) -> str:
        """
        Format context dictionary into human-readable summary for AI.

        Shows types and simplified representations without hiding secrets
        (because secrets should not be in context in the first place).

        Args:
            context: Context dictionary

        Returns:
            Formatted string summarizing available context
        """
        if not context:
            return "CONTEXT AVAILABLE:\n- (empty)"

        lines = ["CONTEXT AVAILABLE:"]

        for key, value in sorted(context.items()):
            # Get type name
            value_type = type(value).__name__

            # Create simplified representation
            if isinstance(value, bytes):
                # Binary data - show size
                size_kb = len(value) // 1024
                size_bytes = len(value) % 1024
                if size_kb > 0:
                    repr_value = f"<binary data, {size_kb}KB>"
                else:
                    repr_value = f"<binary data, {size_bytes} bytes>"

            elif isinstance(value, str):
                # String - truncate if too long
                if len(value) > 50:
                    repr_value = f'"{value[:50]}..."'
                else:
                    repr_value = f'"{value}"'

            elif isinstance(value, (int, float, bool)):
                # Numbers and booleans - show directly
                repr_value = str(value)

            elif isinstance(value, (list, dict)):
                # Collections - show type and length
                if isinstance(value, list):
                    repr_value = f"<list with {len(value)} items>"
                else:
                    repr_value = f"<dict with {len(value)} keys>"

            else:
                # Other types - just show type
                repr_value = f"<{value_type}>"

            lines.append(f"- {key}: {repr_value} ({value_type})")

        return "\n".join(lines)

    def build_prompt(
        self,
        task: str,
        context: Dict,
        error_history: Optional[List[Dict]] = None
    ) -> str:
        """
        Build complete prompt for AI code generation.

        Assembles:
        1. main.md (always)
        2. Task description
        3. Context summary
        4. Relevant integration docs (auto-detected)
        5. Error history (if retry)

        Args:
            task: Task description/prompt from user
            context: Context dictionary available to code
            error_history: List of previous generation attempts with errors
                          Format: [{"attempt": 1, "error": "...", "code": "..."}]

        Returns:
            Complete prompt string ready for OpenAI API
        """
        sections = []

        # 1. Load main.md (always included)
        try:
            main_doc = self.load_file("main.md")
            sections.append(main_doc)
        except FileNotFoundError:
            # Fallback if main.md doesn't exist yet
            sections.append("# NOVA AI Code Generation System\n\nGenerate Python code based on the task and context provided.")

        sections.append("\n---\n")

        # 2. Task description
        sections.append(f"## TASK\n\n{task}\n")

        # 3. Context summary
        context_summary = self.summarize_context(context)
        sections.append(f"\n{context_summary}\n")

        sections.append("\n---\n")

        # 4. Detect and load integration docs
        integrations = self.detect_integrations(task, context)

        if integrations:
            sections.append("## INTEGRATION DOCUMENTATION\n\n")
            sections.append(f"Relevant integrations detected: {', '.join(integrations)}\n\n")

            for integration in integrations:
                try:
                    integration_path = f"integrations/{integration}.md"
                    integration_doc = self.load_file(integration_path)
                    sections.append(f"### {integration.upper()}\n\n")
                    sections.append(integration_doc)
                    sections.append("\n\n---\n\n")
                except FileNotFoundError:
                    # Skip if integration doc doesn't exist
                    sections.append(f"(Integration doc for '{integration}' not found)\n\n")

        # 5. Error history (if retry)
        if error_history and len(error_history) > 0:
            sections.append("## PREVIOUS ATTEMPTS (FAILED)\n\n")
            sections.append("The following attempts to generate code have failed. "
                          "Please learn from these errors and fix the issues.\n\n")

            for attempt in error_history:
                attempt_num = attempt.get('attempt', '?')
                error_msg = attempt.get('error', 'Unknown error')
                code = attempt.get('code', '')

                sections.append(f"**Attempt {attempt_num}:**\n\n")
                sections.append(f"Error: `{error_msg}`\n\n")

                if code:
                    sections.append("Generated code:\n```python\n")
                    sections.append(code)
                    sections.append("\n```\n\n")

        # 6. Final instruction
        sections.append("\n---\n\n")
        sections.append("## GENERATE PYTHON CODE\n\n")
        sections.append("Write Python code to accomplish the task above using the available context.\n\n")
        sections.append("Requirements:\n")
        sections.append("- Use only the libraries and integrations documented above\n")
        sections.append("- Output results as JSON using print(json.dumps({...}))\n")
        sections.append("- Include proper error handling\n")
        sections.append("- Follow the patterns shown in the integration documentation\n")
        sections.append("- Return context updates via 'context_updates' key in JSON output\n")

        return "".join(sections)
