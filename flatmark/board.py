#!/usr/bin/env python3
import os
import re
import sys

def slugify(text):
    # Convert header text to markdown link anchor format
    text = text.lower().strip()
    text = re.sub(r'[^\w\s-]', '', text)
    text = re.sub(r'[\s_-]+', '-', text)
    return f"#{text}"

def natural_sort_key(s):
    """Helper for alphanumeric sorting (e.g., B4 comes before B23)"""
    return [int(text) if text.isdigit() else text.lower()
            for text in re.split(r'(\d+)', s)]

def escape_pipes(text):
    """Escape pipe characters for markdown table compatibility."""
    if text is None:
        return ""
    return re.sub(r'(?<!\\)\|', r'\\|', str(text))

def escape_cell(text):
    """Normalize whitespace/newlines and escape pipe characters for markdown table cells."""
    if text is None:
        return ""
    text = " ".join(str(text).split())
    return escape_pipes(text)

# Path logic: ensure it works even when called from project root
base_dir = os.path.dirname(os.path.abspath(__file__))
tickets_dir = os.path.join(base_dir, "tickets")
board_path = os.path.join(base_dir, "BOARD.md")
version_path = os.path.join(base_dir, "VERSION")

def get_version():
    if os.path.exists(version_path):
        try:
            with open(version_path, "r", encoding="utf-8") as f:
                return f.read().strip()
        except OSError:
            pass
    return "unknown"

def parse_yaml(content):
    yaml_pattern = re.compile(r"^---[ \t]*\r?\n(.*?)\r?\n---[ \t]*(?:\r?\n|$)", re.DOTALL)
    match = yaml_pattern.search(content)
    if not match:
        return {}

    yaml_content = match.group(1)
    data = {}
    for line in yaml_content.splitlines():
        if ':' in line:
            key, value = line.split(':', 1)
            data[key.strip()] = value.strip()
    return data

