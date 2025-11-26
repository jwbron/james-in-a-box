"""
Configuration loader for context-sync.

Loads environment variables from the standard config location.
Now uses the consolidated ~/.config/jib/ location.
"""

from pathlib import Path


def load_env_file():
    """Load environment variables from the standard config location.

    Search order:
    1. ~/.config/jib/secrets.env (NEW consolidated location)
    2. ~/.config/context-sync/.env (legacy, for backwards compatibility)
    3. repo .env (fallback for development)
    """
    try:
        from dotenv import load_dotenv

        # NEW: Primary location - consolidated jib config
        jib_secrets = Path.home() / ".config" / "jib" / "secrets.env"
        if jib_secrets.exists():
            load_dotenv(jib_secrets)
            return

        # Legacy location: ~/.config/context-sync/.env
        legacy_path = Path.home() / ".config" / "context-sync" / ".env"
        if legacy_path.exists():
            load_dotenv(legacy_path)
            return

        # Fallback: repo .env (for development/testing)
        repo_env = Path(__file__).parent.parent / ".env"
        if repo_env.exists():
            load_dotenv(repo_env)
            return

    except ImportError:
        # dotenv not required, can use system env vars
        pass
