# FlatMark

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Python: 3.13+](https://img.shields.io/badge/python-3.13+-blue.svg)](https://www.python.org/)

**FlatMark** is a lightweight, zero-dependency, file-based ticketing system
designed to live inside any project. Built with pure Python standard library and
Markdown, it is purpose-built for seamless collaboration between human
developers and AI coding agents (such as Antigravity, Claude Code, Cursor,
Copilot, and Aider).

---

## Highlights

- **Zero External Dependencies**: Works out of the box with standard Python
  3.13+. No `pip install`, no databases, no cloud accounts.
- **Git-Native**: Tickets are version-controlled Markdown files stored directly
  in your repository.
- **Automated Board Generator**: Automatically syncs and formats an interactive
  markdown table in `BOARD.md` complete with visual tree hierarchies and
  blocking links.
- **AI Agent Optimized**: Provides a clear, parseable specification
  ([`AGENTS.md`](src/flatmark/AGENTS.md)) that guides AI agents to create, update, and
  resolve tasks deterministically.
- **Hierarchical & Dependency Tracking**: Supports nested tasks (`parent: ...`)
  and dependency blockers (`blocked by: ...`).
- **Clean Lifecycle**: Straightforward workflow from active (`tickets/`) to
  completed (`archive/`).

---

## Directory Structure

When installed into a target project, FlatMark creates a self-contained
`flatmark/` folder:

```text
my-project/
├── flatmark/
│   ├── tickets/       # Active tickets as individual Markdown files
│   ├── archive/       # Completed or obsolete tickets
│   ├── BOARD.md       # Auto-generated ticket board (do not edit manually)
│   ├── AGENTS.md      # Instructions & conventions for AI coding agents
│   ├── board.py       # Synchronizes BOARD.md with tickets/
│   ├── new.py         # Helper script to create tickets with incremental IDs
│   ├── flatmark.py    # Unified CLI entry point (lint, board, new)
│   ├── lint.py        # Validates ticket frontmatter, metadata, and dependencies
│   └── VERSION        # Current FlatMark version
```

---

## Installation & Upgrades

### Quick Install / Upgrade (One-Liner)

Run directly from your target project root using `curl` or `wget`:

```bash
# Using curl:
curl -fsSL https://raw.githubusercontent.com/slesar/flatmark/main/install.py | python3 -

# Using wget:
wget -qO- https://raw.githubusercontent.com/slesar/flatmark/main/install.py | python3 -
```

You can also pass a target project path to the one-liner:

```bash
curl -fsSL https://raw.githubusercontent.com/slesar/flatmark/main/install.py | python3 - /path/to/my-project
```

### Local Clone Installation

If you have a local clone of FlatMark, run `install.py` targeting your project root:

```bash
# From within the target project directory:
python3 /path/to/flatmark/install.py

# Or specify the target project path:
python3 /path/to/flatmark/install.py /path/to/my-project
```

This creates the `flatmark/` directory with initialized folders (`tickets/`,
`archive/`), core scripts, guidelines, and an initial `BOARD.md`.

### Installer Options

| Flag | Description |
| :--- | :--- |
| `--create` | Automatically create the target directory if it does not exist. |
| `--gitattributes` | Automatically configure `merge=ours` in `.gitattributes` without prompting. |
| `-v`, `--version` | Display FlatMark installer version. |
| `-h`, `--help` | Show usage and options. |

By default, `install.py` requires the target project root to exist to avoid accidental directory creation from typos. If the directory does not exist, the installer prompts for confirmation in interactive sessions or fails with a non-zero exit code unless `--create` is passed:

```bash
# Create target directory automatically:
python3 /path/to/flatmark/install.py --create /path/to/my-project

# Or with the curl one-liner:
curl -fsSL https://raw.githubusercontent.com/slesar/flatmark/main/install.py | python3 - --create /path/to/my-project
```

### In-Place Upgrade

Upgrades are completely non-destructive and use the exact same command (via `curl`/`wget` or local `install.py`).

Existing tickets in `tickets/` and `archive/` are **never** overwritten or
deleted. Only system scripts (`board.py`, `new.py`, `AGENTS.md`) and `VERSION`
are updated, followed by an automatic board rebuild.

---

## Usage

You can interact with FlatMark directly from your project root:

### 1. Create a New Ticket

FlatMark supports alphanumeric sorting with standard prefixes:

- `T` - **Task** (general tasks, chores, refactoring)
- `B` - **Bug** (defects, issues, regressions)
- `F` - **Feature** (new functionality, user stories)
- `S` - **Spike** (research, investigations, prototyping)
- `R` - **Release** (deployment checklists, launch prep)
- `D` - **Documentation** (user guides, READMEs, API docs)

Run `new.py` to automatically allocate an ID and generate a template:

```bash
# Default sequential ID:
python3 flatmark/new.py F "User authentication"
# Output: Created ticket: F1 (flatmark/tickets/F1.md)

# Or decentralized short random hash ID (ideal for parallel branches / agents):
python3 flatmark/new.py --scheme random F "User authentication"
# Output: Created ticket: F-7f3a (flatmark/tickets/F-7f3a.md)
```

### 2. Edit Ticket Metadata & Content

Open the newly created ticket file in `flatmark/tickets/` (e.g. `F1.md`):

```markdown
---
id: F1
priority: P1
status: In Progress
---
# User authentication

Implement authentication endpoints and token verification.

Acceptance criteria:

- [ ] User login endpoint
- [ ] JWT issue and validation
```

#### Hierarchy & Dependencies

FlatMark parses optional relation fields in frontmatter:

- `parent`: Establishes parent-child relationships, rendering visual tree
  branches (`├──`, `└──`) on the board.
- `blocked by`: Links to blocking ticket ID(s). Supports a single ID or a comma-separated list of IDs (e.g. `blocked by: T2, T3`). Each blocker is rendered as its own distinct link on the board.

```markdown
---
id: B1
priority: P0
status: Todo
parent: F1
blocked by: T2, T3
---
# Fix token expiry issue
...
```

### 3. Synchronize the Board

Whenever a ticket is created, modified, or moved, regenerate `BOARD.md`:

```bash
python3 flatmark/board.py
```

To verify whether `BOARD.md` is currently up to date without modifying it (useful for CI and pre-commit checks):

```bash
python3 flatmark/board.py --check
```
Exits `0` if up to date, or `1` if out of date or missing.

### 4. Archive Completed Tickets

When a ticket is completed (`Done`) or retired (`Obsolete`):

1. Update its `status` in the YAML frontmatter.
2. Move the file from `flatmark/tickets/` to `flatmark/archive/`.
3. Run `python3 flatmark/board.py` to refresh the active board.

### 5. Lint & Validate Tickets

Validate all tickets for valid frontmatter, valid statuses/priorities, proper directory placement, and dependency integrity:

```bash
python3 flatmark/flatmark.py lint

# Or automatically fix safe issues (move Done tickets to archive/, fix IDs):
python3 flatmark/flatmark.py lint --fix
```

### 6. Check Installed Version

```bash
python3 flatmark/board.py --version
```

---

## Best Practices for AI Agents

FlatMark includes [`AGENTS.md`](src/flatmark/AGENTS.md) (installed at `flatmark/AGENTS.md`), which is designed to be fed
directly into AI context (or referenced in rules like `.cursorrules`,
`CLAUDE.md`, or system prompts).

- **Root Pointer for Discoverability**: Add a one-line reference to your
  project-root `AGENTS.md` or `CLAUDE.md`:
  `See [flatmark/AGENTS.md](flatmark/AGENTS.md) for ticket management rules.`
- **Custom Rules with `AGENTS.local.md`**: For project-specific conventions,
  create `flatmark/AGENTS.local.md`, which is guaranteed never to be overwritten
  by upgrades.
- **Explicit Workflow**: Agents follow: `pick ticket` → `set In Progress` →
  `implement` → `verify criteria` → `set Done` & move to `archive/` →
  `run board.py`.
- **Atomic Changes**: Commit ticket state updates and `BOARD.md`
  synchronization together with the code changes.
- **Traceability**: Reference ticket IDs in commit messages (e.g.,
  `[#F1] Implement JWT validation`).
- **Clear Acceptance Criteria**: Keep checklists in ticket bodies so agents can
  verify completion before marking status as `Done`.

---

## Avoiding Merge Conflicts on BOARD.md

Because `BOARD.md` is an auto-generated file that updates whenever tickets change, parallel branches can conflict on it. FlatMark provides two strategies to handle this:

### Option A: Keep BOARD.md Committed with `merge=ours` (Recommended)

Tell Git to automatically preserve the current branch's version of `BOARD.md` during merges, then regenerate the board:

1. Add to `.gitattributes` (the installer offers to do this automatically):
   ```gitattributes
   flatmark/BOARD.md merge=ours
   ```

2. Enable the `ours` merge driver in your Git configuration:
   ```bash
   git config merge.ours.driver true
   ```

3. After merging branches, regenerate the board:
   ```bash
   python3 flatmark/board.py
   ```

### Option B: Ignore BOARD.md in Version Control

If your team prefers not to commit auto-generated files:

1. Add `flatmark/BOARD.md` to `.gitignore`:
   ```gitignore
   flatmark/BOARD.md
   ```

2. Generate the board locally on demand whenever you want to inspect progress:
   ```bash
   python3 flatmark/board.py
   ```

---

## Pre-Commit Hooks & CI Integration

### 1. Pre-Commit Hook

Ensure `BOARD.md` is fresh and all tickets pass linting before committing.

Using [pre-commit](https://pre-commit.com/):

```yaml
# .pre-commit-config.yaml
repos:
  - repo: local
    hooks:
      - id: flatmark-board-check
        name: check flatmark board freshness
        entry: python3 flatmark/board.py --check
        language: system
        files: ^flatmark/
        pass_filenames: false
      - id: flatmark-lint
        name: lint flatmark tickets
        entry: python3 flatmark/flatmark.py lint
        language: system
        files: ^flatmark/
        pass_filenames: false
```

Or using a standard `.git/hooks/pre-commit` script:

```bash
#!/bin/sh
python3 flatmark/board.py --check || {
    echo "Error: flatmark/BOARD.md is out of date. Run 'python3 flatmark/board.py' to update it."
    exit 1
}
python3 flatmark/flatmark.py lint || exit 1
```

### 2. GitHub Actions CI Snippet

In `.github/workflows/ci.yml`:

```yaml
- name: Verify FlatMark BOARD.md is up to date
  run: python3 flatmark/board.py --check

- name: Lint FlatMark tickets
  run: python3 flatmark/flatmark.py lint
```

---

## Running Tests

FlatMark includes a test suite using standard Python `unittest`:

```bash
python3 -m unittest discover tests
```

---

## Contributing

Contributions are welcome! Please see [`CONTRIBUTING.md`](CONTRIBUTING.md) for details on our development workflow, repository structure, and ticket management for contributors.

---

## License

This project is licensed under the [MIT License](LICENSE).
