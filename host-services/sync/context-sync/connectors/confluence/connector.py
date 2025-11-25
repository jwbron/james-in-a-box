"""
Confluence connector for context-sync.

Wraps the existing ConfluenceSync class to conform to the BaseConnector interface.
"""

import os
from pathlib import Path
from typing import Dict

from connectors.base import BaseConnector
from connectors.confluence.config import ConfluenceConfig
from connectors.confluence.sync import ConfluenceSync


class ConfluenceConnector(BaseConnector):
    """Confluence connector that syncs documentation from Confluence."""
    
    def __init__(self, output_dir: Path = None):
        """Initialize the Confluence connector.
        
        Args:
            output_dir: Optional override for output directory
        """
        # Use configured output dir or default
        if output_dir is None:
            output_dir = Path(ConfluenceConfig.OUTPUT_DIR)
        
        super().__init__("confluence", output_dir)
        
        # Initialize the confluence syncer
        try:
            self.syncer = ConfluenceSync()
            # Override the output directory to use our configured one
            self.syncer.config.OUTPUT_DIR = str(self.output_dir)
            self.syncer.sync_state_file = self.output_dir / ".sync_state"
        except Exception as e:
            self.logger.error(f"Failed to initialize Confluence sync: {e}")
            self.syncer = None
    
    def validate_config(self) -> bool:
        """Validate Confluence configuration."""
        if not ConfluenceConfig.validate():
            errors = ConfluenceConfig.get_validation_errors()
            for error in errors:
                self.logger.error(error)
            return False
        return True
    
    def sync(self, incremental: bool = True) -> bool:
        """Sync all configured Confluence spaces.
        
        Args:
            incremental: If True, only sync changed pages
        
        Returns:
            True if sync was successful, False otherwise
        """
        if self.syncer is None:
            self.logger.error("Confluence syncer not initialized")
            return False
        
        if not self.validate_config():
            self.logger.error("Invalid configuration")
            return False
        
        try:
            self.logger.info("Starting Confluence sync...")
            self.logger.info(f"Output directory: {self.output_dir}")
            
            space_keys = ConfluenceConfig.get_space_keys_list()
            self.logger.info(f"Syncing {len(space_keys)} spaces: {', '.join(space_keys)}")
            
            for space_key in space_keys:
                try:
                    self.logger.info(f"Syncing space: {space_key}")
                    self.syncer.sync_space(space_key, incremental=incremental)
                except Exception as e:
                    self.logger.error(f"Error syncing space {space_key}: {e}")
                    # Continue with other spaces even if one fails
            
            self.logger.info("Confluence sync completed")
            return True
            
        except Exception as e:
            self.logger.error(f"Confluence sync failed: {e}")
            return False
    
    def get_sync_metadata(self) -> Dict:
        """Get metadata about the last Confluence sync."""
        metadata = super().get_sync_metadata()
        
        # Add Confluence-specific metadata
        if ConfluenceConfig.validate():
            metadata['spaces'] = ConfluenceConfig.get_space_keys_list()
            metadata['base_url'] = ConfluenceConfig.BASE_URL
        
        return metadata


def main():
    """Main entry point for running Confluence connector standalone."""
    import argparse
    
    parser = argparse.ArgumentParser(description='Sync Confluence documentation')
    parser.add_argument('--full', action='store_true',
                       help='Full sync (not incremental)')
    parser.add_argument('--output-dir', type=str,
                       help='Override output directory')
    
    args = parser.parse_args()
    
    # Create connector
    output_dir = Path(args.output_dir) if args.output_dir else None
    connector = ConfluenceConnector(output_dir=output_dir)
    
    # Run sync
    success = connector.sync(incremental=not args.full)
    
    # Print metadata
    metadata = connector.get_sync_metadata()
    print(f"\nSync Summary:")
    print(f"  Spaces: {', '.join(metadata.get('spaces', []))}")
    print(f"  Files: {metadata['file_count']}")
    print(f"  Size: {metadata['total_size'] / (1024*1024):.2f} MB")
    print(f"  Last sync: {metadata['last_sync']}")
    
    return 0 if success else 1


if __name__ == "__main__":
    exit(main())

