"""
Configuration loader for context-sync.

Loads environment variables from the standard config location.
"""

from pathlib import Path


def load_env_file():
    """Load environment variables from the standard config location.

    Looks for .env file in ~/.config/context-sync/.env
    Falls back to repo .env if config location doesn't exist (for backwards compatibility).
    """
    try:
        from dotenv import load_dotenv

        # Primary location: ~/.config/context-sync/.env
        config_path = Path.home() / ".config" / "context-sync" / ".env"

        if config_path.exists():
            load_dotenv(config_path)
            return

        # Fallback: repo .env (for backwards compatibility during migration)
        repo_env = Path(__file__).parent.parent / ".env"
        if repo_env.exists():
            load_dotenv(repo_env)
            return

    except ImportError:
        # dotenv not required, can use system env vars
        pass
