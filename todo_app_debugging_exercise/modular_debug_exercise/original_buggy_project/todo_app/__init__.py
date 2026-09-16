"""
todo_app
========
A small, modular CLI To-Do List Manager.

Package layout:
    models.py  - Task data model (what a task IS)
    storage.py - JSON persistence (how tasks are saved/loaded)
    manager.py - TaskManager business logic (rules for creating/editing tasks)
    cli.py     - Text menu interface (how the user interacts with it)
"""

from .models import Task
from .manager import TaskManager, TaskNotFoundError, ValidationError
from .cli import TodoCLI

__all__ = ["Task", "TaskManager", "TaskNotFoundError", "ValidationError", "TodoCLI"]
