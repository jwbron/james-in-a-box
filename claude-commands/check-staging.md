# Check Staging - Review and Apply Staged Changes

You are reviewing staged changes and applying them using git patches.

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
        project_name=$(basename "$project")
        echo ""
        echo "=== $project_name ==="

        # Show CHANGES.md if it exists
        if [ -f "$project/CHANGES.md" ]; then
            cat "$project/CHANGES.md"
        elif [ -f "$project/STAGED-FILES-SUMMARY.md" ]; then
            cat "$project/STAGED-FILES-SUMMARY.md"
        else
            echo "Files:"
            find "$project" -type f -printf "  %P\n" | sort
        fi

        # Show patch stats if available
        if [ -f "$project/changes.patch" ]; then
            echo ""
            echo "📊 Patch Statistics:"
            cd ~/khan/james-in-a-box 2>/dev/null || cd ~/khan
            git apply --stat "$project/changes.patch" 2>/dev/null || echo "  (Patch file exists but stats unavailable)"
        fi
    fi
done
```

### 3. Ask User Which Projects to Apply

After showing summaries:

**"Which project(s) do you want to apply? (Enter project name, 'all', or 'none')"**

- If **'none'**: Stop and report "Staged changes left in place."
- If **'all'**: Apply all projects sequentially
- If **project name**: Apply just that project

### 4. Apply Changes Using Git Patch Workflow

For each project to apply:

```bash
PROJECT_NAME="<user-selected-project>"
STAGING_DIR=~/.jib-sharing/staged-changes/$PROJECT_NAME

# Determine target repository
# Default to james-in-a-box, but can be overridden
TARGET_REPO=~/khan/james-in-a-box

# Check for target hint in CHANGES.md
if [ -f "$STAGING_DIR/CHANGES.md" ]; then
    detected_repo=$(grep -oP "(?<=~/khan/)[a-zA-Z0-9_-]+" "$STAGING_DIR/CHANGES.md" 2>/dev/null | head -1)
    if [ -n "$detected_repo" ] && [ -d ~/khan/$detected_repo ]; then
        TARGET_REPO=~/khan/$detected_repo
    fi
fi

echo ""
echo "=== Applying: $PROJECT_NAME ==="
echo "Target: $TARGET_REPO"
echo ""

# Use the merge-from-claude.sh tool for automatic application
~/.jib-tools/merge-from-claude.sh "$PROJECT_NAME" "$TARGET_REPO"
```

The `merge-from-claude.sh` tool will automatically:
1. Try git patch if available (best option)
2. Check for MANIFEST.txt and use it if present
3. Fall back to file sync if needed

### 5. Review and Commit

After applying each project:

```bash
cd "$TARGET_REPO"

echo ""
echo "=== Review Changes ==="
git status
echo ""
git diff --stat
echo ""

# Ask user if they want to commit
read -p "Commit these changes? (yes/no): " response

if [ "$response" = "yes" ] || [ "$response" = "y" ]; then
    # Read commit message from CHANGES.md if available
    COMMIT_MSG="Changes from $PROJECT_NAME"
    if [ -f "$STAGING_DIR/CHANGES.md" ]; then
        # Extract title and summary
        TITLE=$(head -1 "$STAGING_DIR/CHANGES.md" | sed 's/^# //')
        SUMMARY=$(sed -n '/## Overview/,/##/p' "$STAGING_DIR/CHANGES.md" | grep -v "^##" | sed '/^$/d' | head -5)

        if [ -n "$TITLE" ]; then
            COMMIT_MSG="$TITLE"
            if [ -n "$SUMMARY" ]; then
                COMMIT_MSG="$COMMIT_MSG

$SUMMARY"
            fi
        fi
    fi

    # Add Claude attribution
    COMMIT_MSG="$COMMIT_MSG

