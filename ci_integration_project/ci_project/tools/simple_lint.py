"""
simple_lint.py
----------------
A small, dependency-free lint checker, used to verify code quality in
THIS authoring environment, which has no internet access and
therefore cannot `pip install flake8` (see CI_DOCUMENTATION.md,
"Challenges Encountered" section, for the exact failed install log).

This is NOT a replacement for flake8 -- the actual CI pipeline
(.github/workflows/ci.yml) uses real flake8, installed fresh by
GitHub's runners, which DO have internet access. This script exists
solely so that lint-style checks could be run and verified locally
during development here, the same way flake8 would be run once
installed.

Checks performed (a small, representative subset of what flake8
covers -- see the module docstring in tools/ for the parallel to
tools/simple_static_scanner.py from a previous project, built for the
same underlying reason):
  - Lines over max_line_length columns (flake8 E501)
  - Trailing whitespace (flake8 W291)
  - Tabs mixed with spaces for indentation (flake8 W191-adjacent)
  - Bare `except:` clauses (flake8 E722)
  - Wildcard imports (`from x import *`) (flake8 F403)
  - Unused imports, via a simple AST-based check (flake8 F401) --
    less precise than flake8's real implementation (doesn't handle
    `__all__`, conditional imports, or re-exports specially), but
    catches the common case.

Usage:
    python simple_lint.py <file_or_directory> [<file_or_directory> ...]
"""

from __future__ import annotations

import ast
import os
import sys
from dataclasses import dataclass
from typing import List

MAX_LINE_LENGTH = 99


@dataclass
class LintIssue:
    file: str
    line_number: int
    code: str
    message: str


def _check_lines(path: str, lines: List[str]) -> List[LintIssue]:
    issues = []
    for i, line in enumerate(lines, start=1):
        stripped_newline = line.rstrip("\n")
        if len(stripped_newline) > MAX_LINE_LENGTH:
            issues.append(LintIssue(
                path, i, "E501",
                f"line too long ({len(stripped_newline)} > {MAX_LINE_LENGTH} characters)",
            ))
        if stripped_newline != stripped_newline.rstrip():
            issues.append(LintIssue(path, i, "W291", "trailing whitespace"))
        if "\t" in line:
            issues.append(LintIssue(path, i, "W191", "indentation contains tabs"))
        if stripped_newline.strip().startswith("except:"):
            issues.append(LintIssue(path, i, "E722", "bare 'except:' clause"))
        if stripped_newline.strip().startswith("from ") and " import *" in stripped_newline:
            issues.append(LintIssue(path, i, "F403", "wildcard import used"))
    return issues


def _check_unused_imports(path: str, source: str) -> List[LintIssue]:
    """Simple AST-based unused-import check.

    Known imprecision (documented honestly rather than hidden, same
    approach taken for tools/simple_static_scanner.py in a previous
    project): does not special-case `__all__` exports, `TYPE_CHECKING`
    blocks, or re-export patterns (`from .foo import Bar  # noqa`).
    Real flake8 (via pyflakes) handles these; this lightweight
    stand-in does not, and any of those patterns would need a manual
    read to confirm before treating a flagged import as a genuine
    issue.
    """
    issues = []
    try:
        tree = ast.parse(source, filename=path)
    except SyntaxError as exc:
        return [LintIssue(path, exc.lineno or 0, "E999", f"SyntaxError: {exc.msg}")]

    imported_names = {}  # name -> line number
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module == "__future__":
            # __future__ imports are compiler directives, never
            # "used" by name in code -- real pyflakes (which flake8
            # uses under the hood) never flags these. Special-cased
            # here to match that, rather than reporting a false
            # positive on every module using `from __future__ import
            # annotations`.
            continue
        if isinstance(node, ast.Import):
            for alias in node.names:
                name = alias.asname or alias.name.split(".")[0]
                imported_names[name] = node.lineno
        elif isinstance(node, ast.ImportFrom):
            for alias in node.names:
                if alias.name == "*":
                    continue
                name = alias.asname or alias.name
                imported_names[name] = node.lineno

    # Names re-exported via __all__ are "used" for the purposes of
    # this check, the same way real pyflakes treats them -- an
    # __init__.py that imports a name specifically to make it part of
    # the package's public API (and declares that in __all__) is a
    # normal, intentional pattern, not an unused import.
    exported_names = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name) and target.id == "__all__":
                    if isinstance(node.value, (ast.List, ast.Tuple)):
                        for elt in node.value.elts:
                            if isinstance(elt, ast.Constant) and isinstance(elt.value, str):
                                exported_names.add(elt.value)

    used_names = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Name):
            used_names.add(node.id)
        elif isinstance(node, ast.Attribute):
            # e.g. `os.path` -- the base name `os` counts as used.
            base = node
            while isinstance(base, ast.Attribute):
                base = base.value
            if isinstance(base, ast.Name):
                used_names.add(base.id)

    for name, lineno in imported_names.items():
        if name not in used_names and name not in exported_names and name != "*":
            issues.append(LintIssue(path, lineno, "F401", f"'{name}' imported but unused"))

    return issues


def lint_file(path: str) -> List[LintIssue]:
    try:
        with open(path, "r", encoding="utf-8") as f:
            source = f.read()
    except (UnicodeDecodeError, OSError):
        return []

    lines = source.splitlines(keepends=True)
    issues = _check_lines(path, lines)
    issues.extend(_check_unused_imports(path, source))
    return sorted(issues, key=lambda i: i.line_number)


def lint_path(path: str) -> List[LintIssue]:
    issues: List[LintIssue] = []
    if os.path.isfile(path):
        issues.extend(lint_file(path))
    else:
        for root, _dirs, files in os.walk(path):
            if "__pycache__" in root:
                continue
            for name in sorted(files):
                if name.endswith(".py"):
                    issues.extend(lint_file(os.path.join(root, name)))
    return issues


def print_report(issues: List[LintIssue], label: str) -> int:
    print(f"\n{'=' * 78}\nsimple_lint.py results: {label}\n{'=' * 78}")
    if not issues:
        print("No issues found.")
        return 0
    for issue in issues:
        print(f"{issue.file}:{issue.line_number}: {issue.code} {issue.message}")
    print(f"\n{len(issues)} issue(s) found.")
    return len(issues)


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python simple_lint.py <file_or_directory> [...]")
        sys.exit(1)

    total_issues = 0
    for target in sys.argv[1:]:
        found = lint_path(target)
        total_issues += print_report(found, target)

    # Mirrors flake8's behavior: a non-zero exit code when issues are
    # found, so this can be used as a CI-style gate the same way.
    sys.exit(1 if total_issues > 0 else 0)
