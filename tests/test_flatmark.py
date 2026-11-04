import io
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from contextlib import redirect_stderr
from unittest.mock import patch

import board
import new
import install


class TestBoardHelpers(unittest.TestCase):
    def test_slugify(self):
        self.assertEqual(board.slugify("Hello World"), "#hello-world")
        self.assertEqual(board.slugify("Feature 1: User Login!"), "#feature-1-user-login")
        self.assertEqual(board.slugify("   multiple   spaces  "), "#multiple-spaces")

    def test_natural_sort_key(self):
        items = ["B10", "B1", "B2", "B20", "B3"]
        sorted_items = sorted(items, key=board.natural_sort_key)
        self.assertEqual(sorted_items, ["B1", "B2", "B3", "B10", "B20"])

    def test_parse_yaml(self):
        content = """---
id: T1
priority: P1
status: In Progress
parent: F1
blocked by: B2
---
# Task Title
Body text.
"""
        data = board.parse_yaml(content)
        self.assertEqual(data.get("id"), "T1")
        self.assertEqual(data.get("priority"), "P1")
        self.assertEqual(data.get("status"), "In Progress")
        self.assertEqual(data.get("parent"), "F1")
        self.assertEqual(data.get("blocked by"), "B2")

    def test_parse_yaml_empty(self):
        self.assertEqual(board.parse_yaml("# No frontmatter"), {})
        self.assertEqual(board.parse_yaml(""), {})

    def test_parse_yaml_no_trailing_newline_and_crlf(self):
        # B2: closing --- at EOF without trailing newline
        self.assertEqual(board.parse_yaml("---\nid: T1\nstatus: Todo\n---"), {"id": "T1", "status": "Todo"})
        # B2: CRLF line endings
        self.assertEqual(board.parse_yaml("---\r\nid: T2\r\nstatus: Todo\r\n---\r\n# Title\r\n"), {"id": "T2", "status": "Todo"})

    def test_escape_pipes(self):
        # Escapes pipes without altering whitespace or indentation
        self.assertEqual(board.escape_pipes("   [T1] Parse A | B"), r"   [T1] Parse A \| B")
        self.assertEqual(board.escape_pipes(r"Already \| escaped"), r"Already \| escaped")
        self.assertEqual(board.escape_pipes(""), "")
        self.assertEqual(board.escape_pipes(None), "")

    def test_escape_cell(self):
        # B3: pipes are escaped and whitespace/newlines are normalized
        self.assertEqual(board.escape_cell("Hello World"), "Hello World")
        self.assertEqual(board.escape_cell("Parse A | B"), r"Parse A \| B")
        self.assertEqual(board.escape_cell("  multiple   spaces  |  new\nlines  "), r"multiple spaces \| new lines")
        self.assertEqual(board.escape_cell(r"Already \| escaped"), r"Already \| escaped")
        self.assertEqual(board.escape_cell("| leading and trailing |"), r"\| leading and trailing \|")
        self.assertEqual(board.escape_cell(""), "")
        self.assertEqual(board.escape_cell(None), "")


