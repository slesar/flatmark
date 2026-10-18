# FlatMark

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Python: 3.8+](https://img.shields.io/badge/python-3.8+-blue.svg)](https://www.python.org/)

**FlatMark** is a lightweight, zero-dependency, file-based ticketing system
designed to live inside any project. Built with pure Python standard library and
Markdown, it is purpose-built for seamless collaboration between human
developers and AI coding agents (such as Antigravity, Claude Code, Cursor,
Copilot, and Aider).

---

## Highlights

- **Zero External Dependencies**: Works out of the box with standard Python
  3.8+. No `pip install`, no databases, no cloud accounts.
- **Git-Native**: Tickets are version-controlled Markdown files stored directly
  in your repository.
- **Automated Board Generator**: Automatically syncs and formats an interactive
  markdown table in `BOARD.md` complete with visual tree hierarchies and
  blocking links.
- **AI Agent Optimized**: Provides a clear, parseable specification
  ([`AGENTS.md`](AGENTS.md)) that guides AI agents to create, update, and
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
│   └── VERSION        # Current FlatMark version
```

---

## Installation & Upgrades

### Fresh Installation

Run `install.py` targeting your project root:

```bash
# From within the target project directory:
python3 /path/to/flatmark/install.py

# Or specify the target project path:
python3 /path/to/flatmark/install.py /path/to/my-project
```

This creates the `flatmark/` directory with initialized folders (`tickets/`,
`archive/`), core scripts, guidelines, and an initial `BOARD.md`.

### In-Place Upgrade

Upgrades are completely non-destructive:

```bash
python3 /path/to/flatmark/install.py /path/to/my-project
```

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

Run `new.py` to automatically allocate the next sequential ID and generate a
template:

```bash
python3 flatmark/new.py F "User authentication"
# Output: Created ticket: F1 (flatmark/tickets/F1.md)
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
- `blocked by`: Links to a blocking ticket ID.

```markdown
---
id: B1
priority: P0
status: Todo
parent: F1
blocked by: T2
---
# Fix token expiry issue
...
```

### 3. Synchronize the Board

Whenever a ticket is created, modified, or moved, regenerate `BOARD.md`:

```bash
python3 flatmark/board.py
```

### 4. Archive Completed Tickets

When a ticket is completed (`Done`) or retired (`Obsolete`):

1. Update its `status` in the YAML frontmatter.
2. Move the file from `flatmark/tickets/` to `flatmark/archive/`.
3. Run `python3 flatmark/board.py` to refresh the active board.

### 5. Check Installed Version

```bash
python3 flatmark/board.py --version
```

---

## Best Practices for AI Agents

FlatMark includes [`AGENTS.md`](AGENTS.md), which is designed to be fed
directly into AI context (or referenced in rules like `.cursorrules`,
`CLAUDE.md`, or system prompts).

- **Atomic Changes**: Commit ticket state updates and `BOARD.md`
  synchronization together with the code changes.
- **Traceability**: Reference ticket IDs in commit messages (e.g.,
  `[#F1] Implement JWT validation`).
- **Clear Acceptance Criteria**: Keep checklists in ticket bodies so agents can
  verify completion before marking status as `Done`.

---

## Running Tests

FlatMark includes a test suite using standard Python `unittest`:

```bash
python3 -m unittest discover tests
```

---

## License

This project is licensed under the [MIT License](LICENSE).
