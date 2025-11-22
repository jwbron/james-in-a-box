# Check Staging - Review and Pull Staged Changes

You are reviewing staged changes and optionally pulling them into the repository.

**IMPORTANT**: This command runs on the HOST machine, not in the container.

## Your Task

### 1. Check for Staged Changes

First, list what's in the staging directory:

```bash
echo "=== Staged Changes ==="
ls -la ~/.jib-sharing/staged-changes/
```

If empty, report: "No staged changes found" and exit.

### 2. Show Summary of Each Staged Project

For each project, show what's staged:

```bash
for project in ~/.jib-sharing/staged-changes/*/; do
    if [ -d "$project" ]; then
        echo ""
        echo "=== $(basename "$project") ==="

        # Show STAGED-FILES-SUMMARY.md if it exists
        if [ -f "$project/STAGED-FILES-SUMMARY.md" ]; then
            cat "$project/STAGED-FILES-SUMMARY.md"
        elif [ -f "$project/CHANGES.md" ]; then
            cat "$project/CHANGES.md"
        else
            echo "Files:"
            find "$project" -type f -printf "  %P\n" | sort
        fi
    fi
done
```

### 3. Ask User to Proceed

After showing the summaries, ask:

**"Do you want to pull these changes into the repository? (yes/no)"**

If user says **no**, stop here and report: "Staged changes left in place. Run `@check-staging` again when ready to apply them."

If user says **yes**, continue with the steps below:

---

## Applying Changes (Only if User Approved)

### 2. Archive Current Staging

Move everything to an archive directory with timestamp:

```bash
# SECURITY FIX: Use find with -exec to safely handle filenames
# This prevents globbing attacks from malicious filenames
TIMESTAMP=$(date +%Y%m%d-%H%M%S)
ARCHIVE_DIR=~/.jib-sharing/staged-archive/$TIMESTAMP

# ERROR HANDLING: Create directory and verify success
if ! mkdir -p "$ARCHIVE_DIR"; then
    echo "❌ Error: Failed to create archive directory"
    exit 1
fi

# SECURITY FIX: Move files safely without glob expansion
# Use find with -mindepth/-maxdepth to avoid recursion issues
if ! find ~/.jib-sharing/staged-changes/ -mindepth 1 -maxdepth 1 -exec mv -t "$ARCHIVE_DIR/" {} + 2>/dev/null; then
    # Fallback if -t flag not supported (BSD/macOS)
    find ~/.jib-sharing/staged-changes/ -mindepth 1 -maxdepth 1 -exec mv {} "$ARCHIVE_DIR/" \;
fi

echo "✅ Archived to: $ARCHIVE_DIR"
ls -la "$ARCHIVE_DIR"
```

### 3. Review Each Staged Project

For each subdirectory in the archive:

```bash
cd "$ARCHIVE_DIR"
for project in */; do
    echo "=== Reviewing: $project ==="

    # Check for CHANGES.md or STAGED-FILES-SUMMARY.md (required)
    if [ -f "$project/STAGED-FILES-SUMMARY.md" ]; then
        cat "$project/STAGED-FILES-SUMMARY.md"
    elif [ -f "$project/CHANGES.md" ]; then
        cat "$project/CHANGES.md"
    else
        echo "⚠️ WARNING: No CHANGES.md or STAGED-FILES-SUMMARY.md found in $project"
        echo "This is required documentation - please ask user how to proceed"
    fi

    # List all files
    echo ""
    echo "Files in $project:"
    find "$project" -type f -ls
    echo ""
done
```

### 4. Determine Target Location

For each project, determine where files should be copied:

- If project name is `james-in-a-box`, copy to `~/khan/james-in-a-box/`
- For other projects, ask the user for the target directory

### 5. Copy Files to Repository

For each project:

