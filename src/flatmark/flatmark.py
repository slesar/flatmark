#!/usr/bin/env python3
"""
FlatMark CLI: Unified entry point for FlatMark ticket management.
"""
import argparse
import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

base_dir = os.path.dirname(os.path.abspath(__file__))
if base_dir not in sys.path:
    sys.path.insert(0, base_dir)

import board
import new


class LintIssue:
    def __init__(self, file_path, line, message, fixable=False):
        self.file_path = file_path
        self.line = int(line)
        self.message = message
        self.fixable = fixable

    def __str__(self):
        return f"{self.file_path}:{self.line}: {self.message}"

    def __repr__(self):
        return f"LintIssue({self.file_path!r}, {self.line}, {self.message!r}, fixable={self.fixable})"


def find_flatmark_dir(target=None):
    """Resolve the directory containing tickets/ and archive/."""
    if target:
        p = os.path.abspath(target)
        if os.path.isdir(os.path.join(p, "tickets")):
            return p
        if os.path.isdir(os.path.join(p, "flatmark", "tickets")):
            return os.path.join(p, "flatmark")
        return p

    script_dir = os.path.dirname(os.path.abspath(__file__))
    if os.path.isdir(os.path.join(script_dir, "tickets")):
        return script_dir

    cwd = os.getcwd()
    if os.path.isdir(os.path.join(cwd, "flatmark", "tickets")):
        return os.path.join(cwd, "flatmark")
    if os.path.isdir(os.path.join(cwd, "tickets")):
        return cwd

    return script_dir


def find_parent_cycles(parent_map):
    """Detect cycles in parent relationships.

    Returns dict mapping ticket_id to list representing the cycle path.
    """
    cycles = {}
    for start_id in parent_map:
        visited = []
        visited_set = set()
        curr = start_id
        while curr in parent_map:
            if curr in visited_set:
                idx = visited.index(curr)
                cycle = visited[idx:] + [curr]
                if start_id in cycle:
                    cycles[start_id] = cycle
                break
            visited.append(curr)
            visited_set.add(curr)
            curr = parent_map[curr]
    return cycles


