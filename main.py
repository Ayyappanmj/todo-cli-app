#!/usr/bin/env python3
"""
main.py
-------
Entry point for the To-Do List Manager CLI application.

Usage:
    python main.py [path/to/tasks.json]

If no path is given, tasks are stored in ./tasks.json in the current
working directory. Keeping main.py tiny and free of business logic
means the "real" application (in the todo_app package) can also be
imported and reused elsewhere, e.g. by the test scripts in tests/.
"""

import sys

from todo_app import TodoCLI


def main() -> None:
    filepath = sys.argv[1] if len(sys.argv) > 1 else "tasks.json"
    app = TodoCLI(filepath)
    try:
        app.run()
    except KeyboardInterrupt:
        # Catch Ctrl+C at the top level as a final safety net so the user
        # sees a clean message instead of a raw traceback, even if it
        # happens somewhere prompt() itself doesn't cover.
        print("\nInterrupted. Goodbye!")


if __name__ == "__main__":
    main()
