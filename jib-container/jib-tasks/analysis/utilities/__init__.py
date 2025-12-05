"""
Container-side analysis utilities.

These modules were moved from host-services/ because they are only used
inside the container and don't require host-side access.

Modules:
- confluence_doc_discoverer: Scans Confluence docs for repo relevance
- index_generator: Generates codebase indexes (codebase.json, patterns.json, etc.)
- docs_index_updater: Updates docs/index.md with generated content
"""