def lint_tickets(flatmark_dir=None, fix=False, print_fn=print):
    """Validate all tickets in tickets/ and archive/.

    Returns (issues, fixed_count).
    """
    flatmark_dir = find_flatmark_dir(flatmark_dir)
    tickets_dir = os.path.join(flatmark_dir, "tickets")
    archive_dir = os.path.join(flatmark_dir, "archive")

    if not os.path.isdir(tickets_dir):
        print_fn(f"Error: Tickets directory not found at {tickets_dir}", file=sys.stderr)
        return [LintIssue(tickets_dir, 1, "Tickets directory not found")], 0

    fixed_count = 0
    moved_files = False

    def get_rel_path(p):
        try:
            cwd_abs = os.path.abspath(os.getcwd())
            p_abs = os.path.abspath(p)
            common = os.path.commonpath([p_abs, cwd_abs])
            if common == cwd_abs:
                return os.path.relpath(p, os.getcwd())
        except (ValueError, OSError):
            pass

        try:
            fdir_abs = os.path.abspath(flatmark_dir)
            p_abs = os.path.abspath(p)
            common = os.path.commonpath([p_abs, fdir_abs])
            if common == fdir_abs:
                return os.path.relpath(p, flatmark_dir)
        except (ValueError, OSError):
            pass

        return p

    # If --fix is requested, run auto-fixes first
    if fix:
        os.makedirs(archive_dir, exist_ok=True)
        # Check tickets in tickets/ that should be in archive/
        for filename in sorted(os.listdir(tickets_dir), key=board.natural_sort_key):
            if not filename.endswith(".md"):
                continue
            fpath = os.path.join(tickets_dir, filename)
            try:
                with open(fpath, "r", encoding="utf-8") as f:
                    content = f.read()
            except OSError:
                continue

            yaml_data = board.parse_yaml(content)
            status = yaml_data.get("status", "Todo").replace("⏳", "").strip()
            if status in ("Done", "Obsolete"):
                dest = os.path.join(archive_dir, filename)
                if not os.path.exists(dest):
                    shutil.move(fpath, dest)
                    print_fn(f"Fixed: moved {get_rel_path(fpath)} -> {get_rel_path(dest)}")
                    fixed_count += 1
                    moved_files = True
                else:
                    print_fn(f"Warning: Cannot move {filename} to archive/: destination already exists", file=sys.stderr)

        # Check tickets in archive/ that should be in tickets/
        if os.path.isdir(archive_dir):
            for filename in sorted(os.listdir(archive_dir), key=board.natural_sort_key):
                if not filename.endswith(".md"):
                    continue
                fpath = os.path.join(archive_dir, filename)
                try:
                    with open(fpath, "r", encoding="utf-8") as f:
                        content = f.read()
                except OSError:
                    continue

                yaml_data = board.parse_yaml(content)
                status = yaml_data.get("status", "Todo").replace("⏳", "").strip()
                if status in ("Todo", "In Progress"):
                    dest = os.path.join(tickets_dir, filename)
                    if not os.path.exists(dest):
                        shutil.move(fpath, dest)
                        print_fn(f"Fixed: moved {get_rel_path(fpath)} -> {get_rel_path(dest)}")
                        fixed_count += 1
                        moved_files = True
                    else:
                        print_fn(f"Warning: Cannot move {filename} to tickets/: destination already exists", file=sys.stderr)

        # Check missing or mismatched ID
        for folder in (tickets_dir, archive_dir):
            if not os.path.isdir(folder):
                continue
            for filename in sorted(os.listdir(folder), key=board.natural_sort_key):
                if not filename.endswith(".md"):
                    continue
                fpath = os.path.join(folder, filename)
                try:
                    with open(fpath, "r", encoding="utf-8") as f:
                        content = f.read()
                except OSError:
                    continue

                lines = content.splitlines()
                if not lines or lines[0].strip() != "---":
                    continue

                expected_id = filename[:-3]
                closing_idx = -1
                for i in range(1, len(lines)):
                    if lines[i].strip() == "---":
                        closing_idx = i
                        break
                if closing_idx == -1:
                    continue

                id_line_idx = -1
                cur_id = None
                for i in range(1, closing_idx):
                    line_s = lines[i].strip()
                    if line_s.startswith("id:"):
                        id_line_idx = i
                        cur_id = line_s.split(":", 1)[1].strip()
                        if len(cur_id) >= 2 and ((cur_id.startswith('"') and cur_id.endswith('"')) or (cur_id.startswith("'") and cur_id.endswith("'"))):
                            cur_id = cur_id[1:-1].strip()
                        break

                if id_line_idx == -1:
                    new_lines = [lines[0], f"id: {expected_id}"] + lines[1:]
                    with open(fpath, "w", encoding="utf-8", newline="\n") as f:
                        f.write("\n".join(new_lines) + ("\n" if content.endswith("\n") else ""))
                    print_fn(f"Fixed: added 'id: {expected_id}' to {get_rel_path(fpath)}")
                    fixed_count += 1
                elif cur_id != expected_id:
                    new_lines = list(lines)
                    new_lines[id_line_idx] = f"id: {expected_id}"
                    with open(fpath, "w", encoding="utf-8", newline="\n") as f:
                        f.write("\n".join(new_lines) + ("\n" if content.endswith("\n") else ""))
                    print_fn(f"Fixed: updated id to '{expected_id}' in {get_rel_path(fpath)}")
                    fixed_count += 1

        # Synchronize board if any tickets were moved
        if moved_files:
            board_script = os.path.join(flatmark_dir, "board.py")
            if os.path.isfile(board_script):
                try:
                    subprocess.run([sys.executable, board_script], check=True, capture_output=True)
                except subprocess.SubprocessError:
                    pass

    # Now perform full validation pass
    issues = []
    parsed_tickets = []
    id_to_tickets = {}

    folders = [("tickets", tickets_dir)]
    if os.path.isdir(archive_dir):
        folders.append(("archive", archive_dir))

    for folder_name, folder_path in folders:
        for filename in sorted(os.listdir(folder_path), key=board.natural_sort_key):
            if not filename.endswith(".md"):
                continue

            abs_path = os.path.join(folder_path, filename)
            rel_path = get_rel_path(abs_path)
            expected_id = filename[:-3]

            try:
                with open(abs_path, "r", encoding="utf-8") as f:
                    content = f.read()
            except OSError as e:
                issues.append(LintIssue(rel_path, 1, f"Could not read file: {e}"))
                continue

            lines = content.splitlines()

            # 1. Missing or invalid frontmatter
            if not lines or lines[0].strip() != "---":
                issues.append(LintIssue(rel_path, 1, "missing YAML frontmatter (file must begin with '---')"))
                continue

            closing_idx = -1
            for i in range(1, len(lines)):
                if lines[i].strip() == "---":
                    closing_idx = i
                    break

            if closing_idx == -1:
                issues.append(LintIssue(rel_path, 1, "unclosed YAML frontmatter (missing closing '---')"))
                continue

            yaml_data = {}
            field_lines = {}
            has_syntax_error = False

            for i in range(1, closing_idx):
                line_str = lines[i]
                stripped = line_str.strip()
                if not stripped or stripped.startswith("#"):
                    continue
                if ":" not in stripped:
                    issues.append(LintIssue(rel_path, i + 1, f"invalid YAML frontmatter line: '{stripped}' (expected 'key: value')"))
                    has_syntax_error = True
                    continue
                key, val = stripped.split(":", 1)
                key = key.strip()
                val = val.strip()
                if len(val) >= 2 and ((val.startswith('"') and val.endswith('"')) or (val.startswith("'") and val.endswith("'"))):
                    val = val[1:-1].strip()
                yaml_data[key] = val
                field_lines[key] = i + 1

            # 2. Missing id, or id != filename
            ticket_id = yaml_data.get("id")
            if not ticket_id:
                issues.append(LintIssue(rel_path, 1, "missing 'id' in frontmatter", fixable=True))
            elif ticket_id != expected_id:
                id_line = field_lines.get("id", 1)
                issues.append(LintIssue(rel_path, id_line, f"ticket id '{ticket_id}' does not match filename '{filename}'", fixable=True))

            effective_id = ticket_id or expected_id

            # 3. Unknown priority values
            if "priority" in yaml_data:
                priority = yaml_data["priority"]
                if priority not in ("P0", "P1", "P2", "P3"):
                    p_line = field_lines.get("priority", 1)
                    issues.append(LintIssue(rel_path, p_line, f"unknown priority '{priority}' (allowed: P0, P1, P2, P3)"))

            # 4. Unknown status values
            raw_status = yaml_data.get("status", "Todo")
            norm_status = raw_status.replace("⏳", "").strip()
            if norm_status not in ("Todo", "In Progress", "Done", "Obsolete"):
                s_line = field_lines.get("status", 1)
                issues.append(LintIssue(rel_path, s_line, f"unknown status '{raw_status}' (allowed: Todo, In Progress, Done, Obsolete)"))

            # 5. Done/Obsolete in tickets/ or Todo/In Progress in archive/
            if folder_name == "tickets" and norm_status in ("Done", "Obsolete"):
                s_line = field_lines.get("status", 1)
                issues.append(LintIssue(rel_path, s_line, f"ticket with status '{raw_status}' should be in archive/", fixable=True))
            elif folder_name == "archive" and norm_status in ("Todo", "In Progress"):
                s_line = field_lines.get("status", 1)
                issues.append(LintIssue(rel_path, s_line, f"ticket with status '{raw_status}' should be in tickets/", fixable=True))

            ticket_info = {
                "rel_path": rel_path,
                "abs_path": abs_path,
                "filename": filename,
                "expected_id": expected_id,
                "id": effective_id,
                "yaml_data": yaml_data,
                "field_lines": field_lines,
                "folder": folder_name,
            }
            parsed_tickets.append(ticket_info)
            id_to_tickets.setdefault(effective_id, []).append(ticket_info)

    # 6. Duplicate IDs (B9)
    for tid, tlist in id_to_tickets.items():
        if len(tlist) > 1:
            for item in tlist:
                others = [o["rel_path"] for o in tlist if o != item]
                id_line = item["field_lines"].get("id", 1)
                issues.append(LintIssue(
                    item["rel_path"],
                    id_line,
                    f"duplicate ticket ID '{tid}' (also defined in {', '.join(others)})"
                ))

    # All known ticket IDs
    all_known_ids = set(id_to_tickets.keys()) | {t["expected_id"] for t in parsed_tickets}

    # 7. Parent/blocker references to non-existent tickets & self-parents
    parent_map = {}
    for item in parsed_tickets:
        yaml_data = item["yaml_data"]
        tid = item["id"]
        rel_path = item["rel_path"]

        # Validate parent
        if "parent" in yaml_data and yaml_data["parent"]:
            parent_val = yaml_data["parent"]
            p_line = item["field_lines"].get("parent", 1)
            if parent_val == tid:
                issues.append(LintIssue(rel_path, p_line, "ticket cannot be its own parent"))
            elif parent_val not in all_known_ids:
                issues.append(LintIssue(rel_path, p_line, f"parent ticket '{parent_val}' does not exist"))
            else:
                parent_map[tid] = parent_val

        # Validate blocked by
        if "blocked by" in yaml_data and yaml_data["blocked by"]:
            blocked_val = yaml_data["blocked by"]
            b_line = item["field_lines"].get("blocked by", 1)
            blockers = [b.strip() for b in blocked_val.split(",") if b.strip()]
            for b in blockers:
                if b == tid:
                    issues.append(LintIssue(rel_path, b_line, "ticket cannot block itself"))
                elif b not in all_known_ids:
                    issues.append(LintIssue(rel_path, b_line, f"blocker ticket '{b}' does not exist"))

    # 8. Parent cycles (B1)
    cycles = find_parent_cycles(parent_map)
    for tid, cycle in cycles.items():
        tlist = id_to_tickets.get(tid, [])
        for item in tlist:
            p_line = item["field_lines"].get("parent", 1)
            cycle_str = " -> ".join(cycle)
            issues.append(LintIssue(
                item["rel_path"],
                p_line,
                f"parent cycle detected: {cycle_str}"
            ))

    # Sort issues deterministically
    issues.sort(key=lambda x: (board.natural_sort_key(x.file_path), x.line, x.message))
    return issues, fixed_count


