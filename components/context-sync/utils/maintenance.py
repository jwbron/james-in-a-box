#!/usr/bin/env python3
"""
Maintenance and cleanup operations for synced documentation.
"""

import os
import sys
from pathlib import Path
from typing import List, Set
from dotenv import load_dotenv

from connectors.confluence.config import ConfluenceConfig


def get_sync_status():
    """Show sync status and statistics."""
    load_dotenv()
    config = ConfluenceConfig()
    
    output_dir = Path(config.OUTPUT_DIR)
    if not output_dir.exists():
        print("No synced documentation found.")
        return
    
    print("Sync Status:")
    print("=" * 50)
    
    total_pages = 0
    total_spaces = 0
    
    for space_dir in output_dir.iterdir():
        if space_dir.is_dir():
            total_spaces += 1
            md_files = list(space_dir.glob("*.md"))
            space_pages = len([f for f in md_files if f.name != "README.md"])
            total_pages += space_pages
            
            print(f"  {space_dir.name}: {space_pages} pages")
    
    print()
    print(f"Total: {total_spaces} spaces, {total_pages} pages")
    
    # Check sync state file
    sync_state_file = output_dir / ".sync_state"
    if sync_state_file.exists():
        print(f"Sync state file: {sync_state_file} (exists)")
    else:
        print("Sync state file: Not found")


def find_orphaned_files(execute: bool = False):
    """Find orphaned files (files that exist but shouldn't)."""
    load_dotenv()
    config = ConfluenceConfig()
    
    output_dir = Path(config.OUTPUT_DIR)
    if not output_dir.exists():
        print("No synced documentation found.")
        return
    
    orphaned_files = []
    
    for space_dir in output_dir.iterdir():
        if not space_dir.is_dir():
            continue
            
        # Check for orphaned files in each space
        for file_path in space_dir.iterdir():
            if file_path.is_file() and file_path.suffix == '.md':
                if file_path.name == 'README.md':
                    continue  # README files are always valid
                
                # Check if this file has a corresponding page in Confluence
                # For now, we'll just list all .md files as potentially orphaned
                # In a real implementation, you'd check against the API
                orphaned_files.append(file_path)
    
    if orphaned_files:
        print(f"Found {len(orphaned_files)} potentially orphaned files:")
        for file_path in orphaned_files:
            print(f"  {file_path}")
        
        if execute:
            print("\nRemoving orphaned files...")
            for file_path in orphaned_files:
                try:
                    file_path.unlink()
                    print(f"  Removed: {file_path}")
                except Exception as e:
                    print(f"  Error removing {file_path}: {e}")
        else:
            print("\nRun with --execute to remove these files.")
    else:
        print("No orphaned files found.")


def main():
    """Main maintenance function."""
    if len(sys.argv) < 2:
        print("Usage: python maintenance.py [--status|--cleanup] [--execute]")
        return
    
    command = sys.argv[1]
    
    if command == '--status':
        get_sync_status()
    elif command == '--cleanup':
        execute = '--execute' in sys.argv
        find_orphaned_files(execute)
    else:
        print("Unknown command. Use --status or --cleanup")


if __name__ == "__main__":
    main()