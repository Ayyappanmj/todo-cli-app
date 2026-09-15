"""
cli.py
------
The presentation layer: a text menu that drives the TaskManager.

Design choice:
    All user interaction (input()/print()) lives here, and nowhere
    else. The CLI never manipulates the task list directly — it only
    calls TaskManager methods and displays results or errors. This
    separation means:
      * Validation/business rules can't be bypassed or duplicated.
      * The same TaskManager could be reused behind a different
        interface (GUI, web API, tests) without change.
      * This file can be read top-to-bottom as "what can a user do?"
"""

from __future__ import annotations

from .manager import TaskManager, TaskNotFoundError, ValidationError
from .storage import StorageError
from .models import VALID_PRIORITIES

MENU = """
==================== TO-DO LIST MANAGER ====================
 1) Add a task
 2) View tasks
 3) Mark task as completed
 4) Mark task as not completed (undo)
 5) Edit a task
 6) Remove a task
 7) Show summary
 8) Exit
==============================================================
"""


def prompt(msg: str) -> str:
    """Wrapper around input() so all prompts are handled consistently
    and Ctrl+C / Ctrl+D during a prompt don't crash with a raw traceback."""
    try:
        return input(msg)
    except (EOFError, KeyboardInterrupt):
        print("\nInput cancelled.")
        return ""


def prompt_int(msg: str) -> int | None:
    """Prompt for an integer, re-asking on invalid input.

    Returns None if the user cancels by entering nothing, so calling
    code can treat that as "go back to the menu" instead of forcing a
    number out of the user.
    """
    while True:
        raw = prompt(msg).strip()
        if raw == "":
            return None
        try:
            return int(raw)
        except ValueError:
            print("Please enter a whole number (or leave blank to cancel).")


def print_task_table(tasks) -> None:
    """Print tasks as a simple aligned table, or a friendly empty message."""
    if not tasks:
        print("No tasks to show.")
        return
    for task in tasks:
        print(f"  {task}")