```bash
PROJECT_NAME="james-in-a-box"  # or whatever the project is
SOURCE_DIR="$ARCHIVE_DIR/$PROJECT_NAME"
TARGET_DIR="$HOME/khan/$PROJECT_NAME"

# ERROR HANDLING: Validate directories exist
if [ ! -d "$SOURCE_DIR" ]; then
    echo "❌ Error: Source directory not found: $SOURCE_DIR"
    exit 1
fi

if [ ! -d "$TARGET_DIR" ]; then
    echo "❌ Error: Target directory not found: $TARGET_DIR"
    exit 1
fi

# Copy files (excluding documentation files - those are for reference only)
echo "Copying from $SOURCE_DIR to $TARGET_DIR"

# SECURITY FIX: Use safer iteration method
find "$SOURCE_DIR" -type f ! -name "CHANGES.md" ! -name "STAGED-FILES-SUMMARY.md" -print0 | \
while IFS= read -r -d '' file; do
    REL_PATH="${file#$SOURCE_DIR/}"
    TARGET_FILE="$TARGET_DIR/$REL_PATH"

    # ERROR HANDLING: Create parent directory and check success
    if ! mkdir -p "$(dirname "$TARGET_FILE")"; then
        echo "❌ Error: Failed to create directory for $TARGET_FILE"
        continue
    fi

    # ERROR HANDLING: Copy file and verify
    if cp -v "$file" "$TARGET_FILE"; then
        echo "  ✅ Copied: $REL_PATH"
    else
        echo "  ❌ Failed to copy: $REL_PATH"
    fi
done
```

### 6. Git Status Check

Show what changed:

```bash
cd "$HOME/khan/$PROJECT_NAME"
git status
git diff --stat
```

### 7. Review and Commit

Present the CHANGES.md content to the user and ask:
- "Review the changes above. Should I commit these to git?"
- If yes, use CHANGES.md to create a comprehensive commit message
- If no, explain how to revert: `git checkout -- .`

### 8. Commit Changes

If user approves:

```bash
cd "$HOME/khan/$PROJECT_NAME" || exit 1

# ERROR HANDLING: Check if there are changes to commit
if ! git diff --quiet || ! git diff --cached --quiet; then
    # Stage all changes
    if ! git add -A; then
        echo "❌ Error: Failed to stage changes"
        exit 1
    fi

    # SECURITY FIX: Use git commit -F instead of embedding content in heredoc
    # This safely reads the CHANGES.md file without command injection risks
    CHANGES_FILE="$ARCHIVE_DIR/$PROJECT_NAME/CHANGES.md"

    if [ -f "$CHANGES_FILE" ]; then
        # Create temporary commit message file
        COMMIT_MSG=$(mktemp)
        trap 'rm -f "$COMMIT_MSG"' EXIT

        # Add CHANGES.md content plus footer
        cat "$CHANGES_FILE" > "$COMMIT_MSG"
        echo "" >> "$COMMIT_MSG"
        echo "🤖 Generated with [Claude Code](https://claude.com/claude-code)" >> "$COMMIT_MSG"
        echo "" >> "$COMMIT_MSG"
        echo "Co-Authored-By: Claude <noreply@anthropic.com>" >> "$COMMIT_MSG"

        # Commit using file
        if git commit -F "$COMMIT_MSG"; then
            echo "✅ Changes committed"
            git log -1 --stat
        else
            echo "❌ Error: Failed to create commit"
            exit 1
        fi
    else
        echo "❌ Error: CHANGES.md not found, cannot create commit message"
        exit 1
    fi
else
    echo "ℹ️  No changes to commit"
fi
```

### 9. Summary

Provide a summary:
- What was staged
- Where it was copied
- Git commit hash (if committed)
- Archive location for reference: `~/.jib-sharing/staged-archive/$TIMESTAMP`

## Important Notes

- **CHANGES.md is required**: If missing, warn and ask user how to proceed
- **Archive, don't delete**: Always move to archive, never delete staged changes
- **Review before commit**: Always show the user what will be committed
- **Preserve structure**: Maintain directory structure when copying
- **Handle conflicts**: If files already exist, show diffs and ask user

## Example Output

```
=== Checking Staging Directory ===
Found staged changes in: james-in-a-box

=== Archiving ===
Archived to: ~/.jib-sharing/staged-archive/20251121-220000

=== Reviewing: james-in-a-box ===
[Display CHANGES.md content]

Files to copy:
- scripts/new-feature.py
- Dockerfile

=== Copying to Repository ===
Copied 2 files to ~/khan/james-in-a-box/

=== Git Status ===
2 files changed, 150 insertions(+), 20 deletions(-)

Review changes above. Should I commit these to git? [User responds]

=== Committed ===
[abc1234] Add new feature
2 files changed, 150 insertions(+), 20 deletions(-)

✅ Staged changes integrated successfully!
Archive available at: ~/.jib-sharing/staged-archive/20251121-220000
```

## Error Handling

- **No CHANGES.md**: Warn and ask user if they want to proceed anyway
- **Multiple projects**: Process one at a time, asking for confirmation each
- **Git conflicts**: Show conflicts and ask user how to resolve
- **Missing target**: Ask user where files should go
