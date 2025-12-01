#!/bin/bash
# Setup script for spec-enricher
# Per ADR: LLM Documentation Index Strategy (Phase 3)

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

echo "Setting up spec-enricher..."

# Make the script executable
chmod +x "$SCRIPT_DIR/spec-enricher.py"

# Create symlink in user's bin if it exists
if [ -d "$HOME/bin" ]; then
    ln -sf "$SCRIPT_DIR/spec-enricher.py" "$HOME/bin/spec-enricher"
    echo "Created symlink: ~/bin/spec-enricher"
fi

# Verify it works
echo "Testing spec-enricher..."
echo "Add Slack notification support" | python3 "$SCRIPT_DIR/spec-enricher.py" --context-only --format yaml

echo ""
echo "Setup complete!"
echo ""
echo "Usage:"
echo "  spec-enricher --spec task.md                    # Enrich a spec file"
echo "  echo 'Add auth' | spec-enricher                 # Enrich from stdin"
echo "  spec-enricher --spec task.md --format yaml      # Output as YAML"
echo "  spec-enricher --spec task.md --context-only     # Just the context"

