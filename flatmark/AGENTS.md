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
- `flatmark.py`: Unified FlatMark CLI entry point (`lint`, `board`, `new`).
- `lint.py`: Helper script to validate ticket frontmatter, metadata, dependencies, and lifecycle status.
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

# Use --create if the target directory does not exist yet:
python3 /path/to/flatmark/install.py --create /path/to/target-project
```

- **Fresh Install**: Creates the `flatmark/` directory containing `tickets/`, `archive/`, core scripts, and an initial `BOARD.md`. By default, `install.py` requires the target project root to exist (or use `--create` to create it).
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

When assigned or picking up a FlatMark ticket, AI agents SHOULD use deterministic FlatMark CLI commands:

1. **Pick a Ticket**:
   - Query the next unblocked ticket:
     ```bash
     python3 flatmark/flatmark.py next
     ```
   - Or query the backlog:
     ```bash
     python3 flatmark/flatmark.py list
     ```
   - Inspect ticket details:
     ```bash
     python3 flatmark/flatmark.py show <ID>
     ```
2. **Claim the Ticket (`start`)**:
   - Claim the ticket in a single atomic step (sets `status: In Progress` and auto-regenerates `BOARD.md`):
     ```bash
     python3 flatmark/flatmark.py start <ID>
     ```
3. **Implement**:
   - Write code and unit tests fulfilling all requirements.
   - Preserve existing documentation and comments.
4. **Verify Acceptance Criteria**:
   - Run the project's test suite to ensure all tests pass.
   - Confirm all acceptance criteria in the ticket file are satisfied.
   - Check all criteria boxes in the ticket file from `- [ ]` to `- [x]`.
5. **Complete and Archive Ticket (`done` or `obsolete`)**:
   - Mark completed and move to `archive/` in one step (auto-regenerates `BOARD.md`):
     ```bash
     python3 flatmark/flatmark.py done <ID>
     ```
     *(or `python3 flatmark/flatmark.py obsolete <ID>` if retiring without implementation)*.
6. **Lint Tickets (Mandatory)**:
   - Run the ticket linter to ensure all tickets, frontmatter, and dependencies are valid:
     ```bash
     python3 flatmark/flatmark.py lint
     ```
     *(Or `python3 flatmark/flatmark.py lint --fix` to auto-resolve safe issues).*
   - Confirm all lint issues are resolved and exit code is 0 before committing.
7. **Commit Changes**:
   - Include the ticket ID in the commit message:
     ```bash
     git commit -m "[#<ID>] Fix bug or implement feature"
     ```

## 5. Unified CLI Usage from Project Root

FlatMark provides a single unified entry point (`flatmark.py`) with agent-friendly verbs. All mutating commands automatically synchronize `BOARD.md`:

- **Create Ticket**:
  ```bash
  python3 flatmark/flatmark.py new [T|B|F|S|R|D] "Ticket Title" [--priority P] [--parent ID] [--blocked-by ID] [--scheme sequential|random]
  ```
- **Claim Ticket**:
  ```bash
  python3 flatmark/flatmark.py start <ID>
  ```
- **Complete Ticket**:
  ```bash
  python3 flatmark/flatmark.py done <ID>
  ```
- **Retire Ticket**:
  ```bash
  python3 flatmark/flatmark.py obsolete <ID>
  ```
- **Find Next Ticket**:
  ```bash
  python3 flatmark/flatmark.py next [--json]
  ```
- **Inspect Ticket**:
  ```bash
  python3 flatmark/flatmark.py show <ID> [--json]
  ```
- **Query Backlog**:
  ```bash
  python3 flatmark/flatmark.py list [--status S] [--priority P] [--all] [--json]
  ```
- **Update or Check Board**:
  ```bash
  python3 flatmark/flatmark.py board
  python3 flatmark/flatmark.py board --check
  ```
- **Lint Tickets**:
  ```bash
  python3 flatmark/flatmark.py lint [--fix]
  ```
- **Check Version**:
  ```bash
  python3 flatmark/flatmark.py --version
  ```
*(Note: `board.py` and `new.py` remain available as backward-compatible wrappers).*

### 5.1 JSON Output Schema

When passing `--json` to `list`, `show`, or `next`, FlatMark outputs structured JSON:

#### `show <id> --json` and `next --json`
Returns a single ticket object (or `null` for `next --json` when no unblocked `Todo` ticket exists):
```json
{
  "id": "F3",
  "title": "Unified flatmark CLI with agent-friendly verbs",
  "status": "In Progress",
  "priority": "P2",
  "parent": null,
  "blocked_by": "T3",
  "archived": false,
  "path": "tickets/F3.md",
  "body": "Description and acceptance criteria markdown..."
}
```

#### `list --json`
Returns an array of ticket summaries:
```json
[
  {
    "id": "B4",
    "title": "Multiple blockers produce a broken link",
    "status": "Todo",
    "priority": "P2",
    "parent": null,
    "blocked_by": null,
    "archived": false,
    "path": "tickets/B4.md"
  }
]
```

- `id` *(string)*: Unique ticket identifier.
- `title` *(string)*: Ticket title extracted from `# Title`.
- `status` *(string)*: Lifecycle status (`Todo`, `In Progress`, `Done`, `Obsolete`).
- `priority` *(string)*: Urgency level (`P0`, `P1`, `P2`, `P3`).
- `parent` *(string | null)*: Parent ticket ID or `null`.
- `blocked_by` *(string | null)*: Blocking ticket ID(s) or `null`.
- `archived` *(boolean)*: `true` if located in `archive/`, `false` if in `tickets/`.
- `path` *(string)*: Relative file path (e.g. `tickets/F3.md` or `archive/T3.md`).
- `body` *(string, show/next only)*: Markdown content following the YAML frontmatter.

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
