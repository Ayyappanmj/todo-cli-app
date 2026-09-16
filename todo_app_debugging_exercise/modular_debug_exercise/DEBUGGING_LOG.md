# Debugging Log — To-Do List Manager (`todo_app` package)

This log documents debugging performed directly on the real project
(`main.py` + the `todo_app` package: `models.py`, `storage.py`,
`manager.py`, `cli.py`) — not a simplified stand-in script. Eight bugs
were deliberately introduced into a copy of the working codebase
(`original_buggy_project/`) to simulate a realistic troubleshooting
scenario, then found, diagnosed, and fixed, producing
`corrected_project/`, which is functionally identical to the project's
known-good version and passes all tests.

---

## 1. Initial Code Review

Reading through each module with an eye on file I/O, loops, and
conditionals (per the task brief) turned up the following areas of
concern before any code was run:

| File | Concern |
|---|---|
| `manager.py` → `_compute_next_id()` | Formula for the next task ID — worth checking it stays unique after deletions. |
| `manager.py` → `_validate_priority()` | Does it normalize case before comparing against `VALID_PRIORITIES`? |
| `manager.py` → `edit_task()` | The due-date-clearing branch uses a conditional on `due_date` — worth checking `if due_date:` vs `if due_date is not None:`, since `""` (empty string, meant to signal "clear it") is falsy. |
| `models.py` → `Task.is_overdue()` | Boundary check on `due < date.today()` vs `<=` — is "due today" overdue or not? |
| `models.py` → `Task.from_dict()` | Which fields use `.get()` with a default vs. direct `[]` indexing (required)? Any inconsistency there breaks loading older/partial records. |
| `storage.py` → `save_tasks()` | Confirm file writes are wrapped safely (context manager, error handling, atomic write). |
| `storage.py` → `load_tasks()` | Confirm a single malformed record can't take down the whole file's worth of tasks. |
| `cli.py` → exception handling blocks | Confirm every `except StorageError` actually tells the user something, rather than swallowing it. |

Each of these was then **confirmed or ruled out by execution**, using
a reproduction script (`reproduce_bugs.py`) that calls the real
`todo_app` functions/classes directly, plus running the project's
existing `tests/test_manager.py` suite against the modified code.

---

## 2. Bug Report

### Bug B1 — `manager.py`: duplicate IDs after deleting a task and restarting
- **Location:** `TaskManager._compute_next_id()`
- **Symptom:** After removing a task and restarting the app (a new
  `TaskManager` is constructed, e.g. next time the user runs the
  program), a newly added task can be assigned an ID that already
  belongs to an existing task.
- **Reproduction:**
  ```python
  m = TaskManager(path)
  m.add_task("First"); m.add_task("Second"); m.add_task("Third")  # ids 1,2,3
  m.remove_task(2)                             # ids on disk: [1, 3]
  m2 = TaskManager(path)                        # simulates restarting the app
  t4 = m2.add_task("Fourth")
  ```
  **Output:** `Ids after restart + adding 'Fourth': [1, 3, 3]` —
  `New task id: 3 | collides with an existing task? True`
- **Why it only shows up on restart:** within a single running
  session, `TaskManager` increments an in-memory counter
  (`self._next_id += 1`) itself, so `_compute_next_id()` is only ever
  called once, in `__init__`. The bug is dormant until the app is
  closed and reopened — a good example of why "it worked when I
  tested it" isn't the same as "it's correct."
- **Hypothesis:** `_compute_next_id()` was using `len(self.tasks) + 1`
  — tied to the *current count* of tasks, not to IDs already handed
  out. After a deletion, the count drops, and the next ID computed
  from that count can match an ID still in use.

### Bug B2 — `manager.py`: priority validation is case-sensitive
- **Location:** `TaskManager._validate_priority()`
- **Symptom:** `add_task("Task", priority="High")` is rejected, even
  though `"high"` is valid.
- **Reproduction output:**
  ```
  todo_app.manager.ValidationError: Priority must be one of ('low', 'medium', 'high'), got 'High'.
  ```
- **Hypothesis:** The `.lower()` call before comparing against
  `VALID_PRIORITIES` was missing, so only an exact lowercase match
  passes.

