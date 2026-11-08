#!/usr/bin/env python3
"""
FlatMark Board Generator and Synchronizer.

Generates and validates BOARD.md from ticket files in tickets/.
"""

from dataclasses import dataclass, replace
from pathlib import Path
import argparse
import os
import re
import sys
import tempfile
from typing import Sequence


@dataclass(frozen=True)
class Ticket:
    """Data model representing a FlatMark ticket."""

    key: str
    id: str
    title: str
    priority: str = "P2"
    blocked_by: str = ""
    parent: str = ""
    status: str = "Todo"
    filename: str = ""
    display_title: str = ""


DEFAULT_BASE_DIR: Path = Path(__file__).resolve().parent

# Module-level paths for backward compatibility with tests using patch.object
base_dir: str = str(DEFAULT_BASE_DIR)
tickets_dir: str = str(DEFAULT_BASE_DIR / "tickets")
archive_dir: str = str(DEFAULT_BASE_DIR / "archive")
board_path: str = str(DEFAULT_BASE_DIR / "BOARD.md")
version_path: str = str(DEFAULT_BASE_DIR / "VERSION")


def slugify(text: str) -> str:
    """Convert header text to markdown link anchor format."""
    text = text.lower().strip()
    text = re.sub(r"[^\w\s-]", "", text)
    text = re.sub(r"[\s_-]+", "-", text)
    return f"#{text}"


def natural_sort_key(s: str) -> list[int | str]:
    """Helper for alphanumeric sorting (e.g., B4 comes before B23)."""
    return [
        int(text) if text.isdigit() else text.lower()
        for text in re.split(r"(\d+)", s)
    ]


def escape_pipes(text: str | None) -> str:
    """Escape pipe characters for markdown table compatibility."""
    if text is None:
        return ""
    return re.sub(r"(?<!\\)\|", r"\|", str(text))


def escape_cell(text: str | None) -> str:
    """Normalize whitespace/newlines and escape pipe characters for markdown table cells."""
    if text is None:
        return ""
    normalized = " ".join(str(text).split())
    return escape_pipes(normalized)


def parse_yaml(content: str) -> dict[str, str]:
    """Parse simple YAML frontmatter delimited by '---'."""
    yaml_pattern = re.compile(
        r"^---[ \t]*\r?\n(.*?)\r?\n---[ \t]*(?:\r?\n|$)", re.DOTALL
    )
    match = yaml_pattern.search(content)
    if not match:
        return {}

    yaml_content = match.group(1)
    data: dict[str, str] = {}
    for line in yaml_content.splitlines():
        if ":" in line:
            key, value = line.split(":", 1)
            data[key.strip()] = value.strip()
    return data


def get_version(root_or_file: Path | str | None = None) -> str:
    """Read FlatMark version from VERSION file, or return 'unknown'."""
    if root_or_file is not None:
        p = Path(root_or_file)
        if p.is_file():
            v_path = p
        elif (p / "VERSION").is_file():
            v_path = p / "VERSION"
        elif (p / "flatmark" / "VERSION").is_file():
            v_path = p / "flatmark" / "VERSION"
        else:
            v_path = p / "VERSION"
    else:
        v_path = Path(version_path)

    if v_path.is_file():
        try:
            return v_path.read_text(encoding="utf-8").strip()
        except OSError:
            pass
    return "unknown"


def _resolve_paths(
    root: Path | str | None,
) -> tuple[Path, Path, Path, Path, Path]:
    """Resolve base directory, tickets directory, archive directory, board path, and version path.

    Honors root if supplied, or falls back to module globals if patched in tests.
    """
    if root is not None:
        r = Path(root).resolve()
        if (r / "tickets").is_dir():
            return r, r / "tickets", r / "archive", r / "BOARD.md", r / "VERSION"
        if (r / "flatmark" / "tickets").is_dir():
            return (
                r / "flatmark",
                r / "flatmark" / "tickets",
                r / "flatmark" / "archive",
                r / "flatmark" / "BOARD.md",
                r / "flatmark" / "VERSION",
            )
        return r, r / "tickets", r / "archive", r / "BOARD.md", r / "VERSION"

    t_path = Path(tickets_dir)
    if (
        archive_dir == str(DEFAULT_BASE_DIR / "archive")
        and tickets_dir != str(DEFAULT_BASE_DIR / "tickets")
    ):
        a_path = t_path.parent / "archive"
    else:
        a_path = Path(archive_dir)

    return (
        Path(base_dir),
        t_path,
        a_path,
        Path(board_path),
        Path(version_path),
    )


