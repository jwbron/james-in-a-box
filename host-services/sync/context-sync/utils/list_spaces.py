#!/usr/bin/env python3
"""
List all available Confluence spaces.
"""

import base64

import requests
from connectors.confluence.config import ConfluenceConfig
from dotenv import load_dotenv


def list_all_spaces():
    """List all available spaces in Confluence."""
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

    url = f"{config.BASE_URL}/api/v2/spaces"

    try:
        response = requests.get(url, headers=headers, timeout=10)
        response.raise_for_status()

        data = response.json()
        spaces = data.get("results", [])

        print(f"Found {len(spaces)} spaces:")
        print()

        for space in spaces:
            status = space.get("status", "unknown")
            space_type = space.get("type", "unknown")
            print(f"  {space.get('key', 'N/A')}: {space.get('name', 'N/A')}")
            print(f"    ID: {space.get('id', 'N/A')}")
            print(f"    Status: {status}")
            print(f"    Type: {space_type}")
            print()

    except Exception as e:
        print(f"Error fetching spaces: {e}")


if __name__ == "__main__":
    list_all_spaces()
