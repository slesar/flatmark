#!/usr/bin/env python3
import os
import re
import secrets
import sys

# Ensure we can import board.py from the same directory
base_dir = os.path.dirname(os.path.abspath(__file__))
sys.path.append(base_dir)
import board

tickets_dir = os.path.join(base_dir, "tickets")
archive_dir = os.path.join(base_dir, "archive")

def get_sequential_id(prefix):
    highest = 0
    pattern = re.compile(rf"^{prefix}(\d+)\.md$")
    
    for folder in [tickets_dir, archive_dir]:
        if os.path.exists(folder):
            for filename in os.listdir(folder):
                match = pattern.match(filename)
                if match:
                    num = int(match.group(1))
                    if num > highest:
                        highest = num
    return f"{prefix}{highest + 1}"

def get_random_id(prefix, length=4):
    existing = set()
    for folder in [tickets_dir, archive_dir]:
        if os.path.exists(folder):
            for filename in os.listdir(folder):
                if filename.endswith(".md"):
                    existing.add(filename[:-3])

    for _ in range(1000):
        token = secrets.token_hex((length + 1) // 2)[:length].lower()
        candidate = f"{prefix}-{token}"
        if candidate not in existing:
            return candidate
    raise RuntimeError(f"Could not generate a unique random ID for prefix {prefix} after 1000 attempts.")

def get_next_id(prefix, scheme="sequential"):
    scheme = str(scheme).strip().lower()
    if scheme in ["random", "hash"]:
        return get_random_id(prefix)
    elif scheme == "sequential":
        return get_sequential_id(prefix)
    else:
        raise ValueError(f"Unknown ID scheme '{scheme}'. Allowed values: sequential, random, hash.")

if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] in ["--version", "-v"]:
        print(f"FlatMark v{board.get_version()}")
        sys.exit(0)

    scheme = "sequential"
    args = sys.argv[1:]
    clean_args = []
    i = 0
    while i < len(args):
        arg = args[i]
        if arg == "--random":
            scheme = "random"
            i += 1
        elif arg == "--sequential":
            scheme = "sequential"
            i += 1
        elif arg == "--scheme":
            if i + 1 < len(args):
                scheme = args[i + 1]
                i += 2
            else:
                print("Error: --scheme requires an argument (sequential or random)", file=sys.stderr)
                sys.exit(2)
        elif arg.startswith("--scheme="):
            scheme = arg.split("=", 1)[1]
            i += 1
        else:
            clean_args.append(arg)
            i += 1

    if len(clean_args) < 1:
        print("Usage: python3 flatmark/new.py [--scheme sequential|random] [T|B|F|S|R|D] <Ticket Title>", file=sys.stderr)
        sys.exit(2)
        
    prefix = clean_args[0].upper()
    if prefix not in ['T', 'B', 'F', 'S', 'R', 'D']:
        print("Error: Prefix must be T (Task), or B (Bug), F (Feature), S (Spike), R (Release), D (Documentation)", file=sys.stderr)
        sys.exit(2)
        
    title = " ".join(clean_args[1:]) if len(clean_args) > 1 else "New Ticket"
    try:
        next_id = get_next_id(prefix, scheme=scheme)
    except ValueError as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(2)

    file_path = os.path.join(tickets_dir, f"{next_id}.md")
    
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

    try:
        with open(file_path, "w", encoding="utf-8", newline="\n") as f:
            f.write(content)
    except OSError as e:
        print(f"Error: Could not write ticket file {file_path}: {e}", file=sys.stderr)
        sys.exit(1)
        
    print(f"Created ticket: {next_id} ({file_path})")
    
    # Automatically synchronize the board
    if not board.update_board():
        sys.exit(1)