def lint_main(argv=None):
    if argv is None:
        argv = sys.argv[1:]

    fix = False
    target = None

    for arg in argv:
        if arg == "--fix":
            fix = True
        elif arg in ("-h", "--help"):
            print("Usage: flatmark.py lint [--fix] [target_path]")
            print("\nValidate ticket frontmatter, filenames, dependencies, and lifecycle status.")
            print("\nOptions:")
            print("  --fix    Automatically resolve safe issues (move Done tickets to archive, fix IDs)")
            print("  -h, --help  Show this help message")
            return 0
        elif not arg.startswith("-"):
            target = arg

    issues, fixed_count = lint_tickets(flatmark_dir=target, fix=fix)

    if issues:
        for issue in issues:
            print(issue)
        if fix:
            print(f"\n{len(issues)} issue(s) remain that could not be auto-fixed.", file=sys.stderr)
        else:
            print(f"\nFound {len(issues)} issue(s). Run with '--fix' to auto-resolve safe issues.", file=sys.stderr)
        return 1

    if fix and fixed_count > 0:
        print(f"\nAll fixable issues resolved ({fixed_count} fix(es) applied). No remaining issues.")
    else:
        print("No issues found.")
    return 0


def parse_ticket_file(
    file_path: Path, base_dir: Path | None = None
) -> dict[str, Any]:
    """Parse a ticket Markdown file into a dictionary representation."""
    content = file_path.read_text(encoding="utf-8")
    yaml_data = board.parse_yaml(content)

    title = ""
    for line in content.splitlines():
        line = line.strip()
        if line.startswith("# ") and not line.startswith("## "):
            title = line[2:].strip()
            break

    body = ""
    m = re.match(r"^---[ \t]*\r?\n.*?\r?\n---[ \t]*(?:\r?\n|$)(.*)", content, re.DOTALL)
    if m:
        body = m.group(1).strip()
    else:
        body = content.strip()

    tid = yaml_data.get("id") or file_path.stem
    priority = yaml_data.get("priority", "P2").strip()
    status = yaml_data.get("status", "Todo").strip()
    parent = yaml_data.get("parent", "").strip() or None
    blocked_by = yaml_data.get("blocked by", "").strip() or None

    is_archived = file_path.parent.name == "archive"

    if base_dir:
        try:
            rel_path = str(file_path.relative_to(base_dir))
        except ValueError:
            rel_path = f"{file_path.parent.name}/{file_path.name}"
    else:
        rel_path = f"{file_path.parent.name}/{file_path.name}"

    return {
        "id": tid,
        "title": title,
        "status": status,
        "priority": priority,
        "parent": parent,
        "blocked_by": blocked_by,
        "archived": is_archived,
        "path": rel_path,
        "body": body,
    }


