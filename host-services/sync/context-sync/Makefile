# Documentation Sync Makefile

# Use the parent host-services venv (managed by uv at the host-services level)
VENV := ../../.venv

# Ensure the virtual environment exists (created by setup.sh via uv sync)
${VENV}/bin/python:
	@echo "Virtual environment not found at ${VENV}"
	@echo "Run 'uv sync' from the host-services directory or run setup.sh"
	@exit 1

.PHONY: deps
deps: ${VENV}/bin/python

# Documentation sync targets
# Sync all connectors
.PHONY: sync-all
sync-all: deps
	@echo "Syncing all connectors (Confluence + JIRA)..."
	${VENV}/bin/python sync_all.py

# Confluence sync targets
.PHONY: docs-sync
docs-sync: deps
	@echo "Syncing documentation from Confluence..."
	${VENV}/bin/python -c "from utils.config_loader import load_env_file; load_env_file(); from connectors.confluence.sync import main; exit(main())"

.PHONY: docs-sync-full
docs-sync-full: docs-clean docs-sync

.PHONY: docs-sync-limited
docs-sync-limited: deps
	@echo "Syncing documentation from Confluence (limited to 100 pages)..."
	CONFLUENCE_MAX_PAGES=100 ${VENV}/bin/python -c "from utils.config_loader import load_env_file; load_env_file(); from connectors.confluence.sync import main; exit(main())"

# Basic sync with ID or URL, optional format and full flag
# Usage: make docs-sync-page PAGE_ID=12345 [FORMAT=markdown] [FULL=1]
.PHONY: docs-sync-page
docs-sync-page: deps
	@if [ -z "$(PAGE_ID)$(PAGE_URL)" ]; then \
		echo "Usage:"; \
		echo "  make docs-sync-page PAGE_ID=12345 [FORMAT=markdown] [FULL=1]"; \
		echo "  make docs-sync-page PAGE_URL=\"https://company.atlassian.net/wiki/...\" [FORMAT=markdown] [FULL=1]"; \
		echo ""; \
		echo "Options:"; \
		echo "  FORMAT=markdown  Output in markdown format (default: html)"; \
		echo "  FULL=1           Force full sync, ignoring cache (re-fetch comments)"; \
		exit 1; \
	fi
	@FULL_FLAG=""; \
	if [ -n "$(FULL)" ]; then \
		FULL_FLAG="--full"; \
		echo "Full sync mode (ignoring cache)"; \
	fi; \
	if [ -n "$(PAGE_ID)" ]; then \
		echo "Syncing page by ID: $(PAGE_ID) (format: $(or $(FORMAT),html))"; \
		if [ -n "$(FORMAT)" ]; then \
			${VENV}/bin/python -c "from utils.config_loader import load_env_file; load_env_file(); from connectors.confluence.sync import main; import sys; sys.argv = ['sync', '--page-id', '$(PAGE_ID)', '--format', '$(FORMAT)'] + (['--full'] if '$(FULL)' else []); exit(main())"; \
		else \
			${VENV}/bin/python -c "from utils.config_loader import load_env_file; load_env_file(); from connectors.confluence.sync import main; import sys; sys.argv = ['sync', '--page-id', '$(PAGE_ID)'] + (['--full'] if '$(FULL)' else []); exit(main())"; \
		fi \
	elif [ -n "$(PAGE_URL)" ]; then \
		echo "Syncing page by URL: $(PAGE_URL) (format: $(or $(FORMAT),html))"; \
		if [ -n "$(FORMAT)" ]; then \
			${VENV}/bin/python -c "from utils.config_loader import load_env_file; load_env_file(); from connectors.confluence.sync import main; import sys; sys.argv = ['sync', '--page-url', '$(PAGE_URL)', '--format', '$(FORMAT)'] + (['--full'] if '$(FULL)' else []); exit(main())"; \
		else \
			${VENV}/bin/python -c "from utils.config_loader import load_env_file; load_env_file(); from connectors.confluence.sync import main; import sys; sys.argv = ['sync', '--page-url', '$(PAGE_URL)'] + (['--full'] if '$(FULL)' else []); exit(main())"; \
		fi \
	fi

