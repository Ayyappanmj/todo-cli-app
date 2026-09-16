# To-Do List Manager (CLI)

A simple, modular command-line To-Do List application written in
standard Python 3 with **no external dependencies**.

---

## 1. Features

- Add tasks with a title, optional description, priority, and due date
- View tasks (all / pending only / filtered by priority), sorted with
  the most actionable tasks first
- Mark tasks as completed or undo a completion
- Edit any field of an existing task
- Remove tasks (with a confirmation prompt)
- Automatic overdue detection (tasks past their due date are flagged)
- A one-line summary (total / completed / pending / overdue)
- Tasks persist between runs in a local JSON file (`tasks.json` by default)
- Robust input validation and error handling throughout

---

## 2. Requirements

- Python 3.9 or later (uses only the standard library — no `pip install` needed)

---

## 3. Installation

1. Unzip this archive.
2. That's it — there are no dependencies to install.

```bash
unzip todo_cli_app.zip
cd todo_cli_app
```

---

## 4. Running the application

```bash
python3 main.py
```

By default, tasks are saved to `tasks.json` in the current directory.
To use a different storage file (e.g. to keep separate task lists),
pass a path as an argument:

```bash
python3 main.py work_tasks.json
```

You'll see a menu like this:

```
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
Choose an option (1-8):
```

Type a number and follow the prompts. Most optional prompts can be
left blank to skip/cancel/keep the current value.

---

## 5. Architecture & Design Decisions

The application follows a **layered / separation-of-concerns**
design so each file has one clear job. This makes the code easier to
read, test, and extend (e.g. swapping the CLI for a GUI later would
only require a new presentation layer — the model, storage, and
business logic underneath would not need to change).

```
todo_cli_app/
├── main.py                 # Entry point — wires everything together
├── todo_app/
│   ├── __init__.py         # Package exports
│   ├── models.py           # Task data model
│   ├── storage.py          # JSON load/save (persistence)
│   ├── manager.py          # TaskManager — business logic & validation
│   └── cli.py              # Text menu (presentation layer)
├── tests/
│   └── test_manager.py     # Automated unit tests
├── tasks.json               # Created automatically on first run
└── README.md
```

### Layer responsibilities

| Layer      | File            | Responsibility |
|------------|-----------------|----------------|
| Model      | `models.py`     | Defines what a `Task` *is* (fields, serialization, `is_overdue()`) |
| Storage    | `storage.py`    | Reads/writes the task list to/from a JSON file. Knows nothing about business rules. |
| Logic      | `manager.py`    | `TaskManager` owns the task list, assigns IDs, validates input, and enforces rules (e.g. no empty titles). This is where "the app" actually lives. |
| Presentation | `cli.py`      | Displays the menu, collects input, and calls `TaskManager` methods. Contains no business rules of its own. |
| Entry point | `main.py`      | Starts the app; keeps it importable/reusable (e.g. by tests). |

This mirrors the classic **Model–Logic–View** separation: the CLI
could be replaced by a web front end or GUI without touching
`models.py` or `manager.py` at all, because those two files have no
knowledge of how the user interacts with the app.

### Key design choices

- **`Task` as a `dataclass`** rather than a plain dict: gives named,
  typed attributes, catches typos at development time, and centralizes
  serialization logic (`to_dict` / `from_dict`) in one place.
- **IDs are never reused.** New IDs are computed as `max(existing) + 1`,
  so deleting task #2 and adding a new task won't accidentally create
  a duplicate ID if task #2's number is later reused elsewhere (e.g.
  in a bookmark or external reference).
- **Atomic file writes.** `storage.py` writes to a temporary file and
  then renames it into place, so an interrupted write (e.g. Ctrl+C)
  can't leave `tasks.json` half-written or corrupted.
- **Fail gracefully, not silently.** Malformed individual task records
  in a corrupted file are skipped with a warning rather than crashing
  the whole app or being lost without explanation.
- **Validation lives in `TaskManager`, not `cli.py`.** This guarantees
  that *any* caller of `TaskManager` — the CLI, a future GUI, or a
  test — gets the same guarantees (no empty titles, valid priorities,
  valid ISO dates), rather than relying on each interface to
  re-implement checks correctly.
- **Auto-save after every mutation.** The user never has to remember
  to "save" — every add/edit/complete/remove immediately persists to
  disk, minimizing data loss if the program is closed unexpectedly.

### Application flow (pseudo-code)

```
START
  create TaskManager(filepath)
      -> load tasks from JSON file (or start empty if none exists)

  LOOP forever:
      print menu
      read user's numeric choice

      IF choice == Add:
          collect title, description, priority, due date
          TRY: manager.add_task(...)   # validates input
          EXCEPT ValidationError: show friendly error message

      ELIF choice == View:
          collect optional filter (pending / priority)
          tasks = manager.list_tasks(filter)
          print each task as one line, sorted:
              incomplete before complete,
              then high > medium > low priority,
              then by id

      ELIF choice == Complete / Undo:
          read task id
          TRY: manager.complete_task(id) / uncomplete_task(id)
          EXCEPT TaskNotFoundError: show friendly error message

      ELIF choice == Edit:
          read task id, look it up
          for each field, prompt "new value (blank = keep current)"
          TRY: manager.edit_task(id, ...only changed fields...)
          EXCEPT ValidationError / TaskNotFoundError: show error

      ELIF choice == Remove:
          read task id, look it up, ask for confirmation (y/N)
          IF confirmed: manager.remove_task(id)

      ELIF choice == Summary:
          print total / completed / pending / overdue counts

      ELIF choice == Exit:
          print goodbye message
          BREAK loop

      ELSE:
          print "invalid choice, try again"

      (every mutating manager call also re-saves tasks.json to disk)

END
```

