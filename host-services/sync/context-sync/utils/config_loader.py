"""
Configuration loader for context-sync.

Loads environment variables from ~/.config/jib/secrets.env.
"""

from pathlib import Path


def load_env_file():
    """Load environment variables from ~/.config/jib/secrets.env.

    Config location: ~/.config/jib/secrets.env
    Run `python3 config/host_config.py --migrate` to migrate from legacy locations.
    """
    try:
        from dotenv import load_dotenv

        jib_secrets = Path.home() / ".config" / "jib" / "secrets.env"
        if jib_secrets.exists():
            load_dotenv(jib_secrets)

    except ImportError:
        # dotenv not required, can use system env vars
        pass