def update_board():
    if not os.path.exists(tickets_dir):
        print(f"Error: {tickets_dir} not found.", file=sys.stderr)
        return False

    tickets_by_key = {}
    id_to_keys = {}
    parent_to_children = {}

    # Read and parse all tickets
    for filename in sorted(os.listdir(tickets_dir), key=natural_sort_key):
        if not filename.endswith(".md"):
            continue

        file_path = os.path.join(tickets_dir, filename)
        with open(file_path, "r", encoding="utf-8") as f:
            content = f.read()

        yaml_data = parse_yaml(content)
        if not yaml_data:
            print(f"Warning: {filename} has missing or invalid YAML frontmatter; skipping.", file=sys.stderr)
            continue

        # Extract title from the first level 1 header
        title_match = re.search(r"^#\s+(.*)", content, re.MULTILINE)
        title = title_match.group(1).strip() if title_match else filename
        title = escape_cell(title)

        expected_id = filename[:-3]
        ticket_id = yaml_data.get("id") or expected_id
        if ticket_id != expected_id:
            print(f"Warning: {filename} has frontmatter id '{ticket_id}' (expected '{expected_id}').", file=sys.stderr)
        ticket_id = escape_cell(ticket_id)

        status = escape_cell(yaml_data.get("status", "Todo"))
        priority = escape_cell(yaml_data.get("priority", "P2"))
        blocked_by = escape_cell(yaml_data.get("blocked by", ""))
        parent = escape_cell(yaml_data.get("parent", ""))

        # Add icon for 'Todo' status if not present
        if "Todo" in status and "⏳" not in status:
            status = f"⏳ {status}"

        key = filename[:-3]
        ticket_info = {
            "key": key,
            "id": ticket_id,
            "title": title,
            "priority": priority,
            "blocked_by": blocked_by,
            "parent": parent,
            "status": status,
            "filename": filename
        }
        tickets_by_key[key] = ticket_info
        id_to_keys.setdefault(ticket_id, []).append(key)

    for tid, keys in id_to_keys.items():
        if len(keys) > 1:
            files = ", ".join(f"{k}.md" for k in keys)
            print(f"Warning: Duplicate ticket ID '{tid}' in {files}.", file=sys.stderr)

    # Resolve parent references (by ID or filename stem) and detect self-parent
    parent_of = {}
    for key, info in tickets_by_key.items():
        raw_parent = info["parent"]
        if not raw_parent:
            continue
        parent_key = None
        if raw_parent in id_to_keys:
            parent_key = id_to_keys[raw_parent][0]
        elif raw_parent in tickets_by_key:
            parent_key = raw_parent

        if parent_key == key:
            print(f"Warning: Ticket '{info['id']}' ({info['filename']}) is its own parent; rendering as root.", file=sys.stderr)
            continue
        if parent_key is not None:
            parent_of[key] = parent_key

    # Detect cycles in parent chain
    in_cycle = set()
    for key in tickets_by_key:
        seen = []
        seen_set = set()
        curr = key
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
        cycle_ids = ", ".join(sorted((tickets_by_key[k]["id"] for k in in_cycle), key=natural_sort_key))
        print(f"Warning: Parent cycle detected among tickets: {cycle_ids}; rendering as roots.", file=sys.stderr)
        for k in in_cycle:
            parent_of.pop(k, None)

    for key, pkey in parent_of.items():
        parent_to_children.setdefault(pkey, []).append(key)

    # Sort children naturally
    for p in parent_to_children:
        parent_to_children[p].sort(key=lambda k: natural_sort_key(tickets_by_key[k]["id"]))

    # Find root tickets (no resolved parent)
    roots = [key for key in tickets_by_key if key not in parent_of]
    roots.sort(key=lambda k: natural_sort_key(tickets_by_key[k]["id"]))

    tickets_data = []
    visited = set()

    def traverse(key, prefix=""):
        if key in visited:
            return
        visited.add(key)
        ticket = tickets_by_key[key]
        children = parent_to_children.get(key, [])

        display_title = f"[{ticket['id']}] {ticket['title']}"
        if prefix:
            display_title = f"{prefix}{display_title}"

        ticket_row = ticket.copy()
        ticket_row["display_title"] = display_title
        tickets_data.append(ticket_row)

        for i, child_key in enumerate(children):
            is_last = (i == len(children) - 1)
            connector = "└── " if is_last else "├── "
            child_prefix = prefix.replace("├── ", "│   ").replace("└── ", "    ") + connector
            traverse(child_key, child_prefix)

    for r in roots:
        traverse(r)

    # Safety fallback: ensure every loaded ticket is rendered
    for key in sorted(tickets_by_key, key=lambda k: natural_sort_key(tickets_by_key[k]["id"])):
        if key not in visited:
            traverse(key)

    # Build Board Table
    board_lines = [
        "# Ticket Board",
        "",
        "| Ticket | Priority | Blocked by | Status |",
        "| :--- | :---: | :---: | :--- |"
    ]
    for ticket in tickets_data:
        # Link to the individual ticket file
        link = f"tickets/{ticket['filename']}"
        blocked_by = ticket["blocked_by"]
        blocked_link = f"[{blocked_by}](tickets/{blocked_by}.md)" if blocked_by else ""
        board_lines.append(f"| [{escape_pipes(ticket['display_title'])}]({link}) | {escape_cell(ticket['priority'])} | {blocked_link} | {escape_cell(ticket['status'])} |")

    version = get_version()
    if version != "unknown":
        board_lines.append("")
        board_lines.append("---")
        board_lines.append(f"*Generated with FlatMark v{version}*")

    board_content = "\n".join(board_lines)

    # Saving the file
    with open(board_path, "w", encoding="utf-8", newline="\n") as f:
        f.write(board_content)

    print(f"Successfully updated {board_path} with {len(tickets_data)} tickets.")
    return True

if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] in ["--version", "-v"]:
        print(f"FlatMark v{get_version()}")
        sys.exit(0)
    if not update_board():
        sys.exit(1)
