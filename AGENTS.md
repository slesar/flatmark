# FlatMark Contributor Guidelines for AI Agents

Welcome to the FlatMark repository! FlatMark is a lightweight, zero-dependency, file-based ticketing system designed to live inside any codebase.

These instructions are specifically for AI agents (and human developers) contributing to FlatMark itself.

## 1. Repository Layout

```text
flatmark/                     # repo
├── src/flatmark/             # Core distribution payload copied by install.py
│   ├── AGENTS.md             # Installed ticket management guidelines for projects
│   ├── board.py              # Ticket board generator & synchronizer
│   ├── flatmark.py           # Unified FlatMark CLI entry point
│   ├── lint.py               # Ticket linter helper script
│   ├── new.py                # Helper script to allocate ticket IDs and templates
│   └── VERSION               # Version file
├── install.py                # Standalone installer (local & remote one-liner)
├── tests/                    # Automated test suite using unittest
├── flatmark/                 # Dogfooding FlatMark instance tracking FlatMark itself
│   ├── tickets/              # Active tickets for FlatMark
│   ├── archive/              # Completed or obsolete tickets
│   └── BOARD.md              # Auto-generated ticket board
├── AGENTS.md                 # This file: contributor instructions for agents developing FlatMark
├── CONTRIBUTING.md           # Contributor guide
└── README.md                 # Public documentation and quick start
```

## 2. Development Setup & Constraints

- **Python Version**: Python 3.13 or newer.
- **Zero External Dependencies**: FlatMark strictly uses the Python standard library. Never add external packages, virtual environments, or `pip install` requirements.
- **Standalone Distribution**: The core payload files in `src/flatmark/` and the installer `install.py` must run as standalone scripts.

## 3. Running Tests

FlatMark uses Python's standard `unittest` module:

```bash
# Run all tests:
python3 -m unittest discover tests -v
```

Always ensure the full test suite passes before concluding your work.

## 4. Code & Architecture Conventions

- **Payload Changes**: If you modify `board.py`, `new.py`, `VERSION`, or the installed `AGENTS.md` template, make edits inside `src/flatmark/`.
- **Dogfooding Synchronization**: After modifying files in `src/flatmark/`, sync them into the repository's dogfooding `flatmark/` instance:
  ```bash
  python3 install.py .
  ```
- **Installer**: `install.py` supports both local installation (`python3 install.py <target>`) and remote piped installation (`curl ... | python3 -`). Always keep `DEFAULT_RAW_BASE_URL` pointing to `https://raw.githubusercontent.com/slesar/flatmark/main/src/flatmark`.
- **Preserve Documentation**: Maintain docstrings, comments, and backwards compatibility unless explicitly instructed otherwise.

## 5. Ticket Management (Dogfooding FlatMark)

We use FlatMark to track work on FlatMark itself! Active tickets are located in `flatmark/tickets/`, completed tickets in `flatmark/archive/`, and the board is `flatmark/BOARD.md`.

<!-- FlatMark Ticket Management -->
See [flatmark/AGENTS.md](flatmark/AGENTS.md) for ticket management rules, frontmatter schema, and agent workflow.

### Explicit Agent Workflow Checklist:
1. **Pick a Ticket**:
   - Inspect `flatmark/BOARD.md` or search `flatmark/tickets/` to identify an unassigned ticket with `status: Todo`.
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
3. **Implement**:
   - Write code and unit tests fulfilling all requirements.
   - Preserve existing documentation and comments.
4. **Verify Acceptance Criteria**:
   - Run the test suite: `python3 -m unittest discover tests`.
   - Confirm all acceptance criteria in the ticket file are satisfied.
   - Check all criteria boxes in the ticket file from `- [ ]` to `- [x]`.
5. **Archive Ticket (`Done` or `Obsolete`)**:
   - Update frontmatter status:
     ```yaml
     status: Done
     ```
     *(or `status: Obsolete` if retiring without implementation)*.
   - Move the file to `flatmark/archive/`:
     ```bash
     mv flatmark/tickets/<ID>.md flatmark/archive/<ID>.md
     ```
6. **Synchronize the Board**:
   - Re-run the board update script:
     ```bash
     python3 flatmark/board.py
     ```
   - Confirm the ticket has moved off the active table in `flatmark/BOARD.md`.
7. **Lint Tickets (Mandatory)**:
   - Run the ticket linter to ensure all tickets, frontmatter, and dependencies are valid:
     ```bash
     python3 flatmark/flatmark.py lint
     ```
     *(Or `python3 flatmark/flatmark.py lint --fix` to auto-resolve safe issues).*
   - Confirm all lint issues are resolved and exit code is 0 before committing.
8. **Commit Changes**:
   - Include the ticket ID in the commit message:
     ```bash
     git commit -m "[#<ID>] Fix bug or implement feature"
     ```
