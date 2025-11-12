"""
Document Loader - Load and chunk documentation for vector store.

Handles:
- Loading markdown files from /knowledge/integrations/
- Fetching official docs via WebFetch
- Intelligent chunking (by sections, with overlap)
- Metadata extraction (source, topic, section)
"""

import re
import logging
from typing import List, Dict, Optional
from pathlib import Path

logger = logging.getLogger(__name__)


class DocumentLoader:
    """
    Load and chunk documentation for vector storage.

    Features:
    - Smart chunking by markdown sections
    - Metadata extraction (source, topic, heading)
    - Overlap to preserve context across boundaries
    """

    def __init__(
        self,
        chunk_size: int = 700,
        chunk_overlap: int = 100
    ):
        """
        Initialize document loader.

        Args:
            chunk_size: Target size for each chunk (chars)
            chunk_overlap: Overlap between chunks (chars)
        """
        self.chunk_size = chunk_size
        self.chunk_overlap = chunk_overlap

    def load_markdown_file(
        self,
        file_path: str,
        source: str,
        topic: Optional[str] = None
    ) -> List[Dict[str, str]]:
        """
        Load and chunk a markdown file.

        Args:
            file_path: Path to .md file
            source: Source library (e.g., "pymupdf", "easyocr")
            topic: Optional topic/category

        Returns:
            List of document chunks with metadata

        Example:
            >>> loader = DocumentLoader()
            >>> docs = loader.load_markdown_file(
            ...     "knowledge/integrations/pdf.md",
            ...     source="pymupdf",
            ...     topic="pdf_processing"
            ... )
        """
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                content = f.read()
        except Exception as e:
            logger.error(f"Failed to read {file_path}: {e}")
            return []

        # Extract topic from filename if not provided
        if topic is None:
            topic = Path(file_path).stem  # e.g., "pdf" from "pdf.md"

        # Chunk the content
        chunks = self._chunk_markdown(content, source, topic)

        logger.info(f"Loaded {len(chunks)} chunks from {file_path}")

        return chunks

    def _chunk_markdown(
        self,
        content: str,
        source: str,
        topic: str
    ) -> List[Dict[str, str]]:
        """
        Chunk markdown content intelligently by sections.

        Strategy:
        1. Split by markdown headings (##, ###)
        2. Each section becomes 1+ chunks
        3. If section > chunk_size, split with overlap
        4. Preserve heading context in each chunk

        Args:
            content: Markdown text
            source: Source library
            topic: Topic/category

        Returns:
            List of chunks with metadata
        """
        chunks = []

        # Split into sections by headings
        sections = self._split_by_headings(content)

        for section in sections:
            heading = section['heading']
            text = section['text']

            # If section is small enough, keep as one chunk
            if len(text) <= self.chunk_size:
                chunks.append({
                    'text': f"{heading}\n\n{text}".strip(),
                    'source': source,
                    'topic': topic,
                    'metadata': {'section': heading}
                })
            else:
                # Split large section into overlapping chunks
                sub_chunks = self._split_with_overlap(text)

                for i, sub_chunk in enumerate(sub_chunks):
                    chunks.append({
                        'text': f"{heading}\n\n{sub_chunk}".strip(),
                        'source': source,
                        'topic': topic,
                        'metadata': {
                            'section': heading,
                            'chunk_index': i
                        }
                    })

        return chunks

    def _split_by_headings(self, content: str) -> List[Dict[str, str]]:
        """
        Split markdown by headings (##, ###).

        Returns:
            List of dicts with 'heading' and 'text' keys
        """
        # Pattern to match markdown headings
        heading_pattern = r'^(#{2,3})\s+(.+)$'

        lines = content.split('\n')
        sections = []
        current_heading = "General"
        current_text = []

        for line in lines:
            match = re.match(heading_pattern, line)

            if match:
                # Save previous section
                if current_text:
                    sections.append({
                        'heading': current_heading,
                        'text': '\n'.join(current_text).strip()
                    })

                # Start new section
                current_heading = match.group(2)
                current_text = []
            else:
                current_text.append(line)

        # Save last section
        if current_text:
            sections.append({
                'heading': current_heading,
                'text': '\n'.join(current_text).strip()
            })

        return sections

    def _split_with_overlap(self, text: str) -> List[str]:
        """
        Split text into overlapping chunks.

        Args:
            text: Text to split

        Returns:
            List of text chunks with overlap
        """
        if len(text) <= self.chunk_size:
            return [text]

        chunks = []
        start = 0

        while start < len(text):
            end = start + self.chunk_size

            # Try to break at sentence boundary
            if end < len(text):
                # Look for sentence end (. ! ?) within last 100 chars
                search_start = max(start, end - 100)
                last_period = text.rfind('.', search_start, end)
                last_question = text.rfind('?', search_start, end)
                last_exclaim = text.rfind('!', search_start, end)

                sentence_end = max(last_period, last_question, last_exclaim)

                if sentence_end > start:
                    end = sentence_end + 1

            chunk = text[start:end].strip()
            chunks.append(chunk)

            # Move start with overlap
            start = end - self.chunk_overlap

        return chunks

    def load_integration_docs(
        self,
        integrations_dir: Optional[str] = None
    ) -> List[Dict[str, str]]:
        """
        Load all integration docs from /knowledge/integrations/.

        Args:
            integrations_dir: Path to integrations directory.
                             Defaults to /nova/knowledge/integrations

        Returns:
            List of all document chunks

        Example:
            >>> loader = DocumentLoader()
            >>> all_docs = loader.load_integration_docs()
            >>> print(f"Loaded {len(all_docs)} total chunks")
        """
        if integrations_dir is None:
            base_dir = Path(__file__).parent.parent.parent.parent
            integrations_dir = str(base_dir / "knowledge" / "integrations")

        integrations_path = Path(integrations_dir)

        if not integrations_path.exists():
            logger.error(f"Integrations directory not found: {integrations_dir}")
            return []

        all_chunks = []

        # Find all .md files (except _index.md)
        md_files = [
            f for f in integrations_path.glob("*.md")
            if f.stem != "_index"
        ]

        logger.info(f"Found {len(md_files)} integration docs to load")

        for md_file in md_files:
            source = md_file.stem  # e.g., "pdf", "ocr", "imap"

            chunks = self.load_markdown_file(
                file_path=str(md_file),
                source=source,
                topic=source  # Use filename as topic
            )

            all_chunks.extend(chunks)

        logger.info(f"Loaded {len(all_chunks)} total chunks from {len(md_files)} files")

        return all_chunks


# Example usage
if __name__ == "__main__":
    # Setup logging
    logging.basicConfig(level=logging.INFO)

    # Initialize loader
    loader = DocumentLoader(chunk_size=700, chunk_overlap=100)

    # Load all integration docs
    docs = loader.load_integration_docs()

    print(f"\nLoaded {len(docs)} chunks")

    # Show first few
    for i, doc in enumerate(docs[:3]):
        print(f"\n--- Chunk {i+1} ---")
        print(f"Source: {doc['source']}")
        print(f"Topic: {doc['topic']}")
        print(f"Section: {doc['metadata'].get('section', 'N/A')}")
        print(f"Text preview: {doc['text'][:150]}...")
