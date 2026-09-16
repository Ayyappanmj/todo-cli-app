"""
reproduce_bugs.py
------------------
Drives the ACTUAL todo_app package (models.py, storage.py, manager.py,
cli.py) — the same modules used by main.py — to reliably reproduce
each injected bug and capture real output/tracebacks for the
debugging log. Run from inside original_buggy_project/.
"""

import os
import sys
import json
import tempfile
import traceback

sys.path.insert(0, ".")


def section(title):
    print("\n" + "=" * 74)
    print(title)
    print("=" * 74)


def run(label, fn):
    print(f"\n--- {label} ---")
    try:
        result = fn()
        print(f"Result: {result!r}")
    except Exception:
        print("EXCEPTION RAISED:")
        traceback.print_exc()


def tmp_path():
    fd, path = tempfile.mkstemp(suffix=".json")
    os.close(fd)
    os.remove(path)
    return path


# ---------------------------------------------------------------------
from todo_app.manager import TaskManager
from todo_app.models import Task

# -----------------------------------------------------------------
# Bug B1: manager._compute_next_id() uses len(tasks)+1 -> duplicate IDs
# -----------------------------------------------------------------
section("BUG B1 (manager.py): duplicate task IDs after deletion + restart")
p = tmp_path()
m = TaskManager(p)
m.add_task("First")      # id 1
m.add_task("Second")     # id 2
m.add_task("Third")      # id 3
m.remove_task(2)         # remove "Second" -> tasks on disk now have ids [1, 3]
# _compute_next_id() only runs when a TaskManager is constructed, so this
# simulates the user closing and reopening the app (a fresh session):
m2 = TaskManager(p)
t4 = m2.add_task("Fourth")
ids = [t.id for t in m2.tasks]
print("Ids after restart + adding 'Fourth':", ids)
print("New task id:", t4.id, "| collides with an existing task?",
      ids.count(t4.id) > 1)

# -----------------------------------------------------------------
# Bug B2: manager._validate_priority() no longer lowercases input
# -----------------------------------------------------------------
section("BUG B2 (manager.py): priority is case-sensitive")
p = tmp_path()
m = TaskManager(p)
run("add_task('Task', priority='High')", lambda: m.add_task("Task", priority="High"))

# -----------------------------------------------------------------
# Bug B3: manager.edit_task() can't clear a due date anymore
# -----------------------------------------------------------------
section("BUG B3 (manager.py): clearing a due date silently does nothing")
p = tmp_path()
m = TaskManager(p)
t = m.add_task("Task with a due date", due_date="2026-01-01")
m.edit_task(t.id, due_date="")   # empty string is meant to CLEAR the due date
reloaded = m.get_task(t.id)
print("due_date after 'clearing' it:", reloaded.due_date, "(expected: None)")

# -----------------------------------------------------------------
# Bug B4: models.Task.is_overdue() flags a task due TODAY as overdue
# -----------------------------------------------------------------
section("BUG B4 (models.py): task due today is incorrectly 'overdue'")
from datetime import date
today_task = Task(id=1, title="Due today", due_date=date.today().isoformat())
print("is_overdue():", today_task.is_overdue(), "(expected: False, it's not overdue until AFTER today)")

# -----------------------------------------------------------------
# Bug B5: models.Task.from_dict() requires 'description' key
# -----------------------------------------------------------------
section("BUG B5 (models.py): loading an older-format record crashes")
old_format_record = {"id": 1, "title": "Legacy task"}  # no 'description' key
run("Task.from_dict(old_format_record)", lambda: Task.from_dict(old_format_record))

# -----------------------------------------------------------------
# Bug B6: storage.save_tasks() no longer handles write errors / atomic write
# -----------------------------------------------------------------
section("BUG B6 (storage.py): save_tasks() crashes with a raw OSError")
from todo_app.storage import save_tasks
bad_path = "/this/directory/does/not/exist/tasks.json"
run("save_tasks(tasks, bad_path)", lambda: save_tasks([Task(id=1, title="x")], bad_path))

# -----------------------------------------------------------------
# Bug B7: storage.load_tasks() - one bad record crashes the WHOLE file
# -----------------------------------------------------------------
section("BUG B7 (storage.py): one malformed task record loses ALL tasks")
p = tmp_path()
with open(p, "w") as f:
    json.dump([
        {"id": 1, "title": "Good task", "description": "", "priority": "medium",
         "due_date": None, "completed": False, "created_at": "2026-01-01T00:00:00"},
        {"id": 2, "title": "Malformed task"},  # missing required fields
    ], f)
from todo_app.storage import load_tasks
run("load_tasks(path_with_one_bad_record)", lambda: load_tasks(p))
print("Expected: the GOOD task should still load; instead the whole load crashes.")

# -----------------------------------------------------------------
# Bug B8: cli.complete_task() swallows StorageError with no feedback
# -----------------------------------------------------------------
section("BUG B8 (cli.py): a failed save gives the user NO feedback at all")
print("(See DEBUGGING_LOG.md — reproduced via code walkthrough: the")
print(" `except StorageError: pass` block prints nothing on failure,")
print(" and the success message in the `else` clause is skipped too,")
print(" so the user sees no output and wrongly assumes nothing happened")
print(" rather than being told their change was lost.)")
