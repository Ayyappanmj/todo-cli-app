"""
vault_cli.py  (VULNERABLE / BASELINE VERSION)
------------------------------------------------
A small personal "vault" CLI application: users register an account,
log in, and store/search/export personal notes (backed by SQLite).

THIS IS THE PRE-AUDIT BASELINE VERSION. It is functionally complete
but contains a number of realistic, common security vulnerabilities,
each flagged with a VULN comment referencing the relevant CWE/OWASP
category. SECURITY_AUDIT_REPORT.md documents each one in full: how it
was found, how it can be exploited (demonstrated for real against
this exact code in exploits/), and the fix applied in
secure_app/vault_cli.py.

Do not deploy this version anywhere. It exists solely as the "before"
half of a before/after security audit.
"""

from __future__ import annotations

import os
import pickle
import random
import sqlite3
import traceback
from dataclasses import dataclass
from typing import List, Optional

# ---------------------------------------------------------------------
# VULN-06 (CWE-798, Use of Hard-coded Credentials / OWASP A07):
# A hard-coded "backdoor" admin password baked directly into the
# source code. Anyone who ever sees this file (including via a public
# repo, a decompiled build, or simple source leakage) gets permanent
# admin access to every deployment of this application, and the
# password can never be rotated without a code change and redeploy.
# ---------------------------------------------------------------------
ADMIN_BACKDOOR_PASSWORD = "letmein123"

LOG_FILE = "vault_activity.log"


@dataclass
class Note:
    id: int
    user_id: int
    title: str
    content: str


class VaultDB:
    """Thin data-access layer over a local SQLite database."""

    def __init__(self, db_path: str):
        self.db_path = db_path
        self.conn = sqlite3.connect(db_path)
        self._create_tables()

    def _create_tables(self) -> None:
        self.conn.execute(
            """CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT UNIQUE NOT NULL,
                password TEXT NOT NULL
            )"""
        )
        self.conn.execute(
            """CREATE TABLE IF NOT EXISTS notes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                title TEXT NOT NULL,
                content TEXT NOT NULL
            )"""
        )
        self.conn.commit()

    # ------------------------------------------------------------------
    def register(self, username: str, password: str) -> int:
        """Create a new user account.

        VULN-01 (CWE-256/CWE-312, Plaintext Storage of Password /
        OWASP A02 Cryptographic Failures): the password is stored
        completely unhashed. Anyone with read access to the database
        file -- via a backup, a misconfigured server, an SQL
        injection elsewhere (see VULN-02/03), or simple theft of the
        .db file -- immediately obtains every user's real password in
        plaintext, which most users reuse across other sites.
        """
        cursor = self.conn.execute(
            f"INSERT INTO users (username, password) VALUES ('{username}', '{password}')"
        )
        # VULN-02 (CWE-89, SQL Injection / OWASP A03): the INSERT above
        # builds the SQL statement via an f-string, directly splicing
        # user-controlled `username`/`password` into the query text.
        # A username like `x', 'y'); DROP TABLE users; --` is executed
        # as SQL, not treated as data.
        self.conn.commit()
        return cursor.lastrowid

    def login(self, username: str, password: str) -> Optional[int]:
        """Return the user's id if the credentials match, else None.

        VULN-03 (CWE-89, SQL Injection / OWASP A03): the WHERE clause
        is built with an f-string. A username of
        `admin' --` bypasses the password check entirely (the `--`
        comments out the rest of the query), and a username of
        `' OR '1'='1` logs in as the FIRST row in the users table
        without knowing any real password. Demonstrated for real in
        exploits/exploit_sql_injection.py.
        """
        query = f"SELECT id FROM users WHERE username = '{username}' AND password = '{password}'"
        cursor = self.conn.execute(query)
        row = cursor.fetchone()
        return row[0] if row else None

    def add_note(self, user_id: int, title: str, content: str) -> int:
        """Store a new note for a user.

        VULN-04 (CWE-89, SQL Injection): same f-string-built-query
        pattern as above, applied to note content this time -- an
        attacker's note content can inject SQL that runs when this
        INSERT executes.

        VULN-05 (CWE-311, Missing Encryption of Sensitive Data /
        OWASP A02): note content is written to the database exactly
        as given, even though the whole point of this app is to store
        sensitive personal notes. Anyone who can read the .db file
        (theft, backup leakage, another vulnerability) reads every
        note in plaintext.
        """
        cursor = self.conn.execute(
            f"INSERT INTO notes (user_id, title, content) VALUES ({user_id}, '{title}', '{content}')"
        )
        self.conn.commit()
        return cursor.lastrowid

    def search_notes(self, user_id: int, keyword: str) -> List[Note]:
        """Search a user's notes by keyword in the title.

        VULN (CWE-89, SQL Injection): the LIKE clause is built by
        directly splicing `keyword` into the query string. A keyword
        of `%' UNION SELECT id, user_id, username, password FROM
        users --` can be used to read data from a completely
        different table than the one this endpoint is meant to query
        -- exactly the kind of injection that leaks other users'
        credentials through a feature that looks read-only and low
        risk on the surface.
        """
        query = (
            f"SELECT id, user_id, title, content FROM notes "
            f"WHERE user_id = {user_id} AND title LIKE '%{keyword}%'"
        )
        cursor = self.conn.execute(query)
        return [Note(*row) for row in cursor.fetchall()]

    def close(self) -> None:
        self.conn.close()


