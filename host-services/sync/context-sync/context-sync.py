#!/usr/bin/env python3
"""
Main sync orchestrator for context-sync.

Runs all configured connectors and syncs content to ~/context-sync/<connector-name>/
"""

import argparse
import sys
from datetime import datetime
from pathlib import Path

# Load environment variables from config location
from utils.config_loader import load_env_file


load_env_file()

# Add shared directory to path for jib_logging
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent / "shared"))

# Import connectors
from connectors.confluence.connector import ConfluenceConnector
from connectors.jira.connector import JIRAConnector
from jib_logging import get_logger


# Initialize logger
logger = get_logger("context-sync")

# Add file handler for persistent logs
log_dir = Path.home() / "context-sync" / "logs"
log_dir.mkdir(parents=True, exist_ok=True)
logger.add_file_handler(log_dir / f"sync_{datetime.now().strftime('%Y%m%d')}.log")


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
            logger.debug("Initialized connector", connector_name="confluence")
        else:
            logger.warning("Connector configuration invalid", connector="Confluence")
    except Exception as e:
        logger.error(
            "Failed to initialize connector",
            connector="Confluence",
            error=str(e),
            error_type=type(e).__name__,
        )

    # JIRA connector
    try:
        connector = JIRAConnector()
        if connector.validate_config():
            connectors.append(connector)
            logger.debug("Initialized connector", connector_name="jira")
        else:
            logger.warning("Connector configuration invalid", connector="JIRA")
    except Exception as e:
        logger.error(
            "Failed to initialize connector",
            connector="JIRA",
            error=str(e),
            error_type=type(e).__name__,
        )

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

    logger.info("Running sync", connector_count=len(connectors))

    for connector in connectors:
        logger.info("Starting connector sync", connector=connector.name)

        try:
            success = connector.sync(incremental=incremental)
            metadata = connector.get_sync_metadata()

            results["connectors"][connector.name] = {"success": success, "metadata": metadata}

            if success:
                results["success_count"] += 1
                results["total_files"] += metadata["file_count"]
                results["total_size"] += metadata["total_size"]
                logger.info(
                    "Connector sync completed successfully",
                    connector_name=connector.name,
                    file_count=metadata["file_count"],
                    total_size_bytes=metadata["total_size"],
                    output_dir=metadata.get("output_dir"),
                )
            else:
                results["failure_count"] += 1
                logger.warning(
                    "Connector sync completed with failures",
                    connector_name=connector.name,
                )

        except Exception as e:
            logger.error(
                "Error syncing connector",
                connector=connector.name,
                error=str(e),
                error_type=type(e).__name__,
            )
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
        logger.info(
            "Starting context-sync",
            mode="full" if args.full else "incremental",
        )
        results = sync_all_connectors(incremental=not args.full)

        if not args.quiet:
            print_summary(results)

        # Return exit code based on results
        if results["failure_count"] > 0:
            logger.error(
                "Context-sync completed with failures",
                failure_count=results["failure_count"],
                success_count=results["success_count"],
            )
            return 1

        logger.info(
            "Context-sync completed successfully",
            success_count=results["success_count"],
            total_files=results["total_files"],
            total_size_mb=results["total_size"] / (1024 * 1024),
        )
        return 0

    except KeyboardInterrupt:
        logger.info("Sync interrupted by user")
        return 130
    except Exception as e:
        logger.error(
            "Sync failed",
            error=str(e),
            error_type=type(e).__name__,
        )
        return 1


if __name__ == "__main__":
    sys.exit(main())
