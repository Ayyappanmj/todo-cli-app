# CI Pipeline Documentation — mini_calc

This document explains how the Continuous Integration pipeline for
`mini_calc` was set up, what it checks on every commit, the
challenges encountered while building it, and how to replicate,
extend, or run it locally.

---

## 1. What This Project Is

`mini_calc` is a small, dependency-free arithmetic expression
evaluator (`evaluate("2 + 3 * 4") == 14.0`), built with test-driven
development -- 94 automated `unittest`-based tests across four layers
(tokenizer, parser, evaluator, integration). It was chosen as the
base for this CI task because it was already clean, modular, fully
tested, and had zero runtime dependencies -- exactly the kind of
project a CI pipeline is meant to keep that way as it grows.

## 2. CI Tool Chosen: GitHub Actions

**GitHub Actions** was chosen over Travis CI or CircleCI because it's
built directly into GitHub (no separate account/service to connect,
no separate billing setup for public repos), is free for public
repositories and generous for private ones, and is the most widely
used CI tool for Python projects on GitHub today. The workflow file
lives at `.github/workflows/ci.yml`.

## 3. Pipeline Design

### 3.1 Triggers

```yaml
"on":
  push:
    branches: [ "main" ]
  pull_request:
    branches: [ "main" ]
  workflow_dispatch:
```

- **`push` to `main`** -- runs on every commit merged/pushed directly
  to the main branch.
- **`pull_request` targeting `main`** -- runs on every PR, so problems
  are caught *before* merging, not after. This is the trigger that
  matters most day-to-day: it's what shows the green/red check on a
  PR before it's approved.
- **`workflow_dispatch`** -- adds a manual "Run workflow" button in the
  Actions tab, for re-running the pipeline on demand without needing
  a new commit.

### 3.2 Matrix: four Python versions, not one

```yaml
strategy:
  fail-fast: false
  matrix:
    python-version: ["3.9", "3.10", "3.11", "3.12"]
```

The whole pipeline runs once per version, in parallel. This is what
actually catches "works on my machine, breaks on the version most
users have" bugs. `fail-fast: false` means one version failing
doesn't cancel the others mid-run, so a single pipeline run shows the
complete picture across every version at once instead of stopping at
the first red result.

### 3.3 Steps, and what each one is for

| Step | Purpose |
|---|---|
| `actions/checkout@v4` | Pulls the repository's code into the runner. |
| `actions/setup-python@v5` | Installs the specific Python version for this matrix entry, with pip caching enabled so dependency installs are fast on repeat runs. |
| `pip install -r requirements-dev.txt` | Installs `flake8`, `pytest`, and `pytest-cov` -- the actual tools used in CI (see Section 5 for why these specifically, and why they aren't used locally in *this* authoring environment). |
| **Lint with flake8** | Fails the job if any lint rule is violated. Configuration in `.flake8` (Section 4). |
| **Run test suite (pytest)** | Runs all 94 tests, generates a JUnit XML report (`test-results/junit.xml`) and a coverage report (terminal + `coverage.xml`). |
| **Upload test results and coverage report** | Attaches both reports as downloadable build artifacts, `if: always()` so they're available even on a failing run. |
| **Publish test report summary** (`dorny/test-reporter`) | Turns the raw JUnit XML into a readable, annotated pass/fail summary shown directly on the commit/PR. |

### 3.4 How the pipeline fails on a test failure

No special "if tests failed, exit 1" logic was written -- it isn't
needed. `pytest`'s own process exit code is non-zero the moment any
test fails, which makes that GitHub Actions **step** fail
automatically, which fails the **job**, which shows as a red X on
the commit/PR. The same is true for `flake8`. This is demonstrated
for real in Section 6 by actually breaking a test and confirming the
failure propagates correctly.

## 4. Configuration Files

| File | Purpose |
|---|---|
| `.flake8` | Lint rules: 99-character line limit, excluded paths, and one documented per-file exception (see below). |
| `pytest.ini` | Tells pytest where the tests live (`tests/`) and to run in verbose mode by default. |
| `requirements-dev.txt` | Pinned versions of `flake8`, `pytest`, `pytest-cov` -- installed fresh by CI on every run. |
| `requirements.txt` | Intentionally near-empty; documents explicitly that `mini_calc` has zero runtime dependencies. |

**One documented lint exception:** `mini_calc/__init__.py` imports
several exception classes purely to re-export them as the package's
public API (`__all__` formalizes this). flake8's default unused-import
check (F401) can't always distinguish this standard pattern from a
genuine leftover import, so it's silenced for that one file only via
`per-file-ignores` in `.flake8`, not disabled project-wide.

## 5. Challenges Encountered

**This authoring/development environment has no internet access.**
`flake8`, `pytest`, and `pytest-cov` could not be installed here to
directly dry-run the exact CI commands before committing them:

```
$ pip install flake8 pytest pytest-cov
ERROR: Could not find a version that satisfies the requirement flake8 (from versions: none)
ERROR: No matching distribution found for flake8
```

This is a constraint of *this specific sandboxed authoring
environment only* -- GitHub's actual Actions runners have normal
internet access and will install these packages from PyPI without
issue the moment this workflow runs for real. It's called out here
rather than silently worked around, because it shaped two real
decisions:

1. **A custom lint tool** (`tools/simple_lint.py`) was written to
   verify code quality locally in the meantime -- a small, honestly
   limited stand-in for flake8 (regex/AST-based checks for long lines,
   trailing whitespace, bare `except:`, wildcard imports, and unused
   imports). It is **not** a replacement for flake8 and isn't used in
   the actual CI pipeline -- `.github/workflows/ci.yml` uses real
   `flake8`, installed by GitHub's runners. Running it surfaced real,
   genuine issues during development (see below), which were fixed
   before this was written up.
2. **A local CI simulation script** (`tools/run_ci_checks.py`) mirrors
   the pipeline's two stages (lint, then test) using what *is*
   available in this environment -- `simple_lint.py` in place of
   `flake8`, and Python's built-in `unittest` (wrapped to additionally
   emit a real JUnit XML report, the same format `pytest --junitxml`
   produces) in place of `pytest`. This was actually run, repeatedly,
   during development -- see Section 6 for its real output, including
   a deliberate-failure test proving the exit-code behavior is
   correct.

