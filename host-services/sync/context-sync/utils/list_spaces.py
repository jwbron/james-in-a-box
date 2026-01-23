#!/usr/bin/env python3
"""
List all available Confluence spaces.
"""

import argparse
import base64

import requests
from connectors.confluence.config import ConfluenceConfig
from dotenv import load_dotenv


def list_all_spaces(space_type: str | None = None, show_personal: bool = True):
    """List all available spaces in Confluence with full pagination.

    Args:
        space_type: Filter by space type ('global' or 'personal'). None = all types.
        show_personal: Whether to show personal spaces (default True).
    """
    load_dotenv()
    config = ConfluenceConfig()

    if not config.validate():
        print("Error: Missing required configuration.")
        return

    # Setup authentication
    auth_string = f"{config.USERNAME}:{config.API_TOKEN}"
    auth_bytes = auth_string.encode("ascii")
    auth_b64 = base64.b64encode(auth_bytes).decode("ascii")

    headers = {
        "Authorization": f"Basic {auth_b64}",
        "Content-Type": "application/json",
        "Accept": "application/json",
    }

    # Fetch all spaces with pagination
    all_spaces = []
    cursor = None
    limit = 100  # Max per page

    try:
        while True:
            url = f"{config.BASE_URL}/api/v2/spaces"
            params = {"limit": limit}

            # Filter by type if specified
            if space_type:
                params["type"] = space_type

            if cursor:
                params["cursor"] = cursor

            response = requests.get(url, headers=headers, params=params, timeout=30)
            response.raise_for_status()

            data = response.json()
            spaces = data.get("results", [])
            all_spaces.extend(spaces)

            # Check for next page using cursor-based pagination
            if "_links" in data and "next" in data["_links"]:
                next_url = data["_links"]["next"]
                if "cursor=" in next_url:
                    cursor = next_url.split("cursor=")[1].split("&")[0]
                else:
                    break
            else:
                break

        # Filter out personal spaces if requested
        if not show_personal and not space_type:
            all_spaces = [s for s in all_spaces if s.get("type") != "personal"]

        # Separate into global and personal for display
        global_spaces = [s for s in all_spaces if s.get("type") == "global"]
        personal_spaces = [s for s in all_spaces if s.get("type") == "personal"]

        print(
            f"Found {len(all_spaces)} spaces "
            f"({len(global_spaces)} global, {len(personal_spaces)} personal)"
        )
        print()

        # Show global spaces first (these are the team/project spaces)
        if global_spaces:
            print("=== Global Spaces (Team/Project) ===")
            print("These are the spaces you typically want to sync:")
            print()
            for space in sorted(global_spaces, key=lambda s: s.get("key", "")):
                status = space.get("status", "unknown")
                print(f"  {space.get('key', 'N/A')}: {space.get('name', 'N/A')}")
                print(f"    ID: {space.get('id', 'N/A')}, Status: {status}")
                print()

        # Show personal spaces second
        if personal_spaces and show_personal:
            print("=== Personal Spaces ===")
            print()
            for space in sorted(personal_spaces, key=lambda s: s.get("key", "")):
                status = space.get("status", "unknown")
                print(f"  {space.get('key', 'N/A')}: {space.get('name', 'N/A')}")
                print(f"    ID: {space.get('id', 'N/A')}, Status: {status}")
                print()

        # Show helpful hint about configuring spaces
        if global_spaces:
            print("---")
            print(
                "TIP: To sync these spaces, add their keys to "
                "CONFLUENCE_SPACE_KEYS in your secrets.env:"
            )
            example_keys = ",".join(s.get("key", "") for s in global_spaces[:5])
            print(f'  CONFLUENCE_SPACE_KEYS="{example_keys}"')
            if len(global_spaces) > 5:
                print(f"  (showing first 5 of {len(global_spaces)} global spaces)")

    except Exception as e:
        print(f"Error fetching spaces: {e}")


def main():
    """Main function with CLI argument parsing."""
    parser = argparse.ArgumentParser(description="List all available Confluence spaces")
    parser.add_argument(
        "--type",
        choices=["global", "personal"],
        help="Filter by space type (default: show all)",
    )
    parser.add_argument(
        "--no-personal",
        action="store_true",
        help="Hide personal spaces from output",
    )
    args = parser.parse_args()

    list_all_spaces(space_type=args.type, show_personal=not args.no_personal)


if __name__ == "__main__":
    main()
