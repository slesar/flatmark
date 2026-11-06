#!/usr/bin/env python3
"""
FlatMark CLI: Unified entry point for FlatMark ticket management.
"""
import os
import re
import shutil
import subprocess
import sys

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


def print_help():
    print("""Usage: python3 flatmark.py <command> [options]

Commands:
  lint [--fix]    Validate ticket frontmatter, metadata, dependencies and status
  check [--fix]   Alias for 'lint'
  board           Regenerate BOARD.md
  new [args...]   Create a new ticket

Options:
  -v, --version   Show FlatMark version
  -h, --help      Show this help message
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

    if command in ("lint", "check"):
        return lint_main(sub_args)
    elif command == "board":
        success = board.update_board()
        return 0 if success else 1
    elif command == "new":
        new_script = os.path.join(base_dir, "new.py")
        proc = subprocess.run([sys.executable, new_script] + sub_args)
        return proc.returncode
    else:
        print(f"Error: Unknown command '{command}'.", file=sys.stderr)
        print_help()
        return 2


if __name__ == "__main__":
    sys.exit(main())
