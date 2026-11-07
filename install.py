#!/usr/bin/env python3
"""
FlatMark Installer.

Installs or upgrades FlatMark in a project directory from local sources or remote raw GitHub URLs.
"""

from pathlib import Path
import argparse
import os
import shutil
import stat
import subprocess
import sys
import urllib.error
import urllib.request
from typing import Any, Sequence

CORE_FILES: list[str] = [
    "AGENTS.md",
    "board.py",
    "new.py",
    "VERSION",
    "flatmark.py",
    "lint.py",
]
EXECUTABLE_FILES: set[str] = {"board.py", "new.py", "flatmark.py", "lint.py"}
DEFAULT_RAW_BASE_URL: str = (
    "https://raw.githubusercontent.com/slesar/flatmark/main/src/flatmark"
)


class FlatMarkError(Exception):
    """Base exception for FlatMark installer errors."""


class RemoteFetchError(FlatMarkError):
    """Raised when fetching a remote file fails."""


class InstallerError(FlatMarkError, SystemExit):
    """Raised when installation cannot proceed."""

    def __init__(self, message: str, code: int = 1):
        super().__init__(code)
        self.message = message
        self.code = code

    def __str__(self) -> str:
        return self.message


def read_version(directory: Path | str) -> str | None:
    """Read version string from VERSION file in directory, or return None."""
    version_file = Path(directory) / "VERSION"
    if version_file.is_file():
        try:
            return version_file.read_text(encoding="utf-8").strip()
        except OSError:
            pass
    return None


def get_local_source_dir() -> Path | None:
    """Locate local source distribution payload directory, or return None."""
    if "__file__" not in globals() or not __file__ or __file__ == "<stdin>":
        return None
    try:
        script_path = Path(__file__).resolve()
    except (OSError, RuntimeError):
        return None

    if not script_path.is_file():
        return None

    script_dir = script_path.parent
    candidate = script_dir / "src" / "flatmark"
    if all((candidate / f).is_file() for f in CORE_FILES):
        return candidate
    if all((script_dir / f).is_file() for f in CORE_FILES):
        return script_dir
    return None


def fetch_remote_file(filename: str, base_url: str | None = None) -> bytes:
    """Download a payload file from remote raw URL.

    Raises RemoteFetchError on network or HTTP error.
    """
    if base_url is None:
        base_url = os.environ.get("FLATMARK_RAW_URL", DEFAULT_RAW_BASE_URL)
    url = f"{base_url.rstrip('/')}/{filename}"
    try:
        req = urllib.request.Request(
            url, headers={"User-Agent": "FlatMark-Installer"}
        )
        with urllib.request.urlopen(req, timeout=15) as response:
            return response.read()  # type: ignore[no-any-return]
    except urllib.error.URLError as e:
        raise RemoteFetchError(f"Failed to download {url}: {e}") from e


def check_agent_discoverability(target_root: Path, dest_dir: Path) -> None:
    """Check and offer to add FlatMark reference pointer to root guidelines."""
    pointer_line = (
        "See [flatmark/AGENTS.md](flatmark/AGENTS.md) for ticket management "
        "rules, frontmatter schema, and agent workflow."
    )
    root_agent_candidates = ["AGENTS.md", "CLAUDE.md", ".cursorrules", ".windsurfrules"]
    found_candidates: list[tuple[str, Path]] = []

    dest_agents = (dest_dir / "AGENTS.md").resolve()
    for candidate in root_agent_candidates:
        candidate_path = target_root / candidate
        if candidate_path.is_file():
            try:
                if candidate_path.resolve() != dest_agents:
                    found_candidates.append((candidate, candidate_path))
            except OSError:
                pass

    added: list[str] = []
    for candidate, candidate_path in found_candidates:
        try:
            content = candidate_path.read_text(encoding="utf-8")
            if "flatmark/AGENTS.md" in content:
                continue

            should_add = False
            if sys.stdin.isatty():
                try:
                    resp = (
                        input(
                            f"Found {candidate} in project root. Add FlatMark reference pointer? (y/N): "
                        )
                        .strip()
                        .lower()
                    )
                    should_add = resp == "y"
                except EOFError:
                    should_add = False

            if should_add:
                with candidate_path.open("a", encoding="utf-8") as f:
                    if not content.endswith("\n"):
                        f.write("\n")
                    f.write(
                        f"\n<!-- FlatMark Ticket Management -->\n{pointer_line}\n"
                    )
                added.append(candidate)
                print(f"Added FlatMark pointer -> {candidate_path}")
        except OSError:
            pass

    print("\nAI Agent Discoverability:")
    if added:
        print(f"  Added FlatMark reference pointer to: {', '.join(added)}")
    else:
        print(
            "  To ensure AI agents discover FlatMark, add this pointer to your project root AGENTS.md or CLAUDE.md:"
        )
        print(f"  {pointer_line}")