def find_ticket_file(
    ticket_id: str, root: Path | str | None = None
) -> tuple[Path | None, bool]:
    """Find a ticket file by its ID or stem in tickets/ or archive/.

    Returns (file_path, is_archived). Active tickets take precedence.
    """
    _, tickets_dir, archive_dir, _, _ = board._resolve_paths(root)

    # Check tickets_dir first
    if tickets_dir.is_dir():
        direct = tickets_dir / f"{ticket_id}.md"
        if direct.is_file():
            return direct, False
        for f in tickets_dir.glob("*.md"):
            if f.stem.lower() == ticket_id.lower():
                return f, False
            try:
                data = board.parse_yaml(f.read_text(encoding="utf-8"))
                if data.get("id", "").strip().lower() == ticket_id.lower():
                    return f, False
            except OSError:
                pass

    # Check archive_dir
    if archive_dir.is_dir():
        direct = archive_dir / f"{ticket_id}.md"
        if direct.is_file():
            return direct, True
        for f in archive_dir.glob("*.md"):
            if f.stem.lower() == ticket_id.lower():
                return f, True
            try:
                data = board.parse_yaml(f.read_text(encoding="utf-8"))
                if data.get("id", "").strip().lower() == ticket_id.lower():
                    return f, True
            except OSError:
                pass

    return None, False


