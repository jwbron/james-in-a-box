#!/usr/bin/env python3
"""
GitHub Check Monitor - One-shot analysis of PR check failures

Triggered by github-sync.service after syncing PR data.
Analyzes check failures and sends notifications.
"""

import sys
from pathlib import Path

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent))

from watcher import GitHubWatcher


def main():
    """Run one-shot check analysis."""
    print("🔍 GitHub Check Monitor - Analyzing PR check failures...")

    watcher = GitHubWatcher()

    # Run one check cycle
    watcher.watch()

    print("✅ Check analysis complete")
    return 0


if __name__ == '__main__':
    sys.exit(main())
