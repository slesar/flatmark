import os
import shutil
import tempfile
import unittest
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
            with open(os.path.join(self.tickets_dir, tid), "w") as f:
                f.write("")

        # Create T3 in archive
        with open(os.path.join(self.archive_dir, "T3.md"), "w") as f:
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


if __name__ == "__main__":
    unittest.main()