def configure_gitattributes(
    target_root: Path, dest_dir: Path, force_enable: bool = False
) -> None:
    """Configure merge=ours for BOARD.md in .gitattributes to prevent merge conflicts."""
    gitattributes_path = target_root / ".gitattributes"
    try:
        rel_board = os.path.relpath(dest_dir / "BOARD.md", target_root)
    except ValueError:
        rel_board = "flatmark/BOARD.md"
    rule_line = f"{rel_board} merge=ours"

    already_configured = False
    if gitattributes_path.is_file():
        try:
            content = gitattributes_path.read_text(encoding="utf-8")
            if rel_board in content or "BOARD.md merge=ours" in content:
                already_configured = True
        except OSError:
            pass

    if already_configured:
        return

    is_git_repo = (
        (target_root / ".git").is_dir()
        or (target_root / ".git").is_file()
        or gitattributes_path.is_file()
    )

    should_add = False
    if force_enable or ("--gitattributes" in sys.argv):
        should_add = True
    elif is_git_repo and sys.stdin.isatty():
        try:
            resp = (
                input(
                    f"Add '{rule_line}' to .gitattributes to prevent merge conflicts? (y/N): "
                )
                .strip()
                .lower()
            )
            should_add = resp == "y"
        except EOFError:
            should_add = False

    if should_add:
        try:
            with gitattributes_path.open("a", encoding="utf-8") as f:
                if (
                    gitattributes_path.is_file()
                    and gitattributes_path.stat().st_size > 0
                ):
                    last_char = gitattributes_path.read_text(
                        encoding="utf-8"
                    )[-1:]
                    if last_char and last_char != "\n":
                        f.write("\n")
                f.write(
                    f"\n# Prevent merge conflicts on auto-generated FlatMark board\n{rule_line}\n"
                )
            print(f"Added merge=ours attribute -> {gitattributes_path}")
            print("\nGit Merge Driver Setup:")
            print(
                "  To enable this attribute, configure Git's 'ours' merge driver once:"
            )
            print("    git config merge.ours.driver true")
            print("  After merging branches, regenerate BOARD.md by running:")
            print("    python3 flatmark/board.py")
        except OSError as e:
            print(
                f"Warning: Could not update {gitattributes_path}: {e}",
                file=sys.stderr,
            )
    elif is_git_repo:
        print("\nGit Conflict Prevention (Optional):")
        print(
            "  To avoid merge conflicts on BOARD.md across branches, add to .gitattributes:"
        )
        print(f"    {rule_line}")
        print("  And enable the driver: git config merge.ours.driver true")
        print("  After merging branches, regenerate with: python3 flatmark/board.py")