class TodoCLI:
    """Thin controller that wires user menu choices to TaskManager calls."""

    def __init__(self, filepath: str = "tasks.json"):
        self.manager = TaskManager(filepath)

    def run(self) -> None:
        print("Welcome to your To-Do List Manager!")
        while True:
            print(MENU)
            choice = prompt("Choose an option (1-8): ").strip()

            # A dispatch table keeps this loop short and makes it obvious
            # where to add a new menu option in future.
            actions = {
                "1": self.add_task,
                "2": self.view_tasks,
                "3": self.complete_task,
                "4": self.uncomplete_task,
                "5": self.edit_task,
                "6": self.remove_task,
                "7": self.show_summary,
                "8": self.exit_app,
            }

            action = actions.get(choice)
            if action is None:
                print("Invalid choice — please enter a number from 1 to 8.")
                continue

            if action():  # actions return True to signal "quit the loop"
                break

    # ------------------------------------------------------------------
    # Menu actions. Each returns True only when the app should exit.
    # ------------------------------------------------------------------
    def add_task(self) -> bool:
        print("\n-- Add a new task --")
        title = prompt("Title (required): ")
        description = prompt("Description (optional): ")
        priority = prompt(
            f"Priority {VALID_PRIORITIES} [default: medium]: "
        ).strip() or "medium"
        due_date = prompt("Due date YYYY-MM-DD (optional): ").strip()

        try:
            task = self.manager.add_task(
                title=title,
                description=description,
                priority=priority,
                due_date=due_date or None,
            )
        except ValidationError as exc:
            print(f"Could not add task: {exc}")
        except StorageError as exc:
            print(f"Task was created but could not be saved to disk: {exc}")
        else:
            print(f"Added task #{task.id}: '{task.title}'")
        return False

    def view_tasks(self) -> bool:
        print("\n-- View tasks --")
        filter_choice = prompt(
            "Filter: [a]ll (default) / [p]ending only / priority (low/medium/high): "
        ).strip().lower()

        show_completed = True
        priority_filter = None
        if filter_choice in ("p", "pending"):
            show_completed = False
        elif filter_choice in VALID_PRIORITIES:
            priority_filter = filter_choice
        elif filter_choice not in ("", "a", "all"):
            print(f"Unrecognized filter '{filter_choice}', showing all tasks instead.")

        try:
            tasks = self.manager.list_tasks(
                show_completed=show_completed, priority_filter=priority_filter
            )
        except ValidationError as exc:
            print(f"Invalid filter: {exc}")
            return False

        print()
        print_task_table(tasks)
        return False

    def complete_task(self) -> bool:
        print("\n-- Mark task as completed --")
        task_id = prompt_int("Task ID (blank to cancel): ")
        if task_id is None:
            return False
        try:
            task = self.manager.complete_task(task_id)
        except TaskNotFoundError as exc:
            print(exc)
        except StorageError as exc:
            print(f"Could not save change: {exc}")
        else:
            print(f"Marked '#{task.id} {task.title}' as completed.")
        return False

    def uncomplete_task(self) -> bool:
        print("\n-- Mark task as not completed --")
        task_id = prompt_int("Task ID (blank to cancel): ")
        if task_id is None:
            return False
        try:
            task = self.manager.uncomplete_task(task_id)
        except TaskNotFoundError as exc:
            print(exc)
        except StorageError as exc:
            print(f"Could not save change: {exc}")
        else:
            print(f"Marked '#{task.id} {task.title}' as not completed.")
        return False

    def edit_task(self) -> bool:
        print("\n-- Edit a task --")
        task_id = prompt_int("Task ID to edit (blank to cancel): ")
        if task_id is None:
            return False

        try:
            existing = self.manager.get_task(task_id)
        except TaskNotFoundError as exc:
            print(exc)
            return False

        print(f"Editing #{existing.id} — leave a field blank to keep it unchanged.")
        print(f"Current title: {existing.title}")
        new_title = prompt("New title: ").strip()
        print(f"Current description: {existing.description or '(none)'}")
        new_description = prompt("New description: ")
        print(f"Current priority: {existing.priority}")
        new_priority = prompt(f"New priority {VALID_PRIORITIES}: ").strip()
        print(f"Current due date: {existing.due_date or '(none)'}")
        new_due_date = prompt("New due date YYYY-MM-DD (type 'clear' to remove): ").strip()
        if new_due_date.lower() == "clear":
            new_due_date = ""  # signals TaskManager.edit_task to clear it
        elif new_due_date == "":
            new_due_date = None  # signals "leave unchanged"

        try:
            self.manager.edit_task(
                task_id,
                title=new_title or None,
                description=new_description if new_description != "" else None,
                priority=new_priority or None,
                due_date=new_due_date,
            )
        except (ValidationError, TaskNotFoundError) as exc:
            print(f"Could not edit task: {exc}")
        except StorageError as exc:
            print(f"Task was updated but could not be saved to disk: {exc}")
        else:
            print(f"Task #{task_id} updated.")
        return False

    def remove_task(self) -> bool:
        print("\n-- Remove a task --")
        task_id = prompt_int("Task ID to remove (blank to cancel): ")
        if task_id is None:
            return False

        try:
            existing = self.manager.get_task(task_id)
        except TaskNotFoundError as exc:
            print(exc)
            return False

        confirm = prompt(f"Delete '#{existing.id} {existing.title}'? (y/N): ").strip().lower()
        if confirm != "y":
            print("Cancelled.")
            return False

        try:
            self.manager.remove_task(task_id)
        except TaskNotFoundError as exc:
            print(exc)
        except StorageError as exc:
            print(f"Could not save change: {exc}")
        else:
            print(f"Removed task #{task_id}.")
        return False

    def show_summary(self) -> bool:
        stats = self.manager.stats()
        print(
            f"\nTotal: {stats['total']} | Completed: {stats['completed']} | "
            f"Pending: {stats['pending']} | Overdue: {stats['overdue']}"
        )
        return False

    def exit_app(self) -> bool:
        print("Goodbye! Your tasks are saved.")
        return True
