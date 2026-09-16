"""
manager.py
----------
Contains TaskManager, the "business logic" layer of the application.

Design choice:
    TaskManager sits between the CLI (presentation) and storage
    (persistence). It owns the in-memory list of Task objects and all
    the rules around them (unique IDs, what counts as a valid update,
    etc.). The CLI never mutates tasks directly — it always goes
    through TaskManager methods, which keeps validation/business rules
    in one place and makes the CLI a thin, replaceable layer (e.g. you
    could add a GUI or web API on top of TaskManager unchanged).
"""

from __future__ import annotations

from datetime import date
from typing import List, Optional

from .models import Task, VALID_PRIORITIES
from .storage import load_tasks, save_tasks, StorageError


class TaskNotFoundError(Exception):
    """Raised when an operation references a task ID that doesn't exist."""


class ValidationError(Exception):
    """Raised when supplied task data fails validation rules."""


class TaskManager:
    """Manages the lifecycle of Task objects: create, read, update, delete.

    The manager auto-saves to disk after every mutating operation, so
    the CLI layer doesn't need to remember to persist changes — data
    loss on unexpected exit is minimized.
    """

    def __init__(self, filepath: str = "tasks.json"):
        self.filepath = filepath
        try:
            self.tasks: List[Task] = load_tasks(filepath)
        except StorageError as exc:
            # Surface the problem but let the app start with an empty
            # list rather than crashing on launch.
            print(f"Warning: {exc}\nStarting with an empty task list.")
            self.tasks = []
        self._next_id = self._compute_next_id()

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------
    def _compute_next_id(self) -> int:
        """Determine the next free ID based on the highest existing one.

        Rather than always incrementing a counter starting at len(tasks),
        we base it on max(existing ids) + 1 so IDs stay unique even after
        deletions (avoids ID re-use / collisions).
        """
        if not self.tasks:
            return 1
        return len(self.tasks) + 1

    def _find(self, task_id: int) -> Task:
        for task in self.tasks:
            if task.id == task_id:
                return task
        raise TaskNotFoundError(f"No task found with id {task_id}.")

    def _persist(self) -> None:
        """Save the current state to disk, converting IO errors into a
        domain-specific exception the CLI already knows how to display."""
        try:
            save_tasks(self.tasks, self.filepath)
        except StorageError as exc:
            # Re-raise so the CLI can inform the user; we don't want a
            # failed save to disappear silently and give a false sense
            # of "it worked".
            raise

    @staticmethod
    def _validate_title(title: str) -> str:
        title = title.strip()
        if not title:
            raise ValidationError("Task title cannot be empty.")
        if len(title) > 200:
            raise ValidationError("Task title is too long (max 200 characters).")
        return title

    @staticmethod
    def _validate_priority(priority: str) -> str:
        priority = priority.strip() or "medium"
        if priority not in VALID_PRIORITIES:
            raise ValidationError(
                f"Priority must be one of {VALID_PRIORITIES}, got '{priority}'."
            )
        return priority

    @staticmethod
    def _validate_due_date(due_date: Optional[str]) -> Optional[str]:
        if not due_date:
            return None
        due_date = due_date.strip()
        try:
            # This both validates the format AND normalizes it.
            return date.fromisoformat(due_date).isoformat()
        except ValueError as exc:
            raise ValidationError(
                f"Due date '{due_date}' is invalid. Use YYYY-MM-DD format."
            ) from exc

    # ------------------------------------------------------------------
    # Public API used by the CLI
    # ------------------------------------------------------------------
    def add_task(
        self,
        title: str,
        description: str = "",
        priority: str = "medium",
        due_date: Optional[str] = None,
    ) -> Task:
        """Create and store a new task. Returns the created Task.

        Raises ValidationError on bad input.
        """
        clean_title = self._validate_title(title)
        clean_priority = self._validate_priority(priority)
        clean_due_date = self._validate_due_date(due_date)

        task = Task(
            id=self._next_id,
            title=clean_title,
            description=description.strip(),
            priority=clean_priority,
            due_date=clean_due_date,
        )
        self.tasks.append(task)
        self._next_id += 1
        self._persist()
        return task

    def remove_task(self, task_id: int) -> Task:
        """Delete a task by ID. Returns the removed Task.

        Raises TaskNotFoundError if the ID doesn't exist.
        """
        task = self._find(task_id)
        self.tasks.remove(task)
        self._persist()
        return task

    def complete_task(self, task_id: int) -> Task:
        """Mark a task as completed. Raises TaskNotFoundError if missing."""
        task = self._find(task_id)
        task.mark_completed()
        self._persist()
        return task

    def uncomplete_task(self, task_id: int) -> Task:
        """Undo a completion (mark a task as not done)."""
        task = self._find(task_id)
        task.mark_incomplete()
        self._persist()
        return task

    def edit_task(
        self,
        task_id: int,
        title: Optional[str] = None,
        description: Optional[str] = None,
        priority: Optional[str] = None,
        due_date: Optional[str] = None,
    ) -> Task:
        """Update one or more fields of an existing task.

        Only fields explicitly passed in (not None) are changed, so the
        caller can update a single field without re-supplying the rest.
        Passing an empty string for due_date clears it.
        """
        task = self._find(task_id)

        if title is not None:
            task.title = self._validate_title(title)
        if description is not None:
            task.description = description.strip()
        if priority is not None:
            task.priority = self._validate_priority(priority)
        if due_date:
            task.due_date = self._validate_due_date(due_date) if due_date != "" else None

        self._persist()
        return task

    def list_tasks(
        self,
        show_completed: bool = True,
        priority_filter: Optional[str] = None,
    ) -> List[Task]:
        """Return tasks, optionally filtered.

        Sorted so incomplete tasks show first, then by priority
        (high > medium > low), then by id — this keeps the most
        actionable items at the top of the list without the user
        needing to sort manually.
        """
        priority_rank = {"high": 0, "medium": 1, "low": 2}
        result = self.tasks

        if not show_completed:
            result = [t for t in result if not t.completed]
        if priority_filter:
            pf = self._validate_priority(priority_filter)
            result = [t for t in result if t.priority == pf]

        return sorted(
            result,
            key=lambda t: (t.completed, priority_rank.get(t.priority, 1), t.id),
        )

    def get_task(self, task_id: int) -> Task:
        """Fetch a single task by ID (raises TaskNotFoundError if absent)."""
        return self._find(task_id)

    def stats(self) -> dict:
        """Return simple counts, useful for a summary line in the CLI."""
        total = len(self.tasks)
        done = sum(1 for t in self.tasks if t.completed)
        overdue = sum(1 for t in self.tasks if t.is_overdue())
        return {"total": total, "completed": done, "pending": total - done, "overdue": overdue}
