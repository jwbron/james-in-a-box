#!/usr/bin/env python3
"""
Docker Development Environment Setup

Installs your organization development tools in the Docker container.
Skips authentication (SSH, gcloud) and interactive steps.
"""

import os
import subprocess
import sys
import tempfile
from pathlib import Path


def run(cmd: list[str], check: bool = True, **kwargs) -> subprocess.CompletedProcess:
    """Run a command and return the result"""
    print(f"Running: {' '.join(cmd)}")
    return subprocess.run(cmd, check=check, **kwargs)


def run_shell(cmd: str, check: bool = True, **kwargs) -> subprocess.CompletedProcess:
    """Run a shell command"""
    # IMPORTANT: Ensure add-apt-repository uses system Python 3.10
    # add-apt-repository requires apt_pkg module which is only in system Python
    # After setting Python 3.11 as default, we need to patch add-apt-repository's shebang
    # to explicitly use python3.10 instead of the python3 symlink
    if "add-apt-repository" in cmd and not cmd.startswith("python3.10"):
        # Replace add-apt-repository command with explicit python3.10 invocation
        cmd = cmd.replace("add-apt-repository", "python3.10 /usr/bin/add-apt-repository")
    print(f"Running: {cmd}")
    return subprocess.run(cmd, shell=True, check=check, executable="/bin/bash", **kwargs)


def detect_distro() -> str:
    """Detect Linux distribution"""
    if Path("/etc/fedora-release").exists():
        return "fedora"
    elif Path("/etc/lsb-release").exists() or Path("/etc/debian_version").exists():
        return "ubuntu"
    return "unknown"


def get_arch() -> str:
    """Get system architecture"""
    return os.uname().machine  # x86_64, aarch64, etc


def install_java(distro: str) -> None:
    """Install Java 11"""
    print("\n=== Installing Java 11 ===")

    if distro == "ubuntu":
        run(["apt-get", "install", "-y", "openjdk-11-jdk"])
        # Set Java 11 as default (non-interactive)
        run_shell(
            "update-alternatives --set java /usr/lib/jvm/java-11-openjdk-*/bin/java || "
            "update-alternatives --auto java",
            check=False,
        )
        run_shell(
            "update-alternatives --set javac /usr/lib/jvm/java-11-openjdk-*/bin/javac || "
            "update-alternatives --auto javac",
            check=False,
        )
    elif distro == "fedora":
        run(["dnf", "install", "-y", "java-11-openjdk", "java-11-openjdk-devel"])
        run_shell(
            "alternatives --set java /usr/lib/jvm/java-11-openjdk/bin/java || "
            "alternatives --auto java",
            check=False,
        )
        run_shell(
            "alternatives --set javac /usr/lib/jvm/java-11-openjdk/bin/javac || "
            "alternatives --auto javac",
            check=False,
        )


def install_go(distro: str) -> None:
    """Install Go"""
    print("\n=== Installing Go ===")

    # Check if recent Go is already installed
    try:
        result = run(["go", "version"], capture_output=True, text=True, check=False)
        if result.returncode == 0 and "go1." in result.stdout:
            version = result.stdout.split()[2].replace("go", "")
            if version >= "1.20":
                print(f"Go {version} already installed, skipping")
                return
    except Exception:
        pass

    if distro == "ubuntu":
        # Add PPA for recent Go
        run_shell(
            "add-apt-repository -y ppa:longsleep/golang-backports && apt-get update -qq -y || "
            "add-apt-repository -y -r ppa:longsleep/golang-backports",
            check=False,
        )
        run(["apt-get", "install", "-y", "golang-go"])
    elif distro == "fedora":
        run(["dnf", "install", "-y", "golang"])