def load_tickets(tickets_directory: Path) -> dict[str, Ticket]:
    """Load and parse all ticket files from the tickets directory.

    Raises FileNotFoundError if tickets_directory does not exist.
    """
    if not tickets_directory.is_dir():
        raise FileNotFoundError(f"{tickets_directory} not found.")

    tickets_by_key: dict[str, Ticket] = {}
    id_to_keys: dict[str, list[str]] = {}

    for file_path in sorted(
        tickets_directory.glob("*.md"), key=lambda p: natural_sort_key(p.name)
    ):
        try:
            content = file_path.read_text(encoding="utf-8")
        except OSError:
            continue

        yaml_data = parse_yaml(content)
        if not yaml_data:
            print(
                f"Warning: {file_path.name} has missing or invalid YAML frontmatter; skipping.",
                file=sys.stderr,
            )
            continue

        title_match = re.search(r"^#\s+(.*)", content, re.MULTILINE)
        raw_title = title_match.group(1).strip() if title_match else file_path.name
        title = escape_cell(raw_title)

        expected_id = file_path.stem
        raw_id = yaml_data.get("id") or expected_id
        if raw_id != expected_id:
            print(
                f"Warning: {file_path.name} has frontmatter id '{raw_id}' (expected '{expected_id}').",
                file=sys.stderr,
            )
        ticket_id = escape_cell(raw_id)

        status = escape_cell(yaml_data.get("status", "Todo"))
        priority = escape_cell(yaml_data.get("priority", "P2"))
        blocked_by = escape_cell(yaml_data.get("blocked by", ""))
        parent = escape_cell(yaml_data.get("parent", ""))

        if "Todo" in status and "⏳" not in status:
            status = f"⏳ {status}"

        key = file_path.stem
        ticket = Ticket(
            key=key,
            id=ticket_id,
            title=title,
            priority=priority,
            blocked_by=blocked_by,
            parent=parent,
            status=status,
            filename=file_path.name,
        )
        tickets_by_key[key] = ticket
        id_to_keys.setdefault(ticket_id, []).append(key)

    for tid, keys in id_to_keys.items():
        if len(keys) > 1:
            files = ", ".join(f"{k}.md" for k in keys)
            print(
                f"Warning: Duplicate ticket ID '{tid}' in {files}.",
                file=sys.stderr,
            )

    return tickets_by_key