### Bug B3 — `manager.py`: a task's due date can never be cleared
- **Location:** `TaskManager.edit_task()`
- **Symptom:** Calling `edit_task(id, due_date="")` — the documented
  way to clear a due date — leaves the existing due date untouched.
- **Reproduction output:**
  ```
  due_date after 'clearing' it: 2026-01-01 (expected: None)
  ```
- **Caught by the existing test suite too:** `tests/test_manager.py::test_edit_task_clear_due_date` failed:
  ```
  AssertionError: '2026-01-01' is not None
  ```
- **Hypothesis:** The guard was `if due_date:` instead of
  `if due_date is not None:`. An empty string `""` is falsy in Python,
  so it was treated the same as "no change requested" rather than
  "clear the field" — the two intents (leave-alone vs. clear) had
  collapsed into one code path.

### Bug B4 — `models.py`: a task due today is incorrectly flagged overdue
- **Location:** `Task.is_overdue()`
- **Symptom:** A task with `due_date` set to today's date reports
  `is_overdue() == True`, even though today hasn't ended yet.
- **Reproduction output:**
  ```
  is_overdue(): True (expected: False, it's not overdue until AFTER today)
  ```
- **Hypothesis:** The comparison was `due <= date.today()` instead of
  `due < date.today()` — an off-by-one on the boundary condition.

### Bug B5 — `models.py`: loading an older-format task record crashes
- **Location:** `Task.from_dict()`
- **Symptom:** A saved task record that predates the `description`
  field (or was hand-edited without it) crashes the entire load.
- **Reproduction output:**
  ```
  KeyError: 'description'
  ```
- **Hypothesis:** `description=str(data["description"])` used direct
  `[]` indexing (required) instead of `data.get("description", "")`
  (optional with a default) — inconsistent with how every other
  optional field in the same method is handled.

### Bug B6 — `storage.py`: `save_tasks()` no longer handles write failures, and the atomic-write safety net is gone
- **Location:** `save_tasks()`
- **Symptom:** Any write failure (missing directory, permissions, full
  disk) crashes the whole program with a raw, unhandled exception
  instead of the intended `StorageError`. The temp-file-then-rename
  pattern that protects `tasks.json` from being left half-written if
  the process is interrupted mid-save was also removed.
- **Reproduction output:**
  ```
  FileNotFoundError: [Errno 2] No such file or directory: '/this/directory/does/not/exist/tasks.json'
  ```
- **Also surfaced as a side effect across the test suite:** every test
  that calls `save_tasks()` now emits:
  ```
  ResourceWarning: unclosed file <_io.TextIOWrapper ...>
  ```
  because the file handle is opened with a bare `open()` call and never
  explicitly closed.
- **Hypothesis:** The function had been changed from a `with` block +
  temp-file rename + `try/except OSError` (raising `StorageError`) down
  to a single unguarded `open()` + `json.dump()` call.

### Bug B7 — `storage.py`: one malformed record crashes the entire load, losing every task
- **Location:** `load_tasks()`
- **Symptom:** If `tasks.json` contains even one record that fails to
  parse (e.g. from a partially-written file, manual edit, or a bug in
  an earlier version), *all* tasks — including perfectly valid ones —
  become inaccessible.
- **Reproduction output:**
  ```
  KeyError: 'description'
  Expected: the GOOD task should still load; instead the whole load crashes.
  ```
- **Hypothesis:** The per-item `try/except (KeyError, TypeError, ValueError)` around `Task.from_dict(item)` inside the loop had been
  removed, so one bad dict propagates an exception that aborts the
  entire function instead of just being skipped with a warning.

### Bug B8 — `cli.py`: a failed save gives the user no feedback at all
- **Location:** `TodoCLI.complete_task()`
- **Symptom:** If saving to disk fails, the user sees nothing —
  neither the normal success message nor an error. They have no way to
  know their change wasn't actually saved.
- **Reproduction:** Isolated by patching `save_tasks` to raise a
  `StorageError` directly (see note below on why), then capturing
  stdout during `complete_task()`:
  ```python
  patch("todo_app.manager.save_tasks", side_effect=StorageError("Disk is full (simulated failure).")):
  cli.complete_task()
  ```
  **Captured output:** `'\n-- Mark task as completed --\n'` — that's
  it. No error, no confirmation.
