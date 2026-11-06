import http.server
import io
import os
import re
import shutil
import subprocess
import sys
import tempfile
import threading
import unittest
from contextlib import redirect_stderr
from unittest.mock import patch

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC_DIR = os.path.join(REPO_ROOT, "src", "flatmark")
for p in [SRC_DIR, REPO_ROOT]:
    if p not in sys.path:
        sys.path.insert(0, p)

import board
import new
import install
import flatmark


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

    def test_board_rendering_and_natural_sort_with_random_ids(self):
        # F1: Board rendering, blockers, and natural sorting with random IDs
        t1_path = os.path.join(self.tickets_dir, "T-7f3a.md")
        with open(t1_path, "w", encoding="utf-8") as f:
            f.write("""---
id: T-7f3a
priority: P1
status: In Progress
---
# Parent Feature
""")

        t2_path = os.path.join(self.tickets_dir, "T-a1b2.md")
        with open(t2_path, "w", encoding="utf-8") as f:
            f.write("""---
id: T-a1b2
priority: P2
status: Todo
parent: T-7f3a
blocked by: T-7f3a
---
# Child Task
""")

        with patch.object(board, "tickets_dir", self.tickets_dir), \
             patch.object(board, "board_path", self.board_path), \
             patch.object(board, "version_path", self.version_path):
            board.update_board()

        with open(self.board_path, "r", encoding="utf-8") as f:
            board_text = f.read()

        self.assertIn("[T-7f3a] Parent Feature", board_text)
        self.assertIn("└── [T-a1b2] Child Task", board_text)
        self.assertIn("[T-7f3a](tickets/T-7f3a.md)", board_text)


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

    def test_get_next_id_random(self):
        # F1: random scheme produces <prefix>-<hex4> format
        with patch.object(new, "tickets_dir", self.tickets_dir), \
             patch.object(new, "archive_dir", self.archive_dir):
            tid = new.get_next_id("T", scheme="random")
            self.assertTrue(re.match(r"^T-[0-9a-f]{4}$", tid), f"ID '{tid}' did not match random format")

            bid = new.get_next_id("B", scheme="hash")
            self.assertTrue(re.match(r"^B-[0-9a-f]{4}$", bid))

    def test_get_next_id_random_avoids_collision(self):
        # F1: random scheme must not generate an ID that already exists
        with open(os.path.join(self.tickets_dir, "T-7f3a.md"), "w", encoding="utf-8") as f:
            f.write("")

        with patch.object(new, "tickets_dir", self.tickets_dir), \
             patch.object(new, "archive_dir", self.archive_dir), \
             patch("secrets.token_hex", side_effect=["7f3a", "a1b2"]):
            tid = new.get_next_id("T", scheme="random")
            self.assertEqual(tid, "T-a1b2")

    def test_get_next_id_default_is_sequential(self):
        # F1: default scheme is sequential
        with patch.object(new, "tickets_dir", self.tickets_dir), \
             patch.object(new, "archive_dir", self.archive_dir):
            tid = new.get_next_id("T")
            self.assertEqual(tid, "T1")

    def test_get_next_id_invalid_scheme_raises(self):
        with self.assertRaises(ValueError):
            new.get_next_id("T", scheme="unsupported")


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
        self.assertTrue(os.path.isfile(os.path.join(dest_dir, "flatmark.py")))
        self.assertTrue(os.path.isfile(os.path.join(dest_dir, "lint.py")))
        self.assertTrue(os.access(os.path.join(dest_dir, "flatmark.py"), os.X_OK))
        self.assertTrue(os.access(os.path.join(dest_dir, "lint.py"), os.X_OK))

        # Check that VERSION content matches source
        source_dir = os.path.join(REPO_ROOT, "src", "flatmark")
        source_ver = install.read_version(source_dir)
        installed_ver = install.read_version(dest_dir)
        self.assertEqual(source_ver, installed_ver)

    def test_remote_install(self):
        source_dir = os.path.join(REPO_ROOT, "src", "flatmark")

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
        self.assertTrue(os.path.isfile(os.path.join(dest_dir, "flatmark.py")))
        self.assertTrue(os.path.isfile(os.path.join(dest_dir, "lint.py")))
        self.assertTrue(os.access(os.path.join(dest_dir, "flatmark.py"), os.X_OK))
        self.assertTrue(os.access(os.path.join(dest_dir, "lint.py"), os.X_OK))

    def test_default_raw_base_url(self):
        self.assertEqual(
            install.DEFAULT_RAW_BASE_URL,
            "https://raw.githubusercontent.com/slesar/flatmark/main/src/flatmark"
        )

    def test_get_local_source_dir(self):
        source_dir = install.get_local_source_dir()
        self.assertIsNotNone(source_dir)
        self.assertTrue(os.path.isdir(source_dir))
        self.assertEqual(
            os.path.abspath(source_dir),
            os.path.abspath(os.path.join(REPO_ROOT, "src", "flatmark"))
        )

    def test_one_liner_stdin_install(self):
        # Emulates: curl ... | python3 - <target>
        class LocalHandler(http.server.SimpleHTTPRequestHandler):
            def __init__(self, *args, **kwargs):
                super().__init__(*args, directory=os.path.join(REPO_ROOT, "src", "flatmark"), **kwargs)

            def log_message(self, format, *args):
                pass

        server = http.server.HTTPServer(("127.0.0.1", 0), LocalHandler)
        t = threading.Thread(target=server.serve_forever, daemon=True)
        t.start()
        port = server.server_port

        try:
            with open(os.path.join(REPO_ROOT, "install.py"), "r", encoding="utf-8") as f:
                installer_code = f.read()

            env = os.environ.copy()
            env["FLATMARK_RAW_URL"] = f"http://127.0.0.1:{port}"
            proc = subprocess.run(
                [sys.executable, "-", self.test_root],
                input=installer_code,
                text=True,
                capture_output=True,
                env=env,
            )
            self.assertEqual(proc.returncode, 0, f"Installer failed with stderr: {proc.stderr}")
            dest_dir = os.path.join(self.test_root, "flatmark")
            self.assertTrue(os.path.isdir(dest_dir))
            self.assertTrue(os.path.isfile(os.path.join(dest_dir, "BOARD.md")))
            self.assertTrue(os.path.isfile(os.path.join(dest_dir, "AGENTS.md")))
            self.assertTrue(os.path.isfile(os.path.join(dest_dir, "board.py")))
            self.assertTrue(os.path.isfile(os.path.join(dest_dir, "new.py")))
            self.assertTrue(os.path.isfile(os.path.join(dest_dir, "VERSION")))
            self.assertTrue(os.path.isfile(os.path.join(dest_dir, "flatmark.py")))
            self.assertTrue(os.path.isfile(os.path.join(dest_dir, "lint.py")))
            self.assertTrue(os.access(os.path.join(dest_dir, "flatmark.py"), os.X_OK))
            self.assertTrue(os.access(os.path.join(dest_dir, "lint.py"), os.X_OK))
        finally:
            server.shutdown()
            server.server_close()

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
    def test_payload_agents_doc_content(self):
        # D2: AGENTS.md schema table, workflow checklist, discoverability, AGENTS.local.md
        agents_path = os.path.join(REPO_ROOT, "src", "flatmark", "AGENTS.md")

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
        self.assertIn("flatmark.py lint", content)

        # Discoverability & Integration
        self.assertIn("Discoverability", content)
        self.assertIn("See [flatmark/AGENTS.md](flatmark/AGENTS.md)", content)

        # Customization story
        self.assertIn("AGENTS.local.md", content)

    def test_root_agents_doc_for_contributors(self):
        root_agents = os.path.join(REPO_ROOT, "AGENTS.md")
        self.assertTrue(os.path.isfile(root_agents))
        with open(root_agents, "r", encoding="utf-8") as f:
            content = f.read()

        self.assertIn("flatmark/AGENTS.md", content)
        self.assertIn("unittest discover tests", content)
        self.assertIn("src/flatmark", content)
        self.assertIn("flatmark/tickets", content)
        self.assertIn("flatmark.py lint", content)

    def test_contributing_doc(self):
        contrib_path = os.path.join(REPO_ROOT, "CONTRIBUTING.md")
        self.assertTrue(os.path.isfile(contrib_path))
        with open(contrib_path, "r", encoding="utf-8") as f:
            content = f.read()

        self.assertIn("Contributing to FlatMark", content)
        self.assertIn("unittest discover tests", content)