def set_ticket_status_in_content(content: str, new_status: str) -> str:
    """Update or insert status in the YAML frontmatter of ticket content."""
    m = re.match(r"^---[ \t]*\r?\n(.*?)\r?\n---[ \t]*(?:\r?\n|$)", content, re.DOTALL)
    if not m:
        return f"---\nstatus: {new_status}\n---\n{content}"

    yaml_block = m.group(1)
    rest_of_file = content[m.end():]
    lines = yaml_block.splitlines()
    status_updated = False
    new_lines = []
    for line in lines:
        if re.match(r"^\s*status\s*:", line, re.IGNORECASE):
            new_lines.append(f"status: {new_status}")
            status_updated = True
        else:
            new_lines.append(line)
    if not status_updated:
        new_lines.append(f"status: {new_status}")

    new_yaml = "\n".join(new_lines)
    return f"---\n{new_yaml}\n---\n{rest_of_file}"


def cmd_new(argv: list[str], root: Path | str | None = None) -> int:
    """Create a new ticket template and regenerate board."""
    parser = argparse.ArgumentParser(
        prog="flatmark new",
        description="Create a new FlatMark ticket template.",
        usage="flatmark new [T|B|F|S|R|D] <Ticket Title> [--parent ID] [--blocked-by ID] [--priority P] [--scheme sequential|random]",
    )
    parser.add_argument("prefix", nargs="?", default=None, help="Ticket prefix: T, B, F, S, R, D")
    parser.add_argument("title", nargs="*", default=[], help="Ticket title")
    parser.add_argument("--parent", default=None, help="Parent ticket ID")
    parser.add_argument("--blocked-by", default=None, help="Blocking ticket ID(s)")
    parser.add_argument("--priority", default="P2", help="Priority (P0, P1, P2, P3)")
    parser.add_argument("--scheme", default="sequential", help="ID generation scheme (sequential, random)")
    parser.add_argument("--random", action="store_const", dest="scheme", const="random", help="Shortcut for --scheme random")
    parser.add_argument("--sequential", action="store_const", dest="scheme", const="sequential", help="Shortcut for --scheme sequential")

    args = parser.parse_args(argv)
    if not args.prefix:
        parser.print_usage(file=sys.stderr)
        return 2

    prefix = args.prefix.strip().upper()
    if prefix not in new.VALID_PREFIXES:
        print(
            "Error: Prefix must be T (Task), or B (Bug), F (Feature), S (Spike), R (Release), D (Documentation)",
            file=sys.stderr,
        )
        return 2

    title = " ".join(args.title) if args.title else "New Ticket"
    try:
        next_id, file_path = new.create_ticket(
            prefix=prefix,
            title=title,
            scheme=args.scheme,
            root=root,
            priority=args.priority,
            parent=args.parent,
            blocked_by=args.blocked_by,
        )
    except ValueError as e:
        print(f"Error: {e}", file=sys.stderr)
        return 2
    except FileExistsError as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1
    except (OSError, RuntimeError) as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1

    print(f"Created ticket: {next_id} ({file_path})")
    return 0


