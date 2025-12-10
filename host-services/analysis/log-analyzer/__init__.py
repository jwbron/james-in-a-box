"""
Log Analyzer - Claude-powered error detection and classification.

Provides centralized log aggregation and intelligent error analysis
using Claude for classification and root cause suggestions.

Usage:
    from log_analyzer import LogAnalyzer, LogAggregator

    # Aggregate logs from all sources
    aggregator = LogAggregator()
    aggregator.aggregate()

    # Analyze errors with Claude
    analyzer = LogAnalyzer()
    errors = analyzer.extract_errors()
    classified = analyzer.classify_errors(errors)

    # Generate summary
    summary = analyzer.generate_summary(classified)

Components:
    - LogAggregator: Collects logs from multiple sources
    - LogAnalyzer: Extracts and classifies errors
    - ErrorClassifier: Claude-powered classification
    - ReportGenerator: Creates summaries and alerts
"""

from .error_classifier import ClassifiedError, ErrorClassifier
from .error_extractor import ErrorExtractor, ExtractedError
from .log_aggregator import LogAggregator
from .log_analyzer import LogAnalyzer


__all__ = [
    "ClassifiedError",
    "ErrorClassifier",
    "ErrorExtractor",
    "ExtractedError",
    "LogAggregator",
    "LogAnalyzer",
]

__version__ = "0.1.0"