# Convenience target for Markdown
.PHONY: docs-sync-page-markdown
docs-sync-page-markdown: deps
	@if [ -z "$(PAGE_ID)$(PAGE_URL)" ]; then \
		echo "Usage:"; \
		echo "  make docs-sync-page-markdown PAGE_ID=12345"; \
		echo "  make docs-sync-page-markdown PAGE_URL=\"https://company.atlassian.net/wiki/...\""; \
		exit 1; \
	fi
	@if [ -n "$(PAGE_ID)" ]; then \
		echo "Syncing page as Markdown by ID: $(PAGE_ID)"; \
		${VENV}/bin/python -c "from utils.config_loader import load_env_file; load_env_file(); from connectors.confluence.sync import main; import sys; sys.argv = ['sync', '--page-id', '$(PAGE_ID)', '--format', 'markdown']; exit(main())"; \
	elif [ -n "$(PAGE_URL)" ]; then \
		echo "Syncing page as Markdown by URL: $(PAGE_URL)"; \
		${VENV}/bin/python -c "from utils.config_loader import load_env_file; load_env_file(); from connectors.confluence.sync import main; import sys; sys.argv = ['sync', '--page-url', '$(PAGE_URL)', '--format', 'markdown']; exit(main())"; \
	fi

.PHONY: docs-search
docs-search: deps
	@if [ -z "$(QUERY)" ]; then \
		echo "Usage: make docs-search QUERY=\"your search term\""; \
		echo "Example: make docs-search QUERY=\"API documentation\""; \
		echo ""; \
		echo "Additional options:"; \
		echo "  make docs-search QUERY=\"term\" SPACE=\"SPACEKEY\"  # Search in specific space"; \
		echo "  make docs-search QUERY=\"term\" MAX_RESULTS=10       # Limit results"; \
		echo "  make docs-search --stats                             # Show statistics"; \
		exit 1; \
	fi
	${VENV}/bin/python -c "from utils.config_loader import load_env_file; load_env_file(); from utils.search import main; import sys; sys.argv = ['search'] + ['$(QUERY)'] + (['--space', '$(SPACE)'] if '$(SPACE)' else []) + (['--max-results', '$(MAX_RESULTS)'] if '$(MAX_RESULTS)' else []); main()"

.PHONY: docs-list-spaces
docs-list-spaces: deps
	${VENV}/bin/python -c "from utils.config_loader import load_env_file; load_env_file(); from utils.search import list_spaces; list_spaces()"

.PHONY: docs-list-all-spaces
docs-list-all-spaces: deps
	${VENV}/bin/python -c "from utils.config_loader import load_env_file; load_env_file(); from utils.list_spaces import list_all_spaces; list_all_spaces()"

.PHONY: docs-get-space-ids
docs-get-space-ids: deps
	${VENV}/bin/python -c "from utils.config_loader import load_env_file; load_env_file(); from utils.get_space_ids import get_space_ids; get_space_ids()"

