#!/usr/bin/env python3
"""
GitHub Watcher Dispatcher - Orchestrates all three services.

This dispatcher runs on a timer (via systemd) and sequentially executes:
1. CI/Conflict Fixer - Fix check failures and merge conflicts
2. Comment Responder - Respond to comments on PRs
3. PR Reviewer - Review PRs where jib is requested

Each service is imported and run directly (not as a subprocess) to share
configuration and state efficiently.

Usage:
    python3 dispatcher.py [--service SERVICE]

Options:
    --service SERVICE  Run only the specified service (comment-responder, pr-reviewer, ci-fixer)
                       If not specified, runs all three services.
"""

import argparse
import sys
from pathlib import Path

_project_root = Path(__file__).parent.parent.parent.parent
sys.path.insert(0, str(_project_root / "shared"))
sys.path.insert(0, str(_project_root))

from jib_logging import get_logger

logger = get_logger("github-watcher-dispatcher")


def run_all_services() -> int:
    """Run all three services sequentially."""
    from gwlib.github_api import check_gh_auth
    from gwlib.state import utc_now_iso

    current_run_start = utc_now_iso()
    logger.info("GitHub Watcher Dispatcher starting", utc_time=current_run_start)

    if not check_gh_auth():
        logger.error("Exiting due to missing gh authentication")
        return 1

    exit_code = 0

    # Run CI/Conflict Fixer first (highest priority - unblock PRs)
    logger.info("Running CI/Conflict Fixer")
    try:
        from ci_fixer import main as ci_fixer_main
        result = ci_fixer_main()
        if result != 0:
            logger.warning("CI/Conflict Fixer returned non-zero", exit_code=result)
            exit_code = result
    except Exception as e:
        logger.error("CI/Conflict Fixer failed", error=str(e))
        exit_code = 1

    # Run Comment Responder (respond to feedback)
    logger.info("Running Comment Responder")
    try:
        from comment_responder import main as comment_responder_main
        result = comment_responder_main()
        if result != 0:
            logger.warning("Comment Responder returned non-zero", exit_code=result)
            exit_code = result
    except Exception as e:
        logger.error("Comment Responder failed", error=str(e))
        exit_code = 1

    # Run PR Reviewer (review PRs)
    logger.info("Running PR Reviewer")
    try:
        from pr_reviewer import main as pr_reviewer_main
        result = pr_reviewer_main()
        if result != 0:
            logger.warning("PR Reviewer returned non-zero", exit_code=result)
            exit_code = result
    except Exception as e:
        logger.error("PR Reviewer failed", error=str(e))
        exit_code = 1

    logger.info("GitHub Watcher Dispatcher completed", overall_exit_code=exit_code)
    return exit_code


def main() -> int:
    """Main entry point."""
    parser = argparse.ArgumentParser(description="GitHub Watcher Dispatcher")
    parser.add_argument(
        "--service",
        choices=["comment-responder", "pr-reviewer", "ci-fixer"],
        help="Run only the specified service",
    )
    args = parser.parse_args()

    if args.service:
        # Run single service
        if args.service == "ci-fixer":
            from ci_fixer import main as service_main
        elif args.service == "comment-responder":
            from comment_responder import main as service_main
        elif args.service == "pr-reviewer":
            from pr_reviewer import main as service_main
        return service_main()
    else:
        # Run all services
        return run_all_services()


if __name__ == "__main__":
    sys.exit(main())