class TestLint(unittest.TestCase):
    def setUp(self):
        self.test_dir = tempfile.mkdtemp()
        self.tickets_dir = os.path.join(self.test_dir, "tickets")
        self.archive_dir = os.path.join(self.test_dir, "archive")
        os.makedirs(self.tickets_dir, exist_ok=True)
        os.makedirs(self.archive_dir, exist_ok=True)

    def tearDown(self):
        shutil.rmtree(self.test_dir)

    def write_ticket(self, folder, filename, content):
        target_dir = self.tickets_dir if folder == "tickets" else self.archive_dir
        path = os.path.join(target_dir, filename)
        with open(path, "w", encoding="utf-8") as f:
            f.write(content)
        return path

    def test_lint_clean_repository(self):
        self.write_ticket("tickets", "T1.md", """---
id: T1
priority: P1
status: Todo
---
# Ticket 1
""")
        self.write_ticket("archive", "T2.md", """---
id: T2
priority: P2
status: Done
---
# Ticket 2
""")
        issues, fixed = flatmark.lint_tickets(self.test_dir)
        self.assertEqual(len(issues), 0)
        self.assertEqual(fixed, 0)

        # lint_main exits 0
        buf = io.StringIO()
        with patch("sys.stdout", buf):
            code = flatmark.lint_main([self.test_dir])
        self.assertEqual(code, 0)
        self.assertIn("No issues found", buf.getvalue())

    def test_lint_missing_and_unclosed_frontmatter(self):
        self.write_ticket("tickets", "T1.md", "# No frontmatter\n")
        self.write_ticket("tickets", "T2.md", "---\nid: T2\nstatus: Todo\n# Missing closing")

        issues, _ = flatmark.lint_tickets(self.test_dir)
        messages = [f"{i.file_path}:{i.line}: {i.message}" for i in issues]

        self.assertTrue(any("T1.md:1: missing YAML frontmatter" in m for m in messages))
        self.assertTrue(any("T2.md:1: unclosed YAML frontmatter" in m for m in messages))

    def test_lint_invalid_frontmatter_line(self):
        self.write_ticket("tickets", "T1.md", """---
id: T1
invalid line without colon
status: Todo
---
# Title
""")
        issues, _ = flatmark.lint_tickets(self.test_dir)
        messages = [f"{i.file_path}:{i.line}: {i.message}" for i in issues]
        self.assertTrue(any("T1.md:3: invalid YAML frontmatter line" in m for m in messages))

    def test_lint_missing_and_mismatched_id(self):
        self.write_ticket("tickets", "T1.md", """---
priority: P1
status: Todo
---
# Missing ID
""")
        self.write_ticket("tickets", "T2.md", """---
id: WRONG
status: Todo
---
# Mismatched ID
""")
        issues, _ = flatmark.lint_tickets(self.test_dir)
        messages = [f"{i.file_path}:{i.line}: {i.message}" for i in issues]
        self.assertTrue(any("T1.md:1: missing 'id' in frontmatter" in m for m in messages))
        self.assertTrue(any("T2.md:2: ticket id 'WRONG' does not match filename 'T2.md'" in m for m in messages))

    def test_lint_unknown_priority_and_status(self):
        self.write_ticket("tickets", "T1.md", """---
id: T1
priority: P9
status: InReview
---
# Title
""")
        issues, _ = flatmark.lint_tickets(self.test_dir)
        messages = [f"{i.file_path}:{i.line}: {i.message}" for i in issues]
        self.assertTrue(any("T1.md:3: unknown priority 'P9'" in m for m in messages))
        self.assertTrue(any("T1.md:4: unknown status 'InReview'" in m for m in messages))

    def test_lint_duplicate_ids(self):
        self.write_ticket("tickets", "T1.md", """---
id: T1
status: Todo
---
# First
""")
        self.write_ticket("tickets", "T1_dup.md", """---
id: T1
status: Todo
---
# Duplicate
""")
        issues, _ = flatmark.lint_tickets(self.test_dir)
        messages = [f"{i.file_path}:{i.line}: {i.message}" for i in issues]
        self.assertTrue(any("T1.md:2: duplicate ticket ID 'T1'" in m for m in messages))
        self.assertTrue(any("T1_dup.md:2: duplicate ticket ID 'T1'" in m for m in messages))

    def test_lint_nonexistent_parent_and_blocker(self):
        self.write_ticket("tickets", "T1.md", """---
id: T1
status: Todo
parent: GHOST_PARENT
blocked by: GHOST_BLOCKER
---
# Title
""")
        issues, _ = flatmark.lint_tickets(self.test_dir)
        messages = [f"{i.file_path}:{i.line}: {i.message}" for i in issues]
        self.assertTrue(any("T1.md:4: parent ticket 'GHOST_PARENT' does not exist" in m for m in messages))
        self.assertTrue(any("T1.md:5: blocker ticket 'GHOST_BLOCKER' does not exist" in m for m in messages))

    def test_lint_self_parent_and_cycle(self):
        self.write_ticket("tickets", "T1.md", """---
id: T1
status: Todo
parent: T1
---
# Self parent
""")
        self.write_ticket("tickets", "T2.md", """---
id: T2
status: Todo
parent: T3
---
# Cycle node 1
""")
        self.write_ticket("tickets", "T3.md", """---
id: T3
status: Todo
parent: T2
---
# Cycle node 2
""")
        issues, _ = flatmark.lint_tickets(self.test_dir)
        messages = [f"{i.file_path}:{i.line}: {i.message}" for i in issues]
        self.assertTrue(any("T1.md:4: ticket cannot be its own parent" in m for m in messages))
        self.assertTrue(any("parent cycle detected: T2 -> T3 -> T2" in m for m in messages))
        self.assertTrue(any("parent cycle detected: T3 -> T2 -> T3" in m for m in messages))

    def test_lint_location_mismatches(self):
        # Done in tickets/
        self.write_ticket("tickets", "T1.md", """---
id: T1
status: Done
---
# Done in tickets
""")
        # Obsolete in tickets/
        self.write_ticket("tickets", "T2.md", """---
id: T2
status: Obsolete
---
# Obsolete in tickets
""")
        # Todo in archive/
        self.write_ticket("archive", "T3.md", """---
id: T3
status: Todo
---
# Active in archive
""")
        # In Progress in archive/
        self.write_ticket("archive", "T4.md", """---
id: T4
status: In Progress
---
# In progress in archive
""")
        issues, _ = flatmark.lint_tickets(self.test_dir)
        messages = [f"{i.file_path}:{i.line}: {i.message}" for i in issues]
        self.assertTrue(any("T1.md:3: ticket with status 'Done' should be in archive/" in m for m in messages))
        self.assertTrue(any("T2.md:3: ticket with status 'Obsolete' should be in archive/" in m for m in messages))
        self.assertTrue(any("T3.md:3: ticket with status 'Todo' should be in tickets/" in m for m in messages))
        self.assertTrue(any("T4.md:3: ticket with status 'In Progress' should be in tickets/" in m for m in messages))

    def test_lint_fix_moves_tickets_and_repairs_ids(self):
        # Setup board.py in test_dir so update_board can run
        shutil.copy2(os.path.join(SRC_DIR, "board.py"), os.path.join(self.test_dir, "board.py"))
        with open(os.path.join(self.test_dir, "VERSION"), "w") as f:
            f.write("0.1.0\n")

        # Done ticket in tickets/
        self.write_ticket("tickets", "T1.md", """---
id: T1
status: Done
---
# Done ticket
""")
        # Todo ticket in archive/
        self.write_ticket("archive", "T2.md", """---
id: T2
status: Todo
---
# Todo ticket
""")
        # Missing ID
        self.write_ticket("tickets", "T3.md", """---
priority: P1
status: Todo
---
# Missing ID
""")
        # Mismatched ID
        self.write_ticket("tickets", "T4.md", """---
id: WRONG_ID
status: Todo
---
# Mismatched ID
""")

        issues, fixed = flatmark.lint_tickets(self.test_dir, fix=True)
        self.assertEqual(len(issues), 0)
        self.assertEqual(fixed, 4)

        # Verify files moved
        self.assertTrue(os.path.isfile(os.path.join(self.archive_dir, "T1.md")))
        self.assertFalse(os.path.isfile(os.path.join(self.tickets_dir, "T1.md")))

        self.assertTrue(os.path.isfile(os.path.join(self.tickets_dir, "T2.md")))
        self.assertFalse(os.path.isfile(os.path.join(self.archive_dir, "T2.md")))

        # Verify IDs fixed
        with open(os.path.join(self.tickets_dir, "T3.md"), "r", encoding="utf-8") as f:
            t3_content = f.read()
        self.assertIn("id: T3", t3_content)

        with open(os.path.join(self.tickets_dir, "T4.md"), "r", encoding="utf-8") as f:
            t4_content = f.read()
        self.assertIn("id: T4", t4_content)
        self.assertNotIn("WRONG_ID", t4_content)

        # Verify BOARD.md was updated
        board_path = os.path.join(self.test_dir, "BOARD.md")
        self.assertTrue(os.path.isfile(board_path))
        with open(board_path, "r", encoding="utf-8") as f:
            board_text = f.read()
        self.assertIn("[T2]", board_text)
        self.assertIn("[T3]", board_text)
        self.assertIn("[T4]", board_text)
        self.assertNotIn("[T1]", board_text)

    def test_lint_cli_and_wrapper_subprocesses(self):
        # Create a ticket with an error
        self.write_ticket("tickets", "T1.md", """---
id: T1
priority: P9
status: Todo
---
# Invalid priority
""")
        flatmark_script = os.path.join(SRC_DIR, "flatmark.py")
        lint_script = os.path.join(SRC_DIR, "lint.py")

        # Test `flatmark.py lint`
        proc1 = subprocess.run(
            [sys.executable, flatmark_script, "lint", self.test_dir],
            capture_output=True,
            text=True,
        )
        self.assertEqual(proc1.returncode, 1)
        self.assertIn("T1.md:3: unknown priority 'P9'", proc1.stdout)

        # Test `flatmark.py check` alias
        proc2 = subprocess.run(
            [sys.executable, flatmark_script, "check", self.test_dir],
            capture_output=True,
            text=True,
        )
        self.assertEqual(proc2.returncode, 1)
        self.assertIn("T1.md:3: unknown priority 'P9'", proc2.stdout)

        # Test `lint.py` wrapper
        proc3 = subprocess.run(
            [sys.executable, lint_script, self.test_dir],
            capture_output=True,
            text=True,
        )
        self.assertEqual(proc3.returncode, 1)
        self.assertIn("T1.md:3: unknown priority 'P9'", proc3.stdout)

if __name__ == "__main__":
    unittest.main()
