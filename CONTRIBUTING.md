# Contributing to FlatMark

Thank you for contributing to FlatMark! We welcome contributions from human developers and AI coding agents.

## Design Philosophy

- **Zero External Dependencies**: FlatMark uses only the Python standard library. No `pip install`, databases, or external dependencies.
- **Git-Native & File-Based**: Tickets are simple Markdown files with YAML frontmatter version-controlled alongside your code.
- **Lightweight & Portable**: Easy to drop into any repository with a single command.

## Repository Layout

```text
flatmark/                     # repo
├── src/flatmark/             # Core distribution payload copied by install.py
│   ├── AGENTS.md             # Installed ticket management guidelines for projects
│   ├── board.py              # Ticket board generator & synchronizer
│   ├── new.py                # Helper script to allocate ticket IDs and templates
│   └── VERSION               # Version file
├── install.py                # Standalone installer (local & remote one-liner)
├── tests/                    # Automated test suite using unittest
├── flatmark/                 # Dogfooding FlatMark instance tracking FlatMark itself
│   ├── tickets/              # Active tickets for FlatMark
│   ├── archive/              # Completed or obsolete tickets
│   └── BOARD.md              # Auto-generated ticket board
├── AGENTS.md                 # Contributor guidelines for AI agents working on FlatMark
├── CONTRIBUTING.md           # Contributor guide
└── README.md                 # Public documentation and quick start
```

## Development Workflow

### Requirements

- Python 3.13+
- Git

### Running Tests

Run the test suite using Python's built-in `unittest`:

```bash
python3 -m unittest discover tests -v
```

### Making Changes

1. **Source Changes**: Edit payload files in `src/flatmark/` or the installer in `install.py`.
2. **Sync Dogfooding Instance**: Update the repository's dogfooding `flatmark/` folder:
   ```bash
   python3 install.py .
   ```
3. **Add Tests**: Add unit tests in `tests/test_flatmark.py` covering new features or bug fixes.
4. **Ticket Workflow**: If working on a FlatMark ticket:
   - Check `flatmark/BOARD.md` to see available tickets.
   - Set `status: In Progress` in `flatmark/tickets/<ID>.md` and run `python3 flatmark/board.py`.
   - Implement your changes and ensure all tests pass.
   - Check all acceptance criteria checkboxes `- [x]`.
   - Set `status: Done` and move the ticket file to `flatmark/archive/<ID>.md`.
   - Run `python3 flatmark/board.py` to refresh the board.
   - Commit your changes with the ticket ID prefix: `[#<ID>] Summary of changes`.

### Code Style & Guidelines

- Maintain zero external dependencies (Python standard library only).
- Ensure scripts run cleanly on Linux, macOS, and Windows.
- Keep CLI outputs clean and parseable for AI agents.