def build_tree(tickets_by_key: dict[str, Ticket]) -> list[Ticket]:
    """Resolve parent hierarchy and order tickets in a depth-first tree structure."""
    id_to_keys: dict[str, list[str]] = {}
    for key, ticket in tickets_by_key.items():
        id_to_keys.setdefault(ticket.id, []).append(key)

    parent_of: dict[str, str] = {}
    for key, ticket in tickets_by_key.items():
        raw_parent = ticket.parent
        if not raw_parent:
            continue
        parent_key: str | None = None
        if raw_parent in id_to_keys:
            parent_key = id_to_keys[raw_parent][0]
        elif raw_parent in tickets_by_key:
            parent_key = raw_parent

        if parent_key == key:
            print(
                f"Warning: Ticket '{ticket.id}' ({ticket.filename}) is its own parent; rendering as root.",
                file=sys.stderr,
            )
            continue
        if parent_key is not None:
            parent_of[key] = parent_key

    # Detect cycles in parent chain
    in_cycle: set[str] = set()
    for key in tickets_by_key:
        seen: list[str] = []
        seen_set: set[str] = set()
        curr: str | None = key
        while curr in parent_of:
            if curr in seen_set:
                cycle_start = seen.index(curr)
                for c in seen[cycle_start:]:
                    in_cycle.add(c)
                break
            seen.append(curr)
            seen_set.add(curr)
            curr = parent_of[curr]

    if in_cycle:
        cycle_ids = ", ".join(
            sorted(
                (tickets_by_key[k].id for k in in_cycle),
                key=natural_sort_key,
            )
        )
        print(
            f"Warning: Parent cycle detected among tickets: {cycle_ids}; rendering as roots.",
            file=sys.stderr,
        )
        for k in in_cycle:
            parent_of.pop(k, None)

    parent_to_children: dict[str, list[str]] = {}
    for key, pkey in parent_of.items():
        parent_to_children.setdefault(pkey, []).append(key)

    # Sort children naturally
    for p in parent_to_children:
        parent_to_children[p].sort(
            key=lambda k: natural_sort_key(tickets_by_key[k].id)
        )

    # Find root tickets (no resolved parent)
    roots = [key for key in tickets_by_key if key not in parent_of]
    roots.sort(key=lambda k: natural_sort_key(tickets_by_key[k].id))

    tickets_data: list[Ticket] = []
    visited: set[str] = set()

    def traverse(key: str, prefix: str = "") -> None:
        if key in visited:
            return
        visited.add(key)
        ticket = tickets_by_key[key]
        children = parent_to_children.get(key, [])

        display_title = f"[{ticket.id}] {ticket.title}"
        if prefix:
            display_title = f"{prefix}{display_title}"

        ticket_with_display = replace(ticket, display_title=display_title)
        tickets_data.append(ticket_with_display)

        for i, child_key in enumerate(children):
            is_last = i == len(children) - 1
            connector = "└── " if is_last else "├── "
            child_prefix = (
                prefix.replace("├── ", "│   ").replace("└── ", "    ") + connector
            )
            traverse(child_key, child_prefix)

    for r in roots:
        traverse(r)

    # Safety fallback: ensure every loaded ticket is rendered
    for key in sorted(
        tickets_by_key, key=lambda k: natural_sort_key(tickets_by_key[k].id)
    ):
        if key not in visited:
            traverse(key)

    return tickets_data


def find_ticket_locations(
    tickets_directory: Path,
    archive_directory: Path | None = None,
    loaded_tickets: dict[str, Ticket] | None = None,
) -> dict[str, str]:
    """Map ticket IDs and file stems to relative Markdown paths from the board.

    Looks in tickets_directory (e.g. 'tickets/foo.md') and archive_directory
    (e.g. 'archive/bar.md'). Active tickets take precedence over archived tickets.
    """
    locations: dict[str, str] = {}

    if archive_directory is not None and archive_directory.is_dir():
        for file_path in sorted(
            archive_directory.glob("*.md"), key=lambda p: natural_sort_key(p.name)
        ):
            locations[file_path.stem] = f"archive/{file_path.name}"
            try:
                content = file_path.read_text(encoding="utf-8")
                yaml_data = parse_yaml(content)
                tid = yaml_data.get("id")
                if tid:
                    locations[tid] = f"archive/{file_path.name}"
            except OSError:
                pass

    if loaded_tickets is not None:
        for ticket in loaded_tickets.values():
            locations[ticket.id] = f"tickets/{ticket.filename}"
            locations[ticket.key] = f"tickets/{ticket.filename}"
    elif tickets_directory.is_dir():
        for file_path in sorted(
            tickets_directory.glob("*.md"), key=lambda p: natural_sort_key(p.name)
        ):
            locations[file_path.stem] = f"tickets/{file_path.name}"
            try:
                content = file_path.read_text(encoding="utf-8")
                yaml_data = parse_yaml(content)
                tid = yaml_data.get("id")
                if tid:
                    locations[tid] = f"tickets/{file_path.name}"
            except OSError:
                pass

    return locations


