"""
Pytest configuration and shared fixtures.
"""
import sys
from pathlib import Path

# Add project root to path for imports
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

# Add shared module to path
SHARED_PATH = PROJECT_ROOT / "shared"
if SHARED_PATH.exists():
    sys.path.insert(0, str(SHARED_PATH))
