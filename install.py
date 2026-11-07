#!/usr/bin/env python3
import os
import shutil
import stat
import subprocess
import sys
import urllib.error
import urllib.request

CORE_FILES = ["AGENTS.md", "board.py", "new.py", "VERSION", "flatmark.py", "lint.py"]
EXECUTABLE_FILES = {"board.py", "new.py", "flatmark.py", "lint.py"}
DEFAULT_RAW_BASE_URL = "https://raw.githubusercontent.com/slesar/flatmark/main/src/flatmark"

def read_version(directory):
    version_file = os.path.join(directory, "VERSION")
    if os.path.exists(version_file):
        try:
            with open(version_file, "r", encoding="utf-8") as f:
                return f.read().strip()
        except OSError:
            pass
    return None

def get_local_source_dir():
    if "__file__" not in globals() or not __file__ or __file__ == "<stdin>":
        return None
    if not os.path.isfile(__file__):
        return None
    script_dir = os.path.dirname(os.path.abspath(__file__))
    candidate = os.path.join(script_dir, "src", "flatmark")
    if all(os.path.isfile(os.path.join(candidate, f)) for f in CORE_FILES):
        return candidate
    if all(os.path.isfile(os.path.join(script_dir, f)) for f in CORE_FILES):
        return script_dir
    return None

def fetch_remote_file(filename, base_url=None):
    if base_url is None:
        base_url = os.environ.get("FLATMARK_RAW_URL", DEFAULT_RAW_BASE_URL)
    url = f"{base_url.rstrip('/')}/{filename}"
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "FlatMark-Installer"})
        with urllib.request.urlopen(req, timeout=15) as response:
            return response.read()
    except urllib.error.URLError as e:
        print(f"Error: Failed to download {url}: {e}", file=sys.stderr)
        sys.exit(1)

def check_agent_discoverability(target_root, dest_dir):
    pointer_line = "See [flatmark/AGENTS.md](flatmark/AGENTS.md) for ticket management rules, frontmatter schema, and agent workflow."
    root_agent_candidates = ["AGENTS.md", "CLAUDE.md", ".cursorrules", ".windsurfrules"]
    found_candidates = []

    for candidate in root_agent_candidates:
        candidate_path = os.path.join(target_root, candidate)
        if os.path.isfile(candidate_path) and os.path.abspath(candidate_path) != os.path.abspath(os.path.join(dest_dir, "AGENTS.md")):
            found_candidates.append((candidate, candidate_path))

    added = []
    for candidate, candidate_path in found_candidates:
        try:
            with open(candidate_path, "r", encoding="utf-8") as f:
                content = f.read()
            if "flatmark/AGENTS.md" in content:
                continue

            should_add = False
            if sys.stdin.isatty():
                try:
                    resp = input(f"Found {candidate} in project root. Add FlatMark reference pointer? (y/N): ").strip().lower()
                    should_add = (resp == "y")
                except EOFError:
                    should_add = False

            if should_add:
                with open(candidate_path, "a", encoding="utf-8") as f:
                    if not content.endswith("\n"):
                        f.write("\n")
                    f.write(f"\n<!-- FlatMark Ticket Management -->\n{pointer_line}\n")
                added.append(candidate)
                print(f"Added FlatMark pointer -> {candidate_path}")
        except OSError:
            pass

    print("\nAI Agent Discoverability:")
    if added:
        print(f"  Added FlatMark reference pointer to: {', '.join(added)}")
    else:
        print("  To ensure AI agents discover FlatMark, add this pointer to your project root AGENTS.md or CLAUDE.md:")
        print(f"  {pointer_line}")

def configure_gitattributes(target_root, dest_dir):
    gitattributes_path = os.path.join(target_root, ".gitattributes")
    try:
        rel_board = os.path.relpath(os.path.join(dest_dir, "BOARD.md"), target_root)
    except ValueError:
        rel_board = "flatmark/BOARD.md"
    rule_line = f"{rel_board} merge=ours"

    already_configured = False
    if os.path.isfile(gitattributes_path):
        try:
            with open(gitattributes_path, "r", encoding="utf-8") as f:
                content = f.read()
            if rel_board in content or "BOARD.md merge=ours" in content:
                already_configured = True
        except OSError:
            pass

    if already_configured:
        return

    is_git_repo = (
        os.path.isdir(os.path.join(target_root, ".git"))
        or os.path.isfile(os.path.join(target_root, ".git"))
        or os.path.isfile(gitattributes_path)
    )

    should_add = False
    if "--gitattributes" in sys.argv:
        should_add = True
    elif is_git_repo and sys.stdin.isatty():
        try:
            resp = input(f"Add '{rule_line}' to .gitattributes to prevent merge conflicts? (y/N): ").strip().lower()
            should_add = (resp == "y")
        except EOFError:
            should_add = False

    if should_add:
        try:
            with open(gitattributes_path, "a", encoding="utf-8") as f:
                if os.path.isfile(gitattributes_path) and os.path.getsize(gitattributes_path) > 0:
                    with open(gitattributes_path, "r", encoding="utf-8") as rf:
                        last_char = rf.read()[-1:]
                    if last_char and last_char != "\n":
                        f.write("\n")
                f.write(f"\n# Prevent merge conflicts on auto-generated FlatMark board\n{rule_line}\n")
            print(f"Added merge=ours attribute -> {gitattributes_path}")
            print("\nGit Merge Driver Setup:")
            print("  To enable this attribute, configure Git's 'ours' merge driver once:")
            print("    git config merge.ours.driver true")
            print("  After merging branches, regenerate BOARD.md by running:")
            print("    python3 flatmark/board.py")
        except OSError as e:
            print(f"Warning: Could not update {gitattributes_path}: {e}", file=sys.stderr)
    elif is_git_repo:
        print("\nGit Conflict Prevention (Optional):")
        print("  To avoid merge conflicts on BOARD.md across branches, add to .gitattributes:")
        print(f"    {rule_line}")
        print("  And enable the driver: git config merge.ours.driver true")
        print("  After merging branches, regenerate with: python3 flatmark/board.py")

