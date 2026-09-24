# VaultCLI — Security Audit & Hardening Project

`VaultCLI` is a personal-notes vault CLI application (SQLite-backed
accounts + notes). This project contains its **original, vulnerable**
implementation, a **hardened, secure** implementation, real exploit
demonstrations proving each vulnerability and each fix, and 32
automated regression tests.

See **[`SECURITY_AUDIT_REPORT.md`](SECURITY_AUDIT_REPORT.md)** for the
full write-up: all 11 vulnerabilities found (each with CWE/OWASP
references and a real, demonstrated exploit), every fix applied with
before/after code, and full test/validation results.

## ⚠️ Important

`vulnerable_app/` is deliberately insecure. It exists solely as the
"before" half of this audit and must never be deployed anywhere or
used with real data. All exploit demos run against local, throwaway
SQLite files created and deleted by the demo scripts themselves —
nothing here touches any external system.

## What's in this repository

```
security_project/
├── vulnerable_app/
│   └── vault_cli.py             # baseline, with VULN-NN comments marking each issue
├── secure_app/
│   └── vault_cli.py             # hardened version, with matching FIX comments
├── tools/
│   └── simple_static_scanner.py # custom static analyzer (bandit unavailable offline)
├── exploits/
│   ├── exploit_sql_injection.py         # real SQLi: auth bypass + data exfiltration
│   ├── exploit_path_traversal.py        # real path traversal file write
│   ├── exploit_pickle_rce.py            # real code execution via crafted pickle
│   ├── exploit_weak_token.py            # predictable password-reset token
│   └── run_exploits_against_secure.py   # re-runs all of the above against secure_app
├── tests/
│   └── test_security_fixes.py   # 32 tests: every fix verified + functionality preserved
├── SECURITY_AUDIT_REPORT.md     # the full audit — read this
└── README.md                    # you are here
```

## Requirements

Python 3.8+ and the `cryptography` package (used for authenticated
encryption of note content). Everything else is standard library.

```bash
pip install cryptography
```

## Running things

**Automated tests** (from the project root):
```bash
python -m unittest tests.test_security_fixes -v
```
Expected: `Ran 32 tests ... OK`.

**See the vulnerabilities happen for real**, one at a time:
```bash
cd exploits
python exploit_sql_injection.py
python exploit_path_traversal.py
python exploit_pickle_rce.py
python exploit_weak_token.py
```

**Confirm the fixes hold** against the exact same attacks:
```bash
python run_exploits_against_secure.py
```
Expected: `All 6 re-tested attacks are blocked by the secure version. ✔`

**Run the static scanner** against either version:
```bash
cd ..
python tools/simple_static_scanner.py vulnerable_app/
python tools/simple_static_scanner.py secure_app/
```

## Quick usage example (secure version)

```python
from secure_app.vault_cli import VaultApp, generate_encryption_key

# Generate and store this key somewhere safe -- NOT in source code,
# NOT alongside the database file (see SECURITY_AUDIT_REPORT.md Section 6).
key = generate_encryption_key()

app = VaultApp("vault.db", encryption_key=key)
user_id = app.register("alice", "a-strong-password-here")
app.login("alice", "a-strong-password-here")
app.add_note(user_id, "Reminder", "Call the bank about the statement")
print(app.search_notes(user_id, "Reminder"))
app.close()
```

## The short version

11 vulnerabilities were found in the original — 3 SQL injections, a
hard-coded admin backdoor, plaintext password storage, no encryption
at rest, passwords logged in plaintext, predictable reset tokens, a
path traversal bug, insecure deserialization via `pickle` (real
arbitrary code execution), and verbose error messages leaking schema
details. Four were demonstrated with real, working exploit scripts —
not just described — and all four attacks fail against the hardened
version, confirmed both by re-running the exact same exploits and by
32 automated regression tests. See
[`SECURITY_AUDIT_REPORT.md`](SECURITY_AUDIT_REPORT.md) for the
complete analysis.
