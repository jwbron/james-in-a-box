#!/bin/bash
# Worktree Watcher - Cleans up orphaned git worktrees from stopped/crashed containers
# Runs periodically via systemd timer to prevent worktree accumulation

# Don't use set -e - we want to continue even if some cleanups fail
set -u

WORKTREE_BASE="$HOME/.jib-worktrees"
LOCAL_OBJECTS_BASE="$HOME/.jib-local-objects"
LOG_PREFIX="[$(date '+%Y-%m-%d %H:%M:%S')]"

log() {
    echo "$LOG_PREFIX $1"
}

cleanup_orphaned_worktrees() {
    log "Starting worktree cleanup check..."

    # Check if worktree directory exists
    if [ ! -d "$WORKTREE_BASE" ]; then
        log "No worktrees directory found at $WORKTREE_BASE"
        return 0
    fi

    local total_checked=0
    local total_cleaned=0

    # Iterate through container worktree directories
    for container_dir in "$WORKTREE_BASE"/jib-*; do
        # Skip if no directories match
        if [ ! -d "$container_dir" ]; then
            continue
        fi

        total_checked=$((total_checked + 1))
        container_id=$(basename "$container_dir")

        # Check if container is still running or exists
        if docker ps -a --format '{{.Names}}' 2>/dev/null | grep -q "^${container_id}$"; then
            log "Container $container_id still exists, keeping worktree"
            continue
        fi

        # Container doesn't exist - clean up worktree
        log "Orphaned worktree found: $container_id"

        # Remove all worktrees for this container
        local worktrees_removed=0
        for worktree in "$container_dir"/*; do
            if [ ! -d "$worktree" ]; then
                continue
            fi

            repo_name=$(basename "$worktree")
            original_repo="$HOME/repos/$repo_name"

            if [ -d "$original_repo/.git" ]; then
                log "  Removing worktree: $repo_name"
                cd "$original_repo"

                # Remove worktree (suppress errors if already gone)
                if git worktree remove "$worktree" --force 2>/dev/null; then
                    worktrees_removed=$((worktrees_removed + 1))
                else
                    log "  Warning: Could not remove worktree $worktree (may already be removed)"
                fi
            fi
        done

        # Remove container directory (best effort - some files may be owned by root/docker)
        log "  Removing directory: $container_dir"
        if rm -rf "$container_dir" 2>/dev/null; then
            log "  Successfully removed directory"
        else
            log "  Warning: Could not remove all files (permission denied on some files)"
            log "  Manual cleanup may be needed: rm -rf $container_dir"
        fi

        # Remove container's local objects directory (worktree isolation)
        local local_objects_dir="$LOCAL_OBJECTS_BASE/$container_id"
        if [ -d "$local_objects_dir" ]; then
            log "  Removing local objects: $local_objects_dir"
            if rm -rf "$local_objects_dir" 2>/dev/null; then
                log "  Successfully removed local objects"
            else
                log "  Warning: Could not remove local objects directory"
            fi
        fi

        total_cleaned=$((total_cleaned + 1))
        log "  Cleaned up $worktrees_removed worktree(s) for container $container_id"
    done

    log "Cleanup complete: checked $total_checked container(s), cleaned $total_cleaned orphaned worktree(s)"
}

prune_stale_worktree_references() {
    log "Pruning stale worktree references..."

    # Prune worktree references in all khan repos
    local repos_pruned=0
    for repo in "$HOME/khan"/*; do
        if [ ! -d "$repo/.git" ]; then
            continue
        fi

        repo_name=$(basename "$repo")
        cd "$repo"

        # Prune stale worktree references (ignore errors)
        local prune_output
        prune_output=$(git worktree prune -v 2>&1 || true)
        if echo "$prune_output" | grep -q "Removing"; then
            log "  Pruned stale references in $repo_name"
            repos_pruned=$((repos_pruned + 1))
        fi
    done

    if [ $repos_pruned -gt 0 ]; then
        log "Pruned stale references in $repos_pruned repo(s)"
    else
        log "No stale references found"
    fi
}

cleanup_orphaned_branches() {
    log "Checking for orphaned jib-temp/jib-exec branches..."

    local total_branches_deleted=0
    local total_branches_skipped=0

    # Iterate through all repos in ~/repos/
    for repo in "$HOME/khan"/*; do
        if [ ! -d "$repo/.git" ]; then
            continue
        fi

        repo_name=$(basename "$repo")
        cd "$repo"

        # Detect the default branch (main, master, etc.)
        local default_branch
        default_branch=$(git symbolic-ref refs/remotes/origin/HEAD 2>/dev/null | sed 's@^refs/remotes/origin/@@')
        if [ -z "$default_branch" ]; then
            # Fallback: try to get from remote
            default_branch=$(git remote show origin 2>/dev/null | grep "HEAD branch" | sed 's/.*: //')
        fi
        if [ -z "$default_branch" ]; then
            # Final fallback
            default_branch="main"
        fi

        # Get GitHub remote owner/repo for PR checks
        local remote_url
        remote_url=$(git remote get-url origin 2>/dev/null || echo "")
        local github_repo=""
        if [[ "$remote_url" =~ github\.com[:/]([^/]+/[^/.]+) ]]; then
            github_repo="${BASH_REMATCH[1]}"
            # Remove .git suffix if present
            github_repo="${github_repo%.git}"
        fi

        # Find all jib-temp-* and jib-exec-* branches
        local branches
        branches=$(git branch --list 'jib-temp-*' 'jib-exec-*' 2>/dev/null | sed 's/^[* ]*//')

        if [ -z "$branches" ]; then
            continue
        fi

        local repo_branches_deleted=0

        # OPTIMIZATION: Fetch all open PRs once per repo instead of per-branch
        # This reduces N API calls (one per branch) to 1 per repo
        local all_open_prs=""
        if [ -n "$github_repo" ] && command -v gh &>/dev/null; then
            all_open_prs=$(gh pr list --repo "$github_repo" --state open --json number,headRefName 2>/dev/null || echo "[]")
        fi

        # Check each branch
        while IFS= read -r branch; do
            if [ -z "$branch" ]; then
                continue
            fi

            # Extract container ID from branch name
            # Branch format: jib-temp-{container_id} or jib-exec-{container_id}
            # Container ID format: jib-YYYYMMDD-HHMMSS-PID or jib-exec-YYYYMMDD-HHMMSS-PID
            local container_id=""
            if [[ "$branch" == jib-temp-* ]]; then
                container_id=$(echo "$branch" | sed 's/^jib-temp-//')
            elif [[ "$branch" == jib-exec-* ]]; then
                # jib-exec branches use the branch name as container ID
                container_id="$branch"
            fi

            # Skip if we couldn't extract a container ID (shouldn't happen given the branch filter)
            if [ -z "$container_id" ]; then
                log "  Warning: Could not extract container ID from branch: $branch"
                continue
            fi

            # Check if container still exists
            if docker ps -a --format '{{.Names}}' 2>/dev/null | grep -q "^${container_id}$"; then
                # Container exists, keep the branch
                continue
            fi

            # Check if worktree directory still exists (means container may still be active)
            local worktree_dir="$HOME/.jib-worktrees/$container_id"
            if [ -d "$worktree_dir" ]; then
                # Worktree exists, keep the branch (worktree cleanup will happen first)
                continue
            fi

            # Check if branch has truly unique commits not in the default branch
            # Use git cherry to find commits that haven't been cherry-picked or merged
            local unmerged_commits=0
            if git rev-parse --verify "origin/$default_branch" &>/dev/null; then
                # Count commits with '+' prefix (truly unique, not cherry-picked)
                unmerged_commits=$(git cherry "origin/$default_branch" "$branch" 2>/dev/null | grep -c '^+' || echo "0")
            elif git rev-parse --verify "$default_branch" &>/dev/null; then
                unmerged_commits=$(git cherry "$default_branch" "$branch" 2>/dev/null | grep -c '^+' || echo "0")
            fi
            # Ensure unmerged_commits is a number (handle potential multi-line issues)
            unmerged_commits=$(echo "$unmerged_commits" | tr -d '[:space:]' | head -1)
            unmerged_commits=${unmerged_commits:-0}

            # Check if branch has an open PR in GitHub (using cached PR list)
            local has_open_pr=false
            if [ -n "$all_open_prs" ] && [ "$all_open_prs" != "[]" ]; then
                # Check if this branch name appears in the cached PR list
                if echo "$all_open_prs" | grep -q "\"headRefName\":\"$branch\""; then
                    has_open_pr=true
                fi
            fi

            # Only delete if: (no unmerged changes) OR (has an open PR)
            # - No unmerged changes: nothing to lose, all work is in main
            # - Has open PR: work is tracked and visible in GitHub
            if [ "$unmerged_commits" -gt 0 ] && [ "$has_open_pr" = false ]; then
                log "  Keeping branch $branch in $repo_name: has $unmerged_commits unmerged commit(s) and no open PR"
                total_branches_skipped=$((total_branches_skipped + 1))
                continue
            fi

            # Safe to delete: either no unique changes or has an open PR tracking them
            local reason=""
            if [ "$unmerged_commits" -eq 0 ]; then
                reason="no unmerged changes"
            else
                reason="has open PR"
            fi
            log "  Deleting orphaned branch in $repo_name: $branch ($reason)"
            if git branch -D "$branch" 2>/dev/null; then
                repo_branches_deleted=$((repo_branches_deleted + 1))
                total_branches_deleted=$((total_branches_deleted + 1))
            else
                log "  Warning: Could not delete branch $branch"
            fi
        done <<< "$branches"

        if [ $repo_branches_deleted -gt 0 ]; then
            log "  Deleted $repo_branches_deleted branch(es) in $repo_name"
        fi
    done

    if [ $total_branches_deleted -gt 0 ] || [ $total_branches_skipped -gt 0 ]; then
        log "Branch cleanup complete: deleted $total_branches_deleted, skipped $total_branches_skipped (have unmerged changes without PR)"
    else
        log "No orphaned branches found"
    fi
}

