"""
simple_static_scanner.py
---------------------------
A small, dependency-free static analysis tool that scans Python source
files for common insecure patterns, in the spirit of tools like
`bandit`. Written from scratch specifically because this environment
has no internet access to install bandit (pip install fails offline --
see SECURITY_AUDIT_REPORT.md Section 2 for that log). It does not
replace a real tool like bandit for production use, but demonstrates
the same category of technique -- pattern-based static analysis -- and
is genuinely useful here: run against vulnerable_app/ vs. secure_app/
it produces a real before/after finding count.

This is intentionally simple (regex-based, line-oriented) rather than
using the `ast` module for full semantic analysis -- adequate for the
known vulnerability classes in this project, and easy to read/audit
itself, which matters for a security tool.

Usage:
    python simple_static_scanner.py <file_or_directory> [<file_or_directory> ...]
"""

from __future__ import annotations

import os
import re
import sys
from dataclasses import dataclass
from typing import List


@dataclass
class Finding:
    file: str
    line_number: int
    line_text: str
    rule_id: str
    severity: str
    message: str


# Each rule: (rule_id, severity, compiled regex, message). Regexes are
# intentionally simple substring/pattern checks on a single line,
# matching how bandit's simpler checks work.
RULES = [
    (
        "PY-SQL-001",
        "HIGH",
        re.compile(r"""(execute|executemany)\s*\(\s*f['"]"""),
        "Possible SQL injection: query built with an f-string passed to execute().",
    ),
    (
        "PY-SQL-002",
        "HIGH",
        re.compile(r"""(execute|executemany)\s*\([^)]*%\s*"""),
        "Possible SQL injection: query built with % string formatting passed to execute().",
    ),
    (
        "PY-SQL-003",
        "HIGH",
        re.compile(r"""(execute|executemany)\s*\([^)]*\+"""),
        "Possible SQL injection: query built with string concatenation (+) passed to execute().",
    ),
    (
        "PY-PICKLE-001",
        "HIGH",
        re.compile(r"\bpickle\.load\s*\("),
        "Insecure deserialization: pickle.load() can execute arbitrary code for a crafted input file.",
    ),
    (
        "PY-EVAL-001",
        "HIGH",
        re.compile(r"\beval\s*\("),
        "Use of eval(): can execute arbitrary code if any part of the argument is influenced by input.",
    ),
    (
        "PY-EVAL-002",
        "HIGH",
        re.compile(r"\bexec\s*\("),
        "Use of exec(): can execute arbitrary code if any part of the argument is influenced by input.",
    ),
    (
        "PY-HARDCODED-001",
        "MEDIUM",
        re.compile(r"""(?i)(password|passwd|secret|api_key|token)\s*=\s*['"][^'"]+['"]"""),
        "Possible hard-coded credential/secret assigned directly in source code.",
    ),
    (
        "PY-WEAKRAND-001",
        "MEDIUM",
        re.compile(r"\brandom\.(random|randint|randrange|choice)\s*\("),
        "Use of the non-cryptographic `random` module; use `secrets` for anything security-sensitive.",
    ),
    (
        "PY-LOGSECRET-001",
        "MEDIUM",
        re.compile(r"""(?i)\.write\([^)]*password"""),
        "Possible sensitive data (password) written to a log/file.",
    ),
    (
        "PY-TRACEBACK-001",
        "LOW",
        re.compile(r"\btraceback\.format_exc\s*\(\s*\)"),
        "Full traceback captured; ensure this is never returned/displayed to an end user.",
    ),
    (
        "PY-PLAINPW-001",
        "MEDIUM",
        re.compile(r"""INSERT INTO users.*password"""),
        "Password appears to be inserted into the database without an obvious hashing step nearby.",
    ),
]


