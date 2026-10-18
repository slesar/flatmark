#!/usr/bin/env python3
import os
import re
import sys

# Ensure we can import board.py from the same directory
base_dir = os.path.dirname(os.path.abspath(__file__))
sys.path.append(base_dir)
import board

tickets_dir = os.path.join(base_dir, "tickets")
archive_dir = os.path.join(base_dir, "archive")

def get_next_id(prefix):
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

if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] in ["--version", "-v"]:
        print(f"FlatMark v{board.get_version()}")
        sys.exit(0)

    if len(sys.argv) < 2:
        print("Usage: python3 flatmark/new.py [T|B|F|S|R|D] <Ticket Title>")
        sys.exit(1)
        
    prefix = sys.argv[1].upper()
    if prefix not in ['T', 'B', 'F', 'S', 'R', 'D']:
        print("Error: Prefix must be T (Task), or B (Bug), F (Feature), S (Spike), R (Release), D (Documentation)")
        sys.exit(1)
        
    title = " ".join(sys.argv[2:]) if len(sys.argv) > 2 else "New Ticket"
    next_id = get_next_id(prefix)
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

    with open(file_path, "w") as f:
        f.write(content)
        
    print(f"Created ticket: {next_id} ({file_path})")
    
    # Automatically synchronize the board
    board.update_board()
