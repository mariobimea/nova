"""
KnowledgeManager - Manages knowledge base documentation for AI code generation.

This component:
1. Loads markdown documentation files with caching (deprecated - uses vector store now)
2. Detects which integrations are needed based on task and context
3. Retrieves relevant documentation from vector store
4. Summarizes context for AI prompts
5. Builds complete prompts for code generation
"""

import os
import logging
from typing import Dict, List, Optional
from pathlib import Path

logger = logging.getLogger(__name__)


class KnowledgeManager:
    """Manages knowledge base documentation for AI-powered code generation."""

    def __init__(self, knowledge_base_path: Optional[str] = None, use_vector_store: bool = True):
        """
        Initialize KnowledgeManager.

        Args:
            knowledge_base_path: Path to knowledge base directory.
                                Defaults to /nova/knowledge
            use_vector_store: Use vector store for doc retrieval (recommended).
                             If False, falls back to loading .md files directly.
        """
        if knowledge_base_path is None:
            # Default to /nova/knowledge (absolute path)
            base_dir = Path(__file__).parent.parent.parent.parent
            knowledge_base_path = str(base_dir / "knowledge")

        self.knowledge_base_path = knowledge_base_path
        self._cache: Dict[str, str] = {}  # In-memory cache for loaded files
        self.use_vector_store = use_vector_store

        # Initialize vector store if enabled
        if use_vector_store:
            try:
                from .vector_store import VectorStore
                self.vector_store = VectorStore()
                logger.info("KnowledgeManager initialized with vector store")
            except Exception as e:
                logger.warning(f"Failed to initialize vector store: {e}. Falling back to file loading.")
                self.use_vector_store = False
                self.vector_store = None
        else:
            self.vector_store = None

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

        SMART DETECTION for PDF extraction:
        - If context has 'recommended_extraction_method' = 'pymupdf' → load PyMuPDF docs
        - If context has 'recommended_extraction_method' = 'ocr' → load EasyOCR docs
        - If context has both 'pdf_data' and mentions method in task → load specific doc
        - Otherwise → use standard keyword detection

        DEPENDENCY SYSTEM:
        - Some integrations require others to work (e.g., OCR needs PDF for conversion)
        - Dependencies are automatically loaded when parent integration is detected

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
            'pymupdf': ['pdf', 'pymupdf', 'fitz', 'text layer', 'extract text'],
            'postgres': ['database', 'db', 'save', 'store', 'query', 'insert', 'update', 'postgres', 'sql'],
            'regex': ['pattern', 'regex', 'search text', 'extract amount', 'find', 'match'],
            'easyocr': ['ocr', 'easyocr', 'scan', 'scanned', 'image to text', 'recognize text', 'optical']
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
            'pymupdf': ['pdf_filename', 'pdf_text', 'pdf_data'],
            'postgres': ['invoice_id', 'db_table', 'sql_query'],
            'regex': ['pdf_text', 'total_amount', 'amount_found'],
            'easyocr': ['invoice_image_path', 'image_path', 'scanned_pdf', 'ocr_text']
        }

        for integration, hint_keys in context_key_hints.items():
            for hint_key in hint_keys:
                if hint_key in context:
                    detected.add(integration)
                    break

        # SMART RULE: Add recommended method if specified in context
        # This comes from the check_pdf_type node and tells us exactly which method to use
        recommended_method = context.get('recommended_extraction_method')

        if recommended_method == 'pymupdf':
            # PDF digital → Use PyMuPDF
            detected.add('pymupdf')
            # Note: Don't remove OCR - it might still be useful for hybrid PDFs

        elif recommended_method == 'ocr':
            # PDF scanned/hybrid → Use OCR
            detected.add('easyocr')
            # Note: Don't remove PyMuPDF - OCR needs PDF library to convert pages to images

        # DEPENDENCY SYSTEM: Automatically load required integrations
        # Define which integrations depend on others
        integration_dependencies = {
            'easyocr': ['pymupdf'],  # OCR needs PyMuPDF for converting PDF pages to images
            # Future examples:
            # 'smtp': ['regex'],  # SMTP might need regex for email templates
        }

        # Add dependencies for all detected integrations
        detected_with_deps = detected.copy()
        for integration in detected:
            if integration in integration_dependencies:
                for dependency in integration_dependencies[integration]:
                    detected_with_deps.add(dependency)

        return sorted(list(detected_with_deps))  # Sort for consistency

    def summarize_context(self, context: Dict) -> str:
        """
        Format context dictionary into human-readable summary for AI.

        Shows types and simplified representations with METADATA about encoding/format.
        This helps the AI know exactly how to handle each field.

        SMART TRUNCATION:
        - Heavy fields (pdf_data, image_data, etc.) are truncated to save tokens
        - Important text fields (ocr_text, email_body, etc.) are shown in full
        - Credentials and config are shown directly (they should be in env vars anyway)

        METADATA ADDITIONS:
        - Base64 fields get "BASE64-ENCODED" tag with decode instructions
        - Binary fields get "BINARY DATA" tag
        - Plain text fields get "PLAIN TEXT" tag

        Args:
            context: Context dictionary

        Returns:
            Formatted string summarizing available context with metadata
        """
        if not context:
            return "CONTEXT AVAILABLE:\n- (empty)"

        lines = ["CONTEXT AVAILABLE:"]

        # Define which fields should be truncated (heavy binary/base64 data)
        truncate_fields = {
            'pdf_data',      # Base64 PDF (huge)
            'image_data',    # Base64 images
            'attachment_data',  # Email attachments
            'file_data',     # Generic file data
        }

        # Define which fields are base64-encoded (need decode)
        base64_fields = {
            'pdf_data',
            'image_data',
            'attachment_data',
            'file_data',
        }

        for key, value in sorted(context.items()):
            # Get type name
            value_type = type(value).__name__

            # Metadata tags for the AI
            metadata_tags = []

            # Create simplified representation
            if isinstance(value, bytes):
                # Binary data - show size
                size_kb = len(value) // 1024
                size_bytes = len(value) % 1024
                if size_kb > 0:
                    repr_value = f"<binary data, {size_kb}KB>"
                else:
                    repr_value = f"<binary data, {size_bytes} bytes>"

                metadata_tags.append("BINARY DATA (already decoded)")

            elif isinstance(value, str):
                # String handling with SMART truncation
                should_truncate = key in truncate_fields
                is_base64 = key in base64_fields

                if should_truncate and len(value) > 100:
                    # Heavy field (like base64) - truncate aggressively
                    repr_value = f'"{value[:100]}..." (truncated, {len(value)} chars total)'
                else:
                    # Important text field - show in full (ocr_text, email_body, etc.)
                    repr_value = f'"{value}"'

                # Add metadata tag
                if is_base64:
                    metadata_tags.append("BASE64-ENCODED")
                    metadata_tags.append(f"Decode with: base64.b64decode({key})")
                elif should_truncate:
                    metadata_tags.append("LARGE STRING (truncated)")
                else:
                    metadata_tags.append("PLAIN TEXT")

            elif isinstance(value, (int, float, bool)):
                # Numbers and booleans - show directly
                repr_value = str(value)
                metadata_tags.append("PRIMITIVE VALUE")

            elif isinstance(value, (list, dict)):
                # Collections - show type and length
                if isinstance(value, list):
                    repr_value = f"<list with {len(value)} items>"
                else:
                    repr_value = f"<dict with {len(value)} keys>"

                metadata_tags.append("COLLECTION")

            else:
                # Other types - just show type
                repr_value = f"<{value_type}>"

            # Build line with metadata
            line = f"- {key}: {repr_value} ({value_type})"

            if metadata_tags:
                line += f"\n  → {' | '.join(metadata_tags)}"

            lines.append(line)

        return "\n".join(lines)

    def retrieve_docs(
        self,
        task: str,
        integrations: List[str],
        top_k_per_integration: int = 3
    ) -> str:
        """
        Retrieve relevant documentation from vector store.

        Args:
            task: Task description for semantic search
            integrations: List of integration names (e.g., ["pymupdf", "easyocr"])
            top_k_per_integration: How many chunks to retrieve per integration

        Returns:
            Formatted documentation string ready for prompt

        Example:
            >>> manager = KnowledgeManager()
            >>> docs = manager.retrieve_docs(
            ...     task="extract text from PDF",
            ...     integrations=["pymupdf"]
            ... )
        """
        if not self.use_vector_store or self.vector_store is None:
            logger.warning("Vector store not available, returning empty docs")
            return ""

        all_docs = []

        # Query for each integration
        for integration in integrations:
            logger.debug(f"Retrieving docs for integration: {integration}")

            # Query vector store
            results = self.vector_store.query(
                query_text=f"{integration} {task}",
                top_k=top_k_per_integration,
                filter_source=integration
            )

            if results:
                all_docs.extend(results)
                logger.debug(f"Retrieved {len(results)} chunks for {integration}")

        if not all_docs:
            logger.warning(f"No docs found for integrations: {integrations}")
            return ""

        # Format docs for prompt
        formatted_sections = []

        for integration in integrations:
            # Get docs for this integration
            integration_docs = [d for d in all_docs if d['source'] == integration]

            if not integration_docs:
                continue

            formatted_sections.append(f"## {integration.upper()} Documentation\n")

            for doc in integration_docs:
                formatted_sections.append(doc['text'])
                formatted_sections.append("\n---\n")

        formatted_docs = "\n".join(formatted_sections)

        logger.info(f"Retrieved {len(all_docs)} total chunks from {len(integrations)} integrations")

        return formatted_docs

    def build_prompt(
        self,
        task: str,
        context: Dict,
        error_history: Optional[List[Dict]] = None
    ) -> tuple[str, Dict]:
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
            Tuple of (prompt_string, metadata_dict)
            - prompt_string: Complete prompt ready for OpenAI API
            - metadata_dict: Debug info with keys:
                - integrations_detected: List[str]
                - context_summary: str
                - docs_retrieved_count: int
                - retrieval_method: str ("vector_store" or "file_loading")
        """
        sections = []
        metadata = {
            "integrations_detected": [],
            "context_summary": "",
            "docs_retrieved_count": 0,
            "retrieval_method": "none"
        }

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
        metadata["context_summary"] = context_summary

        sections.append("\n---\n")

        # 4. Integration docs (auto-detected based on task and context)
        integrations = self.detect_integrations(task, context)
        metadata["integrations_detected"] = integrations

        if integrations:
            sections.append("## INTEGRATION DOCUMENTATION\n\n")
            sections.append(f"Relevant integrations detected: {', '.join(integrations)}\n\n")

            # Use vector store retrieval if available, otherwise fall back to file loading
            if self.use_vector_store and self.vector_store is not None:
                # NEW: Retrieve docs from vector store
                logger.info(f"Retrieving docs for integrations: {integrations}")

                # Track retrieval stats
                docs_count = 0
                for integration in integrations:
                    results = self.vector_store.query(
                        query_text=f"{integration} {task}",
                        top_k=3,  # 3 most relevant chunks per integration
                        filter_source=integration
                    )
                    docs_count += len(results)

                metadata["retrieval_method"] = "vector_store"
                metadata["docs_retrieved_count"] = docs_count

                retrieved_docs = self.retrieve_docs(
                    task=task,
                    integrations=integrations,
                    top_k_per_integration=3
                )

                if retrieved_docs:
                    sections.append(retrieved_docs)
                else:
                    sections.append("(No relevant documentation found in vector store)\n\n")

            else:
                # FALLBACK: Load from .md files (old method)
                logger.info("Using fallback file loading for integration docs")
                metadata["retrieval_method"] = "file_loading"
                metadata["docs_retrieved_count"] = len(integrations)  # One doc per integration

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

        # 5. Error history - Show ALL previous failed attempts
        if error_history and len(error_history) > 0:
            sections.append("## PREVIOUS ATTEMPTS (FAILED)\n\n")
            sections.append(
                "⚠️  You have already tried to generate code for this task, but it FAILED.\n"
                "Learn from these errors and fix the issues.\n\n"
            )

            for attempt in error_history:
                attempt_num = attempt.get('attempt', '?')
                error_msg = attempt.get('error', 'Unknown error')
                code = attempt.get('code', '')

                sections.append(f"### Attempt {attempt_num}/{len(error_history) + 1} - FAILED\n\n")

                # Error message
                sections.append(f"**Error:**\n```\n{error_msg}\n```\n\n")

                # Generated code (if available)
                if code:
                    # Truncate code if too long (save tokens)
                    max_code_lines = 50
                    code_lines = code.split('\n')

                    if len(code_lines) > max_code_lines:
                        truncated_code = '\n'.join(code_lines[:max_code_lines])
                        sections.append(f"**Generated code (first {max_code_lines} lines):**\n```python\n")
                        sections.append(truncated_code)
                        sections.append(f"\n... ({len(code_lines) - max_code_lines} more lines)\n```\n\n")
                    else:
                        sections.append("**Generated code:**\n```python\n")
                        sections.append(code)
                        sections.append("\n```\n\n")

                # Add specific hints based on error type
                error_lower = error_msg.lower()

                if "not valid json" in error_lower or "expecting value" in error_lower:
                    sections.append(
                        "💡 **Hint:** The code didn't print valid JSON. Make sure:\n"
                        "- You print exactly ONE json.dumps() statement at the end\n"
                        "- The JSON is properly formatted\n"
                        "- No extra print statements or text before/after the JSON\n\n"
                    )

                elif "ocr" in error_lower or "easyocr" in error_lower:
                    sections.append(
                        "💡 **Hint:** EasyOCR issue detected. Remember:\n"
                        "- EasyOCR CANNOT read PDF bytes directly\n"
                        "- You must convert PDF to image first using PyMuPDF (fitz)\n"
                        "- Example: `pix = page.get_pixmap(); img_bytes = pix.tobytes('png')`\n\n"
                    )

                elif "timeout" in error_lower:
                    sections.append(
                        "💡 **Hint:** Code timed out. Make sure:\n"
                        "- The code doesn't have infinite loops\n"
                        "- Heavy operations are optimized\n"
                        "- You're not loading huge files unnecessarily\n\n"
                    )

                sections.append("---\n\n")

            # Final instruction after showing all errors
            sections.append(
                "## YOUR TASK NOW\n\n"
                "Fix the errors shown above and generate WORKING code.\n\n"
                "Common mistakes to avoid:\n"
                "❌ EasyOCR cannot read PDF bytes - convert to image first\n"
                "❌ Printing multiple JSON outputs - only ONE print(json.dumps(...)) at the end\n"
                "❌ Not handling errors - always use try/except\n"
                "❌ Forgetting to add extracted data to context_updates\n\n"
            )

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

        full_prompt = "".join(sections)
        return full_prompt, metadata