class VaultApp:
    def __init__(self, db_path: str = "vault.db"):
        self.db = VaultDB(db_path)

    # ------------------------------------------------------------------
    def register(self, username: str, password: str) -> int:
        return self.db.register(username, password)

    def login(self, username: str, password: str) -> Optional[int]:
        """Attempt to log in, with logging and an admin backdoor.

        VULN-07 (CWE-532, Insertion of Sensitive Information into Log
        File / OWASP A09): every login attempt is logged INCLUDING
        THE PLAINTEXT PASSWORD. Log files are routinely shipped to
        third-party log aggregators, kept far longer than the primary
        database, backed up separately, and read by a much wider set
        of engineers than the production DB -- this leaks every
        password (successful or not, including typos of real
        passwords) to anyone with log access.
        """
        with open(LOG_FILE, "a") as f:
            f.write(f"LOGIN ATTEMPT: username={username} password={password}\n")

        # VULN-06 continued: the hard-coded backdoor password grants
        # admin (user_id 0) access to ANY username, bypassing the
        # entire authentication system.
        if password == ADMIN_BACKDOOR_PASSWORD:
            return 0  # pseudo admin user id

        user_id = self.db.login(username, password)
        return user_id

    def add_note(self, user_id: int, title: str, content: str) -> int:
        return self.db.add_note(user_id, title, content)

    def search_notes(self, user_id: int, keyword: str) -> List[Note]:
        return self.db.search_notes(user_id, keyword)

    # ------------------------------------------------------------------
    def generate_password_reset_token(self) -> str:
        """Generate a token to email a user for password reset.

        VULN-08 (CWE-330/CWE-338, Use of Insufficiently Random Values
        / OWASP A02): uses the `random` module, which is a
        non-cryptographic PRNG (Mersenne Twister) seeded from
        predictable state (system time, by default). Its output is
        predictable enough that an attacker who observes a few tokens
        (or knows roughly when a token was generated) can often
        reconstruct the internal state and predict FUTURE tokens --
        letting them take over any account by requesting a "reset"
        and guessing/computing the token, without ever seeing the
        victim's email.
        """
        return str(random.randint(100000, 999999))

    # ------------------------------------------------------------------
    def export_notes(self, user_id: int, filename: str) -> str:
        """Export a user's notes to a text file at `filename`.

        VULN-09 (CWE-22, Path Traversal / OWASP A01): `filename` is
        used directly to build a file path with no validation. A
        filename like `../../../../etc/cron.d/evil` (on a real
        deployment) lets an attacker write the exported content
        WHEREVER on the filesystem the running process has write
        access -- turning a "download my notes" feature into an
        arbitrary file write. Demonstrated in
        exploits/exploit_path_traversal.py by writing outside the
        intended export directory.
        """
        notes = self.db.search_notes(user_id, "")
        export_path = os.path.join("exports", filename)
        with open(export_path, "w") as f:
            for note in notes:
                f.write(f"{note.title}\n{note.content}\n\n")
        return export_path

    def import_notes(self, backup_path: str) -> int:
        """Restore notes from a backup file previously saved with
        export_notes_binary() (see below).

        VULN-10 (CWE-502, Deserialization of Untrusted Data / OWASP
        A08): uses pickle.load() on a file the caller provides.
        Unpickling is NOT just "loading data" -- a crafted pickle file
        can execute arbitrary code the instant it's loaded, via a
        `__reduce__` method that returns a callable (like
        `os.system`) to run during deserialization. Anyone who can
        supply a "backup file" to import -- a malicious file shared
        as a backup, a compromised storage location, a supply-chain
        attack on a backup service -- can achieve full code execution
        on the machine running this import, not just corrupt data.
        Demonstrated in exploits/exploit_pickle_rce.py.
        """
        with open(backup_path, "rb") as f:
            notes = pickle.load(f)
        count = 0
        for note in notes:
            self.add_note(note["user_id"], note["title"], note["content"])
            count += 1
        return count

    def export_notes_binary(self, user_id: int, backup_path: str) -> str:
        """Save notes as a pickle file (paired with import_notes above)."""
        notes = self.db.search_notes(user_id, "")
        data = [{"user_id": n.user_id, "title": n.title, "content": n.content} for n in notes]
        with open(backup_path, "wb") as f:
            pickle.dump(data, f)
        return backup_path

    # ------------------------------------------------------------------
    def run_query_and_report(self, sql_fragment: str) -> str:
        """A diagnostic helper used by an internal 'run a report' menu
        option, which shows the *outcome* of a raw error, illustrating
        a separate issue from the injection points above.

        VULN-11 (CWE-209, Generation of Error Message Containing
        Sensitive Information / OWASP A05): on any failure, the FULL
        exception (including the raw SQL, table/column names, and a
        complete Python traceback with file paths) is returned
        straight to the caller. In a real app this text would be
        printed to a user-facing terminal or HTTP response, handing an
        attacker a live map of the database schema and internal file
        layout for free, and often more than enough detail to refine
        a SQL injection attempt through pure trial and error.
        """
        try:
            cursor = self.db.conn.execute(sql_fragment)
            return str(cursor.fetchall())
        except Exception:
            return traceback.format_exc()

    def close(self) -> None:
        self.db.close()