def cmd_start(ticket_id: str, root: Path | str | None = None) -> int:
    """Mark ticket as In Progress and regenerate board."""
    r_base, r_tickets, _, _, _ = board._resolve_paths(root)
    file_path, is_archived = find_ticket_file(ticket_id, root=r_base)
    if file_path is None:
        print(f"Error: Ticket '{ticket_id}' not found.", file=sys.stderr)
        return 1

    content = file_path.read_text(encoding="utf-8")
    new_content = set_ticket_status_in_content(content, "In Progress")

    target_path = r_tickets / file_path.name
    if is_archived:
        r_tickets.mkdir(parents=True, exist_ok=True)
        new.atomic_write(target_path, new_content)
        file_path.unlink()
    else:
        new.atomic_write(file_path, new_content)

    board.update_board(root=r_base)
    print(f"Started {ticket_id}: status set to In Progress.")
    return 0


def cmd_done(ticket_id: str, root: Path | str | None = None) -> int:
    """Mark ticket as Done, move to archive/, and regenerate board."""
    r_base, _, r_archive, _, _ = board._resolve_paths(root)
    file_path, is_archived = find_ticket_file(ticket_id, root=r_base)
    if file_path is None:
        print(f"Error: Ticket '{ticket_id}' not found.", file=sys.stderr)
        return 1

    content = file_path.read_text(encoding="utf-8")
    new_content = set_ticket_status_in_content(content, "Done")

    r_archive.mkdir(parents=True, exist_ok=True)
    target_path = r_archive / file_path.name
    new.atomic_write(target_path, new_content)
    if not is_archived and file_path.resolve() != target_path.resolve():
        file_path.unlink()

    board.update_board(root=r_base)
    print(f"Completed {ticket_id}: status set to Done and moved to archive.")
    return 0


def cmd_obsolete(ticket_id: str, root: Path | str | None = None) -> int:
    """Mark ticket as Obsolete, move to archive/, and regenerate board."""
    r_base, _, r_archive, _, _ = board._resolve_paths(root)
    file_path, is_archived = find_ticket_file(ticket_id, root=r_base)
    if file_path is None:
        print(f"Error: Ticket '{ticket_id}' not found.", file=sys.stderr)
        return 1

    content = file_path.read_text(encoding="utf-8")
    new_content = set_ticket_status_in_content(content, "Obsolete")

    r_archive.mkdir(parents=True, exist_ok=True)
    target_path = r_archive / file_path.name
    new.atomic_write(target_path, new_content)
    if not is_archived and file_path.resolve() != target_path.resolve():
        file_path.unlink()

    board.update_board(root=r_base)
    print(f"Retired {ticket_id}: status set to Obsolete and moved to archive.")
    return 0


def cmd_board(argv: list[str], root: Path | str | None = None) -> int:
    """Regenerate or verify BOARD.md ticket board."""
    if "--help" in argv or "-h" in argv:
        print("Usage: flatmark board [--check]")
        print("\nRegenerate or verify BOARD.md ticket board.")
        print("\nOptions:")
        print("  --check, -c    Check if BOARD.md is up to date without modifying it")
        print("  -h, --help     Show this help message")
        return 0

    check_mode = ("--check" in argv or "-c" in argv)
    success = board.update_board(root=root, check=check_mode)
    return 0 if success else 1


