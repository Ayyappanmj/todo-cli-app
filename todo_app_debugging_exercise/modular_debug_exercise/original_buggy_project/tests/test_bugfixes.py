"""
test_bugfixes.py
-----------------
Regression tests targeting the specific bugs found and fixed during
this debugging exercise. Run alongside the existing tests/test_manager.py:

    python -m unittest discover -s tests -v

(test_manager.py already independently catches Bug B3 via
test_edit_task_clear_due_date, and surfaces Bug B6 as a ResourceWarning
on every test that calls save_tasks — both are noted in DEBUGGING_LOG.md
rather than duplicated here.)
"""

import os
import sys
import json
import tempfile
import unittest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from todo_app.manager import TaskManager
from todo_app.models import Task
from todo_app.storage import load_tasks, save_tasks


class TestBugFixes(unittest.TestCase):
    def setUp(self):
        fd, self.path = tempfile.mkstemp(suffix=".json")
        os.close(fd)
        os.remove(self.path)

    def tearDown(self):
        for path in (self.path, f"{self.path}.tmp"):
            if os.path.exists(path):
                os.remove(path)

    def test_bug_b1_ids_not_reused_after_restart(self):
        """Bug B1: _compute_next_id() must use max(id)+1, not len(tasks)+1,
        so IDs stay unique even after a task is deleted and the app is
        restarted (a fresh TaskManager is constructed)."""
        m = TaskManager(self.path)
        m.add_task("First")
        m.add_task("Second")
        m.add_task("Third")
        m.remove_task(2)

        m2 = TaskManager(self.path)  # simulates restarting the app
        new_task = m2.add_task("Fourth")
        ids = [t.id for t in m2.tasks]
        self.assertEqual(len(ids), len(set(ids)), f"duplicate ids found: {ids}")
        self.assertEqual(new_task.id, 4)  # max existing (3) + 1, not len(2)+1

    def test_bug_b2_priority_is_case_insensitive(self):
        """Bug B2: priority validation must normalize case."""
        m = TaskManager(self.path)
        task = m.add_task("Task", priority="High")
        self.assertEqual(task.priority, "high")

    def test_bug_b4_task_due_today_is_not_overdue(self):
        """Bug B4: a task due today should not be flagged overdue until
        AFTER today (strict less-than, not less-than-or-equal)."""
        from datetime import date
        task = Task(id=1, title="Due today", due_date=date.today().isoformat())
        self.assertFalse(task.is_overdue())

    def test_bug_b5_from_dict_handles_missing_description(self):
        """Bug B5: older-format records without a 'description' key must
        still load, defaulting to an empty string."""
        old_record = {"id": 1, "title": "Legacy task"}
        task = Task.from_dict(old_record)
        self.assertEqual(task.description, "")

    def test_bug_b7_one_bad_record_does_not_lose_the_rest(self):
        """Bug B7: a single malformed task record in tasks.json must be
        skipped with a warning, not crash the load and lose every task."""
        with open(self.path, "w") as f:
            json.dump([
                {"id": 1, "title": "Good task", "description": "", "priority": "medium",
                 "due_date": None, "completed": False, "created_at": "2026-01-01T00:00:00"},
                {"title": "Malformed task — missing the required 'id' field"},
            ], f)
        tasks = load_tasks(self.path)  # must not raise
        self.assertEqual(len(tasks), 1)
        self.assertEqual(tasks[0].title, "Good task")

    def test_bug_b6_save_tasks_reports_write_failures(self):
        """Bug B6: a write failure must raise a clear StorageError, not a
        raw, unhandled OSError/FileNotFoundError."""
        from todo_app.storage import StorageError
        bad_path = "/this/directory/does/not/exist/tasks.json"
        with self.assertRaises(StorageError):
            save_tasks([Task(id=1, title="x")], bad_path)


if __name__ == "__main__":
    unittest.main()