def scan_file(path: str) -> List[Finding]:
    findings: List[Finding] = []
    try:
        with open(path, "r", encoding="utf-8") as f:
            lines = f.readlines()
    except (UnicodeDecodeError, OSError):
        return findings

    # --- Simple single-pass "taint tracking" for the common pattern:
    #     query = f"...{user_input}..."
    #     cursor = self.conn.execute(query)
    # A pure single-line regex (the RULES above) only catches
    # execute(f"...") written inline, and misses this equally common
    # two-step form entirely -- a real limitation of line-oriented
    # regex scanning, discussed in SECURITY_AUDIT_REPORT.md. This
    # narrow addition (tracking simple `name = f"..."` / `name = "..." %`
    # assignments and flagging a later `execute(name)`) closes that
    # specific, common gap without implementing full dataflow analysis.
    assign_pattern = re.compile(r"""^\s*(\w+)\s*=\s*\(?\s*f?['"].*['"]?\s*$""")
    fstring_assign_pattern = re.compile(r"""^\s*(\w+)\s*=.*f['"]""")
    percent_assign_pattern = re.compile(r"""^\s*(\w+)\s*=.*['"]\s*%\s*""")
    execute_var_pattern = re.compile(r"""(execute|executemany)\s*\(\s*(\w+)\s*\)""")

    tainted_vars = {}  # var_name -> line_number where it was assigned
    for i, line in enumerate(lines, start=1):
        m = fstring_assign_pattern.match(line) or percent_assign_pattern.match(line)
        if m:
            tainted_vars[m.group(1)] = i

    in_docstring = False
    for i, line in enumerate(lines, start=1):
        stripped = line.strip()
        triple_quote_count = stripped.count('"""') + stripped.count("'''")
        if triple_quote_count % 2 == 1:
            # Line opens or closes a docstring/triple-quoted block.
            in_docstring = not in_docstring
            continue
        if in_docstring:
            continue
        if stripped.startswith("#"):
            continue
        for rule_id, severity, pattern, message in RULES:
            if pattern.search(line):
                findings.append(Finding(path, i, stripped, rule_id, severity, message))

        m = execute_var_pattern.search(line)
        if m:
            var_name = m.group(2)
            if var_name in tainted_vars:
                findings.append(Finding(
                    path, i, stripped, "PY-SQL-004", "HIGH",
                    f"Possible SQL injection: execute({var_name}) where '{var_name}' was built "
                    f"with an f-string/format on line {tainted_vars[var_name]}.",
                ))

    return findings


def scan_path(path: str) -> List[Finding]:
    findings: List[Finding] = []
    if os.path.isfile(path):
        findings.extend(scan_file(path))
    else:
        for root, _dirs, files in os.walk(path):
            for name in files:
                if name.endswith(".py"):
                    findings.extend(scan_file(os.path.join(root, name)))
    return findings


def print_report(findings: List[Finding], label: str) -> None:
    print(f"\n{'=' * 78}\nStatic scan results: {label}\n{'=' * 78}")
    if not findings:
        print("No findings.")
        return

    severity_order = {"HIGH": 0, "MEDIUM": 1, "LOW": 2}
    findings_sorted = sorted(findings, key=lambda f: (severity_order.get(f.severity, 9), f.file, f.line_number))

    counts = {"HIGH": 0, "MEDIUM": 0, "LOW": 0}
    for f in findings_sorted:
        counts[f.severity] = counts.get(f.severity, 0) + 1
        print(f"\n[{f.severity}] {f.rule_id}  {f.file}:{f.line_number}")
        print(f"  {f.line_text}")
        print(f"  -> {f.message}")

    print(f"\n{'-' * 78}")
    print(f"Total findings: {len(findings_sorted)}  "
          f"(HIGH={counts.get('HIGH', 0)}, MEDIUM={counts.get('MEDIUM', 0)}, LOW={counts.get('LOW', 0)})")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python simple_static_scanner.py <file_or_directory> [...]")
        sys.exit(1)

    for target in sys.argv[1:]:
        results = scan_path(target)
        print_report(results, target)