def cmd_show(argv: list[str], root: Path | str | None = None) -> int:
    """Display details of a ticket in text or JSON format."""
    parser = argparse.ArgumentParser(
        prog="flatmark show",
        description="Display details of a ticket.",
        usage="flatmark show <id> [--json]",
    )
    parser.add_argument("id", nargs="?", default=None, help="Ticket ID")
    parser.add_argument("--json", action="store_true", help="Output in JSON format")

    args = parser.parse_args(argv)
    if not args.id:
        parser.print_usage(file=sys.stderr)
        return 2

    r_base, _, _, _, _ = board._resolve_paths(root)
    file_path, _ = find_ticket_file(args.id, root=r_base)
    if file_path is None:
        print(f"Error: Ticket '{args.id}' not found.", file=sys.stderr)
        return 1

    ticket_data = parse_ticket_file(file_path, base_dir=r_base)
    if args.json:
        print(json.dumps(ticket_data, indent=2))
    else:
        print(f"ID:          {ticket_data['id']}")
        print(f"Title:       {ticket_data['title']}")
        print(f"Status:      {ticket_data['status']}")
        print(f"Priority:    {ticket_data['priority']}")
        print(f"Parent:      {ticket_data['parent'] or 'none'}")
        print(f"Blocked by:  {ticket_data['blocked_by'] or 'none'}")
        print(f"Path:        {ticket_data['path']}")
        print("")
        print(ticket_data["body"])
    return 0


def cmd_list(argv: list[str], root: Path | str | None = None) -> int:
    """Query backlog tickets without parsing Markdown."""
    parser = argparse.ArgumentParser(
        prog="flatmark list",
        description="Query tickets in backlog without parsing Markdown.",
        usage="flatmark list [--status S] [--priority P] [--all] [--json]",
    )
    parser.add_argument("--status", default=None, help="Filter by status (e.g. Todo, 'In Progress', Done, Obsolete)")
    parser.add_argument("--priority", default=None, help="Filter by priority (P0, P1, P2, P3)")
    parser.add_argument("--all", action="store_true", help="Include archived tickets")
    parser.add_argument("--json", action="store_true", help="Output in JSON format")

    args = parser.parse_args(argv)
    r_base, r_tickets, r_archive, _, _ = board._resolve_paths(root)

    include_archive = args.all or (
        args.status is not None and args.status.strip().lower() in ("done", "obsolete")
    )

    tickets: list[dict[str, Any]] = []

    if r_tickets.is_dir():
        for f in sorted(r_tickets.glob("*.md"), key=lambda p: board.natural_sort_key(p.name)):
            try:
                t = parse_ticket_file(f, base_dir=r_base)
                tickets.append(t)
            except OSError:
                pass

    if include_archive and r_archive.is_dir():
        for f in sorted(r_archive.glob("*.md"), key=lambda p: board.natural_sort_key(p.name)):
            try:
                t = parse_ticket_file(f, base_dir=r_base)
                tickets.append(t)
            except OSError:
                pass

    if args.status:
        target_status = args.status.strip().lower()
        tickets = [t for t in tickets if t["status"].lower() == target_status]

    if args.priority:
        target_pri = args.priority.strip().upper()
        tickets = [t for t in tickets if t["priority"].upper() == target_pri]

    pri_order = {"P0": 0, "P1": 1, "P2": 2, "P3": 3}
    tickets.sort(
        key=lambda t: (
            pri_order.get(t["priority"].upper(), 99),
            board.natural_sort_key(t["id"]),
        )
    )

    if args.json:
        list_payload = [
            {
                "id": t["id"],
                "title": t["title"],
                "status": t["status"],
                "priority": t["priority"],
                "parent": t["parent"],
                "blocked_by": t["blocked_by"],
                "archived": t["archived"],
                "path": t["path"],
            }
            for t in tickets
        ]
        print(json.dumps(list_payload, indent=2))
    else:
        if not tickets:
            print("No tickets found.")
            return 0
        header = f"{'ID':<8} {'PRIORITY':<9} {'STATUS':<13} {'BLOCKED BY':<12} {'TITLE'}"
        print(header)
        print("-" * max(len(header), 60))
        for t in tickets:
            blocked = t["blocked_by"] or ""
            print(f"{t['id']:<8} {t['priority']:<9} {t['status']:<13} {blocked:<12} {t['title']}")

    return 0