🤖 Generated with [Claude Code](https://claude.com/claude-code)

Co-Authored-By: Claude <noreply@anthropic.com>"

    # Commit
    git add -A
    git commit -m "$COMMIT_MSG"

    echo ""
    echo "✅ Committed:"
    git log -1 --stat
else
    echo "Changes not committed. To revert:"
    echo "  cd $TARGET_REPO && git checkout -- ."
fi
```

### 6. Archive Applied Changes

After successfully applying (whether committed or not):

```bash
TIMESTAMP=$(date +%Y%m%d-%H%M%S)
ARCHIVE_DIR=~/.jib-sharing/staged-archive/$TIMESTAMP

mkdir -p "$ARCHIVE_DIR"
mv "$STAGING_DIR" "$ARCHIVE_DIR/"

echo ""
echo "✅ Archived to: $ARCHIVE_DIR/$(basename $STAGING_DIR)"
```

### 7. Summary

After processing all selected projects:

```bash
echo ""
echo "=== Summary ==="
echo "Applied and archived staged changes"
echo ""
echo "Archive location: ~/.jib-sharing/staged-archive/"
echo ""

# Show remaining staged changes if any
remaining=$(ls -1 ~/.jib-sharing/staged-changes/ 2>/dev/null | wc -l)
if [ $remaining -gt 0 ]; then
    echo "Remaining staged changes: $remaining"
    ls -1 ~/.jib-sharing/staged-changes/
else
    echo "No remaining staged changes"
fi
```

## Error Handling

### If git patch fails

```bash
# merge-from-claude.sh automatically falls back to sync
# But if you need to manually handle it:

echo "Git patch failed. Trying sync approach..."
~/.jib-tools/sync-staging.sh "$PROJECT_NAME" "$TARGET_REPO"
```

### If target repo is unclear

```bash
echo "Could not determine target repository."
echo ""
echo "Available repos:"
ls -1 ~/khan/
echo ""
read -p "Enter target repo name: " repo_name
TARGET_REPO=~/khan/$repo_name
```

### If merge conflicts

```bash
echo "Merge conflicts detected."
echo ""
echo "Options:"
echo "1. Manually resolve conflicts in $TARGET_REPO"
echo "2. Skip this project and continue"
echo "3. Abort entire operation"
echo ""
read -p "Choose (1/2/3): " choice

case $choice in
    1)
        echo "Opening in editor for manual resolution..."
        # User handles manually
        ;;
    2)
        echo "Skipping $PROJECT_NAME"
        git checkout -- .  # Revert changes
        ;;
    3)
        echo "Aborting"
        git checkout -- .  # Revert changes
        exit 1
        ;;
esac
```

## Important Notes

- **Git patch preferred**: Uses git patches for clean, reviewable merges
- **CHANGES.md required**: Should document what changed and why
- **Archive, don't delete**: Staged changes moved to archive for reference
- **Review before commit**: Always show diffs before committing
- **Automatic fallback**: Falls back to file sync if git patch unavailable

## Example Session

```
=== Staged Changes ===
slack-notifier-fix
api-improvements

=== slack-notifier-fix ===
# Fix: Slack Notifier Polling Interval

## Overview
Reduced polling interval from 60s to 30s for faster notifications.

## Files Modified
- scripts/slack-notifier.py

📊 Patch Statistics:
scripts/slack-notifier.py | 2 +-
1 file changed, 1 insertion(+), 1 deletion(-)

=== api-improvements ===
# Feature: Add rate limiting to API endpoints

[etc...]

Which project(s) do you want to apply? slack-notifier-fix

=== Applying: slack-notifier-fix ===
Target: ~/khan/james-in-a-box

✓ Found git patch - using git approach

Checking patch...

Applying patch...

✅ Patch applied successfully!

On branch main
Changes not staged for commit:
  modified:   scripts/slack-notifier.py

=== Review Changes ===
On branch main
Changes not staged for commit:
  modified:   scripts/slack-notifier.py

 scripts/slack-notifier.py | 2 +-
 1 file changed, 1 insertion(+), 1 deletion(-)

Commit these changes? yes

✅ Committed:
[abc1234] Fix: Slack Notifier Polling Interval
 1 file changed, 1 insertion(+), 1 deletion(-)

✅ Archived to: ~/.jib-sharing/staged-archive/20251122-143000/slack-notifier-fix

=== Summary ===
Applied and archived staged changes

Archive location: ~/.jib-sharing/staged-archive/

Remaining staged changes: 1
api-improvements
```

## Quick Reference

**One-liner to apply specific project:**
```bash
~/.jib-tools/merge-from-claude.sh <project-name> ~/khan/<repo>
```

**Check what would be applied:**
```bash
cd ~/khan/<repo>
git apply --stat ~/.jib-sharing/staged-changes/<project>/changes.patch
git apply --check ~/.jib-sharing/staged-changes/<project>/changes.patch
```

**Manual revert if needed:**
```bash
cd ~/khan/<repo>
git checkout -- .
```