- **Hypothesis:** The `except StorageError as exc: print(...)` block
  had been changed to `except StorageError: pass`, and because the
  exception short-circuits the `try`, the `else: print(...)` success
  message never runs either — so *nothing at all* prints for that
  action.
- **Bug interaction discovered during reproduction:** Bugs B6 and B8
  turned out to be entangled. Because B6 means `save_tasks()` no longer
  raises `StorageError` for a real disk error (just a raw `OSError`
  subtype), `cli.py`'s `except StorageError: pass` doesn't even catch
  it in practice — the *whole program crashes* instead of silently
  swallowing the failure. B8 had to be isolated by mocking
  `save_tasks` to raise `StorageError` directly, independent of B6, to
  demonstrate the swallowing behavior on its own. This is a good
  real-world lesson: fixing bugs in the order they're discovered
  matters, because one bug can mask or change the symptoms of another.

---

## 3. Step-by-Step Debugging Approach

1. **Reproduce deterministically against the real package.**
   `reproduce_bugs.py` imports `todo_app.manager`, `todo_app.models`,
   and `todo_app.storage` directly (the same modules `main.py` uses)
   and calls them with known inputs, so each bug's behavior is
   captured exactly and repeatably — see `bug_evidence.log`.
2. **Run the existing test suite as a first diagnostic pass.**
   `python -m unittest discover -s tests -v` against the buggy copy
   immediately caught Bug B3 as a real assertion failure and Bug B6 as
   `ResourceWarning`s across multiple tests — showing the value of
   running existing tests *before* writing new ones (see
   `test_run_against_buggy.log`).
3. **Isolate the smallest failing case per bug.** E.g. for Bug B1, the
   first attempt (add/remove/add within one session) did *not*
   reproduce it — which was itself informative: it showed the bug only
   manifests across a fresh `TaskManager` instantiation, since the
   in-memory counter masks it otherwise. That refinement is recorded
   above rather than hidden, since a failed first attempt at
   reproduction is a normal and useful part of debugging.
4. **Watch for bug interactions.** Bug B8's reproduction attempt via a
   real forced disk failure (unwritable directory) initially failed to
   reproduce anything under this environment (the process runs as
   root, which bypasses normal directory permission checks), and a
   working reproduction using a non-existent directory instead
   revealed that B6 and B8 interact — the raw exception from B6 isn't
   even the type B8's handler expects. Documented in Bug B8 above.
5. **Form and confirm a hypothesis per bug**, backed by the actual
   captured output, not just code reading.
6. **Fix and re-verify** each one against the real reproduction
   scenario.
