# mini_calc — with Continuous Integration

[![CI](https://github.com/YOUR-USERNAME/YOUR-REPO/actions/workflows/ci.yml/badge.svg)](https://github.com/YOUR-USERNAME/YOUR-REPO/actions/workflows/ci.yml)

A small, dependency-free arithmetic expression evaluator
(`evaluate("2 + 3 * 4") == 14.0`), with a GitHub Actions CI pipeline
that lints and tests every commit and pull request across four Python
versions.

**For the full CI write-up — how the pipeline was built, every
decision explained, challenges encountered, and how to replicate or
extend it — see [`CI_DOCUMENTATION.md`](CI_DOCUMENTATION.md).** This
README covers the project itself and quick local usage.

> Replace `YOUR-USERNAME/YOUR-REPO` in the badge URL above once this
> is pushed to your own repository, so it points at your real Actions
> page instead of a placeholder.

## What's in this repository

```
ci_project/
├── .github/
│   └── workflows/
│       └── ci.yml              # the GitHub Actions pipeline itself
├── mini_calc/                  # the module (tokenizer -> parser -> evaluator)
├── tests/                      # 94 automated tests (unittest, pytest-compatible)
├── tools/
│   ├── simple_lint.py          # local lint stand-in (see CI_DOCUMENTATION.md §5)
│   └── run_ci_checks.py        # runs lint + tests locally in one command
├── .flake8                     # lint configuration
├── pytest.ini                  # pytest configuration
├── requirements.txt            # runtime deps (none)
├── requirements-dev.txt        # flake8, pytest, pytest-cov
├── ci_failure_demo_output.txt  # real evidence the pipeline fails correctly (see docs §6.2)
├── CI_DOCUMENTATION.md         # the full CI write-up — read this
└── README.md                   # you are here
```

## ⚠️ Important: adding this into an existing multi-project repository

GitHub Actions **only** discovers workflow files at
`.github/workflows/` in the **repository root** — not in a subfolder.

- **Using this as its own repository?** Push it as-is; nothing to
  change.
- **Adding it into an existing repo that already has other projects
  in subfolders** (e.g. alongside previous weeks' work)? You must:
  1. Move `.github/workflows/ci.yml` to the **root** of that
     repository (create `.github/workflows/` there if it doesn't
     exist yet).
  2. Add a working-directory so the workflow's commands run inside
     this project's subfolder instead of the repo root. In
     `ci.yml`, add this once near the top of the `lint-and-test` job
     (right after `steps:` is fine, or as a job-level default):
     ```yaml
     defaults:
       run:
         working-directory: ci_project   # <- your subfolder's name
     ```
  3. Keep `mini_calc/`, `tests/`, `tools/`, `.flake8`, `pytest.ini`,
     `requirements*.txt` together inside that same subfolder — only
     the workflow file itself needs to move to the root.

## Requirements

Python 3.8+ for the module itself. `flake8` + `pytest` + `pytest-cov`
for running the same checks CI runs (see `requirements-dev.txt`) —
installed automatically by the pipeline; install locally with
`pip install -r requirements-dev.txt` if you have internet access.

## Running things locally

```bash
# With flake8/pytest installed (recommended — the real tools):
pip install -r requirements-dev.txt
flake8 mini_calc tests
pytest tests/ -v

# Without installing anything (stdlib-only stand-in — see CI_DOCUMENTATION.md §5):
python tools/run_ci_checks.py
```

## Quick usage example

```python
from mini_calc import evaluate

evaluate("2 + 3 * 4")        # 14.0
evaluate("(2 + 3) ** 2")     # 25.0
evaluate("-2 ** 2")          # -4.0  (matches Python's own precedence)
```

## The short version

This project takes an already-tested Python module (94 passing
`unittest` tests) and wraps it in a GitHub Actions pipeline that runs
on every push and pull request: lint with `flake8`, run the full test
suite with `pytest` across Python 3.9–3.12, generate a JUnit XML +
coverage report, upload both as artifacts, and publish a readable
pass/fail summary — failing the whole pipeline automatically if
anything doesn't pass. See
[`CI_DOCUMENTATION.md`](CI_DOCUMENTATION.md) for the complete
explanation, including real evidence the pipeline actually fails
correctly when a test is broken.
