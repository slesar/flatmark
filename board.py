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
    yaml_pattern = re.compile(r"^---\s*\n(.*?)\n---\s*\n", re.DOTALL)
    match = yaml_pattern.search(content)
    if not match:
        return {}

    yaml_content = match.group(1)
    data = {}
    for line in yaml_content.split('\n'):
        if ':' in line:
            key, value = line.split(':', 1)
            data[key.strip()] = value.strip()
    return data

def update_board():
    if not os.path.exists(tickets_dir):
        print(f"Error: {tickets_dir} not found.")
        return

    tickets_by_id = {}
    parent_to_children = {}

    # Read and parse all tickets
    for filename in os.listdir(tickets_dir):
        if not filename.endswith(".md"):
            continue

        file_path = os.path.join(tickets_dir, filename)
        with open(file_path, "r") as f:
            content = f.read()

        yaml_data = parse_yaml(content)
        if not yaml_data:
            continue

        # Extract title from the first level 1 header
        title_match = re.search(r"^#\s+(.*)", content, re.MULTILINE)
        title = title_match.group(1) if title_match else filename

        ticket_id = yaml_data.get("id", filename[:-3])
        status = yaml_data.get("status", "Todo")
        priority = yaml_data.get("priority", "P2")
        blocked_by = yaml_data.get("blocked by", "")
        parent = yaml_data.get("parent", "")

        # Add icon for 'Todo' status if not present
        if "Todo" in status and "⏳" not in status:
            status = f"⏳ {status}"

        ticket_info = {
            "id": ticket_id,
            "title": title,
            "priority": priority,
            "blocked_by": blocked_by,
            "parent": parent,
            "status": status,
            "filename": filename
        }
        tickets_by_id[ticket_id] = ticket_info

        if parent:
            parent_to_children.setdefault(parent, []).append(ticket_id)

    # Sort children naturally
    for p in parent_to_children:
        parent_to_children[p].sort(key=natural_sort_key)

    # Find root tickets (no parent, or parent not present/loaded)
    roots = [
        tid for tid in tickets_by_id
        if not tickets_by_id[tid].get("parent") or tickets_by_id[tid].get("parent") not in tickets_by_id
    ]
    roots.sort(key=natural_sort_key)

    tickets_data = []

    def traverse(ticket_id, prefix=""):
        ticket = tickets_by_id[ticket_id]
        children = parent_to_children.get(ticket_id, [])

        display_title = f"[{ticket_id}] {ticket['title']}"
        if prefix:
            display_title = f"{prefix}{display_title}"

        ticket_row = ticket.copy()
        ticket_row["display_title"] = display_title
        tickets_data.append(ticket_row)

        for i, child_id in enumerate(children):
            is_last = (i == len(children) - 1)
            connector = "└── " if is_last else "├── "
            child_prefix = prefix.replace("├── ", "│   ").replace("└── ", "    ") + connector
            traverse(child_id, child_prefix)

    for r in roots:
        traverse(r)

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
        board_lines.append(f"| [{ticket['display_title']}]({link}) | {ticket['priority']} | {blocked_link} | {ticket['status']} |")

    version = get_version()
    if version != "unknown":
        board_lines.append("")
        board_lines.append("---")
        board_lines.append(f"*Generated with FlatMark v{version}*")

    board_content = "\n".join(board_lines)

    # Saving the file
    with open(board_path, "w") as f:
        f.write(board_content)

    print(f"Successfully updated {board_path} with {len(tickets_data)} tickets.")

if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] in ["--version", "-v"]:
        print(f"FlatMark v{get_version()}")
        sys.exit(0)
    update_board()