def install(
    target_root: Path | str | None = None,
    base_url: str | None = None,
    create: bool = False,
    gitattributes: bool = False,
) -> None:
    """Install or upgrade FlatMark in the specified project directory.

    Raises InstallerError if installation fails.
    """
    if target_root is None:
        target_path = Path.cwd()
    else:
        target_path = Path(target_root).resolve()

    create = create or ("--create" in sys.argv)

    if not target_path.exists():
        if create:
            try:
                target_path.mkdir(parents=True, exist_ok=True)
                print(f"Created target directory: {target_path}")
            except OSError as e:
                print(
                    f"Error: Could not create target directory '{target_path}': {e}",
                    file=sys.stderr,
                )
                raise InstallerError(str(e), code=1) from e
        else:
            should_create = False
            if sys.stdin.isatty():
                try:
                    resp = (
                        input(
                            f"Target directory '{target_path}' does not exist. Create it? (y/N): "
                        )
                        .strip()
                        .lower()
                    )
                    should_create = resp == "y"
                except EOFError:
                    should_create = False

            if should_create:
                try:
                    target_path.mkdir(parents=True, exist_ok=True)
                    print(f"Created target directory: {target_path}")
                except OSError as e:
                    print(
                        f"Error: Could not create target directory '{target_path}': {e}",
                        file=sys.stderr,
                    )
                    raise InstallerError(str(e), code=1) from e
            else:
                print(
                    f"Error: Target directory '{target_path}' does not exist.",
                    file=sys.stderr,
                )
                print("Use --create to create it automatically.", file=sys.stderr)
                raise InstallerError(
                    f"Target directory '{target_path}' does not exist.", code=1
                )

    if not target_path.is_dir():
        print(
            f"Error: Target path '{target_path}' is not a directory.",
            file=sys.stderr,
        )
        raise InstallerError(
            f"Target path '{target_path}' is not a directory.", code=1
        )

    source_dir = get_local_source_dir()
    dest_dir = target_path / "flatmark"

    # Avoid installing into source dir itself
    if source_dir:
        try:
            if target_path.resolve() == source_dir.resolve():
                print(
                    f"Warning: Current working directory is the FlatMark source directory ({source_dir})."
                )
                try:
                    confirm = (
                        input(
                            "Are you sure you want to create a nested 'flatmark/' folder here? (y/N): "
                        )
                        .strip()
                        .lower()
                    )
                except EOFError:
                    confirm = "n"
                if confirm != "y":
                    print("Installation aborted.")
                    return
        except OSError:
            pass

    remote_files: dict[str, bytes] = {}
    if source_dir:
        source_version = read_version(source_dir) or "0.2.0"
    else:
        for filename in CORE_FILES:
            try:
                remote_files[filename] = fetch_remote_file(
                    filename, base_url=base_url
                )
            except RemoteFetchError as e:
                print(f"Error: {e}", file=sys.stderr)
                raise InstallerError(str(e), code=1) from e
        source_version = (
            remote_files["VERSION"].decode("utf-8").strip() or "0.2.0"
        )

    archive_dir = dest_dir / "archive"
    tickets_dir = dest_dir / "tickets"

    existing_version = read_version(dest_dir)
    if existing_version:
        if existing_version == source_version:
            print(
                f"FlatMark is already up to date (v{source_version}) in: {dest_dir}. Re-syncing scripts..."
            )
        else:
            print(
                f"Upgrading FlatMark from v{existing_version} to v{source_version} in: {dest_dir}..."
            )
    else:
        print(f"Installing FlatMark v{source_version} into: {dest_dir}...")

    archive_dir.mkdir(parents=True, exist_ok=True)
    tickets_dir.mkdir(parents=True, exist_ok=True)

    for filename in CORE_FILES:
        dst = dest_dir / filename
        if source_dir:
            src = source_dir / filename
            if src.is_file():
                shutil.copy2(src, dst)
                print(f"Copied {filename} -> {dst}")
            else:
                print(
                    f"Error: Required file {src} not found.", file=sys.stderr
                )
                raise InstallerError(f"Required file {src} not found.", code=1)
        else:
            dst.write_bytes(remote_files[filename])
            if filename in EXECUTABLE_FILES:
                dst.chmod(
                    dst.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH
                )
            print(f"Downloaded {filename} -> {dst}")

    # Run copied board.py to generate/rebuild BOARD.md without code duplication
    target_board_script = dest_dir / "board.py"
    subprocess.run([sys.executable, str(target_board_script)], check=True)

    local_agents = dest_dir / "AGENTS.local.md"
    if local_agents.is_file():
        print(f"Preserved custom agent rules in {local_agents}")

    print(f"\nFlatMark v{source_version} installed successfully!")
    print("Usage from project root:")
    print("  python3 flatmark/new.py [T|B|F|S|R|D] \"Ticket Title\"")
    print("  python3 flatmark/board.py")
    print("  python3 flatmark/flatmark.py lint")

    check_agent_discoverability(target_path, dest_dir)
    configure_gitattributes(
        target_path, dest_dir, force_enable=gitattributes
    )


def get_installer_version() -> str:
    """Resolve installer version string."""
    source_dir = get_local_source_dir()
    if source_dir:
        return read_version(source_dir) or "unknown"
    try:
        return fetch_remote_file("VERSION").decode("utf-8").strip() or "unknown"
    except RemoteFetchError:
        return "unknown"


class VersionAction(argparse.Action):
    """Custom argparse action for --version that queries version dynamically."""

    def __init__(
        self,
        option_strings: list[str],
        dest: str = argparse.SUPPRESS,
        default: str = argparse.SUPPRESS,
        help: str = "Show FlatMark installer version",
    ) -> None:
        super().__init__(
            option_strings=option_strings,
            dest=dest,
            default=default,
            nargs=0,
            help=help,
        )

    def __call__(
        self,
        parser: argparse.ArgumentParser,
        namespace: argparse.Namespace,
        values: str | Sequence[Any] | None = None,
        option_string: str | None = None,
    ) -> None:
        ver = get_installer_version()
        print(f"FlatMark Installer v{ver}")
        parser.exit(0)


def build_arg_parser() -> argparse.ArgumentParser:
    """Build the argument parser for install.py CLI."""
    parser = argparse.ArgumentParser(
        prog="install.py",
        description="Install or upgrade FlatMark in the specified project directory.",
    )
    parser.add_argument(
        "--create",
        action="store_true",
        help="Create target directory if it does not exist",
    )
    parser.add_argument(
        "--gitattributes",
        action="store_true",
        help="Configure merge=ours in .gitattributes without prompting",
    )
    parser.add_argument(
        "-v",
        "--version",
        action=VersionAction,
    )
    parser.add_argument(
        "target_path",
        nargs="?",
        default=None,
        help="Target project directory (default: current working directory)",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    """CLI entry point for install.py."""
    parser = build_arg_parser()
    args = parser.parse_args(argv)
    try:
        install(
            target_root=args.target_path,
            create=args.create,
            gitattributes=args.gitattributes,
        )
        return 0
    except InstallerError as e:
        return e.code
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