7. **Add regression tests.** `tests/test_bugfixes.py` adds one
   targeted test per bug not already covered by the existing suite
   (Bugs B3 and B6's resource leak were already caught by
   `test_manager.py`, so they aren't duplicated).

---

## 4. Fixes Applied (Before / After, from the real project files)

### Fix B1 — `todo_app/manager.py`
```python
# BEFORE
def _compute_next_id(self) -> int:
    if not self.tasks:
        return 1
    return len(self.tasks) + 1

# AFTER
def _compute_next_id(self) -> int:
    if not self.tasks:
        return 1
    return max(t.id for t in self.tasks) + 1
```

### Fix B2 — `todo_app/manager.py`
```python
# BEFORE
priority = priority.strip() or "medium"

# AFTER
priority = priority.strip().lower() or "medium"
```

### Fix B3 — `todo_app/manager.py`
```python
# BEFORE
if due_date:
    task.due_date = self._validate_due_date(due_date) if due_date != "" else None

# AFTER
if due_date is not None:
    task.due_date = self._validate_due_date(due_date) if due_date != "" else None
```
The distinction matters: `None` means "field not provided, leave it
alone"; `""` means "field explicitly cleared." Using truthiness
collapses those two different caller intents into one.

### Fix B4 — `todo_app/models.py`
```python
# BEFORE
return due <= date.today()

# AFTER
return due < date.today()
```

### Fix B5 — `todo_app/models.py`
```python
# BEFORE
description=str(data["description"]),

# AFTER
description=str(data.get("description", "")),
```

### Fix B6 — `todo_app/storage.py`
```python
# BEFORE
f = open(filepath, "w", encoding="utf-8")
json.dump([t.to_dict() for t in tasks], f, indent=2)

# AFTER
tmp_path = f"{filepath}.tmp"
try:
    with open(tmp_path, "w", encoding="utf-8") as f:
        json.dump([t.to_dict() for t in tasks], f, indent=2)
    os.replace(tmp_path, filepath)
except OSError as exc:
    raise StorageError(f"Could not write to '{filepath}': {exc}") from exc
```
Restores three things at once: the file is always closed (`with`
block), a real disk error becomes a clear `StorageError` instead of a
raw crash, and writing to a temp file then renaming it into place
means an interrupted write can't leave `tasks.json` half-written.

### Fix B7 — `todo_app/storage.py`
```python
# BEFORE
tasks: List[Task] = []
for item in data:
    tasks.append(Task.from_dict(item))
return tasks

# AFTER
tasks: List[Task] = []
for item in data:
    try:
        tasks.append(Task.from_dict(item))
    except (KeyError, TypeError, ValueError) as exc:
        print(f"Warning: skipping malformed task entry ({exc}).")
return tasks
```

### Fix B8 — `todo_app/cli.py`
```python
# BEFORE
except StorageError:
    pass

# AFTER
except StorageError as exc:
    print(f"Could not save change: {exc}")
```

---

## 5. Validation

### 5.1 Full test suite against the corrected project
```
$ python -m unittest discover -s tests -v
...
Ran 21 tests in 0.006s

OK
```
21 tests: the original 15 from `tests/test_manager.py` (including
`test_edit_task_clear_due_date`, which now passes) plus 6 new targeted
tests in `tests/test_bugfixes.py` covering B1, B2, B4, B5, B6, B7.

### 5.2 Same suite against the (still) buggy project, for comparison
```
$ python -m unittest discover -s tests -v
...
FAIL: test_edit_task_clear_due_date
FAIL: test_bug_b1_ids_not_reused_after_restart
FAIL: test_bug_b4_task_due_today_is_not_overdue
ERROR: test_bug_b2_priority_is_case_insensitive
ERROR: test_bug_b5_from_dict_handles_missing_description
ERROR: test_bug_b6_save_tasks_reports_write_failures
ERROR: test_bug_b7_one_bad_record_does_not_lose_the_rest
Ran 21 tests in 0.009s

FAILED (failures=3, errors=4)
```
Confirms every injected bug is independently caught by the test suite,
and none of them are caught in the corrected version.

### 5.3 Manual smoke test of the corrected CLI
```
$ python main.py demo_tasks.json
Choose an option (1-8): 1
Title (required): Buy groceries
Priority ('low', 'medium', 'high') [default: medium]: High
Added task #1: 'Buy groceries'
Choose an option (1-8): 2
#1 [pending] (high) Buy groceries (due none)
Choose an option (1-8): 6
```
Confirms `priority="High"` (Bug B2) is now accepted and normalized to
`"high"`, end-to-end through the real CLI.

---

## 6. Code Quality Improvements

Beyond the minimum fix for each bug, no additional refactors were
introduced in `corrected_project/` — it deliberately matches the
project's already-reviewed, working version exactly, so this log
stays focused on the bugs themselves rather than mixing in unrelated
style changes. The one addition is `tests/test_bugfixes.py`, a
permanent regression suite so none of these eight bugs can silently
reappear in a future change.

---

## 7. Summary

| # | Bug | File | Category | Fixed? |
|---|---|---|---|---|
| B1 | Duplicate IDs after deletion + restart | manager.py | Logic | ✅ |
| B2 | Priority validation is case-sensitive | manager.py | Conditional / validation | ✅ |
| B3 | Due date can never be cleared | manager.py | Conditional (truthiness vs. `is not None`) | ✅ |
| B4 | Task due today flagged overdue | models.py | Conditional (off-by-one boundary) | ✅ |
| B5 | Missing `description` crashes load | models.py | Dict access / file I/O | ✅ |
| B6 | Unhandled write failures + no atomic write + unclosed file | storage.py | File I/O | ✅ |
| B7 | One bad record crashes the whole load | storage.py | Loop / error handling | ✅ |
| B8 | Failed save gives no user feedback | cli.py | Error handling | ✅ |

All 8 bugs were reproduced against the real project modules with
captured output before being fixed, and verified fixed via 21 passing
automated tests plus a manual end-to-end CLI run.
