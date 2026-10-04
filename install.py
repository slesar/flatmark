#!/usr/bin/env python3
import os
import shutil
import subprocess
import sys

def read_version(directory):
    version_file = os.path.join(directory, "VERSION")
    if os.path.exists(version_file):
        try:
            with open(version_file, "r", encoding="utf-8") as f:
                return f.read().strip()
        except OSError:
            pass
    return None

def install(target_root=None):
    if target_root is None:
        target_root = os.getcwd()
    else:
        target_root = os.path.abspath(target_root)

    source_dir = os.path.dirname(os.path.abspath(__file__))
    source_version = read_version(source_dir) or "0.1.0"
    dest_dir = os.path.join(target_root, "flatmark")

    # Safety check: avoid installing into the flatmark repository root as a nested flatmark folder
    # if someone accidentally runs install.py without arguments inside the repo itself.
    if os.path.abspath(target_root) == source_dir:
        print(f"Warning: Current working directory is the FlatMark source directory ({source_dir}).")
        confirm = input("Are you sure you want to create a nested 'flatmark/' folder here? (y/N): ").strip().lower()
        if confirm != 'y':
            print("Installation aborted.")
            return

    archive_dir = os.path.join(dest_dir, "archive")
    tickets_dir = os.path.join(dest_dir, "tickets")

    existing_version = read_version(dest_dir)
    if existing_version:
        if existing_version == source_version:
            print(f"FlatMark is already up to date (v{source_version}) in: {dest_dir}. Re-syncing scripts...")
        else:
            print(f"Upgrading FlatMark from v{existing_version} to v{source_version} in: {dest_dir}...")
    else:
        print(f"Installing FlatMark v{source_version} into: {dest_dir}...")

    os.makedirs(archive_dir, exist_ok=True)
    os.makedirs(tickets_dir, exist_ok=True)

    # Core files to copy from source_dir
    files_to_copy = ["AGENTS.md", "board.py", "new.py", "VERSION"]
    for filename in files_to_copy:
        src = os.path.join(source_dir, filename)
        dst = os.path.join(dest_dir, filename)
        if os.path.exists(src):
            shutil.copy2(src, dst)
            print(f"Copied {filename} -> {dst}")
        else:
            print(f"Error: Required file {src} not found.", file=sys.stderr)
            sys.exit(1)

    # Run copied board.py to generate/rebuild BOARD.md without code duplication
    target_board_script = os.path.join(dest_dir, "board.py")
    subprocess.run([sys.executable, target_board_script], check=True)

    print(f"\nFlatMark v{source_version} installed successfully!")
    print("Usage from project root:")
    print("  python3 flatmark/new.py [T|B|F|S|R|D] \"Ticket Title\"")
    print("  python3 flatmark/board.py")

if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] in ["--version", "-v"]:
        source_dir = os.path.dirname(os.path.abspath(__file__))
        ver = read_version(source_dir) or "unknown"
        print(f"FlatMark Installer v{ver}")
        sys.exit(0)

    target = sys.argv[1] if len(sys.argv) > 1 else None
    install(target)
