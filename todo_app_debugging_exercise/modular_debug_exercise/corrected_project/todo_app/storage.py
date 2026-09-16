"""
storage.py
----------
Handles persistence of tasks to disk as JSON.

Design choice:
    Persistence is isolated in its own module (Single Responsibility
    Principle). TaskManager doesn't know or care whether tasks live in
    a JSON file, a database, or memory only — it just calls
    load_tasks() / save_tasks(). This makes it easy to swap the storage
    backend later (e.g. SQLite) without touching business logic in
    manager.py, and makes both modules easier to test in isolation.
"""

from __future__ import annotations

import json
import os
from typing import List

from .models import Task


class StorageError(Exception):
    """Raised when tasks cannot be read from or written to disk."""


DEFAULT_FILE = "tasks.json"


def load_tasks(filepath: str = DEFAULT_FILE) -> List[Task]:
    """Load tasks from a JSON file.

    Returns an empty list if the file does not exist yet (first run),
    which keeps the caller's code simple (no need to special-case a
    "missing file" scenario).

    Raises:
        StorageError: if the file exists but contains invalid/corrupt
            JSON, so the caller can decide how to inform the user
            instead of the program crashing with a raw traceback.
    """
    if not os.path.exists(filepath):
        return []

    try:
        with open(filepath, "r", encoding="utf-8") as f:
            raw = f.read().strip()
    except OSError as exc:
        raise StorageError(f"Could not read '{filepath}': {exc}") from exc

    if not raw:
        # Empty file is treated as "no tasks yet" rather than an error.
        return []

    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise StorageError(
            f"'{filepath}' is not valid JSON and may be corrupted: {exc}"
        ) from exc

    if not isinstance(data, list):
        raise StorageError(f"'{filepath}' does not contain a list of tasks.")

    tasks: List[Task] = []
    for item in data:
        try:
            tasks.append(Task.from_dict(item))
        except (KeyError, TypeError, ValueError) as exc:
            # Skip a malformed individual record rather than discarding
            # the whole file — one bad entry shouldn't nuke everything.
            print(f"Warning: skipping malformed task entry ({exc}).")
    return tasks


def save_tasks(tasks: List[Task], filepath: str = DEFAULT_FILE) -> None:
    """Persist the given list of tasks to a JSON file.

    Writes to a temporary file first and then renames it into place.
    This "atomic write" pattern avoids leaving a half-written/corrupt
    tasks.json if the program is interrupted mid-write (e.g. Ctrl+C or
    a power loss during the write).
    """
    tmp_path = f"{filepath}.tmp"
    try:
        with open(tmp_path, "w", encoding="utf-8") as f:
            json.dump([t.to_dict() for t in tasks], f, indent=2)
        os.replace(tmp_path, filepath)
    except OSError as exc:
        raise StorageError(f"Could not write to '{filepath}': {exc}") from exc
