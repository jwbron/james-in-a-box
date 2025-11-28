"""
Shared enrichment module for LLM Documentation Strategy.

Per ADR: LLM Documentation Index Strategy (Phase 3)

Provides task/spec enrichment with relevant documentation context.
Dynamically parses docs/index.md to discover available documentation.
"""

from .enricher import (
    DocReference,
    CodeExample,
    EnrichedContext,
    SpecEnricher,
    enrich_task,
)

__all__ = [
    "DocReference",
    "CodeExample",
    "EnrichedContext",
    "SpecEnricher",
    "enrich_task",
]
