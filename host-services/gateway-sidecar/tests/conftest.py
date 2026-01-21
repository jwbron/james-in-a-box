"""
Test configuration for gateway-sidecar tests.

Uses importlib to properly load modules since the directory name (gateway-sidecar)
contains a hyphen which is not valid for Python package names.

All modules with relative imports are loaded with those imports converted to
absolute imports that resolve to our loaded modules.
"""

import importlib.util
import os
import sys
from pathlib import Path
from types import ModuleType

# Set up test secret before any gateway imports
TEST_SECRET = "test-secret-token-12345"
os.environ["JIB_GATEWAY_SECRET"] = TEST_SECRET

# Get the gateway-sidecar directory
GATEWAY_DIR = Path(__file__).parent.parent
SHARED_DIR = GATEWAY_DIR.parent.parent / "shared"

# Add shared to path for jib_logging
sys.path.insert(0, str(SHARED_DIR))


def _load_module_with_replaced_imports(
    name: str,
    path: Path,
    import_replacements: dict[str, str] | None = None,
) -> ModuleType:
    """
    Load a module from a file path, optionally replacing import statements.

    Args:
        name: Name for the loaded module
        path: Path to the Python file
        import_replacements: Dict mapping old import statements to new ones
    """
    source = path.read_text()

    # Apply import replacements
    if import_replacements:
        for old, new in import_replacements.items():
            source = source.replace(old, new)

    # Create module
    module = ModuleType(name)
    module.__file__ = str(path)
    module.__loader__ = None
    module.__package__ = ""

    # Execute the modified source
    code = compile(source, path, "exec")
    exec(code, module.__dict__)

    sys.modules[name] = module
    return module


# Load modules in dependency order
# github_client has no relative imports to other gateway modules
github_client = _load_module_with_replaced_imports(
    "github_client",
    GATEWAY_DIR / "github_client.py",
)

# policy imports from .github_client - convert to absolute
policy = _load_module_with_replaced_imports(
    "policy",
    GATEWAY_DIR / "policy.py",
    import_replacements={
        "from .github_client import": "from github_client import",
    },
)

# gateway imports from both
gateway = _load_module_with_replaced_imports(
    "gateway",
    GATEWAY_DIR / "gateway.py",
    import_replacements={
        "from .github_client import": "from github_client import",
        "from .policy import": "from policy import",
    },
)

# Also load the __init__.py to prevent pytest from trying to import it
# and failing on relative imports
init_module = _load_module_with_replaced_imports(
    "gateway_sidecar_init",
    GATEWAY_DIR / "__init__.py",
    import_replacements={
        "from .gateway import": "from gateway import",
        "from .github_client import": "from github_client import",
        "from .policy import": "from policy import",
    },
)
