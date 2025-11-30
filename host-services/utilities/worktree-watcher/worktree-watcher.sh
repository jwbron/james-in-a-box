#!/bin/bash
# Worktree Watcher - Cleans up orphaned container directories from stopped/crashed containers
# Runs periodically via systemd timer to prevent disk space accumulation
#
# With the isolated git approach:
# - Each container has its own isolated git directories in ~/.jib-worktrees/{container-id}/
# - No interaction with host's git repos (~/khan/) is needed
# - Cleanup is simple: just delete orphaned container directories
# - No git worktree remove, prune, or branch cleanup needed

# Don't use set -e - we want to continue even if some cleanups fail
set -u

WORKTREE_BASE="$HOME/.jib-worktrees"
LOG_PREFIX="[$(date '+%Y-%m-%d %H:%M:%S')]"

log() {
    echo "$LOG_PREFIX $1"
}

cleanup_orphaned_containers() {
    log "Starting container directory cleanup check..."

    # Check if worktree directory exists
    if [ ! -d "$WORKTREE_BASE" ]; then
        log "No container directory found at $WORKTREE_BASE"
        return 0
    fi

    local total_checked=0
    local total_cleaned=0
    local total_space_freed=0

    # Iterate through container directories
    for container_dir in "$WORKTREE_BASE"/jib-*; do
        # Skip if no directories match
        if [ ! -d "$container_dir" ]; then
            continue
        fi

        total_checked=$((total_checked + 1))
        container_id=$(basename "$container_dir")

        # Check if container is still running or exists
        if docker ps -a --format '{{.Names}}' 2>/dev/null | grep -q "^${container_id}$"; then
            log "Container $container_id still exists, keeping directory"
            continue
        fi

        # Container doesn't exist - clean up directory
        log "Orphaned container directory found: $container_id"

        # Calculate size before deletion
        local dir_size
        dir_size=$(du -sh "$container_dir" 2>/dev/null | cut -f1 || echo "unknown")

        # Remove container directory
        # This includes:
        # - Isolated .git-{repo} directories (container's own git state)
        # - Worktree directories (working copies)
        # No host git state is affected - complete isolation
        log "  Removing directory ($dir_size): $container_dir"
        if rm -rf "$container_dir" 2>/dev/null; then
            log "  Successfully removed directory"
            total_cleaned=$((total_cleaned + 1))
        else
            log "  Warning: Could not remove all files (permission denied on some files)"
            log "  Manual cleanup may be needed: rm -rf $container_dir"
        fi
    done

    log "Cleanup complete: checked $total_checked container(s), cleaned $total_cleaned orphaned directory(ies)"
}

# Run cleanup
cleanup_orphaned_containers

exit 0
