"""
Context Summary - Schema representation of workflow context

This module defines the structure for context summaries used by LLMs.
Instead of sending the full context (which can be huge), we send a summary
with schemas and metadata about what has been analyzed.

Key Concepts:
- Context Summary: Schema + metadata (for LLMs)
- Context (full): Actual data values (for E2B execution)
- Incremental Analysis: Only analyze new keys, reuse previous schemas
"""

from typing import Dict, Any, List, Optional
from pydantic import BaseModel, Field
from datetime import datetime


class AnalysisEntry(BaseModel):
    """
    Record of a single analysis performed by InputAnalyzer.

    Tracks what was analyzed at each node to enable incremental analysis.
    """
    node_id: str = Field(..., description="ID of the node where analysis happened")
    analyzed_keys: List[str] = Field(..., description="Keys that were analyzed")
    schema_generated: Dict[str, Any] = Field(..., description="Schema generated for analyzed keys")
    timestamp: str = Field(default_factory=lambda: datetime.utcnow().isoformat())

    class Config:
        frozen = True


class ContextLayers(BaseModel):
    """
    Classification of context keys by processing level.

    Layers:
        - raw: Original input data (e.g., pdf_path, email_from)
        - processed: Extracted/transformed data (e.g., document_text, entities)
        - structured: Final clean data (e.g., invoice_amount, vendor_name)

    This is primarily for visualization/debugging. The system can infer
    layers automatically based on data types and patterns.
    """
    raw: List[str] = Field(default_factory=list)
    processed: List[str] = Field(default_factory=list)
    structured: List[str] = Field(default_factory=list)

    def add_key(self, key: str, layer: str) -> None:
        """Add a key to a specific layer"""
        if layer == "raw" and key not in self.raw:
            self.raw.append(key)
        elif layer == "processed" and key not in self.processed:
            self.processed.append(key)
        elif layer == "structured" and key not in self.structured:
            self.structured.append(key)

    def get_layer(self, key: str) -> Optional[str]:
        """Get the layer of a key"""
        if key in self.raw:
            return "raw"
        elif key in self.processed:
            return "processed"
        elif key in self.structured:
            return "structured"
        return None


class ContextSummary(BaseModel):
    """
    Summary of the workflow context for LLM consumption.

    Contains:
        - schema: Type definitions and descriptions of context keys
        - analysis_history: What has been analyzed at each node
        - context_layers: Classification of keys by processing level

    This is what gets sent to LLMs (CodeGenerator, OutputValidator) instead
    of the full context, which can be very large (e.g., PDFs, images).

    Example:
        >>> summary = ContextSummary(
        ...     schema={
        ...         "invoice_amount": {
        ...             "type": "number",
        ...             "description": "Total invoice amount in USD"
        ...         }
        ...     },
        ...     analysis_history=[
        ...         AnalysisEntry(
        ...             node_id="parse_invoice",
        ...             analyzed_keys=["document_text"],
        ...             schema_generated={...}
        ...         )
        ...     ]
        ... )
    """
    context_schema: Dict[str, Any] = Field(
        default_factory=dict,
        description="Schema of all context keys with type and description",
        alias="schema"  # Keep backward compatibility
    )
    analysis_history: List[AnalysisEntry] = Field(
        default_factory=list,
        description="History of analysis operations (for incremental analysis)"
    )
    context_layers: ContextLayers = Field(
        default_factory=ContextLayers,
        description="Classification of keys by processing level"
    )

    def add_analysis(self, entry: AnalysisEntry) -> None:
        """Add a new analysis entry to history"""
        self.analysis_history.append(entry)
        # Merge new schema with existing
        self.context_schema.update(entry.schema_generated)

    def get_analyzed_keys(self) -> set:
        """Get all keys that have been analyzed so far"""
        analyzed = set()
        for entry in self.analysis_history:
            analyzed.update(entry.analyzed_keys)
        return analyzed

    def get_new_keys(self, current_context_keys: set) -> set:
        """
        Identify keys in current context that haven't been analyzed yet.

        This is the core of incremental analysis: only analyze what's new.
        """
        # Exclude metadata keys (start with _)
        current_keys = {k for k in current_context_keys if not k.startswith("_")}
        analyzed_keys = self.get_analyzed_keys()
        return current_keys - analyzed_keys

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization"""
        return {
            "schema": self.context_schema,
            "analysis_history": [
                {
                    "node_id": entry.node_id,
                    "analyzed_keys": entry.analyzed_keys,
                    "schema_generated": entry.schema_generated,
                    "timestamp": entry.timestamp
                }
                for entry in self.analysis_history
            ],
            "context_layers": {
                "raw": self.context_layers.raw,
                "processed": self.context_layers.processed,
                "structured": self.context_layers.structured
            }
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ContextSummary":
        """Create from dictionary"""
        return cls(
            schema=data.get("schema", {}),
            analysis_history=[
                AnalysisEntry(**entry)
                for entry in data.get("analysis_history", [])
            ],
            context_layers=ContextLayers(**data.get("context_layers", {}))
        )

    class Config:
        # Allow mutation for adding analysis entries
        frozen = False
