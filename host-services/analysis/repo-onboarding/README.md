# Repository Onboarding Tools

Tools for onboarding repositories to Jib, the autonomous software engineering agent.

Per ADR: [Jib Repository Onboarding Strategy](../../../docs/adr/in-progress/ADR-Jib-Repo-Onboarding.md)

## Overview

When Jib works on a repository, it needs to understand that repository's structure, patterns, and conventions. These tools establish a standardized onboarding process that generates documentation indexes in target repositories.

## Quick Start

```bash
# Install the tools
./setup.sh

# Onboard a repository
jib-internal-devtools-setup --repo ~/khan/webapp

# Or just regenerate indexes (quick)
jib-regenerate-indexes ~/khan/webapp
```

## Tools

### jib-internal-devtools-setup

Full repository onboarding orchestration script. Runs all phases:

1. **Phase 1: Confluence Discovery** - Scans pre-synced Confluence docs for relevant documentation
2. **Phase 2: Feature Analysis** - Runs feature-analyzer to generate FEATURES.md
3. **Phase 3: Index Generation** - Creates codebase.json, patterns.json, dependencies.json
4. **Phase 4: Index Updates** - Updates docs/index.md with navigation links

```bash
# Full onboarding
jib-internal-devtools-setup --repo ~/khan/webapp

# Skip Confluence for public repos
jib-internal-devtools-setup --repo ~/khan/public-lib --skip-confluence --public-repo

# Preview changes
jib-internal-devtools-setup --repo ~/khan/webapp --dry-run
```

### jib-regenerate-indexes

Quick regeneration of local codebase indexes. Run after pulling changes to keep indexes fresh.

```bash
# Regenerate in current directory
jib-regenerate-indexes

# Regenerate for specific repo
jib-regenerate-indexes ~/khan/webapp
```

### docs-index-updater.py

Updates or creates docs/index.md with references to generated content.

```bash
docs-index-updater --repo-root ~/khan/webapp
```

## Generated Artifacts

| File | Location | Git Tracked | Purpose |
|------|----------|-------------|---------|
| `FEATURES.md` | `docs/FEATURES.md` | Yes | Feature-to-source mapping |
| `features/*.md` | `docs/features/` | Yes | Feature category documentation |
| `codebase.json` | `docs/generated/` | No | Project structure index |
| `patterns.json` | `docs/generated/` | No | Code patterns index |
| `dependencies.json` | `docs/generated/` | No | Dependency graph |
| `external-docs.json` | `docs/generated/` | No | Confluence doc references |

## GitHub Actions Template

Copy `templates/check-feature-docs.yml` to `.github/workflows/` to enable feature documentation drift detection:

```bash
cp templates/check-feature-docs.yml ~/khan/webapp/.github/workflows/
```

## Architecture

```
repo-onboarding/
├── jib-internal-devtools-setup  # Main orchestration script
├── jib-regenerate-indexes       # Quick index regeneration
├── docs-index-updater.py        # Updates docs/index.md
├── setup.sh                     # Installation script
├── templates/
│   └── check-feature-docs.yml   # GitHub Actions template
└── README.md                    # This file

../confluence-doc-discoverer/
└── confluence-doc-discoverer.py # Confluence doc discovery
```

## Related Tools

These tools integrate with existing analysis tools:

- **[feature-analyzer](../feature-analyzer/)** - Feature detection and FEATURES.md generation
- **[index-generator](../index-generator/)** - Codebase index generation
- **[doc-generator](../doc-generator/)** - Documentation generation and drift detection

## See Also

- [ADR: Jib Repository Onboarding Strategy](../../../docs/adr/in-progress/ADR-Jib-Repo-Onboarding.md)
- [ADR: Feature Analyzer Documentation Sync](../../../docs/adr/implemented/ADR-Feature-Analyzer-Documentation-Sync.md)
- [ADR: LLM Documentation Index Strategy](../../../docs/adr/implemented/ADR-LLM-Documentation-Index-Strategy.md)
