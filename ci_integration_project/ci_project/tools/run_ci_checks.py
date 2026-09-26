"""
run_ci_checks.py
-------------------
Runs the same checks as .github/workflows/ci.yml, locally, in one
command: lint, then tests, then a JUnit-style XML test report.

WHY THIS EXISTS: the real CI pipeline uses flake8 and pytest,
installed fresh by GitHub's runners (which have internet access).
This authoring/development environment does not have internet access
(see CI_DOCUMENTATION.md, "Challenges Encountered"), so flake8 and
pytest could not be installed here to dry-run the pipeline directly.
This script performs the equivalent checks using tools that ARE
available -- tools/simple_lint.py in place of flake8, and Python's
built-in `unittest` (wrapped to also emit a JUnit XML report, the
same format pytest's --junitxml produces) in place of pytest.

Anyone WITH a normal internet connection should prefer the real
tools directly (see README.md "Running checks locally" section for
both options side by side):
    pip install -r requirements-dev.txt
    flake8 mini_calc tests
    pytest --junitxml=test-results/junit.xml -v

Usage:
    python tools/run_ci_checks.py
Exit code 0 if everything passes, non-zero otherwise -- safe to use
as a pre-commit gate the same way the real CI job is a merge gate.
"""

from __future__ import annotations

import os
import subprocess
import sys
import time
import unittest
import xml.etree.ElementTree as ET

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))


def run_lint() -> bool:
    print("\n" + "=" * 78)
    print("STEP 1/2: Lint  (tools/simple_lint.py -- stand-in for flake8; see docstring)")
    print("=" * 78)
    result = subprocess.run(
        [sys.executable, os.path.join(ROOT, "tools", "simple_lint.py"),
         os.path.join(ROOT, "mini_calc"), os.path.join(ROOT, "tests")],
    )
    return result.returncode == 0


class XMLTestResult(unittest.TextTestResult):
    """A unittest TestResult subclass that also records per-test
    timing and outcome, so a JUnit-style XML report can be built from
    it afterward -- the same information pytest's --junitxml captures
    from a real pytest run."""

    def startTest(self, test):
        self._start_time = time.perf_counter()
        super().startTest(test)

    def addSuccess(self, test):
        super().addSuccess(test)
        self._record(test, "pass")

    def addFailure(self, test, err):
        super().addFailure(test, err)
        self._record(test, "failure", self._exc_info_to_string(err, test))

    def addError(self, test, err):
        super().addError(test, err)
        self._record(test, "error", self._exc_info_to_string(err, test))

    def addSkip(self, test, reason):
        super().addSkip(test, reason)
        self._record(test, "skipped", reason)

    def _record(self, test, outcome, detail=""):
        if not hasattr(self, "records"):
            self.records = []
        elapsed = time.perf_counter() - getattr(self, "_start_time", time.perf_counter())
        classname = test.__class__.__module__ + "." + test.__class__.__qualname__
        self.records.append({
            "classname": classname,
            "name": test._testMethodName,
            "time": elapsed,
            "outcome": outcome,
            "detail": detail,
        })


def write_junit_xml(records, path: str, suite_name: str = "mini_calc") -> None:
    """Write a JUnit XML report in the same shape pytest's
    --junitxml produces, from the collected unittest records above."""
    total = len(records)
    failures = sum(1 for r in records if r["outcome"] == "failure")
    errors = sum(1 for r in records if r["outcome"] == "error")
    skipped = sum(1 for r in records if r["outcome"] == "skipped")
    total_time = sum(r["time"] for r in records)

    testsuite = ET.Element("testsuite", {
        "name": suite_name,
        "tests": str(total),
        "failures": str(failures),
        "errors": str(errors),
        "skipped": str(skipped),
        "time": f"{total_time:.4f}",
    })

    for r in records:
        testcase = ET.SubElement(testsuite, "testcase", {
            "classname": r["classname"],
            "name": r["name"],
            "time": f"{r['time']:.6f}",
        })
        if r["outcome"] == "failure":
            failure_el = ET.SubElement(testcase, "failure", {"message": "test failure"})
            failure_el.text = r["detail"]
        elif r["outcome"] == "error":
            error_el = ET.SubElement(testcase, "error", {"message": "test error"})
            error_el.text = r["detail"]
        elif r["outcome"] == "skipped":
            skipped_el = ET.SubElement(testcase, "skipped", {"message": r["detail"] or "skipped"})

    os.makedirs(os.path.dirname(path), exist_ok=True)
    tree = ET.ElementTree(testsuite)
    ET.indent(tree, space="  ")
    tree.write(path, encoding="unicode", xml_declaration=True)


def run_tests() -> bool:
    print("\n" + "=" * 78)
    print("STEP 2/2: Tests  (unittest, wrapped to also emit a JUnit XML report)")
    print("=" * 78)

    loader = unittest.TestLoader()
    suite = loader.discover(os.path.join(ROOT, "tests"), top_level_dir=ROOT)

    runner = unittest.TextTestRunner(verbosity=2, resultclass=XMLTestResult)
    result = runner.run(suite)

    records = getattr(result, "records", [])
    report_path = os.path.join(ROOT, "test-results", "junit.xml")
    write_junit_xml(records, report_path)
    print(f"\nJUnit XML report written to: {report_path}")

    return result.wasSuccessful()


def main() -> int:
    lint_ok = run_lint()
    tests_ok = run_tests()

    print("\n" + "=" * 78)
    print("SUMMARY")
    print("=" * 78)
    print(f"  Lint:  {'PASSED' if lint_ok else 'FAILED'}")
    print(f"  Tests: {'PASSED' if tests_ok else 'FAILED'}")

    if lint_ok and tests_ok:
        print("\nAll checks passed. ✔ (this is what a green CI run looks like)")
        return 0
    else:
        print("\nOne or more checks failed. ✘ (this is what would fail the CI pipeline)")
        return 1


if __name__ == "__main__":
    sys.exit(main())