def render_board(
    tickets: Sequence[Ticket],
    version: str | None = None,
    ticket_locations: dict[str, str] | None = None,
) -> str:
    """Pure function to render the Markdown table content for BOARD.md."""
    if ticket_locations is None:
        ticket_locations = {
            ticket.id: f"tickets/{ticket.filename}" for ticket in tickets
        }
        ticket_locations.update(
            {ticket.key: f"tickets/{ticket.filename}" for ticket in tickets}
        )

    board_lines = [
        "# Ticket Board",
        "",
        "| Ticket | Priority | Blocked by | Status |",
        "| :--- | :---: | :---: | :--- |",
    ]
    for ticket in tickets:
        link = f"tickets/{ticket.filename}"
        blocked_by = ticket.blocked_by
        if blocked_by:
            blocker_keys = [b.strip() for b in blocked_by.split(",") if b.strip()]
            rendered_blockers: list[str] = []
            for b in blocker_keys:
                if b in ticket_locations:
                    rendered_blockers.append(
                        f"[{escape_pipes(b)}]({ticket_locations[b]})"
                    )
                else:
                    print(
                        f"Warning: Blocker ticket '{b}' not found; rendering as plain text.",
                        file=sys.stderr,
                    )
                    rendered_blockers.append(escape_cell(b))
            blocked_link = ", ".join(rendered_blockers)
        else:
            blocked_link = ""

        row = (
            f"| [{escape_pipes(ticket.display_title)}]({link}) | "
            f"{escape_cell(ticket.priority)} | {blocked_link} | "
            f"{escape_cell(ticket.status)} |"
        )
        board_lines.append(row)

    if version and version != "unknown":
        board_lines.append("")
        board_lines.append("---")
        board_lines.append(f"*Generated with FlatMark v{version}*")

    return "\n".join(board_lines)


def write_board(destination: Path, content: str) -> None:
    """Write content to destination path atomically using a temporary file."""
    destination.parent.mkdir(parents=True, exist_ok=True)
    temp_file = tempfile.NamedTemporaryFile(
        dir=destination.parent,
        prefix=f".{destination.name}.",
        suffix=".tmp",
        delete=False,
        mode="w",
        encoding="utf-8",
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


def update_board(
    root: Path | str | None = None, check: bool = False
) -> bool:
    """Regenerate or verify BOARD.md ticket board.

    Returns True if board is successfully updated (or in check mode, is up to date).
    Returns False on error or if out of date in check mode.
    """
    # Allow calling update_board(True) as shorthand for check=True
    if isinstance(root, bool):
        check = root
        root = None

    r_base, r_tickets, r_archive, r_board, r_version = _resolve_paths(root)

    try:
        tickets_by_key = load_tickets(r_tickets)
    except FileNotFoundError as e:
        print(f"Error: {e}", file=sys.stderr)
        return False

    tree = build_tree(tickets_by_key)
    version = get_version(r_version)
    ticket_locations = find_ticket_locations(
        tickets_directory=r_tickets,
        archive_directory=r_archive,
        loaded_tickets=tickets_by_key,
    )
    board_content = render_board(
        tree,
        version=version,
        ticket_locations=ticket_locations,
    )

    if check:
        if not r_board.is_file():
            print(
                f"Error: {r_board} does not exist. Run board.py to generate it.",
                file=sys.stderr,
            )
            return False
        try:
            existing_content = r_board.read_text(encoding="utf-8")
        except OSError as e:
            print(f"Error: Could not read {r_board}: {e}", file=sys.stderr)
            return False

        if existing_content.strip() != board_content.strip():
            print(
                f"Error: {r_board} is out of date. Run 'python3 flatmark/board.py' to update it.",
                file=sys.stderr,
            )
            return False

        print(f"{r_board} is up to date.")
        return True

    try:
        write_board(r_board, board_content)
    except OSError as e:
        print(f"Error: Could not write {r_board}: {e}", file=sys.stderr)
        return False

    print(f"Successfully updated {r_board} with {len(tree)} tickets.")
    return True


def build_arg_parser() -> argparse.ArgumentParser:
    """Build the argument parser for the board CLI."""
    parser = argparse.ArgumentParser(
        prog="board.py",
        description="Regenerate or verify BOARD.md ticket board.",
    )
    parser.add_argument(
        "--check",
        "-c",
        action="store_true",
        help="Check if BOARD.md is up to date without modifying it",
    )
    parser.add_argument(
        "-v",
        "--version",
        action="version",
        version=f"FlatMark v{get_version()}",
        help="Show version",
    )
    parser.add_argument(
        "root",
        nargs="?",
        default=None,
        help="Target directory containing flatmark (default: detected from script)",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    """CLI entry point for board.py."""
    parser = build_arg_parser()
    args = parser.parse_args(argv)
    success = update_board(root=args.root, check=args.check)
    return 0 if success else 1


if __name__ == "__main__":
    sys.exit(main())