class TestBoardGeneration(unittest.TestCase):
    def setUp(self):
        self.test_dir = tempfile.mkdtemp()
        self.tickets_dir = os.path.join(self.test_dir, "tickets")
        os.makedirs(self.tickets_dir, exist_ok=True)
        self.board_path = os.path.join(self.test_dir, "BOARD.md")
        self.version_path = os.path.join(self.test_dir, "VERSION")

        with open(self.version_path, "w", encoding="utf-8") as f:
            f.write("0.1.0\n")

    def tearDown(self):
        shutil.rmtree(self.test_dir)

    def test_update_board_empty(self):
        with patch.object(board, "tickets_dir", self.tickets_dir), \
             patch.object(board, "board_path", self.board_path), \
             patch.object(board, "version_path", self.version_path):
            board.update_board()

        self.assertTrue(os.path.exists(self.board_path))
        with open(self.board_path, "r", encoding="utf-8") as f:
            content = f.read()

        self.assertIn("# Ticket Board", content)
        self.assertIn("| Ticket | Priority | Blocked by | Status |", content)
        self.assertIn("*Generated with FlatMark v0.1.0*", content)

    def test_update_board_with_hierarchy_and_blockers(self):
        # Create root feature F1
        f1_path = os.path.join(self.tickets_dir, "F1.md")
        with open(f1_path, "w", encoding="utf-8") as f:
            f.write("""---
id: F1
priority: P1
status: In Progress
---
# Main Feature
""")

        # Create child task T1 under F1
        t1_path = os.path.join(self.tickets_dir, "T1.md")
        with open(t1_path, "w", encoding="utf-8") as f:
            f.write("""---
id: T1
priority: P2
status: Todo
parent: F1
blocked by: B1
---
# Subtask
""")

        # Create bug B1
        b1_path = os.path.join(self.tickets_dir, "B1.md")
        with open(b1_path, "w", encoding="utf-8") as f:
            f.write("""---
id: B1
priority: P0
status: Todo
---
# Critical Bug
""")

        with patch.object(board, "tickets_dir", self.tickets_dir), \
             patch.object(board, "board_path", self.board_path), \
             patch.object(board, "version_path", self.version_path):
            board.update_board()

        with open(self.board_path, "r", encoding="utf-8") as f:
            board_text = f.read()

        # Check tickets exist in board
        self.assertIn("[B1] Critical Bug", board_text)
        self.assertIn("[F1] Main Feature", board_text)
        # Check hierarchy tree connector for child
        self.assertIn("└── [T1] Subtask", board_text)
        # Check Todo icon added
        self.assertIn("⏳ Todo", board_text)
        # Check blocker link
        self.assertIn("[B1](tickets/B1.md)", board_text)

    def test_self_parent_and_cycles_rendered_with_warnings(self):
        # B1: self-parent (T3 -> T3) and 2-node cycle (T1 <-> T2)
        tickets = {
            "T1.md": "---\nid: T1\nparent: T2\n---\n# Cycle A\n",
            "T2.md": "---\nid: T2\nparent: T1\n---\n# Cycle B\n",
            "T3.md": "---\nid: T3\nparent: T3\n---\n# Self Parent\n",
        }
        for name, content in tickets.items():
            with open(os.path.join(self.tickets_dir, name), "w", encoding="utf-8") as f:
                f.write(content)

        stderr_buf = io.StringIO()
        with patch.object(board, "tickets_dir", self.tickets_dir), \
             patch.object(board, "board_path", self.board_path), \
             patch.object(board, "version_path", self.version_path), \
             redirect_stderr(stderr_buf):
            ok = board.update_board()

        self.assertTrue(ok)
        with open(self.board_path, "r", encoding="utf-8") as f:
            board_text = f.read()

        self.assertIn("[T1] Cycle A", board_text)
        self.assertIn("[T2] Cycle B", board_text)
        self.assertIn("[T3] Self Parent", board_text)
        stderr_out = stderr_buf.getvalue()
        self.assertIn("own parent", stderr_out)
        self.assertIn("cycle", stderr_out.lower())

    def test_invalid_frontmatter_warns(self):
        # B2: file without frontmatter in tickets/ warns on stderr
        with open(os.path.join(self.tickets_dir, "T1.md"), "w", encoding="utf-8") as f:
            f.write("# No frontmatter here\n")

        stderr_buf = io.StringIO()
        with patch.object(board, "tickets_dir", self.tickets_dir), \
             patch.object(board, "board_path", self.board_path), \
             patch.object(board, "version_path", self.version_path), \
             redirect_stderr(stderr_buf):
            board.update_board()

        self.assertIn("T1.md", stderr_buf.getvalue())

    def test_duplicate_ids_both_rendered_and_warned(self):
        # B9: two files with the same id in frontmatter
        with open(os.path.join(self.tickets_dir, "T1.md"), "w", encoding="utf-8") as f:
            f.write("---\nid: T1\n---\n# First T1\n")
        with open(os.path.join(self.tickets_dir, "T1_copy.md"), "w", encoding="utf-8") as f:
            f.write("---\nid: T1\n---\n# Second T1\n")

        stderr_buf = io.StringIO()
        with patch.object(board, "tickets_dir", self.tickets_dir), \
             patch.object(board, "board_path", self.board_path), \
             patch.object(board, "version_path", self.version_path), \
             redirect_stderr(stderr_buf):
            board.update_board()

        with open(self.board_path, "r", encoding="utf-8") as f:
            board_text = f.read()

        self.assertIn("First T1", board_text)
        self.assertIn("Second T1", board_text)
        stderr_out = stderr_buf.getvalue()
        self.assertIn("Duplicate ticket ID 'T1'", stderr_out)
        self.assertIn("T1_copy.md", stderr_out)

    def test_missing_tickets_dir_returns_false_and_exits_nonzero(self):
        # B8: missing tickets/ prints to stderr, returns False, CLI exits non-zero
        missing_dir = os.path.join(self.test_dir, "nonexistent")
        stderr_buf = io.StringIO()
        with patch.object(board, "tickets_dir", missing_dir), \
             redirect_stderr(stderr_buf):
            ok = board.update_board()

        self.assertFalse(ok)
        self.assertIn("Error:", stderr_buf.getvalue())

        # Subprocess exit code check on an installed copy with missing tickets/
        install_root = os.path.join(self.test_dir, "proj")
        os.makedirs(install_root, exist_ok=True)
        install.install(install_root)
        shutil.rmtree(os.path.join(install_root, "flatmark", "tickets"))

        proc = subprocess.run(
            [sys.executable, os.path.join(install_root, "flatmark", "board.py")],
            capture_output=True,
            text=True,
        )
        self.assertNotEqual(proc.returncode, 0)
        self.assertIn("Error:", proc.stderr)

        proc_new = subprocess.run(
            [sys.executable, os.path.join(install_root, "flatmark", "new.py"), "INVALID"],
            capture_output=True,
            text=True,
        )
        self.assertNotEqual(proc_new.returncode, 0)
        self.assertIn("Error:", proc_new.stderr)

    def test_pipe_and_whitespace_in_title_and_status(self):
        # B3: pipe in title and status must be escaped to avoid breaking the markdown table
        import re

        t1_path = os.path.join(self.tickets_dir, "T1.md")
        with open(t1_path, "w", encoding="utf-8") as f:
            f.write("""---
id: T1
priority:   P1  
status: In Progress | Blocked
---
#   Parse A | B  
""")

        t2_path = os.path.join(self.tickets_dir, "T2.md")
        with open(t2_path, "w", encoding="utf-8") as f:
            f.write("""---
id: T2
priority: P2
status: Todo | Waiting
parent: T1
---
#   Child | Ticket   \r
""")

        with patch.object(board, "tickets_dir", self.tickets_dir), \
             patch.object(board, "board_path", self.board_path), \
             patch.object(board, "version_path", self.version_path):
            board.update_board()

        with open(self.board_path, "r", encoding="utf-8") as f:
            board_text = f.read()

        # Check that pipes are escaped in display titles and statuses
        self.assertIn(r"[T1] Parse A \| B", board_text)
        self.assertIn(r"In Progress \| Blocked", board_text)
        self.assertIn(r"└── [T2] Child \| Ticket", board_text)
        self.assertIn(r"⏳ Todo \| Waiting", board_text)

        # Verify that all table data rows have exactly 4 columns
        for line in board_text.splitlines():
            line = line.strip()
            if line.startswith("|") and not line.startswith("| :---"):
                # Split row by unescaped pipe
                cells = [c.strip() for c in re.split(r'(?<!\\)\|', line)[1:-1]]
                if cells and cells[0] != "Ticket":  # skip header
                    self.assertEqual(len(cells), 4, f"Row should have 4 cells: {line}")


