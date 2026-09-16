"""
test_manager.py
----------------
Unit tests for TaskManager, using Python's built-in unittest module
(no extra dependencies required).

Run with:
    python -m unittest discover -s tests -v
from the project root, or simply:
    python tests/test_manager.py

Each test uses a temporary file for storage so tests never touch a
real tasks.json and can run in any order without interfering with
each other.
"""

import os
import sys
import tempfile
import unittest

# Make the project root importable when running this file directly.
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from todo_app.manager import TaskManager, TaskNotFoundError, ValidationError


class TestTaskManager(unittest.TestCase):
    def setUp(self):
        # A fresh temp file per test avoids cross-test contamination.
        fd, self.path = tempfile.mkstemp(suffix=".json")
        os.close(fd)
        os.remove(self.path)  # start from "file does not exist yet"
        self.manager = TaskManager(self.path)

    def tearDown(self):
        if os.path.exists(self.path):
            os.remove(self.path)
        tmp = f"{self.path}.tmp"
        if os.path.exists(tmp):
            os.remove(tmp)

    def test_add_task_basic(self):
        task = self.manager.add_task("Buy milk")
        self.assertEqual(task.title, "Buy milk")
        self.assertEqual(task.priority, "medium")
        self.assertFalse(task.completed)
        self.assertEqual(len(self.manager.list_tasks()), 1)

    def test_add_task_empty_title_raises(self):
        with self.assertRaises(ValidationError):
            self.manager.add_task("   ")

    def test_add_task_invalid_priority_raises(self):
        with self.assertRaises(ValidationError):
            self.manager.add_task("Task", priority="urgent!")

    def test_add_task_invalid_due_date_raises(self):
        with self.assertRaises(ValidationError):
            self.manager.add_task("Task", due_date="31-12-2026")

    def test_ids_increment_and_do_not_reuse_after_delete(self):
        t1 = self.manager.add_task("First")
        t2 = self.manager.add_task("Second")
        self.manager.remove_task(t1.id)
        t3 = self.manager.add_task("Third")
        self.assertNotEqual(t3.id, t1.id)
        self.assertEqual(t3.id, t2.id + 1)

    def test_complete_task(self):
        task = self.manager.add_task("Finish report")
        self.manager.complete_task(task.id)
        updated = self.manager.get_task(task.id)
        self.assertTrue(updated.completed)

    def test_complete_nonexistent_task_raises(self):
        with self.assertRaises(TaskNotFoundError):
            self.manager.complete_task(999)

    def test_remove_task(self):
        task = self.manager.add_task("Temp task")
        self.manager.remove_task(task.id)
        with self.assertRaises(TaskNotFoundError):
            self.manager.get_task(task.id)

    def test_remove_nonexistent_task_raises(self):
        with self.assertRaises(TaskNotFoundError):
            self.manager.remove_task(42)

    def test_edit_task_partial_update(self):
        task = self.manager.add_task("Old title", priority="low")
        self.manager.edit_task(task.id, priority="high")
        updated = self.manager.get_task(task.id)
        self.assertEqual(updated.title, "Old title")  # unchanged
        self.assertEqual(updated.priority, "high")  # changed

    def test_edit_task_clear_due_date(self):
        task = self.manager.add_task("Task", due_date="2026-01-01")
        self.manager.edit_task(task.id, due_date="")
        updated = self.manager.get_task(task.id)
        self.assertIsNone(updated.due_date)

    def test_list_tasks_filter_pending(self):
        t1 = self.manager.add_task("A")
        t2 = self.manager.add_task("B")
        self.manager.complete_task(t1.id)
        pending = self.manager.list_tasks(show_completed=False)
        self.assertEqual([t.id for t in pending], [t2.id])

    def test_list_tasks_filter_priority(self):
        self.manager.add_task("Low one", priority="low")
        high_task = self.manager.add_task("High one", priority="high")
        results = self.manager.list_tasks(priority_filter="high")
        self.assertEqual([t.id for t in results], [high_task.id])

    def test_persistence_across_manager_instances(self):
        task = self.manager.add_task("Persisted task")
        reloaded = TaskManager(self.path)
        self.assertEqual(len(reloaded.tasks), 1)
        self.assertEqual(reloaded.tasks[0].title, task.title)

    def test_stats(self):
        t1 = self.manager.add_task("A")
        self.manager.add_task("B")
        self.manager.complete_task(t1.id)
        stats = self.manager.stats()
        self.assertEqual(stats["total"], 2)
        self.assertEqual(stats["completed"], 1)
        self.assertEqual(stats["pending"], 1)


if __name__ == "__main__":
    unittest.main()
