#!/usr/bin/env python3
"""
FlatMark Ticket Creator.

Helper script to allocate unique ticket IDs and create ticket templates.
"""

from pathlib import Path
import argparse
import os
import re
import secrets
import sys
import tempfile

try:
    from . import board
except ImportError:
    import board

DEFAULT_BASE_DIR: Path = Path(__file__).resolve().parent

# Module-level paths for backward compatibility with tests using patch.object
base_dir: str = str(DEFAULT_BASE_DIR)
tickets_dir: str = str(DEFAULT_BASE_DIR / "tickets")
archive_dir: str = str(DEFAULT_BASE_DIR / "archive")

VALID_PREFIXES: set[str] = {"T", "B", "F", "S", "R", "D"}


def _resolve_paths(
    root: Path | str | None,
) -> tuple[Path, Path, Path]:
    """Resolve base directory, tickets directory, and archive directory.

    Honors root if supplied, or falls back to module globals if patched in tests.
    """
    if root is not None:
        r = Path(root).resolve()
        if (r / "tickets").is_dir():
            return r, r / "tickets", r / "archive"
        if (r / "flatmark" / "tickets").is_dir():
            return (
                r / "flatmark",
                r / "flatmark" / "tickets",
                r / "flatmark" / "archive",
            )
        return r, r / "tickets", r / "archive"

    return Path(base_dir), Path(tickets_dir), Path(archive_dir)


def get_sequential_id(
    prefix: str, root: Path | str | None = None
) -> str:
    """Find the next sequential ticket ID for a prefix (e.g., T4 if T3 exists)."""
    _, t_dir, a_dir = _resolve_paths(root)
    highest = 0
    pattern = re.compile(rf"^{re.escape(prefix)}(\d+)\.md$")

    for folder in [t_dir, a_dir]:
        if folder.is_dir():
            for file_path in folder.glob(f"{prefix}*.md"):
                match = pattern.match(file_path.name)
                if match:
                    num = int(match.group(1))
                    if num > highest:
                        highest = num
    return f"{prefix}{highest + 1}"


def get_random_id(
    prefix: str, length: int = 4, root: Path | str | None = None
) -> str:
    """Generate a unique random ticket ID for a prefix (e.g., T-7f3a)."""
    _, t_dir, a_dir = _resolve_paths(root)
    existing: set[str] = set()

    for folder in [t_dir, a_dir]:
        if folder.is_dir():
            for file_path in folder.glob("*.md"):
                existing.add(file_path.stem)

    for _ in range(1000):
        token = secrets.token_hex((length + 1) // 2)[:length].lower()
        candidate = f"{prefix}-{token}"
        if candidate not in existing:
            return candidate

    raise RuntimeError(
        f"Could not generate a unique random ID for prefix {prefix} after 1000 attempts."
    )


def get_next_id(
    prefix: str,
    scheme: str = "sequential",
    root: Path | str | None = None,
) -> str:
    """Allocate the next ticket ID using the specified scheme ('sequential', 'random', or 'hash')."""
    normalized_scheme = str(scheme).strip().lower()
    if normalized_scheme in ("random", "hash"):
        return get_random_id(prefix, root=root)
    if normalized_scheme == "sequential":
        return get_sequential_id(prefix, root=root)
    raise ValueError(
        f"Unknown ID scheme '{scheme}'. Allowed values: sequential, random, hash."
    )


def atomic_write(
    destination: Path, content: str, encoding: str = "utf-8"
) -> None:
    """Write content to destination path atomically using a temporary file and os.replace."""
    destination.parent.mkdir(parents=True, exist_ok=True)
    temp_file = tempfile.NamedTemporaryFile(
        dir=destination.parent,
        prefix=f".{destination.name}.",
        suffix=".tmp",
        delete=False,
        mode="w",
        encoding=encoding,
        newline="\n",
    )
    temp_path = Path(temp_file.name)
    try:
        temp_file.write(content)
        temp_file.flush()
        os.fsync(temp_file.fileno())
        temp_file.close()
        os.replace(temp_path, destination)
    except Exception:
        temp_file.close()
        if temp_path.exists():
            temp_path.unlink()
        raise


def create_ticket(
    prefix: str,
    title: str = "New Ticket",
    scheme: str = "sequential",
    root: Path | str | None = None,
) -> tuple[str, Path]:
    """Create a new ticket file atomically and update BOARD.md.

    Raises ValueError if prefix is invalid or scheme is unknown.
    Raises OSError if ticket cannot be written.
    """
    prefix_clean = prefix.strip().upper()
    if prefix_clean not in VALID_PREFIXES:
        raise ValueError(
            "Prefix must be T (Task), or B (Bug), F (Feature), S (Spike), R (Release), D (Documentation)"
        )

    r_base, r_tickets, _ = _resolve_paths(root)
    r_tickets.mkdir(parents=True, exist_ok=True)

    next_id = get_next_id(prefix_clean, scheme=scheme, root=root)
    file_path = r_tickets / f"{next_id}.md"

    content = f"""---
id: {next_id}
priority: P2
status: Todo
---
# {title}

Description goes here.

Acceptance criteria:
- [ ] Criteria 1
"""

    atomic_write(file_path, content)
    board.update_board(root=r_base)
    return next_id, file_path


def build_arg_parser() -> argparse.ArgumentParser:
    """Build the argument parser for new.py CLI."""
    parser = argparse.ArgumentParser(
        prog="new.py",
        description="Create a new FlatMark ticket template in tickets/.",
        usage="python3 flatmark/new.py [--scheme sequential|random] [T|B|F|S|R|D] <Ticket Title>",
    )
    parser.add_argument(
        "--scheme",
        default="sequential",
        help="ID generation scheme (sequential, random, hash)",
    )
    parser.add_argument(
        "--random",
        action="store_const",
        dest="scheme",
        const="random",
        help="Shortcut for --scheme random",
    )
    parser.add_argument(
        "--sequential",
        action="store_const",
        dest="scheme",
        const="sequential",
        help="Shortcut for --scheme sequential",
    )
    parser.add_argument(
        "-v",
        "--version",
        action="version",
        version=f"FlatMark v{board.get_version()}",
        help="Show version",
    )
    parser.add_argument(
        "prefix",
        nargs="?",
        default=None,
        help="Ticket prefix: T, B, F, S, R, D",
    )
    parser.add_argument(
        "title",
        nargs="*",
        default=[],
        help="Ticket title",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    """CLI entry point for new.py."""
    if argv is None:
        argv = sys.argv[1:]

    parser = build_arg_parser()
    args = parser.parse_args(argv)

    if not args.prefix:
        parser.print_usage(file=sys.stderr)
        return 2

    prefix = args.prefix.strip().upper()
    if prefix not in VALID_PREFIXES:
        print(
            "Error: Prefix must be T (Task), or B (Bug), F (Feature), S (Spike), R (Release), D (Documentation)",
            file=sys.stderr,
        )
        return 2

    title = " ".join(args.title) if args.title else "New Ticket"
    try:
        next_id, file_path = create_ticket(
            prefix=prefix,
            title=title,
            scheme=args.scheme,
        )
    except ValueError as e:
        print(f"Error: {e}", file=sys.stderr)
        return 2
    except (OSError, RuntimeError) as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1

    print(f"Created ticket: {next_id} ({file_path})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
