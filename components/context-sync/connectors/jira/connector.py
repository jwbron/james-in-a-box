The file doesn't exist in the codebase. Based on your request, you've provided the file content and asked me to fix it by removing the duplicate import. Here's the fixed file content with the second `from pathlib import Path` import removed:

```
"""
JIRA connector for context-sync.

Wraps the JIRASync class to conform to the BaseConnector interface.
"""

# Load environment variables from config location before any imports
import sys
from pathlib import Path

# Add parent directory to path to import utils
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from utils.config_loader import load_env_file
load_env_file()

from typing import Dict

from connectors.base import BaseConnector
from connectors.jira.config import JIRAConfig
from connectors.jira.sync import JIRASync


class JIRAConnector(BaseConnector):
    """JIRA connector that syncs tickets and comments."""
    
    def __init__(self, output_dir: Path = None):
        """Initialize the JIRA connector.
        
        Args:
            output_dir: Optional override for output directory
        """
        # Use configured output dir or default
        if output_dir is None:
            output_dir = Path(JIRAConfig.OUTPUT_DIR)
        
        super().__init__("jira", output_dir)
        
        # Initialize the JIRA syncer
        try:
            self.syncer = JIRASync()
            # Override the output directory to use our configured one
            self.syncer.config.OUTPUT_DIR = str(self.output_dir)
            self.syncer.sync_state_file = self.output_dir / ".sync_state"
        except Exception as e:
            self.logger.error(f"Failed to initialize JIRA sync: {e}")
            self.syncer = None
    
    def validate_config(self) -> bool:
        """Validate JIRA configuration."""
        if not JIRAConfig.validate():
            errors = JIRAConfig.get_validation_errors()
            for error in errors:
                self.logger.error(error)
            return False
        return True
    
    def sync(self, incremental: bool = True) -> bool:
        """Sync JIRA tickets and comments.
        
        Args:
            incremental: If True, only sync changed tickets
        
        Returns:
            True if sync was successful, False otherwise
        """
        if self.syncer is None:
            self.logger.error("JIRA syncer not initialized")
            return False
        
        if not self.validate_config():
            self.logger.error("Invalid configuration")
            return False
        
        try:
            self.logger.info("Starting JIRA sync...")
            self.logger.info(f"Output directory: {self.output_dir}")
            self.logger.info(f"JQL query: {JIRAConfig.JQL_QUERY}")
            
            self.syncer.sync_all_issues(incremental=incremental)
            
            self.logger.info("JIRA sync completed")
            return True
            
        except Exception as e:
            self.logger.error(f"JIRA sync failed: {e}")
            return False
    
    def get_sync_metadata(self) -> Dict:
        """Get metadata about the last JIRA sync."""
        metadata = super().get_sync_metadata()
        
        # Add JIRA-specific metadata
        if JIRAConfig.validate():
            metadata['jql_query'] = JIRAConfig.JQL_QUERY
            metadata['base_url'] = JIRAConfig.BASE_URL
            metadata['include_comments'] = JIRAConfig.INCLUDE_COMMENTS
            metadata['include_attachments'] = JIRAConfig.INCLUDE_ATTACHMENTS
        
        return metadata


def main():
    """Main entry point for running JIRA connector standalone."""
    import argparse

    parser = argparse.ArgumentParser(description='Sync JIRA tickets')
    parser.add_argument('--full', action='store_true',
                       help='Full sync (not incremental)')
    parser.add_argument('--output-dir', type=str,
                       help='Override output directory')

    args = parser.parse_args()

    # Create connector
    output_dir = Path(args.output_dir) if args.output_dir else None
    connector = JIRAConnector(output_dir=output_dir)
    
    # Run sync
    success = connector.sync(incremental=not args.full)
    
    # Print metadata
    metadata = connector.get_sync_metadata()
    print(f"\nSync Summary:")
    print(f"  JQL Query: {metadata.get('jql_query', 'N/A')}")
    print(f"  Files: {metadata['file_count']}")
    print(f"  Size: {metadata['total_size'] / (1024*1024):.2f} MB")
    print(f"  Last sync: {metadata['last_sync']}")
    
    return 0 if success else 1


if __name__ == "__main__":
    exit(main())
```

The only change is removing line 18 (`from pathlib import Path`) since `Path` is already imported on line 9.