**What the custom lint tool actually found, during development:**
```
mini_calc/__init__.py:25: F401 'CalculatorError' imported but unused
mini_calc/__init__.py:25: F401 'TokenizeError' imported but unused
mini_calc/__init__.py:25: F401 'ParseError' imported but unused
mini_calc/__init__.py:25: F401 'EvaluationError' imported but unused
mini_calc/ast_nodes.py:13: F401 'annotations' imported but unused
mini_calc/evaluator.py:14: F401 'annotations' imported but unused
mini_calc/parser.py:23: F401 'annotations' imported but unused
mini_calc/tokenizer.py:17: F401 'annotations' imported but unused

tests/test_tokenizer.py:67: E501 line too long (106 > 99 characters)
tests/test_tokenizer.py:71: E501 line too long (103 > 99 characters)
tests/test_tokenizer.py:114: E501 line too long (102 > 99 characters)
```

Two categories, handled two different ways:
- The three `E501` long-line findings in `tests/test_tokenizer.py`
  were **real** and were fixed (three `assertEqual` calls reformatted
  across multiple lines).
- The `F401` findings were **false positives of the simplified
  checker**, not real issues: `from __future__ import annotations` is
  a compiler directive real `pyflakes` never flags (the checker was
  updated to special-case it), and the `__init__.py` imports are
  intentional re-exports (handled via the documented
  `.flake8`/`per-file-ignores` exception above). After both fixes,
  `simple_lint.py` reports zero issues project-wide.

This distinction -- a real finding vs. an artifact of a simplified
tool -- is exactly the kind of judgment call a static tool can't make
for you, and is documented here rather than glossed over.

## 6. Test Integration -- Real, Local Evidence

Since the exact `flake8`/`pytest` commands couldn't be dry-run in this
environment, `tools/run_ci_checks.py` (Section 5) was used instead to
verify the pipeline's logic end-to-end, for real:

### 6.1 A normal, passing run

```
$ python tools/run_ci_checks.py
...
==============================================================================
STEP 1/2: Lint  (tools/simple_lint.py -- stand-in for flake8; see docstring)
==============================================================================
No issues found.

==============================================================================
STEP 2/2: Tests  (unittest, wrapped to also emit a JUnit XML report)
==============================================================================
...
Ran 94 tests in 0.004s

OK

JUnit XML report written to: .../test-results/junit.xml

==============================================================================
SUMMARY
==============================================================================
  Lint:  PASSED
  Tests: PASSED

All checks passed. (this is what a green CI run looks like)
```

