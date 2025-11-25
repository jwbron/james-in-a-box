#!/usr/bin/env python3
"""
Get space IDs for configured spaces.
"""

import os
import requests
import base64
from dotenv import load_dotenv

from connectors.confluence.config import ConfluenceConfig


def get_space_ids():
    """Get space IDs for configured spaces."""
    load_dotenv()
    config = ConfluenceConfig()
    
    if not config.validate():
        print("Error: Missing required configuration.")
        return
    
    space_keys = config.get_space_keys_list()
    if not space_keys:
        print("No space keys configured.")
        return
    
    # Setup authentication
    auth_string = f"{config.USERNAME}:{config.API_TOKEN}"
    auth_bytes = auth_string.encode('ascii')
    auth_b64 = base64.b64encode(auth_bytes).decode('ascii')
    
    headers = {
        'Authorization': f'Basic {auth_b64}',
        'Content-Type': 'application/json',
        'Accept': 'application/json'
    }
    
    print("Space IDs for configured spaces:")
    print()
    
    for space_key in space_keys:
        url = f"{config.BASE_URL}/api/v2/spaces"
        params = {
            'keys': space_key,
            'limit': 1
        }
        
        try:
            response = requests.get(url, headers=headers, params=params, timeout=10)
            response.raise_for_status()
            
            data = response.json()
            spaces = data.get('results', [])
            
            if spaces:
                space = spaces[0]
                print(f"  {space_key}: {space.get('id', 'N/A')} ({space.get('name', 'N/A')})")
            else:
                print(f"  {space_key}: Not found")
                
        except Exception as e:
            print(f"  {space_key}: Error - {e}")


if __name__ == "__main__":
    get_space_ids() 