class TestNewTicket(unittest.TestCase):
    def setUp(self):
        self.test_dir = tempfile.mkdtemp()
        self.tickets_dir = os.path.join(self.test_dir, "tickets")
        self.archive_dir = os.path.join(self.test_dir, "archive")
        os.makedirs(self.tickets_dir, exist_ok=True)
        os.makedirs(self.archive_dir, exist_ok=True)

    def tearDown(self):
        shutil.rmtree(self.test_dir)

    def test_get_next_id_empty(self):
        with patch.object(new, "tickets_dir", self.tickets_dir), \
             patch.object(new, "archive_dir", self.archive_dir):
            self.assertEqual(new.get_next_id("T"), "T1")
            self.assertEqual(new.get_next_id("B"), "B1")

    def test_get_next_id_incremental(self):
        # Create T1, T2 in tickets
        for tid in ["T1.md", "T2.md"]:
            with open(os.path.join(self.tickets_dir, tid), "w", encoding="utf-8") as f:
                f.write("")

        # Create T3 in archive
        with open(os.path.join(self.archive_dir, "T3.md"), "w", encoding="utf-8") as f:
            f.write("")

        with patch.object(new, "tickets_dir", self.tickets_dir), \
             patch.object(new, "archive_dir", self.archive_dir):
            self.assertEqual(new.get_next_id("T"), "T4")
            # Other prefixes should still start at 1
            self.assertEqual(new.get_next_id("B"), "B1")


