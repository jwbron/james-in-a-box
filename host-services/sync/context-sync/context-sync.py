#!/usr/bin/env python3
"""
Main sync orchestrator for context-sync.

Runs all configured connectors and syncs content to ~/context-sync/<connector-name>/
"""

import argparse
import logging
import sys
from datetime import datetime
from pathlib import Path

# Load environment variables from config location
from utils.config_loader import load_env_file


load_env_file()

# Import connectors
from connectors.confluence.connector import ConfluenceConnector
from connectors.jira.connector import JIRAConnector


# Configure root logger
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler(
            Path.home() / "context-sync" / "logs" / f"sync_{datetime.now().strftime('%Y%m%d')}.log"
        ),
    ],
)

logger = logging.getLogger("context-sync")


def get_all_connectors() -> list:
    """Get all available connectors.

    Returns:
        List of connector instances
    """
    connectors = []

    # Confluence connector
    try:
        connector = ConfluenceConnector()
        if connector.validate_config():
            connectors.append(connector)
        else:
            logger.warning("Confluence connector configuration invalid, skipping")
    except Exception as e:
        logger.error(f"Failed to initialize Confluence connector: {e}")

    # JIRA connector
    try:
        connector = JIRAConnector()
        if connector.validate_config():
            connectors.append(connector)
        else:
            logger.warning("JIRA connector configuration invalid, skipping")
    except Exception as e:
        logger.error(f"Failed to initialize JIRA connector: {e}")

    # Add more connectors here as they are implemented
    # Example:
    # try:
    #     connector = GitHubConnector()
    #     if connector.validate_config():
    #         connectors.append(connector)
    # except Exception as e:
    #     logger.error(f"Failed to initialize GitHub connector: {e}")

    return connectors


def sync_all_connectors(incremental: bool = True) -> dict:
    """Sync all configured connectors.

    Args:
        incremental: If True, only sync changed content

    Returns:
        Dictionary with sync results
    """
    results = {
        "started_at": datetime.now().isoformat(),
        "connectors": {},
        "total_files": 0,
        "total_size": 0,
        "success_count": 0,
        "failure_count": 0,
    }

    connectors = get_all_connectors()

    if not connectors:
        logger.warning("No connectors configured or available")
        return results

    logger.info(f"Running sync for {len(connectors)} connector(s)")

    for connector in connectors:
        logger.info(f"{'=' * 60}")
        logger.info(f"Syncing: {connector.name}")
        logger.info(f"{'=' * 60}")

        try:
            success = connector.sync(incremental=incremental)
            metadata = connector.get_sync_metadata()

            results["connectors"][connector.name] = {"success": success, "metadata": metadata}

            if success:
                results["success_count"] += 1
                results["total_files"] += metadata["file_count"]
                results["total_size"] += metadata["total_size"]
            else:
                results["failure_count"] += 1

        except Exception as e:
            logger.error(f"Error syncing {connector.name}: {e}")
            results["connectors"][connector.name] = {"success": False, "error": str(e)}
            results["failure_count"] += 1

    results["completed_at"] = datetime.now().isoformat()

    return results


def print_summary(results: dict):
    """Print a summary of sync results.

    Args:
        results: Sync results dictionary
    """
    print("\n" + "=" * 60)
    print("SYNC SUMMARY")
    print("=" * 60)
    print(f"Started:  {results.get('started_at', 'Unknown')}")
    if "completed_at" in results:
        print(f"Completed: {results['completed_at']}")
    print(f"Success:  {results['success_count']} connector(s)")
    print(f"Failed:   {results['failure_count']} connector(s)")
    print(f"Total files: {results['total_files']}")
    print(f"Total size:  {results['total_size'] / (1024 * 1024):.2f} MB")
    print()

    for connector_name, connector_result in results["connectors"].items():
        status = "✓" if connector_result["success"] else "✗"
        print(f"{status} {connector_name}")

        if connector_result["success"]:
            metadata = connector_result["metadata"]
            print(f"    Files: {metadata['file_count']}")
            print(f"    Size: {metadata['total_size'] / (1024 * 1024):.2f} MB")
            print(f"    Output: {metadata['output_dir']}")
            if metadata["last_sync"]:
                print(f"    Last sync: {metadata['last_sync']}")
        elif "error" in connector_result:
            print(f"    Error: {connector_result['error']}")

    print("=" * 60)


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(description="Sync all context-sync connectors")
    parser.add_argument("--full", action="store_true", help="Full sync (not incremental)")
    parser.add_argument("--quiet", action="store_true", help="Suppress summary output")

    args = parser.parse_args()

    # Ensure logs directory exists
    log_dir = Path.home() / "context-sync" / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)

    try:
        logger.info("Starting context-sync")
        results = sync_all_connectors(incremental=not args.full)

        if not args.quiet:
            print_summary(results)

        # Return exit code based on results
        if results["failure_count"] > 0:
            logger.error(f"{results['failure_count']} connector(s) failed")
            return 1

        logger.info("Context-sync completed successfully")
        return 0

    except KeyboardInterrupt:
        logger.info("Sync interrupted by user")
        return 130
    except Exception as e:
        logger.error(f"Sync failed: {e}", exc_info=True)
        return 1


if __name__ == "__main__":
    sys.exit(main())