cleanup_orphaned_local_objects() {
    log "Checking for orphaned local objects directories..."

    # Check if local objects directory exists
    if [ ! -d "$LOCAL_OBJECTS_BASE" ]; then
        log "No local objects directory found at $LOCAL_OBJECTS_BASE"
        return 0
    fi

    local total_cleaned=0

    # Iterate through container local objects directories
    for objects_dir in "$LOCAL_OBJECTS_BASE"/jib-*; do
        # Skip if no directories match
        if [ ! -d "$objects_dir" ]; then
            continue
        fi

        container_id=$(basename "$objects_dir")

        # Check if container is still running or exists
        if docker ps -a --format '{{.Names}}' 2>/dev/null | grep -q "^${container_id}$"; then
            continue
        fi

        # Check if worktree still exists (container might still be cleaning up)
        if [ -d "$WORKTREE_BASE/$container_id" ]; then
            continue
        fi

        # Neither container nor worktree exists - safe to remove
        log "Orphaned local objects found: $container_id"
        if rm -rf "$objects_dir" 2>/dev/null; then
            log "  Removed local objects for $container_id"
            total_cleaned=$((total_cleaned + 1))
        else
            log "  Warning: Could not remove $objects_dir"
        fi
    done

    if [ $total_cleaned -gt 0 ]; then
        log "Cleaned up $total_cleaned orphaned local objects director(ies)"
    else
        log "No orphaned local objects directories found"
    fi
}

# Run cleanup
cleanup_orphaned_worktrees

# Clean up orphaned local objects
cleanup_orphaned_local_objects

# Prune stale references
prune_stale_worktree_references

# Clean up orphaned branches
cleanup_orphaned_branches

exit 0