### Flow diagram (text form)

```
 ┌────────────┐
 │   Start    │
 └─────┬──────┘
       ▼
 ┌─────────────────────┐
 │ Load tasks.json      │
 │ (or start empty)     │
 └─────┬────────────────┘
       ▼
 ┌─────────────────────┐◄────────────────────────────┐
 │   Show menu (1-8)    │                              │
 └─────┬────────────────┘                              │
       ▼                                                │
 ┌─────────────────────┐   invalid   ┌────────────────┐ │
 │  Read user choice    │────────────►│ Show error msg │─┘
 └─────┬────────────────┘             └────────────────┘
       │ valid
       ▼
 ┌─────────────────────────────────────────────┐
 │ Dispatch to action:                          │
 │  Add / View / Complete / Undo / Edit /       │
 │  Remove / Summary / Exit                     │
 └─────┬─────────────────────────────────────────┘
       │
       ├── Exit? ── yes ──► ┌────────────┐
       │                     │   Stop     │
       │                     └────────────┘
       │ no
       ▼
 ┌─────────────────────────────┐
 │ Validate input / run action  │
 │ (TaskManager methods)        │
 └─────┬─────────────────────────┘
       │
       ├── error? ──► show friendly message
       │
       ▼
 ┌─────────────────────────────┐
 │ Save tasks.json (atomic)     │
 └─────┬─────────────────────────┘
       │
       └────────────► back to "Show menu"
```

---

## 6. Error handling & input validation

The app is designed to never crash on bad user input. Examples of
what is handled gracefully:

| Situation | Behavior |
|---|---|
| Non-numeric menu choice | "Invalid choice — please enter a number from 1 to 8." |
| Empty task title | Rejected with `ValidationError`: "Task title cannot be empty." |
| Unknown priority (e.g. "urgent") | Rejected: "Priority must be one of ('low', 'medium', 'high')..." |
| Malformed due date (e.g. "31-12-2026") | Rejected: "Due date '...' is invalid. Use YYYY-MM-DD format." |
| Non-numeric task ID | Re-prompted: "Please enter a whole number (or leave blank to cancel)." |
| Task ID that doesn't exist | `TaskNotFoundError`: "No task found with id N." |
| Ctrl+C / Ctrl+D during a prompt | Caught; returns to the menu instead of crashing |
| Corrupted / unreadable `tasks.json` | App starts with an empty list and a warning, instead of crashing on launch |
| Disk write failure (e.g. permissions) | Reported to the user instead of silently losing the change |

---

## 7. Testing

### Automated tests

15 unit tests cover `TaskManager`'s core logic (add/edit/remove/
complete, validation, ID uniqueness, filtering, persistence). Run
them with:

```bash
python3 -m unittest discover -s tests -v
```

Expected output: `Ran 15 tests ... OK`.

### Manual test scenarios

Try these by running `python3 main.py demo_tasks.json`:

1. **Add a valid task**
   - Choose `1`, enter title "Buy milk", leave other fields blank.
   - Expect: "Added task #1: 'Buy milk'".

2. **Reject an empty title**
   - Choose `1`, press Enter without typing a title.
   - Expect: "Could not add task: Task title cannot be empty."

3. **Reject an invalid priority**
   - Choose `1`, enter a title, then type `urgent` for priority.
   - Expect: a validation error message, and the task is *not* added.

4. **Reject a malformed due date**
   - Choose `1`, enter a title, then type `2026/13/40` for due date.
   - Expect: a validation error about the date format.

5. **View tasks with filters**
   - Choose `2`, try `a` (all), `p` (pending only), and `high`.
   - Expect: the list narrows correctly each time.

6. **Complete a task, then view it**
   - Choose `3`, enter a valid task ID.
   - Choose `2` again — the task should show a `✔` and sort below
     incomplete tasks.

7. **Try to complete a non-existent task**
   - Choose `3`, enter `999` (or any unused ID).
   - Expect: "No task found with id 999."

8. **Edit a task, changing only one field**
   - Choose `5`, pick a task, leave title/description/due date blank,
     change only priority.
   - Choose `2` — confirm the title is unchanged but priority updated.

9. **Remove a task with confirmation**
   - Choose `6`, pick a task, answer `n` first (should cancel), then
     repeat and answer `y` (should delete).

10. **Persistence across runs**
    - Add a task, exit (`8`), then re-run `python3 main.py demo_tasks.json`.
    - Choose `2` — the task should still be there, confirming it was
      saved to `demo_tasks.json`.

---

## 8. Possible future extensions

(Not implemented, to keep this submission focused, but the layered
design makes these straightforward to add):

- Command-line flags for non-interactive/scriptable use (e.g. `--add`, `--list`)
- Sub-tasks or task categories/tags
- Recurring tasks
- A GUI or web front end reusing `TaskManager` unchanged