.PHONY: docs-clean
docs-clean:
	@echo "Cleaning synced documentation..."
	rm -rf confluence-docs/*
	rm -f confluence-docs/.sync_state

.PHONY: docs-status
docs-status: deps
	${VENV}/bin/python -c "from utils.config_loader import load_env_file; load_env_file(); from utils.maintenance import main; import sys; sys.argv = ['maintenance', '--status']; main()"

.PHONY: docs-cleanup
docs-cleanup: deps
	${VENV}/bin/python -c "from utils.config_loader import load_env_file; load_env_file(); from utils.maintenance import main; import sys; sys.argv = ['maintenance', '--cleanup']; main()"

.PHONY: docs-cleanup-execute
docs-cleanup-execute: deps
	${VENV}/bin/python -c "from utils.config_loader import load_env_file; load_env_file(); from utils.maintenance import main; import sys; sys.argv = ['maintenance', '--cleanup', '--execute']; main()"

.PHONY: docs-link
docs-link: deps
	@if [ -z "$(PROJECT)" ]; then \
		echo "Usage: make docs-link PROJECT=\"/path/to/project\""; \
		echo "Example: make docs-link PROJECT=~/projects/my-app"; \
		echo "Example: make docs-link PROJECT=~/workspace/backend LINK_NAME=confluence-docs"; \
		exit 1; \
	fi
	${VENV}/bin/python -c "from utils.config_loader import load_env_file; load_env_file(); from utils.create_symlink import create_symlink; import sys; create_symlink('$(PROJECT)', '$(LINK_NAME)' if '$(LINK_NAME)' else 'confluence-docs')"

.PHONY: docs-list-links
docs-list-links: deps
	${VENV}/bin/python -c "from utils.config_loader import load_env_file; load_env_file(); from utils.create_symlink import list_projects_with_symlinks; list_projects_with_symlinks()"

.PHONY: docs-link-khan
docs-link-khan: deps
	@echo "Creating symlinks to Confluence documentation in all Khan Academy projects..."
	${VENV}/bin/python -c "from utils.config_loader import load_env_file; load_env_file(); from utils.link_to_khan_projects import create_symlinks_for_khan_projects; import sys; dry_run = '--execute' not in sys.argv; link_name = 'confluence-docs'; create_symlinks_for_khan_projects(link_name, dry_run)"

.PHONY: docs-link-khan-execute
docs-link-khan-execute: deps
	@echo "Creating symlinks to Confluence documentation in all Khan Academy projects..."
	${VENV}/bin/python -c "from utils.config_loader import load_env_file; load_env_file(); from utils.link_to_khan_projects import create_symlinks_for_khan_projects; link_name = 'confluence-docs'; create_symlinks_for_khan_projects(link_name, False)"

.PHONY: docs-list-khan-links
docs-list-khan-links: deps
	${VENV}/bin/python -c "from utils.config_loader import load_env_file; load_env_file(); from utils.link_to_khan_projects import list_khan_projects_with_links; list_khan_projects_with_links()"

.PHONY: docs-setup-cursor
docs-setup-cursor: deps
	@echo "Setting up Cursor rule for confluence-docs directories..."
	${VENV}/bin/python -c "from utils.config_loader import load_env_file; load_env_file(); from utils.link_to_khan_projects import ensure_cursor_rule; ensure_cursor_rule()"

.PHONY: docs-bootstrap
docs-bootstrap: deps
	@echo "Bootstrapping Confluence documentation sync for Khan Academy..."
	@echo ""
	@echo "Step 1: Setting up configuration..."
	@if [ ! -f .env ]; then \
		echo "No .env file found. Running interactive setup..."; \
		${VENV}/bin/python -m utils.setup; \
	else \
		echo ".env file found. Testing configuration..."; \
		${VENV}/bin/python -m utils.setup test; \
	fi
	@echo ""
	@echo "Step 2: Running full sync of Confluence documentation (all pages)..."
	${VENV}/bin/python -c "from utils.config_loader import load_env_file; load_env_file(); from connectors.confluence.sync import main; exit(main())"
	@echo ""
	@echo "Step 3: Creating symlinks in all Khan Academy projects..."
	${VENV}/bin/python -c "from utils.config_loader import load_env_file; load_env_file(); from utils.link_to_khan_projects import create_symlinks_for_khan_projects; link_name = 'confluence-docs'; create_symlinks_for_khan_projects(link_name, False)"
	@echo ""
	@echo "Bootstrap complete! Your Confluence documentation is now:"
	@echo "   - Synced locally in confluence-docs/"
	@echo "   - Available in all Khan Academy projects via symlinks"
	@echo "   - Ready for Cursor to index and search"
	@echo ""
	@echo "Next steps:"
	@echo "   - Search documentation: make docs-search QUERY=\"your search term\""
	@echo "   - View status: make docs-status"
	@echo "   - List linked projects: make docs-list-khan-links"

.PHONY: docs-setup
docs-setup: deps
	@echo "Setting up Confluence documentation sync..."
	${VENV}/bin/python -m utils.setup

.PHONY: docs-test
docs-test: deps
	@echo "Testing Confluence connection..."
	${VENV}/bin/python -m utils.setup test

# JIRA sync targets
.PHONY: jira-sync
jira-sync: deps
	@echo "Syncing JIRA tickets..."
	${VENV}/bin/python -m connectors.jira.connector

.PHONY: jira-sync-full
jira-sync-full: deps
	@echo "Syncing JIRA tickets (full sync)..."
	${VENV}/bin/python -m connectors.jira.connector --full

.PHONY: jira-clean
jira-clean:
	@echo "Cleaning synced JIRA tickets..."
	rm -rf ~/context-sync/jira/*
	rm -f ~/context-sync/jira/.sync_state

.PHONY: help
help:
	@echo "Available commands:"
	@echo ""
	@echo "Multi-connector sync:"
	@echo "  make sync-all        - Sync all connectors (Confluence + JIRA)"
	@echo ""
	@echo "Confluence documentation:"
	@echo "  make docs-bootstrap  - Complete setup for Khan Academy users"
	@echo "  make docs-setup      - Interactive configuration setup"
	@echo "  make docs-test       - Test Confluence connection"
	@echo "  make docs-sync       - Sync documentation from Confluence (incremental)"
	@echo "  make docs-sync-full  - Full sync (clean + sync all pages)"
	@echo "  make docs-sync-limited - Sync with 100 page limit (for testing)"
	@echo "  make docs-sync-page PAGE_ID=12345 [FORMAT=markdown] [FULL=1] - Sync single page by ID"
	@echo "  make docs-sync-page PAGE_URL=\"https://...\" [FORMAT=markdown] [FULL=1] - Sync single page by URL"
	@echo "  make docs-sync-page-markdown PAGE_ID=12345 - Sync single page as Markdown"
	@echo "  make docs-search QUERY=\"term\" - Search synced documentation"
	@echo "  make docs-search --stats - Show documentation statistics"
	@echo "  make docs-list-spaces - List available spaces"
	@echo "  make docs-list-all-spaces - List all spaces with details"
	@echo "  make docs-get-space-ids - Get space IDs for configured spaces"
	@echo "  make docs-status      - Show sync status and statistics"
	@echo "  make docs-cleanup     - Find orphaned files (dry run)"
	@echo "  make docs-cleanup-execute - Remove orphaned files"
	@echo "  make docs-clean       - Clean all synced documentation"
	@echo "  make docs-link PROJECT=\"/path\" - Create symlink in another project"
	@echo "  make docs-list-links  - List projects with symlinks"
	@echo "  make docs-link-khan   - Create symlinks in all Khan Academy projects (dry run)"
	@echo "  make docs-link-khan-execute - Create symlinks in all Khan Academy projects"
	@echo "  make docs-list-khan-links - List Khan Academy projects with symlinks"
	@echo "  make docs-setup-cursor   - Set up Cursor rule for confluence-docs"
	@echo ""
	@echo "JIRA tickets:"
	@echo "  make jira-sync       - Sync JIRA tickets (incremental)"
	@echo "  make jira-sync-full  - Full JIRA sync (re-download all tickets)"
	@echo "  make jira-clean      - Clean synced JIRA tickets"
	@echo ""
	@echo "General:"
	@echo "  make help             - Show this help"
	@echo ""
	@echo "Search options:"
	@echo "  make docs-search QUERY=\"term\" SPACE=\"SPACEKEY\" - Search in specific space"
	@echo "  make docs-search QUERY=\"term\" MAX_RESULTS=10 - Limit search results"
	@echo ""
	@echo "Linking options:"
	@echo "  make docs-link PROJECT=\"/path\" LINK_NAME=\"docs\" - Create symlink with custom name"
	@echo "  make docs-link-khan - Link to all Khan Academy git projects" 