def install_nodejs(distro: str) -> None:
    """Install Node.js 20.x"""
    print("\n=== Installing Node.js 20.x ===")

    if distro == "ubuntu":
        # Setup NodeSource repository for Node 20
        run(["mkdir", "-p", "/usr/share/keyrings"])
        run_shell(
            "rm -f /usr/share/keyrings/nodesource.gpg /etc/apt/sources.list.d/nodesource.list"
        )

        run_shell(
            "curl -fsSL https://deb.nodesource.com/gpgkey/nodesource-repo.gpg.key | "
            "gpg --dearmor -o /usr/share/keyrings/nodesource.gpg"
        )

        with open("/etc/apt/sources.list.d/nodesource.list", "w") as f:
            f.write(
                "deb [signed-by=/usr/share/keyrings/nodesource.gpg] "
                "https://deb.nodesource.com/node_20.x nodistro main\n"
            )

        run(["chmod", "a+rX", "/etc/apt/sources.list.d/nodesource.list"])

        # Pin nodejs to nodesource
        with open("/etc/apt/preferences.d/nodejs", "w") as f:
            f.write("Package: nodejs\nPin: origin deb.nodesource.com\nPin-Priority: 999\n")

        run(["apt-get", "update", "-qq", "-y"])
        run(["apt-get", "install", "-y", "nodejs"])

    elif distro == "fedora":
        # Remove Fedora nodejs if present
        run(["dnf", "remove", "-y", "nodejs", "nodejs-npm"], check=False)

        # Setup NodeSource repository
        run_shell("curl -fsSL https://rpm.nodesource.com/setup_20.x | bash -")
        run(["dnf", "install", "-y", "nodejs"])


def install_python(distro: str) -> None:
    """Install Python 3.11"""
    print("\n=== Installing Python 3.11 ===")

    if distro == "ubuntu":
        # Add deadsnakes PPA for recent Python
        run_shell("add-apt-repository -y ppa:deadsnakes/ppa && apt-get update -qq -y", check=False)
        run(
            [
                "apt-get",
                "install",
                "-y",
                "python3.11",
                "python3.11-venv",
                "python3.11-dev",
                "python3-dev",
                "python3-setuptools",
                "python3-pip",
                "python3-venv",
                "python-is-python3",
            ]
        )
    elif distro == "fedora":
        run(
            [
                "dnf",
                "install",
                "-y",
                "python3.11",
                "python3.11-devel",
                "python3-devel",
                "python3-setuptools",
                "python3-pip",
            ]
        )


def install_dev_packages(distro: str) -> None:
    """Install core development packages"""
    print("\n=== Installing development packages ===")

    if distro == "ubuntu":
        packages = [
            "git",
            # Image processing
            "libfreetype6",
            "libfreetype6-dev",
            "libpng-dev",
            "libjpeg-dev",
            "imagemagick",
            # XML/YAML
            "libxslt1-dev",
            "libyaml-dev",
            # Terminal
            "libncurses-dev",
            "libreadline-dev",
            # Redis
            "redis-server",
            # Utils
            "unzip",
            "jq",
            "curl",
            "wget",
            # Build tools
            "build-essential",
            "pkg-config",
            # Rust
            "cargo",
            "cargo-doc",
            # Other tools
            "lsof",
            "uuid-runtime",
            "unrar",
            "ack-grep",
            # Editors
            "vim",
            "emacs",
        ]
        run(["apt-get", "install", "-y"] + packages)

        # Setup ack shortcut
        run_shell(
            "dpkg-divert --local --divert /usr/bin/ack --rename --add /usr/bin/ack-grep || "
            "echo 'ack already configured'",
            check=False,
        )

    elif distro == "fedora":
        packages = [
            "git",
            # Image processing
            "freetype",
            "freetype-devel",
            "libpng-devel",
            "libjpeg-turbo-devel",
            "ImageMagick",
            # XML/YAML
            "libxslt-devel",
            "libyaml-devel",
            # Terminal
            "ncurses-devel",
            "readline-devel",
            # Redis
            "redis",
            # Utils
            "unzip",
            "jq",
            "curl",
            "wget",
            # Build tools
            "gcc",
            "gcc-c++",
            "make",
            "pkgconf",
            "pkg-config",
            # Rust
            "cargo",
            "rust-doc",
            # Other tools
            "lsof",
            "util-linux",
            "unrar",
            "ack",
            # Editors
            "vim",
            "emacs",
        ]
        run(["dnf", "install", "-y", "--skip-unavailable"] + packages)