def cmd_next(argv: list[str], root: Path | str | None = None) -> int:
    """Find the highest-priority unblocked Todo ticket."""
    parser = argparse.ArgumentParser(
        prog="flatmark next",
        description="Find the highest-priority unblocked Todo ticket.",
        usage="flatmark next [--json]",
    )
    parser.add_argument("--json", action="store_true", help="Output in JSON format")

    args = parser.parse_args(argv)
    r_base, r_tickets, r_archive, _, _ = board._resolve_paths(root)

    if not r_tickets.is_dir():
        if args.json:
            print("null")
        else:
            print("No unblocked Todo tickets found.")
        return 0

    ticket_locations = board.find_ticket_locations(r_tickets, r_archive)

    candidates: list[dict[str, Any]] = []
    for f in r_tickets.glob("*.md"):
        try:
            t = parse_ticket_file(f, base_dir=r_base)
            if t["status"].lower() != "todo":
                continue
            blocked_by = t["blocked_by"] or ""
            if board._has_unresolved_blockers(blocked_by, ticket_locations):
                continue
            candidates.append(t)
        except OSError:
            pass

    if not candidates:
        if args.json:
            print("null")
        else:
            print("No unblocked Todo tickets found.")
        return 0

    pri_order = {"P0": 0, "P1": 1, "P2": 2, "P3": 3}
    candidates.sort(
        key=lambda t: (
            pri_order.get(t["priority"].upper(), 99),
            board.natural_sort_key(t["id"]),
        )
    )

    chosen = candidates[0]
    if args.json:
        print(json.dumps(chosen, indent=2))
    else:
        print("Next available ticket:")
        print(f"  ID:          {chosen['id']}")
        print(f"  Priority:    {chosen['priority']}")
        print(f"  Title:       {chosen['title']}")
        print(f"  Path:        {chosen['path']}")

    return 0


def print_help():
    print("""Usage: python3 flatmark.py <command> [options]

Commands:
  new <prefix> <title>    Create a new ticket template
  start <id>              Set ticket status to In Progress and update board
  done <id>               Set ticket status to Done, move to archive/, and update board
  obsolete <id>           Set ticket status to Obsolete, move to archive/, and update board
  board [--check]         Regenerate or verify BOARD.md ticket board
  list [options]          Query tickets without parsing Markdown
  next [--json]           Find the highest-priority unblocked Todo ticket
  show <id> [--json]      Display ticket details
  lint [--fix]            Validate ticket frontmatter, metadata, dependencies and status
  check [--fix]           Alias for 'lint'

Options:
  -v, --version           Show FlatMark version
  -h, --help              Show this help message
""")


def main(argv=None):
    if argv is None:
        argv = sys.argv[1:]

    if not argv or argv[0] in ("-h", "--help", "help"):
        print_help()
        return 0

    if argv[0] in ("-v", "--version"):
        print(f"FlatMark v{board.get_version()}")
        return 0

    command = argv[0].lower()
    sub_args = argv[1:]

    root = None
    if "--root" in sub_args:
        idx = sub_args.index("--root")
        if idx + 1 < len(sub_args):
            root = Path(sub_args[idx + 1])
            sub_args = sub_args[:idx] + sub_args[idx + 2 :]

    if command in ("lint", "check"):
        return lint_main(sub_args)
    elif command == "board":
        return cmd_board(sub_args, root=root)
    elif command == "new":
        return cmd_new(sub_args, root=root)
    elif command == "start":
        if not sub_args or sub_args[0] in ("-h", "--help"):
            print("Usage: flatmark start <ticket_id>")
            print("\nSet ticket status to In Progress and regenerate the board.")
            return 0 if sub_args and sub_args[0] in ("-h", "--help") else 2
        return cmd_start(sub_args[0], root=root)
    elif command == "done":
        if not sub_args or sub_args[0] in ("-h", "--help"):
            print("Usage: flatmark done <ticket_id>")
            print("\nSet ticket status to Done, move to archive/, and regenerate the board.")
            return 0 if sub_args and sub_args[0] in ("-h", "--help") else 2
        return cmd_done(sub_args[0], root=root)
    elif command == "obsolete":
        if not sub_args or sub_args[0] in ("-h", "--help"):
            print("Usage: flatmark obsolete <ticket_id>")
            print("\nSet ticket status to Obsolete, move to archive/, and regenerate the board.")
            return 0 if sub_args and sub_args[0] in ("-h", "--help") else 2
        return cmd_obsolete(sub_args[0], root=root)
    elif command == "list":
        return cmd_list(sub_args, root=root)
    elif command == "next":
        return cmd_next(sub_args, root=root)
    elif command == "show":
        return cmd_show(sub_args, root=root)
    else:
        print(f"Error: Unknown command '{command}'.", file=sys.stderr)
        print_help()
        return 2


if __name__ == "__main__":
    sys.exit(main())
