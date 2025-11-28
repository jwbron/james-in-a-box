#!/bin/bash
# Create pull request using jib to generate description
# This runs on the host machine but uses jib container for LLM operations

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && cd ../.. && pwd)"
LOG_FILE="$HOME/.config/jib-notifier/remote-control.log"

# Logging
log() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] $1" | tee -a "$LOG_FILE"
}

# Send notification back to user
notify() {
    local notification_dir="$HOME/.jib-sharing/notifications"
    mkdir -p "$notification_dir"

    local timestamp
    timestamp=$(date +%Y%m%d-%H%M%S)
    local notification_file="$notification_dir/${timestamp}-pr-result.md"

    cat > "$notification_file" <<EOF
# 🔀 Pull Request

$1

---
Created at: $(date)
EOF

    log "Notification sent: $notification_file"
}

# Get default branch for a repo
get_default_branch() {
    local repo_path=$1
    local repo_name
    repo_name=$(basename "$repo_path")

    # Special cases: webapp and frontend use development branches
    case "$repo_name" in
        webapp)
            echo "master"  # webapp typically uses master as development branch
            ;;
        frontend)
            echo "main"  # frontend typically uses main
            ;;
        *)
            # Try to detect default branch from origin
            cd "$repo_path"
            local default
            default=$(git symbolic-ref refs/remotes/origin/HEAD 2>/dev/null | sed 's@^refs/remotes/origin/@@')
            if [ -z "$default" ]; then
                # Fallback: check if main or master exists
                if git rev-parse --verify main >/dev/null 2>&1; then
                    echo "main"
                elif git rev-parse --verify master >/dev/null 2>&1; then
                    echo "master"
                else
                    echo "main"  # Final fallback
                fi
            else
                echo "$default"
            fi
            ;;
    esac
}