def install(target_root=None, base_url=None, create=False):
    if target_root is None:
        target_root = os.getcwd()
    else:
        target_root = os.path.abspath(target_root)

    create = create or ("--create" in sys.argv)

    if not os.path.exists(target_root):
        if create:
            try:
                os.makedirs(target_root, exist_ok=True)
                print(f"Created target directory: {target_root}")
            except OSError as e:
                print(f"Error: Could not create target directory '{target_root}': {e}", file=sys.stderr)
                sys.exit(1)
        else:
            should_create = False
            if sys.stdin.isatty():
                try:
                    resp = input(f"Target directory '{target_root}' does not exist. Create it? (y/N): ").strip().lower()
                    should_create = (resp == "y")
                except EOFError:
                    should_create = False

            if should_create:
                try:
                    os.makedirs(target_root, exist_ok=True)
                    print(f"Created target directory: {target_root}")
                except OSError as e:
                    print(f"Error: Could not create target directory '{target_root}': {e}", file=sys.stderr)
                    sys.exit(1)
            else:
                print(f"Error: Target directory '{target_root}' does not exist.", file=sys.stderr)
                print("Use --create to create it automatically.", file=sys.stderr)
                sys.exit(1)

    if not os.path.isdir(target_root):
        print(f"Error: Target path '{target_root}' is not a directory.", file=sys.stderr)
        sys.exit(1)

    source_dir = get_local_source_dir()
    dest_dir = os.path.join(target_root, "flatmark")

    # Safety check: avoid installing into the flatmark repository root as a nested flatmark folder
    # if someone accidentally runs install.py without arguments inside the repo itself.
    if source_dir and os.path.abspath(target_root) == source_dir:
        print(f"Warning: Current working directory is the FlatMark source directory ({source_dir}).")
        try:
            confirm = input("Are you sure you want to create a nested 'flatmark/' folder here? (y/N): ").strip().lower()
        except EOFError:
            confirm = "n"
        if confirm != "y":
            print("Installation aborted.")
            return

    remote_files = {}
    if source_dir:
        source_version = read_version(source_dir) or "0.2.0"
    else:
        for filename in CORE_FILES:
            remote_files[filename] = fetch_remote_file(filename, base_url=base_url)
        source_version = remote_files["VERSION"].decode("utf-8").strip() or "0.2.0"

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

    for filename in CORE_FILES:
        dst = os.path.join(dest_dir, filename)
        if source_dir:
            src = os.path.join(source_dir, filename)
            if os.path.exists(src):
                shutil.copy2(src, dst)
                print(f"Copied {filename} -> {dst}")
            else:
                print(f"Error: Required file {src} not found.", file=sys.stderr)
                sys.exit(1)
        else:
            with open(dst, "wb") as f:
                f.write(remote_files[filename])
            if filename in EXECUTABLE_FILES:
                os.chmod(dst, os.stat(dst).st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
            print(f"Downloaded {filename} -> {dst}")

    # Run copied board.py to generate/rebuild BOARD.md without code duplication
    target_board_script = os.path.join(dest_dir, "board.py")
    subprocess.run([sys.executable, target_board_script], check=True)

    local_agents = os.path.join(dest_dir, "AGENTS.local.md")
    if os.path.isfile(local_agents):
        print(f"Preserved custom agent rules in {local_agents}")

    print(f"\nFlatMark v{source_version} installed successfully!")
    print("Usage from project root:")
    print("  python3 flatmark/new.py [T|B|F|S|R|D] \"Ticket Title\"")
    print("  python3 flatmark/board.py")
    print("  python3 flatmark/flatmark.py lint")

    check_agent_discoverability(target_root, dest_dir)
    configure_gitattributes(target_root, dest_dir)

if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] in ["--version", "-v"]:
        source_dir = get_local_source_dir()
        if source_dir:
            ver = read_version(source_dir) or "unknown"
        else:
            ver = fetch_remote_file("VERSION").decode("utf-8").strip() or "unknown"
        print(f"FlatMark Installer v{ver}")
        sys.exit(0)

    if len(sys.argv) > 1 and sys.argv[1] in ["--help", "-h"]:
        print("Usage: python3 install.py [--create] [--gitattributes] [target_path]")
        print("\nInstall or upgrade FlatMark in the specified project directory.")
        print("\nOptions:")
        print("  --create        Create target directory if it does not exist")
        print("  --gitattributes Configure merge=ours in .gitattributes without prompting")
        print("  -v, --version   Show FlatMark installer version")
        print("  -h, --help      Show this help message")
        sys.exit(0)

    positional = [a for a in sys.argv[1:] if not a.startswith("-")]
    target = positional[0] if positional else None
    create_flag = "--create" in sys.argv
    install(target, create=create_flag)
