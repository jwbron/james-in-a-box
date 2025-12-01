"""
LLM Inefficiency Detector

Phase 2 of ADR-LLM-Inefficiency-Reporting: Pattern detection engine
for identifying processing inefficiencies in LLM trace sessions.
"""

from .inefficiency_detector import InefficiencyDetector
from .inefficiency_schema import (
    AggregateInefficiencyReport,
    DetectedInefficiency,
    InefficiencyCategory,
    SessionInefficiencyReport,
    Severity,
)


__all__ = [
    "AggregateInefficiencyReport",
    "DetectedInefficiency",
    "InefficiencyCategory",
    "InefficiencyDetector",
    "SessionInefficiencyReport",
    "Severity",
]