# Main PR creation logic
create_pr() {
    local repo_name=$1
    local draft=${2:-true}

    log "Creating PR for repo: ${repo_name:-current}"

    # Determine repo path
    local repo_path
    if [ -z "$repo_name" ] || [ "$repo_name" = "james-in-a-box" ]; then
        repo_path="$SCRIPT_DIR"
        repo_name="james-in-a-box"
    else
        repo_path="$HOME/khan/$repo_name"
        if [ ! -d "$repo_path" ]; then
            notify "❌ Repository not found: $repo_path

Available repos in ~/khan/:
$(ls -1 ~/khan/ | grep -v '^\.' | head -10)"
            return 1
        fi
    fi

    cd "$repo_path"
    log "Working in: $repo_path"

    # Check if in a git repo
    if ! git rev-parse --git-dir > /dev/null 2>&1; then
        notify "❌ Not a git repository: $repo_path"
        return 1
    fi

    # Get current branch
    local current_branch
    current_branch=$(git branch --show-current)
    if [ -z "$current_branch" ]; then
        notify "❌ Not on a branch (detached HEAD state)"
        return 1
    fi

    # Get default branch
    local base_branch
    base_branch=$(get_default_branch "$repo_path")
    log "Current branch: $current_branch"
    log "Base branch: $base_branch"

    # Check if current branch is same as base
    if [ "$current_branch" = "$base_branch" ]; then
        notify "❌ Cannot create PR from base branch ($base_branch)

Create a feature branch first:
\`\`\`bash
cd $repo_path
git checkout -b feature/your-feature-name
\`\`\`"
        return 1
    fi

    # Check if there are commits ahead of base
    local commits_ahead
    commits_ahead=$(git rev-list --count "$base_branch..$current_branch" 2>/dev/null || echo "0")
    if [ "$commits_ahead" = "0" ]; then
        notify "❌ No commits to create PR from

Current branch '$current_branch' has no commits ahead of '$base_branch'"
        return 1
    fi

    log "Branch has $commits_ahead commits ahead of $base_branch"

    # Generate PR description using jib
    log "Generating PR description using jib..."

    local pr_desc_file="/tmp/pr-description-$$.md"

    # Create prompt for Claude in jib
    local prompt_file="/tmp/pr-prompt-$$.txt"
    cat > "$prompt_file" <<'PROMPT'
Generate a pull request description for the current branch.

Requirements:
- Use the Khan Academy commit template format
- Be concise but provide appropriate context for reviewers
- Include one-line summary, full summary, issue link, and test plan
- Focus on what changed and why, not implementation details
- Keep it under 500 words total

Format:
```
<one-line summary>

<full summary - 2-3 paragraphs explaining what changed and why>

Issue: <JIRA link or "none">

Test plan:
- How you tested this change
- What reviewers should verify
```

Analyze the git diff and recent commits to understand what changed.
PROMPT

    # Execute in jib container to generate description
    # Use docker exec instead of jib --exec for simpler invocation
    if docker ps | grep -q jib-claude; then
        # Container is running, use it
        log "Using running jib container to generate PR description"

        # Run Claude Code in container to generate description
        docker exec jib-claude bash -c "
            cd ~/khan/$repo_name 2>/dev/null || cd ~/khan/james-in-a-box

            # Get git diff and commits
            DIFF=\$(git diff $base_branch...HEAD)
            COMMITS=\$(git log $base_branch..HEAD --oneline)

            # Use claude code to generate description
            echo 'Generate a concise PR description following Khan Academy format.

Commits:
\$COMMITS

Changes (abbreviated):
\$(echo \"\$DIFF\" | head -100)

Format:
<one-line summary>

<2-3 paragraph explanation>

Issue: <link or none>

Test plan:
- Testing steps' | claude --dangerously-skip-permissions --no-auto-update
        " > "$pr_desc_file" 2>&1

        if [ $? -eq 0 ] && [ -s "$pr_desc_file" ]; then
            log "PR description generated successfully"
        else
            log "Failed to generate PR description, using template"
            # Use template as fallback
            cat > "$pr_desc_file" <<EOF
$(git log -1 --pretty=%B)

## Changes

$(git diff --stat $base_branch...HEAD | head -20)

Issue: none

Test plan:
- Review the changes
- Run tests
EOF
        fi
    else
        log "jib container not running, using simple template"
        # Container not running, use simple template
        cat > "$pr_desc_file" <<EOF
$(git log -1 --pretty=%B)

## Changes

$(git diff --stat $base_branch...HEAD | head -20)

Issue: none

Test plan:
- Review the changes
- Run tests
EOF
    fi

    # Clean up temporary files
    rm -f "$prompt_file"

    # Check if gh CLI is available
    if ! command -v gh &> /dev/null; then
        notify "❌ GitHub CLI (gh) not installed

Install with: brew install gh
Or: sudo apt install gh"
        rm -f "$pr_desc_file"
        return 1
    fi

    # Check if authenticated
    if ! gh auth status &> /dev/null; then
        notify "❌ Not authenticated with GitHub

Run: gh auth login"
        rm -f "$pr_desc_file"
        return 1
    fi

    # Push branch to remote
    log "Pushing branch to remote..."
    if ! git push -u origin "$current_branch" 2>&1; then
        notify "❌ Failed to push branch to remote

Check that you have push permissions and the remote is configured correctly."
        rm -f "$pr_desc_file"
        return 1
    fi

    # Create PR
    log "Creating pull request..."
    local draft_flag=""
    if [ "$draft" = "true" ]; then
        draft_flag="--draft"
    fi

    local pr_url
    if pr_url=$(gh pr create \
        --base "$base_branch" \
        --head "$current_branch" \
        --body-file "$pr_desc_file" \
        $draft_flag 2>&1); then

        log "PR created successfully: $pr_url"

        # Get PR description for notification
        local pr_desc
        pr_desc=$(head -20 "$pr_desc_file")

        notify "✅ Pull Request Created

**Repository**: $repo_name
**Source Branch**: \`$current_branch\` (your changes)
**Target Branch**: \`$base_branch\` (merging into)
**Status**: ${draft:+Draft }PR
**Commits**: $commits_ahead commit(s)
**PR URL**: $pr_url

**Description Preview** (first 20 lines):
\`\`\`
$pr_desc
\`\`\`

View full PR: $pr_url"

        rm -f "$pr_desc_file"
        return 0
    else
        log "Failed to create PR: $pr_url"
        notify "❌ Failed to create pull request

Error:
\`\`\`
$pr_url
\`\`\`

Check:
- Branch is pushed to remote
- No existing PR for this branch
- You have repository access"
        rm -f "$pr_desc_file"
        return 1
    fi
}

# Parse arguments
repo_name=""
draft="true"

while [[ $# -gt 0 ]]; do
    case $1 in
        --ready)
            draft="false"
            shift
            ;;
        *)
            repo_name=$1
            shift
            ;;
    esac
done

# Execute
create_pr "$repo_name" "$draft"
