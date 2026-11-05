# FlatMark Ticket Management Guidelines

FlatMark is a lightweight, file-based ticketing system designed to be independent of the project's
primary codebase and optimized for autonomous AI coding agents and human developers alike.

## 1. Core Files and Structure

When installed, FlatMark creates a self-contained `flatmark/` directory:

- `tickets/`: Directory containing active tickets in individual Markdown files with YAML frontmatter.
- `archive/`: Directory containing completed or obsolete tickets.
- `BOARD.md`: An auto-generated Markdown overview of all active tickets. **Do not edit manually.**
- `board.py`: Synchronizes `BOARD.md` with the tickets in `tickets/`.
- `new.py`: Helper script to allocate sequential ticket IDs and create ticket templates.
- `VERSION`: File containing the currently installed FlatMark version.
- `AGENTS.md`: This file. Guidelines and workflow rules for AI agents (overwritten during upgrades).
- `AGENTS.local.md`: *(Optional)* Project-specific agent rules and conventions (**never** overwritten).

## 2. Installation and Upgrades

For complete setup instructions and options, see [`README.md`](README.md#installation--upgrades).

To install or upgrade FlatMark in a project root:

```bash
# Using curl:
curl -fsSL https://raw.githubusercontent.com/slesar/flatmark/main/install.py | python3 -

# Or using wget:
wget -qO- https://raw.githubusercontent.com/slesar/flatmark/main/install.py | python3 -

# Or from a local clone of flatmark:
python3 /path/to/flatmark/install.py /path/to/target-project
```

- **Fresh Install**: Creates the `flatmark/` directory containing `tickets/`, `archive/`, core scripts, and an initial `BOARD.md`.
- **In-Place Upgrade**: Upgrades safely update system scripts (`board.py`, `new.py`, `AGENTS.md`) and `VERSION`, followed by an automatic board refresh.
- **Safety Guarantees**: Existing tickets in `tickets/`, `archive/`, and project-specific `AGENTS.local.md` are **never** overwritten or deleted.

## 3. Frontmatter Schema

Every ticket in `tickets/` MUST begin with a YAML frontmatter block enclosed between `---` markers.

| Field | Required | Allowed Values | Default | Description |
| :--- | :---: | :--- | :--- | :--- |
| `id` | **Yes** | `[T\|B\|F\|S\|R\|D]<number>` or `[T\|B\|F\|S\|R\|D]-<hex>` | *(derived from filename)* | Unique ticket identifier matching the filename stem (e.g. `B8.md` -> `B8`, `T-7f3a.md` -> `T-7f3a`). |
| `priority` | No | `P0`, `P1`, `P2`, `P3` | `P2` | Urgency level: `P0` (critical), `P1` (high), `P2` (medium), `P3` (low). |
| `status` | No | `Todo`, `In Progress`, `Done`, `Obsolete` | `Todo` | Current ticket lifecycle status. |
| `parent` | No | Existing ticket ID (e.g. `F2`) | *(none)* | Parent ticket ID for visual hierarchical tree nesting (`├──`, `└──`). |
| `blocked by` | No | Existing ticket ID (e.g. `T1`) | *(none)* | Blocking ticket dependency link. |

### Frontmatter Notes
- `board.py` automatically renders `⏳ Todo` on the board for tickets with status `Todo`.
- Pipe characters (`|`) in titles, statuses, and frontmatter fields are automatically escaped as `\|` when rendered on the board table.
- Leading/trailing whitespace and newlines in frontmatter values are normalized.

### Example Ticket
```markdown
---
id: B8
priority: P1
status: In Progress
parent: F2
blocked by: T1
---
# Ticket Title

Description goes here.

Acceptance criteria:
- [ ] First criteria
- [ ] Second criteria
```

## 4. Explicit Agent Workflow Checklist

When assigned or picking up a FlatMark ticket, AI agents MUST follow this exact sequence:

1. **Pick a Ticket**:
   - Inspect `BOARD.md` or search `tickets/` to identify an unassigned ticket with `status: Todo`.
   - Verify that the ticket is not blocked by another unfinished ticket (`blocked by`).
2. **Claim the Ticket (`In Progress`)**:
   - Open `flatmark/tickets/<ID>.md` and set:
     ```yaml
     status: In Progress
     ```
   - Synchronize the board immediately:
     ```bash
     python3 flatmark/board.py
     ```
   - *(Optional)* Stage or commit this change if working concurrently to signal that the ticket is claimed.
3. **Implement**:
   - Write code and unit tests fulfilling all requirements.
   - Preserve existing documentation and comments.
4. **Verify Acceptance Criteria**:
   - Run the project's test suite to ensure all tests pass.
   - Confirm all acceptance criteria in the ticket file are satisfied.
   - Check all criteria boxes in the ticket file from `- [ ]` to `- [x]`.
5. **Archive Ticket (`Done` or `Obsolete`)**:
   - Update frontmatter status:
     ```yaml
     status: Done
     ```
     *(or `status: Obsolete` if retiring without implementation)*.
   - Move the file to `archive/`:
     ```bash
     mv flatmark/tickets/<ID>.md flatmark/archive/<ID>.md
     ```
     *(Use `git mv` when working in a Git worktree to preserve rename history)*.
6. **Synchronize the Board**:
   - Re-run the board update script:
     ```bash
     python3 flatmark/board.py
     ```
   - Confirm the ticket has moved off the active table in `BOARD.md`.
7. **Commit Changes**:
   - Include the ticket ID in the commit message:
     ```bash
     git commit -m "[#<ID>] Fix bug or implement feature"
     ```

## 5. Usage from Project Root

You can interact with FlatMark without leaving the project root:

- **Create a New Ticket**:
  ```bash
  python3 flatmark/new.py [--scheme sequential|random] [T|B|F|S|R|D] "Ticket Title"
  ```
- **Update the Board**:
  ```bash
  python3 flatmark/board.py
  ```
- **Check Version**:
  ```bash
  python3 flatmark/board.py --version
  ```
- **Quick Search**:
  Use `grep` or your IDE search across `tickets/` to find tickets by ID, keyword, parent, or status.

## 6. Ticket ID Prefixes & Schemes

FlatMark supports alphanumeric sorting with standard prefixes:

- **`T`**: Tasks (general tasks, chores, and refactoring)
- **`B`**: Bugs (defects, issues, and regressions)
- **`F`**: Features (new functionality, user stories)
- **`S`**: Spikes (research, investigations, prototyping)
- **`R`**: Releases (deployment checklists, launch prep)
- **`D`**: Documentation (user guides, READMEs, API docs)

### ID Allocation Schemes

FlatMark supports two ID allocation schemes:

1. **Sequential Numbers** (*default*): Generates sequential IDs like `T1`, `B2`.
2. **Short Random Hash**: Generates decentralized short hex IDs like `T-7f3a`, `B-c2d4`. Ideal for parallel autonomous agents and feature branches to eliminate ID collisions.

To generate a ticket with a random ID, pass `--scheme random` (or `--random`) to `new.py`:
```bash
python3 flatmark/new.py --scheme random T "Ticket Title"
```

## 7. Discoverability & Integration with Root Agent Files

Most AI coding assistants (Antigravity, Claude Code, Cursor, Copilot, Windsurf) automatically load configuration files located in the project root (such as `AGENTS.md`, `CLAUDE.md`, `.cursorrules`, `.windsurfrules`, or `.github/copilot-instructions.md`).

Because FlatMark is isolated inside `flatmark/`, agents might not read `flatmark/AGENTS.md` unless explicitly directed.

To ensure all agents discover and follow FlatMark, add a one-line reference to your project's root agent file:

```markdown
<!-- FlatMark Ticket Management -->
See [flatmark/AGENTS.md](flatmark/AGENTS.md) for ticket management rules, frontmatter schema, and agent workflow.
```

The FlatMark installer (`install.py`) automatically detects root agent files and offers to add this pointer, or prints setup guidance.

## 8. Project Customization (`AGENTS.local.md`)

Upgrades to FlatMark (`install.py`) safely update system scripts and overwrite `flatmark/AGENTS.md` to ensure guidelines match installed script versions.

If your project requires customized agent instructions, custom ticket prefixes, or language/stack-specific conventions (e.g. test runner commands, build steps, or style guidelines):
1. Create `flatmark/AGENTS.local.md`.
2. Add your project-specific rules there.

**Guarantee**: Upgrades will **never** overwrite, alter, or remove `flatmark/AGENTS.local.md`. AI agents should check for and adhere to `flatmark/AGENTS.local.md` in addition to `flatmark/AGENTS.md`.

## 9. Best Practices for Agents

- **Reference Tickets in Commits**: Always prefix commit messages with the ticket ID, e.g. `[#T15] Fix bug`.
- **Atomic Commits**: Keep the implementation, ticket archiving, and updated `BOARD.md` together in the same commit.
- **Detailed Checklists**: Keep acceptance criteria testable and explicit with markdown checkboxes (`- [ ]`).
- **Strict Status Progression**: Follow `Todo` → `In Progress` → `Done` (or `Obsolete`).