def install_npm_version() -> None:
    """Install correct npm version"""
    print("\n=== Configuring npm ===")

    try:
        result = run(["npm", "--version"], capture_output=True, text=True)
        current_version = result.stdout.strip()

        # We need npm >= 8.0.0
        if current_version.startswith(("5.", "6.", "7.")):
            print(f"Upgrading npm from {current_version} to 8.11.0")
            run(["npm", "install", "-g", "npm@8.11.0", "--loglevel=error"])
        else:
            print(f"npm version {current_version} is sufficient")
    except Exception as e:
        print(f"Warning: Could not check npm version: {e}")


def install_mkcert() -> None:
    """Install and setup mkcert for HTTPS development"""
    print("\n=== Installing mkcert ===")

    try:
        run(["which", "mkcert"], capture_output=True, check=True)
        print("mkcert already installed")
        return
    except subprocess.CalledProcessError:
        pass

    with tempfile.TemporaryDirectory() as tmpdir:
        print("Building mkcert from source...")
        run(["git", "clone", "https://github.com/FiloSottile/mkcert", tmpdir])

        original_dir = os.getcwd()
        try:
            os.chdir(tmpdir)
            run(["go", "mod", "download"])
            version = run(
                ["git", "describe", "--tags"], capture_output=True, text=True
            ).stdout.strip()
            run(["go", "build", "-ldflags", f"-X main.Version={version}"])
            run(["install", "-m", "755", "mkcert", "/usr/local/bin"])
        finally:
            os.chdir(original_dir)

    # Install CA (non-interactive)
    run(["mkcert", "-install"])
    print("mkcert installed and CA configured")


def install_watchman(distro: str) -> None:
    """Install watchman for file watching"""
    print("\n=== Installing watchman ===")

    # Try package manager first
    if distro == "ubuntu":
        result = run(["apt-get", "install", "-y", "watchman"], check=False)
        if result.returncode == 0:
            return
    elif distro == "fedora":
        result = run(["dnf", "install", "-y", "watchman"], check=False)
        if result.returncode == 0:
            return

    # Build from source if package not available
    print("Building watchman from source...")

    # Install build dependencies
    if distro == "ubuntu":
        run(
            [
                "apt-get",
                "install",
                "-y",
                "autoconf",
                "automake",
                "build-essential",
                "libtool",
                "libssl-dev",
            ]
        )
    elif distro == "fedora":
        run(
            [
                "dnf",
                "install",
                "-y",
                "autoconf",
                "automake",
                "gcc",
                "gcc-c++",
                "make",
                "libtool",
                "openssl-devel",
            ]
        )

    with tempfile.TemporaryDirectory() as tmpdir:
        try:
            run(["git", "clone", "https://github.com/facebook/watchman.git", tmpdir])

            original_dir = os.getcwd()
            try:
                os.chdir(tmpdir)
                run(["git", "checkout", "tags/v4.9.0"])
                run(["./autogen.sh"])
                run(["./configure", "--enable-lenient"])
                run(["make"])
                run(["make", "install"])
            finally:
                os.chdir(original_dir)
        except Exception as e:
            print(f"Warning: Failed to build watchman: {e}")
            print("Continuing without watchman...")


def install_postgresql(distro: str) -> None:
    """Install PostgreSQL"""
    print("\n=== Installing PostgreSQL ===")

    if distro == "ubuntu":
        # Add PostgreSQL repository
        run_shell(
            "curl https://www.postgresql.org/media/keys/ACCC4CF8.asc | "
            "gpg --dearmor | tee /etc/apt/trusted.gpg.d/apt.postgresql.org.gpg >/dev/null"
        )

        lsb_release = run(
            ["lsb_release", "-c", "-s"], capture_output=True, text=True
        ).stdout.strip()

        run_shell(
            f'add-apt-repository -y "deb http://apt.postgresql.org/pub/repos/apt/ {lsb_release}-pgdg main"'
        )
        run(["apt-get", "update"])
        run(["apt-get", "install", "-y", "postgresql-14"])

    elif distro == "fedora":
        run(["dnf", "install", "-y", "postgresql-server", "postgresql-contrib"])

        # Initialize database if needed
        if not Path("/var/lib/pgsql/data/PG_VERSION").exists():
            run(["postgresql-setup", "--initdb", "--unit", "postgresql"])

        # Enable postgresql
        run(["systemctl", "enable", "postgresql"], check=False)


