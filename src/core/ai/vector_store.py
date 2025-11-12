"""
Vector Store Manager - Chroma-based document retrieval for AI code generation.

This module manages the vector database for storing and retrieving documentation.
Uses ChromaDB with sentence-transformers for embeddings.
"""

import os
import logging
from typing import List, Dict, Optional
from pathlib import Path

try:
    import chromadb
    from chromadb.config import Settings
    from sentence_transformers import SentenceTransformer
except ImportError:
    raise ImportError(
        "ChromaDB and sentence-transformers required. "
        "Install with: pip install chromadb sentence-transformers"
    )

logger = logging.getLogger(__name__)


class VectorStore:
    """
    Manages vector database for documentation retrieval.

    Uses:
    - ChromaDB for vector storage (local, persistent)
    - sentence-transformers/all-MiniLM-L6-v2 for embeddings (384 dims)

    Example:
        >>> store = VectorStore()
        >>> store.add_documents([
        ...     {"text": "PyMuPDF opens PDFs with fitz.open()", "source": "pymupdf", "topic": "opening"},
        ...     {"text": "EasyOCR requires gpu=False", "source": "easyocr", "topic": "config"}
        ... ])
        >>> results = store.query("how to open PDF", top_k=3)
        >>> for doc in results:
        ...     print(doc['text'])
    """

    def __init__(
        self,
        persist_directory: Optional[str] = None,
        collection_name: str = "nova_docs"
    ):
        """
        Initialize vector store.

        Args:
            persist_directory: Where to store the Chroma DB.
                              Defaults to /nova/knowledge/vector_db
            collection_name: Name of the collection (default: "nova_docs")
        """
        # Default persist directory
        if persist_directory is None:
            base_dir = Path(__file__).parent.parent.parent.parent
            persist_directory = str(base_dir / "knowledge" / "vector_db")

        self.persist_directory = persist_directory
        self.collection_name = collection_name

        # Ensure directory exists
        os.makedirs(persist_directory, exist_ok=True)

        # Initialize ChromaDB client with persistence
        self.client = chromadb.PersistentClient(
            path=persist_directory,
            settings=Settings(
                anonymized_telemetry=False,  # Disable telemetry
                allow_reset=True
            )
        )

        # Initialize embedding model
        # all-MiniLM-L6-v2: Fast, lightweight, 384 dimensions
        logger.info("Loading sentence-transformers model (all-MiniLM-L6-v2)...")
        self.embedding_model = SentenceTransformer('all-MiniLM-L6-v2')
        logger.info("Embedding model loaded")

        # Get or create collection
        try:
            self.collection = self.client.get_collection(
                name=collection_name
            )
            logger.info(f"Loaded existing collection: {collection_name}")
            logger.info(f"Collection size: {self.collection.count()} documents")
        except Exception:
            self.collection = self.client.create_collection(
                name=collection_name,
                metadata={"description": "NOVA AI documentation for code generation"}
            )
            logger.info(f"Created new collection: {collection_name}")

    def add_documents(
        self,
        documents: List[Dict[str, str]],
        batch_size: int = 100
    ) -> int:
        """
        Add documents to the vector store.

        Args:
            documents: List of dicts with keys:
                - text (required): Document text
                - source (optional): Source library (e.g., "pymupdf", "easyocr")
                - topic (optional): Topic/category (e.g., "opening", "text_extraction")
                - metadata (optional): Additional metadata dict
            batch_size: Process in batches to avoid memory issues

        Returns:
            Number of documents added

        Example:
            >>> docs = [
            ...     {
            ...         "text": "fitz.open() opens a PDF document",
            ...         "source": "pymupdf",
            ...         "topic": "opening"
            ...     }
            ... ]
            >>> count = store.add_documents(docs)
        """
        if not documents:
            logger.warning("No documents to add")
            return 0

        logger.info(f"Adding {len(documents)} documents to vector store...")

        added_count = 0

        # Process in batches
        for i in range(0, len(documents), batch_size):
            batch = documents[i:i + batch_size]

            # Extract texts and metadata
            texts = [doc['text'] for doc in batch]

            # Generate unique IDs
            ids = [f"doc_{self.collection.count() + j}" for j in range(len(batch))]

            # Build metadata for each document
            metadatas = []
            for doc in batch:
                meta = {
                    'source': doc.get('source', 'unknown'),
                    'topic': doc.get('topic', 'general'),
                }
                # Add any additional metadata
                if 'metadata' in doc:
                    meta.update(doc['metadata'])
                metadatas.append(meta)

            # Generate embeddings
            embeddings = self.embedding_model.encode(
                texts,
                show_progress_bar=False,
                convert_to_numpy=True
            ).tolist()

            # Add to collection
            self.collection.add(
                ids=ids,
                embeddings=embeddings,
                documents=texts,
                metadatas=metadatas
            )

            added_count += len(batch)
            logger.debug(f"Added batch {i // batch_size + 1}: {len(batch)} documents")

        logger.info(f"Successfully added {added_count} documents")
        logger.info(f"Total documents in collection: {self.collection.count()}")

        return added_count

    def query(
        self,
        query_text: str,
        top_k: int = 5,
        filter_source: Optional[str] = None,
        filter_topic: Optional[str] = None
    ) -> List[Dict[str, any]]:
        """
        Query the vector store for relevant documents.

        Args:
            query_text: Query string (e.g., "how to open PDF from bytes")
            top_k: Number of results to return (default: 5)
            filter_source: Filter by source library (e.g., "pymupdf")
            filter_topic: Filter by topic (e.g., "opening")

        Returns:
            List of dicts with keys:
                - text: Document text
                - source: Source library
                - topic: Topic/category
                - distance: Similarity distance (lower = more similar)

        Example:
            >>> results = store.query("extract text from PDF", top_k=3)
            >>> for doc in results:
            ...     print(f"{doc['source']}: {doc['text'][:100]}...")
        """
        if self.collection.count() == 0:
            logger.warning("Vector store is empty. No documents to query.")
            return []

        # Build where filter if source/topic specified
        where_filter = {}
        if filter_source:
            where_filter['source'] = filter_source
        if filter_topic:
            where_filter['topic'] = filter_topic

        # Generate query embedding
        query_embedding = self.embedding_model.encode(
            [query_text],
            show_progress_bar=False,
            convert_to_numpy=True
        ).tolist()[0]

        # Query collection
        results = self.collection.query(
            query_embeddings=[query_embedding],
            n_results=top_k,
            where=where_filter if where_filter else None,
            include=['documents', 'metadatas', 'distances']
        )

        # Format results
        formatted_results = []
        for i in range(len(results['documents'][0])):
            formatted_results.append({
                'text': results['documents'][0][i],
                'source': results['metadatas'][0][i].get('source', 'unknown'),
                'topic': results['metadatas'][0][i].get('topic', 'general'),
                'distance': results['distances'][0][i]
            })

        logger.debug(f"Query '{query_text[:50]}...' returned {len(formatted_results)} results")

        return formatted_results

    def clear(self):
        """
        Clear all documents from the collection.

        WARNING: This is destructive and cannot be undone.
        """
        logger.warning(f"Clearing collection: {self.collection_name}")
        self.client.delete_collection(self.collection_name)
        self.collection = self.client.create_collection(
            name=self.collection_name,
            metadata={"description": "NOVA AI documentation for code generation"}
        )
        logger.info("Collection cleared and recreated")

    def get_stats(self) -> Dict[str, any]:
        """
        Get statistics about the vector store.

        Returns:
            Dict with stats:
                - total_documents: Total number of docs
                - sources: List of unique sources
                - topics: List of unique topics
        """
        count = self.collection.count()

        if count == 0:
            return {
                'total_documents': 0,
                'sources': [],
                'topics': []
            }

        # Get all documents to compute stats
        # (Note: This is not efficient for large collections,
        #  but fine for documentation which is small)
        all_docs = self.collection.get(
            include=['metadatas']
        )

        sources = set()
        topics = set()

        for metadata in all_docs['metadatas']:
            sources.add(metadata.get('source', 'unknown'))
            topics.add(metadata.get('topic', 'general'))

        return {
            'total_documents': count,
            'sources': sorted(list(sources)),
            'topics': sorted(list(topics))
        }


# Example usage
if __name__ == "__main__":
    # Setup logging
    logging.basicConfig(level=logging.INFO)

    # Initialize store
    store = VectorStore()

    # Example: Add some documents
    docs = [
        {
            "text": "Use fitz.open() to open a PDF document. For bytes, use fitz.open(stream=BytesIO(data), filetype='pdf')",
            "source": "pymupdf",
            "topic": "opening"
        },
        {
            "text": "Extract text with page.get_text(). Returns plain text by default.",
            "source": "pymupdf",
            "topic": "text_extraction"
        },
        {
            "text": "EasyOCR requires gpu=False in NOVA sandbox (CPU-only). reader = easyocr.Reader(['es', 'en'], gpu=False)",
            "source": "easyocr",
            "topic": "initialization"
        }
    ]

    store.add_documents(docs)

    # Example: Query
    results = store.query("how to open PDF from bytes", top_k=2)

    print("\nQuery results:")
    for doc in results:
        print(f"- [{doc['source']}] {doc['text'][:80]}...")

    # Stats
    stats = store.get_stats()
    print(f"\nStats: {stats}")
