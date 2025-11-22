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
TIMESTAMP=$(date +%Y%m%d-%H%M%S)
ARCHIVE_DIR=~/.jib-sharing/staged-archive/$TIMESTAMP
mkdir -p "$ARCHIVE_DIR"
mv ~/.jib-sharing/staged-changes/* "$ARCHIVE_DIR/"

echo "Archived to: $ARCHIVE_DIR"
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

# Copy files (excluding documentation files - those are for reference only)
echo "Copying from $SOURCE_DIR to $TARGET_DIR"

for file in $(find "$SOURCE_DIR" -type f ! -name "CHANGES.md" ! -name "STAGED-FILES-SUMMARY.md"); do
    REL_PATH=${file#$SOURCE_DIR/}
    TARGET_FILE="$TARGET_DIR/$REL_PATH"

    # Create parent directory if needed
    mkdir -p "$(dirname "$TARGET_FILE")"

    # Copy file
    cp -v "$file" "$TARGET_FILE"
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
cd "$HOME/khan/$PROJECT_NAME"

# Stage all changes
git add -A

# Create commit using CHANGES.md content
# Extract summary from CHANGES.md and create detailed commit message
git commit -m "$(cat <<'EOF'
[Title from CHANGES.md]

[Content from CHANGES.md formatted as commit message]

🤖 Generated with [Claude Code](https://claude.com/claude-code)

Co-Authored-By: Claude <noreply@anthropic.com>
EOF
)"

# Show commit
git log -1 --stat
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