A real `test-results/junit.xml` was produced (94 `<testcase>` entries,
`failures="0" errors="0"`) -- included in this submission as evidence.

### 6.2 A deliberately broken run -- proving the fail behavior is real

To confirm the pipeline genuinely fails (not just "should" fail), one
assertion was temporarily changed to an intentionally wrong expected
value (`assertEqual(evaluate_ast(Number(5)), 5)` -> `... 999)`), and
the checks re-run:

```
$ python tools/run_ci_checks.py
...
FAILED (failures=1)

==============================================================================
SUMMARY
==============================================================================
  Lint:  PASSED
  Tests: FAILED

One or more checks failed. (this is what would fail the CI pipeline)

$ echo $?
1
```

Exit code **1** -- confirmed by checking `$?` directly (not through a
pipe, which would report the wrong process's exit code) -- is exactly
what makes a GitHub Actions **step** fail, which fails the **job**,
which shows as a red X on the commit. The change was then reverted and
the suite re-confirmed passing (94/94, exit code 0) before proceeding.
This output is saved in `ci_failure_demo_output.txt`.

### 6.3 What the real GitHub Actions run will additionally show

Once pushed, every commit/PR will show, in the **Actions** tab:
- A run per matrix entry (`Lint & Test (Python 3.9)` through `3.12`),
  each with full step-by-step logs.
- A green check or red X next to the commit/PR the moment the workflow
  finishes.
- Under each run's **Summary** page, downloadable **Artifacts**
  (`test-results-py3.9` through `py3.12`) containing `junit.xml` and
  `coverage.xml` for that Python version.
- A **Checks** entry from `dorny/test-reporter` giving a readable
  pass/fail breakdown of all 94 tests without needing to open the raw
  log -- this is the "test report" the task asks for, generated
  automatically on every run.

## 7. How to Replicate / Run Locally

### 7.1 With a normal internet connection (recommended -- uses the real tools)

```bash
git clone <your-repo-url>
cd <repo>
pip install -r requirements-dev.txt

flake8 mini_calc tests --count --statistics
pytest tests/ -v --junitxml=test-results/junit.xml --cov=mini_calc --cov-report=term-missing
```

Both commands are exactly what CI runs -- running them locally before
pushing is the fastest way to catch an issue before it shows up as a
red X on GitHub.

### 7.2 Without internet access, or without installing anything extra

```bash
python tools/run_ci_checks.py
```

Runs the equivalent checks using only the Python standard library
(Section 5/6). Exit code 0 on success, 1 on failure -- safe to use as
a pre-commit gate the same way the real CI job is a merge gate.

### 7.3 Viewing CI logs on GitHub, after pushing

1. Push this project to a GitHub repository (or add it to an existing
   one -- see the important note in **README.md** about workflow file
   placement if adding this into a repo that already has other
   projects in subfolders).
2. Open the repository on GitHub -> the **Actions** tab.
3. Click the most recent workflow run (named after the triggering
   commit).
4. Click any of the four `Lint & Test (Python ...)` jobs to see its
   live/complete log, step by step.
5. Scroll to the bottom of a job's Summary page for the
   **Artifacts** section and the test-reporter **Checks** summary.

## 8. Summary

| Aspect | Detail |
|---|---|
| CI tool | GitHub Actions |
| Triggers | push to main, pull requests to main, manual dispatch |
| Python versions tested | 3.9, 3.10, 3.11, 3.12 (matrix, all run in parallel) |
| Lint tool | flake8 (real, in CI); `tools/simple_lint.py` used locally in this offline authoring environment as a stand-in |
| Test tool | pytest (real, in CI), running all 94 existing `unittest`-based tests unchanged |
| Test report | JUnit XML + coverage XML, both uploaded as artifacts; human-readable summary via `dorny/test-reporter` |
| Fails on test failure? | Yes -- confirmed with a real, deliberately-broken test run (Section 6.2), exit code 1 |
| Local replication | `pip install -r requirements-dev.txt` then `flake8`/`pytest` directly, or `python tools/run_ci_checks.py` with zero installs |
