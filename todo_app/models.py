"""
models.py
---------
Defines the core data structure of the application: the Task.

Design choice:
    A Task is modelled as a plain, self-contained class rather than a
    dictionary. This gives us:
      * Named, typed attributes (fewer "magic string" key lookups / typos).
      * A single place (to_dict / from_dict) to control how a Task is
        serialized, which decouples the in-memory representation from
        the on-disk (JSON) representation.
      * Room to grow (e.g. validation, extra fields) without touching
        every other module that manipulates tasks.
"""

from __future__ import annotations

from dataclasses import dataclass, field, asdict
from datetime import datetime, date
from typing import Optional


# Allowed priority levels. Kept as a module-level constant so both the
# model (for validation) and the CLI (for prompting/choices) share one
# source of truth instead of duplicating the list of valid values.
VALID_PRIORITIES = ("low", "medium", "high")


@dataclass
class Task:
    """Represents a single to-do item.

    Attributes:
        id: Unique integer identifier assigned by the TaskManager.
        title: Short, required description of the task.
        description: Optional longer text with more detail.
        priority: One of VALID_PRIORITIES ('low', 'medium', 'high').
        due_date: Optional ISO date string (YYYY-MM-DD).
        completed: Whether the task has been marked done.
        created_at: Timestamp string set automatically on creation.
    """

    id: int
    title: str
    description: str = ""
    priority: str = "medium"
    due_date: Optional[str] = None
    completed: bool = False
    created_at: str = field(
        default_factory=lambda: datetime.now().isoformat(timespec="seconds")
    )

    def mark_completed(self) -> None:
        """Flip the task's status to completed."""
        self.completed = True

    def mark_incomplete(self) -> None:
        """Flip the task's status back to not completed (undo)."""
        self.completed = False

    def to_dict(self) -> dict:
        """Convert the Task into a plain dict for JSON serialization."""
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "Task":
        """Rebuild a Task instance from a dict (e.g. loaded from JSON).

        Using a classmethod keeps the "how do I deserialize" logic next
        to the class it produces, rather than scattered in storage.py.
        """
        return cls(
            id=int(data["id"]),
            title=str(data["title"]),
            description=str(data.get("description", "")),
            priority=str(data.get("priority", "medium")),
            due_date=data.get("due_date"),
            completed=bool(data.get("completed", False)),
            created_at=str(data.get("created_at", datetime.now().isoformat())),
        )

    def is_overdue(self) -> bool:
        """Return True if the task has a due date in the past and is not done."""
        if not self.due_date or self.completed:
            return False
        try:
            due = date.fromisoformat(self.due_date)
        except ValueError:
            # Malformed date strings are treated as "no due date" rather
            # than crashing the whole application.
            return False
        return due < date.today()

    def __str__(self) -> str:
        """Human-friendly one-line representation used by the CLI table."""
        status = "✔" if self.completed else "✘"
        due = f" | due: {self.due_date}" if self.due_date else ""
        overdue = " (OVERDUE)" if self.is_overdue() else ""
        return f"[{status}] #{self.id} ({self.priority}) {self.title}{due}{overdue}"