def install_fastly(distro: str, arch: str) -> None:
    """Install Fastly CLI"""
    print("\n=== Installing Fastly CLI ===")

    with tempfile.TemporaryDirectory() as tmpdir:
        original_dir = os.getcwd()
        try:
            os.chdir(tmpdir)

            if distro == "ubuntu":
                if arch == "aarch64":
                    url = "https://github.com/fastly/cli/releases/download/v3.3.0/fastly_3.3.0_linux_arm64.deb"
                    run(["curl", "-LO", url])
                    run(["apt", "install", "-y", "./fastly_3.3.0_linux_arm64.deb"])
                else:
                    url = "https://github.com/fastly/cli/releases/download/v3.3.0/fastly_3.3.0_linux_amd64.deb"
                    run(["curl", "-LO", url])
                    run(["apt", "install", "-y", "./fastly_3.3.0_linux_amd64.deb"])

            elif distro == "fedora":
                if arch == "aarch64":
                    url = "https://github.com/fastly/cli/releases/download/v3.3.0/fastly_3.3.0_linux_arm64.rpm"
                    run(["curl", "-LO", url])
                    run(["dnf", "install", "-y", "./fastly_3.3.0_linux_arm64.rpm"])
                else:
                    url = "https://github.com/fastly/cli/releases/download/v3.3.0/fastly_3.3.0_linux_amd64.rpm"
                    run(["curl", "-LO", url])
                    run(["dnf", "install", "-y", "./fastly_3.3.0_linux_amd64.rpm"])
        finally:
            os.chdir(original_dir)


def configure_system(distro: str) -> None:
    """Configure system settings"""
    print("\n=== Configuring system ===")

    # Increase inotify watchers for webpack
    print("Configuring inotify...")
    with open("/etc/sysctl.conf", "a") as f:
        f.write("\nfs.inotify.max_user_watches=524288\n")
    run(["sysctl", "-p"], check=False)


def main():
    """Main setup process"""
    if os.geteuid() != 0:
        print("This script must be run as root (for apt/dnf installs)")
        sys.exit(1)

    print("=" * 60)
    print("your organization Docker Development Environment Setup")
    print("=" * 60)
    print()
    print("This script installs development tools WITHOUT:")
    print("  - SSH keys or authentication")
    print("  - gcloud CLI")
    print("  - Interactive prompts")
    print("  - Browser/GUI-specific tools")
    print()

    distro = detect_distro()
    arch = get_arch()

    print(f"Detected: {distro} on {arch}")
    print()

    if distro == "unknown":
        print("WARNING: Unknown distribution. This may not work correctly.")
        print("Supported: Ubuntu, Fedora")
        response = input("Continue anyway? (yes/no): ")
        if response.lower() != "yes":
            sys.exit(1)

    try:
        # Core language runtimes
        install_python(distro)
        install_nodejs(distro)
        install_go(distro)
        install_java(distro)

        # Development packages
        install_dev_packages(distro)
        install_npm_version()

        # Development tools
        install_mkcert()
        install_watchman(distro)
        install_postgresql(distro)
        install_fastly(distro, arch)

        # System configuration
        configure_system(distro)

        print()
        print("=" * 60)
        print("Setup complete!")
        print("=" * 60)
        print()
        print("Installed:")
        print("  ✓ Python 3.11")
        print("  ✓ Node.js 20.x")
        print("  ✓ Go")
        print("  ✓ Java 11")
        print("  ✓ PostgreSQL 14")
        print("  ✓ Development libraries")
        print("  ✓ mkcert (HTTPS)")
        print("  ✓ Watchman (file watching)")
        print("  ✓ Fastly CLI")
        print()
        print("Skipped (not needed in Docker):")
        print("  - SSH key generation")
        print("  - gcloud CLI")
        print("  - Browser certificates")
        print()

    except Exception as e:
        print(f"\nError during setup: {e}", file=sys.stderr)
        import traceback

        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