class TestInstall(unittest.TestCase):
    def setUp(self):
        self.test_root = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.test_root)

    def test_fresh_install(self):
        install.install(self.test_root)
        dest_dir = os.path.join(self.test_root, "flatmark")

        self.assertTrue(os.path.isdir(dest_dir))
        self.assertTrue(os.path.isdir(os.path.join(dest_dir, "tickets")))
        self.assertTrue(os.path.isdir(os.path.join(dest_dir, "archive")))
        self.assertTrue(os.path.isfile(os.path.join(dest_dir, "BOARD.md")))
        self.assertTrue(os.path.isfile(os.path.join(dest_dir, "AGENTS.md")))
        self.assertTrue(os.path.isfile(os.path.join(dest_dir, "board.py")))
        self.assertTrue(os.path.isfile(os.path.join(dest_dir, "new.py")))
        self.assertTrue(os.path.isfile(os.path.join(dest_dir, "VERSION")))

        # Check that VERSION content matches source
        source_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        source_ver = install.read_version(source_dir)
        installed_ver = install.read_version(dest_dir)
        self.assertEqual(source_ver, installed_ver)

    def test_remote_install(self):
        source_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

        def mock_fetch(filename, base_url=None):
            with open(os.path.join(source_dir, filename), "rb") as f:
                return f.read()

        with patch.object(install, "get_local_source_dir", return_value=None), \
             patch.object(install, "fetch_remote_file", side_effect=mock_fetch):
            install.install(self.test_root)

        dest_dir = os.path.join(self.test_root, "flatmark")
        self.assertTrue(os.path.isdir(dest_dir))
        self.assertTrue(os.path.isfile(os.path.join(dest_dir, "BOARD.md")))
        self.assertTrue(os.path.isfile(os.path.join(dest_dir, "board.py")))
        self.assertTrue(os.path.isfile(os.path.join(dest_dir, "new.py")))
        self.assertTrue(os.access(os.path.join(dest_dir, "board.py"), os.X_OK))
        self.assertTrue(os.access(os.path.join(dest_dir, "new.py"), os.X_OK))

    def test_discoverability_pointer_added_interactively(self):
        # D2: installer offers to add pointer to project root AGENTS.md / CLAUDE.md
        root_agent = os.path.join(self.test_root, "AGENTS.md")
        with open(root_agent, "w", encoding="utf-8") as f:
            f.write("# Project Root Guidelines\n")

        with patch("sys.stdin.isatty", return_value=True), \
             patch("builtins.input", return_value="y"):
            install.install(self.test_root)

        with open(root_agent, "r", encoding="utf-8") as f:
            content = f.read()
        self.assertIn("See [flatmark/AGENTS.md](flatmark/AGENTS.md)", content)

    def test_customization_preserves_agents_local(self):
        # D2: upgrades must never overwrite or delete flatmark/AGENTS.local.md
        install.install(self.test_root)
        dest_dir = os.path.join(self.test_root, "flatmark")
        local_rules_path = os.path.join(dest_dir, "AGENTS.local.md")

        with open(local_rules_path, "w", encoding="utf-8") as f:
            f.write("# Custom Project Rules\nNever overwrite me!\n")

        # Upgrade/re-install
        install.install(self.test_root)

        self.assertTrue(os.path.isfile(local_rules_path))
        with open(local_rules_path, "r", encoding="utf-8") as f:
            content = f.read()
        self.assertEqual(content, "# Custom Project Rules\nNever overwrite me!\n")


class TestAgentsDoc(unittest.TestCase):
    def test_agents_doc_content(self):
        # D2: AGENTS.md schema table, workflow checklist, discoverability, AGENTS.local.md
        repo_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        agents_path = os.path.join(repo_root, "AGENTS.md")

        self.assertTrue(os.path.isfile(agents_path))
        with open(agents_path, "r", encoding="utf-8") as f:
            content = f.read()

        # Schema table
        self.assertIn("| Field | Required | Allowed Values | Default | Description |", content)
        self.assertIn("`id`", content)
        self.assertIn("`priority`", content)
        self.assertIn("`status`", content)
        self.assertIn("`parent`", content)
        self.assertIn("`blocked by`", content)

        # Agent workflow checklist
        self.assertIn("Agent Workflow Checklist", content)
        self.assertIn("In Progress", content)
        self.assertIn("Done", content)
        self.assertIn("board.py", content)

        # Discoverability & Integration
        self.assertIn("Discoverability", content)
        self.assertIn("See [flatmark/AGENTS.md](flatmark/AGENTS.md)", content)

        # Customization story
        self.assertIn("AGENTS.local.md", content)

if __name__ == "__main__":
    unittest.main()
