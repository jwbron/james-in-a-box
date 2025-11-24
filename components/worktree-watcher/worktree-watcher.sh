#!/bin/bash
# Worktree Watcher - Cleans up orphaned git worktrees from stopped/crashed containers
# Runs periodically via systemd timer to prevent worktree accumulation

# Don't use set -e - we want to continue even if some cleanups fail
set -u

WORKTREE_BASE="$HOME/.jib-worktrees"
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
            original_repo="$HOME/khan/$repo_name"

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

# Run cleanup
cleanup_orphaned_worktrees

# Prune stale references
prune_stale_worktree_references

exit 0
