#!/bin/bash
# apply-staged-changes.sh - Quick tool to apply staged changes from Claude
#
# Usage: apply-staged-changes.sh [project-name] [target-repo]
#
# This is a simplified wrapper for the host to quickly apply staged changes.
# Can be run without arguments for interactive mode.

set -e

STAGING_BASE="$HOME/.jib-sharing/staged-changes"
PROJECT_NAME="$1"
TARGET_REPO="$2"

# Color output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

echo -e "${BLUE}🤖 Claude Staged Changes - Apply Tool${NC}"
echo ""

# Interactive mode if no project specified
if [ -z "$PROJECT_NAME" ]; then
    echo "Available staged changes:"
    echo ""

    projects=()
    for dir in "$STAGING_BASE"/*; do
        if [ -d "$dir" ]; then
            name=$(basename "$dir")
            projects+=("$name")
            echo "  • $name"

            # Show brief summary
            if [ -f "$dir/CHANGES.md" ]; then
                title=$(head -1 "$dir/CHANGES.md" | sed 's/^# //')
                echo -e "    ${YELLOW}$title${NC}"
            fi

            # Show if patch exists
            if [ -f "$dir/changes.patch" ]; then
                echo -e "    ${GREEN}✓ Git patch available${NC}"
            fi
            echo ""
        fi
    done

    if [ ${#projects[@]} -eq 0 ]; then
        echo -e "${YELLOW}No staged changes found.${NC}"
        exit 0
    fi

    echo ""
    read -p "Which project to apply? (or 'quit'): " PROJECT_NAME

    if [ "$PROJECT_NAME" = "quit" ] || [ -z "$PROJECT_NAME" ]; then
        echo "Cancelled."
        exit 0
    fi
fi

STAGING_DIR="$STAGING_BASE/$PROJECT_NAME"

# Validate staging directory
if [ ! -d "$STAGING_DIR" ]; then
    echo -e "${RED}Error: Staging directory not found: $STAGING_DIR${NC}"
    echo ""
    echo "Available projects:"
    ls -1 "$STAGING_BASE" 2>/dev/null || echo "(none)"
    exit 1
fi

# Show what's in this staging directory
echo -e "${BLUE}=== $PROJECT_NAME ===${NC}"
echo ""

if [ -f "$STAGING_DIR/CHANGES.md" ]; then
    cat "$STAGING_DIR/CHANGES.md"
    echo ""
fi

# Auto-detect target repo if not specified
if [ -z "$TARGET_REPO" ]; then
    # Try to detect from CHANGES.md
    if [ -f "$STAGING_DIR/CHANGES.md" ]; then
        detected=$(grep -oP "(?<=~/khan/)[a-zA-Z0-9_-]+" "$STAGING_DIR/CHANGES.md" 2>/dev/null | head -1)
        if [ -n "$detected" ] && [ -d "$HOME/khan/$detected" ]; then
            TARGET_REPO="$HOME/khan/$detected"
            echo -e "${GREEN}Auto-detected target: $TARGET_REPO${NC}"
        fi
    fi

    # Default to james-in-a-box
    if [ -z "$TARGET_REPO" ]; then
        TARGET_REPO="$HOME/khan/james-in-a-box"
        echo -e "${YELLOW}Using default target: $TARGET_REPO${NC}"
    fi

    echo ""
    read -p "Continue with this target? (yes/no/specify): " response

    case "$response" in
        yes|y|Y)
            # Continue
            ;;
        no|n|N)
            echo "Cancelled."
            exit 0
            ;;
        *)
            # User wants to specify
            TARGET_REPO="$response"
            # Expand ~ if needed
            TARGET_REPO="${TARGET_REPO/#\~/$HOME}"
            ;;
    esac
fi

# Validate target repo
if [ ! -d "$TARGET_REPO" ]; then
    echo -e "${RED}Error: Target repository not found: $TARGET_REPO${NC}"
    exit 1
fi

echo ""
echo -e "${BLUE}Applying changes to: $TARGET_REPO${NC}"
echo ""

# Check if merge-from-claude.sh exists
MERGE_TOOL="$HOME/.jib-tools/merge-from-claude.sh"

if [ -f "$MERGE_TOOL" ]; then
    # Use the merge tool (it handles git patch, manifest, sync automatically)
    "$MERGE_TOOL" "$PROJECT_NAME" "$TARGET_REPO"
    exit_code=$?

    if [ $exit_code -eq 0 ]; then
        echo ""
        echo -e "${GREEN}✅ Changes applied successfully!${NC}"
        echo ""

        # Offer to commit
        cd "$TARGET_REPO"

        if git diff --quiet && git diff --cached --quiet; then
            echo -e "${YELLOW}No changes to commit (files may already match).${NC}"
        else
            echo "=== Review Changes ==="
            git status
            echo ""
            git diff --stat
            echo ""

            read -p "Commit these changes? (yes/no): " commit_response

            if [ "$commit_response" = "yes" ] || [ "$commit_response" = "y" ]; then
                # Build commit message from CHANGES.md
                COMMIT_MSG="Changes from $PROJECT_NAME"

                if [ -f "$STAGING_DIR/CHANGES.md" ]; then
                    TITLE=$(head -1 "$STAGING_DIR/CHANGES.md" | sed 's/^# //')
                    SUMMARY=$(sed -n '/## Overview/,/##/p' "$STAGING_DIR/CHANGES.md" | grep -v "^##" | sed '/^$/d' | head -5)

                    if [ -n "$TITLE" ]; then
                        COMMIT_MSG="$TITLE"
                        if [ -n "$SUMMARY" ]; then
                            COMMIT_MSG=$(cat <<EOF
$TITLE

$SUMMARY
EOF
)
                        fi
                    fi
                fi

                # Add attribution
                COMMIT_MSG=$(cat <<EOF
$COMMIT_MSG

🤖 Generated with [Claude Code](https://claude.com/claude-code)

Co-Authored-By: Claude <noreply@anthropic.com>
EOF
)

                git add -A
                git commit -m "$COMMIT_MSG"

                echo ""
                echo -e "${GREEN}✅ Committed:${NC}"
                git log -1 --oneline
            else
                echo ""
                echo "Changes applied but not committed."
                echo "To commit later:"
                echo "  cd $TARGET_REPO"
                echo "  git add -A && git commit"
                echo ""
                echo "To revert:"
                echo "  cd $TARGET_REPO && git checkout -- ."
            fi
        fi

        # Archive the staging directory
        TIMESTAMP=$(date +%Y%m%d-%H%M%S)
        ARCHIVE_DIR="$HOME/.jib-sharing/staged-archive/$TIMESTAMP"
        mkdir -p "$ARCHIVE_DIR"
        mv "$STAGING_DIR" "$ARCHIVE_DIR/"

        echo ""
        echo -e "${BLUE}📦 Archived to: $ARCHIVE_DIR/$(basename $STAGING_DIR)${NC}"

    else
        echo ""
        echo -e "${RED}❌ Failed to apply changes (exit code: $exit_code)${NC}"
        exit 1
    fi
else
    # Fallback: Direct git patch application
    echo -e "${YELLOW}Merge tool not found, trying direct git patch...${NC}"
    echo ""

    PATCH_FILE="$STAGING_DIR/changes.patch"

    if [ ! -f "$PATCH_FILE" ]; then
        echo -e "${RED}Error: No git patch found at: $PATCH_FILE${NC}"
        echo ""
        echo "Manual copy required:"
        echo "  cp -r $STAGING_DIR/* $TARGET_REPO/"
        exit 1
    fi

    cd "$TARGET_REPO"

    echo "Checking patch..."
    if git apply --check "$PATCH_FILE" 2>&1; then
        echo ""
        echo "Applying patch..."
        git apply "$PATCH_FILE"

        echo ""
        echo -e "${GREEN}✅ Patch applied successfully!${NC}"
        echo ""
        git status
    else
        echo ""
        echo -e "${RED}❌ Patch check failed.${NC}"
        echo ""
        echo "Try manual merge:"
        echo "  cd $TARGET_REPO"
        echo "  git apply --3way $PATCH_FILE"
        exit 1
    fi
fi
