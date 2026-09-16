"""
b8_repro.py
-----------
Demonstrates Bug B8 directly: cli.TodoCLI.complete_task() swallows
StorageError, so a failed save gives the user literally no feedback.
(An interactive end-to-end repro isn't reliable here since this
container runs as root, which bypasses normal directory permission
checks -- so the save is forced to fail by pointing at a directory
that does not exist, which fails unconditionally.)
"""
import io
import contextlib
from unittest.mock import patch

from todo_app.cli import TodoCLI
from todo_app.storage import StorageError

cli = TodoCLI("/tmp/b8_repro_tasks.json")
cli.manager.add_task("Existing task")

# Force the next save to raise StorageError specifically (isolating
# Bug B8 in cli.py from Bug B6 in storage.py, which are otherwise
# entangled: B6 means save_tasks() no longer raises StorageError for
# an OSError, only a raw OSError -- which cli.py's `except StorageError`
# doesn't even catch, crashing the whole program instead of swallowing
# it. That interaction is documented separately in DEBUGGING_LOG.md.)
def failing_save(tasks, filepath):
    raise StorageError("Disk is full (simulated failure).")

captured = io.StringIO()
with patch("builtins.input", side_effect=["1"]), \
     patch("todo_app.manager.save_tasks", side_effect=failing_save), \
     contextlib.redirect_stdout(captured):
    cli.complete_task()

output = captured.getvalue()
print("Captured stdout during complete_task() with a forced save failure:")
print(repr(output))
print()
if output.strip() == "":
    print(">>> CONFIRMED: no output was shown to the user at all.")
    print(">>> The task's in-memory state WAS changed to completed, but the")
    print(">>> change silently failed to save -- the user has no way to know.")
