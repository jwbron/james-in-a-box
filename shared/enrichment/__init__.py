"""
Shared enrichment module for LLM Documentation Strategy.

Per ADR: LLM Documentation Index Strategy (Phase 3)

Provides task/spec enrichment with relevant documentation context.
Dynamically parses docs/index.md to discover available documentation.
"""

from .enricher import (
    CodeExample,
    DocReference,
    EnrichedContext,
    SpecEnricher,
    enrich_task,
)


__all__ = [
    "CodeExample",
    "DocReference",
    "EnrichedContext",
    "SpecEnricher",
    "enrich_task",
]
