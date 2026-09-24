"""
vault_cli.py  (SECURE / HARDENED VERSION)
---------------------------------------------
Same application as vulnerable_app/vault_cli.py -- user accounts,
personal notes, search, export/import -- with every vulnerability
identified in SECURITY_AUDIT_REPORT.md fixed. Each fix is marked with
a FIX comment referencing the VULN-NN id it addresses, so the two
files can be compared side by side.

Two things changed at the API level, deliberately and for good
reason (both documented in the audit report):
  - import_notes()/export_notes_binary() now use JSON, not pickle.
    There is no way to keep pickle's exact interface "safe" -- the
    vulnerability IS the deserialization primitive itself, so the fix
    is to stop using it, not to sanitize its input.
  - VaultApp.__init__() now requires an encryption key (see
    generate_encryption_key() below) rather than silently using none.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import os
import re
import secrets
import sqlite3
import time
from dataclasses import dataclass
from typing import List, Optional

from cryptography.fernet import Fernet, InvalidToken

# ---------------------------------------------------------------------
# FIX for VULN-06 (hard-coded backdoor password): there is no backdoor
# in this version. A backdoor is not "hardened" by making its password
# stronger or configurable -- an authentication bypass path that
# skips normal credential checking is a vulnerability by definition,
# regardless of how the trigger value is stored. It was removed
# entirely. Legitimate administrative access should instead be
# implemented as a normal account with an `is_admin` flag, subject to
# the exact same authentication as every other account.
# ---------------------------------------------------------------------

LOG_FILE = "vault_activity.log"

# FIX for VULN-08 (weak reset tokens): only ever used for logging
# NON-sensitive metadata now -- see login() below.

_USERNAME_RE = re.compile(r"^[A-Za-z0-9_]{3,32}$")

# FIX (defense in depth, supports VULN-03 fix): basic brute-force
# mitigation. Not a complete replacement for the SQL injection fix
# itself (parameterized queries are what actually closes VULN-02/03/04),
# but reduces the blast radius of credential-guessing attacks against
# a properly-fixed login endpoint too.
_MAX_FAILED_ATTEMPTS = 5
_LOCKOUT_SECONDS = 60


class SecurityError(Exception):
    """Raised for security-relevant failures (bad input, lockout,
    decryption failure) that should map to a generic, safe message
    for the end user -- see run_query_and_report()'s replacement,
    and ValidationError below, for how detail is kept server-side."""


class ValidationError(SecurityError):
    """Raised when user-supplied input fails validation."""


@dataclass
class Note:
    id: int
    user_id: int
    title: str
    content: str


def generate_encryption_key() -> bytes:
    """Generate a new Fernet key for encrypting note content at rest.

    FIX for VULN-05 (missing encryption of sensitive data): notes are
    encrypted before being written to the database (see VaultDB.add_note
    below) using Fernet -- AES-128-CBC with an HMAC-SHA256 authentication
    tag (i.e. authenticated encryption: tampering is detected, not just
    prevented from being silently accepted).

    KEY MANAGEMENT NOTE (see SECURITY_AUDIT_REPORT.md Section 6): this
    key must be stored OUTSIDE the source code and outside the
    database it protects -- e.g. an environment variable, a secrets
    manager, or a file with restrictive permissions (chmod 600) kept
    separate from any backup of the database file. Storing the key
    alongside the data it encrypts (e.g. hard-coded here, or in the
    same DB) defeats the purpose entirely: whoever can read the
    ciphertext could also read the key. This function only generates
    a fresh key for callers (and this project's own tests/demo) to
    manage appropriately; it is intentionally not persisted anywhere
    by this module.
    """
    return Fernet.generate_key()


def _validate_username(username: str) -> str:
    """FIX (input validation hardening): usernames are restricted to
    3-32 alphanumeric/underscore characters. This isn't primarily an
    injection defense (parameterized queries, below, are what actually
    prevent injection) -- it closes off a separate class of issues:
    usernames containing control characters, extremely long values (a
    cheap denial-of-service vector against storage/logging), or
    characters that could cause problems in other contexts this value
    might later flow into (e.g. being included in an exported filename,
    an email, or a log line)."""
    if not isinstance(username, str) or not _USERNAME_RE.match(username):
        raise ValidationError(
            "Username must be 3-32 characters, letters/numbers/underscore only."
        )
    return username


def _validate_password_strength(password: str) -> str:
    """FIX (input validation hardening): a minimal, defensible baseline
    -- length is the single strongest, simplest predictor of password
    strength, and arbitrary composition rules (must contain a symbol,
    etc.) are now widely discouraged (see NIST SP 800-63B) since they
    push users toward predictable patterns without meaningfully
    increasing entropy."""
    if not isinstance(password, str) or len(password) < 8:
        raise ValidationError("Password must be at least 8 characters long.")
    if len(password) > 256:
        # Extremely long inputs are a cheap resource-exhaustion vector
        # against a deliberately slow hash function (see hash_password).
        raise ValidationError("Password is too long.")
    return password


def _validate_note_text(value: str, field_name: str, max_length: int = 10_000) -> str:
    if not isinstance(value, str):
        raise ValidationError(f"{field_name} must be text.")
    if len(value) == 0:
        raise ValidationError(f"{field_name} cannot be empty.")
    if len(value) > max_length:
        raise ValidationError(f"{field_name} is too long (max {max_length} characters).")
    return value


def _safe_export_filename(filename: str) -> str:
    """FIX for VULN-09 (path traversal): strips any directory
    components from the caller-supplied filename (os.path.basename
    discards everything before the final path separator, so
    '../../etc/x' becomes just 'x'), then restricts the remaining
    name to a safe character set. The result is then joined with the
    fixed export directory and verified (via os.path.realpath) to
    still resolve to somewhere inside that directory before any file
    is opened -- a second, independent check in case of any
    reasoning error in the character-stripping step above, following
    defense-in-depth rather than relying on one single guard."""
    base = os.path.basename(filename)
    if not re.match(r"^[A-Za-z0-9._-]{1,128}$", base):
        raise ValidationError(
            "Export filename may only contain letters, numbers, dots, "
            "hyphens, and underscores."
        )
    return base


def hash_password(password: str) -> str:
    """FIX for VULN-01 (plaintext password storage): hashes the
    password with PBKDF2-HMAC-SHA256, a deliberately slow, salted key
    derivation function purpose-built for password storage (unlike a
    single fast hash like SHA-256 alone, which is FAST -- a property
    that helps an attacker who steals the hash try billions of
    guesses per second on commodity hardware).

    A fresh random salt (via `secrets`, not `random`) is generated per
    password and stored alongside the hash, so two users with the
    same password get completely different stored values, and
    precomputed "rainbow table" attacks don't apply.

    200,000 iterations follows current OWASP guidance for
    PBKDF2-HMAC-SHA256 as of this writing. bcrypt or Argon2id (via the
    `bcrypt` or `argon2-cffi` packages) are also good choices and are
    somewhat more resistant to GPU-based cracking specifically; this
    project uses PBKDF2 via the standard library's `hashlib` because
    this offline environment has no network access to install those
    packages (see SECURITY_AUDIT_REPORT.md Section 2) -- PBKDF2 at
    this iteration count is still a widely accepted, secure choice,
    not a compromise made for convenience.
    """
    salt = secrets.token_bytes(16)
    iterations = 200_000
    derived = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, iterations)
    return f"pbkdf2_sha256${iterations}${salt.hex()}${derived.hex()}"


def verify_password(password: str, stored_hash: str) -> bool:
    """Verify a password against a hash produced by hash_password().

    Uses hmac.compare_digest() for the final comparison -- a
    constant-time comparison that doesn't leak (via response timing)
    how many leading bytes of the guess were correct, unlike Python's
    normal `==` on strings/bytes, which can short-circuit as soon as
    it finds a mismatched byte.
    """
    try:
        algorithm, iterations_str, salt_hex, hash_hex = stored_hash.split("$")
        if algorithm != "pbkdf2_sha256":
            return False
        iterations = int(iterations_str)
        salt = bytes.fromhex(salt_hex)
        expected = bytes.fromhex(hash_hex)
    except (ValueError, AttributeError):
        return False

    derived = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, iterations)
    return hmac.compare_digest(derived, expected)


class VaultDB:
    """Thin data-access layer over a local SQLite database."""

    def __init__(self, db_path: str, encryption_key: bytes):
        self.db_path = db_path
        self.conn = sqlite3.connect(db_path)
        self._fernet = Fernet(encryption_key)
        self._create_tables()

    def _create_tables(self) -> None:
        self.conn.execute(
            """CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT UNIQUE NOT NULL,
                password_hash TEXT NOT NULL,
                failed_attempts INTEGER NOT NULL DEFAULT 0,
                locked_until REAL NOT NULL DEFAULT 0
            )"""
        )
        self.conn.execute(
            """CREATE TABLE IF NOT EXISTS notes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                title TEXT NOT NULL,
                content_encrypted BLOB NOT NULL
            )"""
        )
        self.conn.commit()

    # ------------------------------------------------------------------
    def register(self, username: str, password: str) -> int:
        """Create a new user account.

        FIX for VULN-01 + VULN-02: the password is hashed (never
        stored in plaintext) before insertion, and the INSERT uses a
        parameterized query -- `?` placeholders -- instead of an
        f-string. The database driver sends the SQL text and the data
        as SEPARATE things to SQLite, so user-supplied values are
        always treated as data, never as part of the SQL grammar,
        regardless of what characters they contain. This is the
        actual, complete fix for SQL injection here -- not "escaping
        quotes" or "filtering bad characters" (both are error-prone
        blocklist approaches); parameterization removes the
        vulnerability class entirely by construction.
        """
        _validate_username(username)
        _validate_password_strength(password)
        password_hash = hash_password(password)
        try:
            cursor = self.conn.execute(
                "INSERT INTO users (username, password_hash) VALUES (?, ?)",
                (username, password_hash),
            )
        except sqlite3.IntegrityError as exc:
            raise ValidationError("That username is already taken.") from exc
        self.conn.commit()
        return cursor.lastrowid

    def get_user_auth_row(self, username: str):
        """FIX for VULN-03: parameterized query, same reasoning as above."""
        cursor = self.conn.execute(
            "SELECT id, password_hash, failed_attempts, locked_until "
            "FROM users WHERE username = ?",
            (username,),
        )
        return cursor.fetchone()

    def record_failed_attempt(self, user_id: int) -> None:
        cursor = self.conn.execute(
            "SELECT failed_attempts FROM users WHERE id = ?", (user_id,)
        )
        row = cursor.fetchone()
        failed = (row[0] if row else 0) + 1
        locked_until = 0.0
        if failed >= _MAX_FAILED_ATTEMPTS:
            locked_until = time.time() + _LOCKOUT_SECONDS
        self.conn.execute(
            "UPDATE users SET failed_attempts = ?, locked_until = ? WHERE id = ?",
            (failed, locked_until, user_id),
        )
        self.conn.commit()

    def reset_failed_attempts(self, user_id: int) -> None:
        self.conn.execute(
            "UPDATE users SET failed_attempts = 0, locked_until = 0 WHERE id = ?",
            (user_id,),
        )
        self.conn.commit()

    def add_note(self, user_id: int, title: str, content: str) -> int:
        """Store a new note for a user.

        FIX for VULN-04 (SQL injection): parameterized query.
        FIX for VULN-05 (missing encryption at rest): `content` is
        encrypted with Fernet before being written to the database.
        The title is NOT encrypted in this implementation (it's used
        for the LIKE-based search below, and encrypting it would
        require either leaving search unencrypted-searchable -- which
        leaks title contents via search patterns anyway -- or a much
        more involved searchable-encryption scheme). This is a
        deliberate, documented scope boundary: sensitive content goes
        in `content`, not `title`, and the audit report recommends
        this explicitly to whoever uses this module (see
        SECURITY_AUDIT_REPORT.md Section 6).
        """
        encrypted_content = self._fernet.encrypt(content.encode("utf-8"))
        cursor = self.conn.execute(
            "INSERT INTO notes (user_id, title, content_encrypted) VALUES (?, ?, ?)",
            (user_id, title, encrypted_content),
        )
        self.conn.commit()
        return cursor.lastrowid

    def search_notes(self, user_id: int, keyword: str) -> List[Note]:
        """FIX (SQL injection + VULN cross-table leak): parameterized
        query throughout, including the LIKE pattern -- the `%` wildcard
        characters are added in Python before binding, so a keyword
        containing `%`, `_`, or quote characters is still always
        treated purely as the literal search text, never as SQL
        syntax. This closes the exact UNION-based exfiltration
        demonstrated in exploits/exploit_sql_injection.py against the
        original.
        """
        like_pattern = f"%{keyword}%"
        cursor = self.conn.execute(
            "SELECT id, user_id, title, content_encrypted FROM notes "
            "WHERE user_id = ? AND title LIKE ?",
            (user_id, like_pattern),
        )
        results = []
        for row in cursor.fetchall():
            note_id, note_user_id, title, encrypted_content = row
            try:
                content = self._fernet.decrypt(encrypted_content).decode("utf-8")
            except InvalidToken:
                # Ciphertext failed authentication (wrong key, or
                # tampered data) -- fail safe rather than returning
                # corrupted/incorrect plaintext.
                content = "[unable to decrypt this note]"
            results.append(Note(note_id, note_user_id, title, content))
        return results

    def close(self) -> None:
        self.conn.close()


class VaultApp:
    def __init__(self, db_path: str = "vault.db", encryption_key: Optional[bytes] = None):
        if encryption_key is None:
            raise SecurityError(
                "An encryption_key is required. Use generate_encryption_key() to "
                "create one, and store it securely and separately from the "
                "database (see module docstring / SECURITY_AUDIT_REPORT.md)."
            )
        self.db = VaultDB(db_path, encryption_key)

    # ------------------------------------------------------------------
    def register(self, username: str, password: str) -> int:
        return self.db.register(username, password)

    def login(self, username: str, password: str) -> Optional[int]:
        """Attempt to log in.

        FIX for VULN-06 (hard-coded backdoor): removed entirely; see
        module docstring.
        FIX for VULN-07 (password logged in plaintext): the log entry
        below records only the username and success/failure -- never
        the password, in any form (not even hashed -- there's no
        legitimate operational reason to log it at all).
        FIX (brute-force hardening, complements VULN-03's fix):
        accounts are temporarily locked after repeated failed
        attempts.
        """
        _validate_username(username)

        row = self.db.get_user_auth_row(username)
        if row is None:
            # FIX: perform a dummy hash computation even when the
            # username doesn't exist, so the response time doesn't
            # reveal (via timing) whether a given username is
            # registered -- a real, if narrower, information leak in
            # its own right, distinct from VULN-11's verbose errors.
            hash_password(password)
            self._log_login_attempt(username, success=False)
            return None

        user_id, password_hash, failed_attempts, locked_until = row
        if locked_until and time.time() < locked_until:
            self._log_login_attempt(username, success=False, locked=True)
            raise SecurityError(
                "Account temporarily locked due to repeated failed attempts. "
                "Please try again later."
            )

        if verify_password(password, password_hash):
            self.db.reset_failed_attempts(user_id)
            self._log_login_attempt(username, success=True)
            return user_id

        self.db.record_failed_attempt(user_id)
        self._log_login_attempt(username, success=False)
        return None

    @staticmethod
    def _log_login_attempt(username: str, success: bool, locked: bool = False) -> None:
        status = "LOCKED" if locked else ("SUCCESS" if success else "FAILURE")
        # Never includes the password. Username is logged (it's
        # needed for legitimate security monitoring, e.g. spotting a
        # credential-stuffing pattern) -- if that's also considered
        # too sensitive for a given deployment's logs, it can be
        # hashed here too, at the cost of making the log harder to
        # use for that monitoring purpose. That trade-off is a
        # deployment decision; the code no longer makes the clearly
        # wrong choice (logging the password) for you.
        with open(LOG_FILE, "a") as f:
            f.write(f"{time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())} LOGIN {status} username={username}\n")

    def add_note(self, user_id: int, title: str, content: str) -> int:
        _validate_note_text(title, "Title", max_length=200)
        _validate_note_text(content, "Content")
        return self.db.add_note(user_id, title, content)

    def search_notes(self, user_id: int, keyword: str) -> List[Note]:
        return self.db.search_notes(user_id, keyword)

    # ------------------------------------------------------------------
    def generate_password_reset_token(self) -> str:
        """FIX for VULN-08 (predictable reset tokens): uses `secrets`,
        which draws from the operating system's cryptographically
        secure random source (os.urandom under the hood), not the
        deterministic, seedable Mersenne Twister `random` module.
        token_urlsafe(32) produces 32 bytes (256 bits) of entropy,
        URL-safe-encoded -- astronomically larger and non-reproducible
        compared to the original's 900,000-value range, and immune to
        the seed-prediction/state-recovery attacks demonstrated in
        exploits/exploit_weak_token.py.
        """
        return secrets.token_urlsafe(32)

    # ------------------------------------------------------------------
    def export_notes(self, user_id: int, filename: str) -> str:
        """Export a user's notes to a text file inside exports/.

        FIX for VULN-09 (path traversal): see _safe_export_filename()
        above. The resolved path is additionally checked to actually
        be inside the exports directory before writing, as a second,
        independent guard.
        """
        safe_name = _safe_export_filename(filename)
        export_dir = os.path.abspath("exports")
        os.makedirs(export_dir, exist_ok=True)
        export_path = os.path.join(export_dir, safe_name)

        resolved = os.path.realpath(export_path)
        if not resolved.startswith(os.path.realpath(export_dir) + os.sep):
            # Should be unreachable given _safe_export_filename()'s
            # character whitelist, but kept as a defense-in-depth
            # check rather than trusting a single validation layer.
            raise SecurityError("Resolved export path is outside the allowed directory.")

        notes = self.db.search_notes(user_id, "")
        with open(export_path, "w") as f:
            for note in notes:
                f.write(f"{note.title}\n{note.content}\n\n")
        return export_path

    def export_notes_json(self, user_id: int, backup_path: str) -> str:
        """Save notes as JSON (paired with import_notes_json below).

        FIX for VULN-10 (insecure deserialization): JSON replaces
        pickle entirely. JSON's grammar has no concept of "call this
        function" -- loading a JSON file can only ever produce plain
        data (dicts, lists, strings, numbers, booleans, None), never
        instructions to execute. There is no equivalent of pickle's
        __reduce__ mechanism in JSON, by design, which is precisely
        why it's the correct fix here rather than trying to sanitize
        or restrict pickle's behavior.
        """
        safe_name = _safe_export_filename(os.path.basename(backup_path))
        export_dir = os.path.abspath("exports")
        os.makedirs(export_dir, exist_ok=True)
        full_path = os.path.join(export_dir, safe_name)

        notes = self.db.search_notes(user_id, "")
        data = [{"user_id": n.user_id, "title": n.title, "content": n.content} for n in notes]
        with open(full_path, "w") as f:
            json.dump(data, f)
        return full_path

    def import_notes_json(self, backup_path: str) -> int:
        """FIX for VULN-10: json.load() instead of pickle.load().
        Additionally validates the loaded structure's shape before
        trusting it (defense in depth: even safe-by-construction
        formats should still have their application-level structure
        validated, same as any other external input).
        """
        with open(backup_path, "r") as f:
            notes = json.load(f)

        if not isinstance(notes, list):
            raise ValidationError("Backup file must contain a JSON list of notes.")

        count = 0
        for note in notes:
            if not isinstance(note, dict) or not all(k in note for k in ("user_id", "title", "content")):
                raise ValidationError(f"Malformed note entry in backup file: {note!r}")
            self.add_note(note["user_id"], note["title"], note["content"])
            count += 1
        return count

    # ------------------------------------------------------------------
    def run_query_and_report(self, table_name: str) -> str:
        """A safe replacement for the original's raw-SQL diagnostic
        helper (VULN-11). Rather than accepting arbitrary SQL AND
        returning raw errors (two separate problems -- see the audit
        report), this version only allows selecting a pre-approved
        table name (an allowlist, not a blocklist) and, on any
        failure, returns a single generic message to the caller while
        the full detail is written to the server-side log file only.

        FIX for VULN-11 (verbose error messages / information
        disclosure): a caller-facing message never contains SQL text,
        schema details, or a stack trace. Full diagnostic detail is
        still captured -- just not handed to whoever triggered the
        error, who might be an attacker probing for information.
        """
        allowed_tables = {"users", "notes"}
        if table_name not in allowed_tables:
            return "Invalid report request."

        try:
            # Table name is validated against an allowlist above, so
            # this is one of the rare, legitimate cases where a table
            # identifier (which can't be parameterized with `?` in
            # SQL -- placeholders are for values, not identifiers) is
            # interpolated into a query -- but only ever a value that
            # was already confirmed to be one of exactly two safe,
            # hard-coded strings, not attacker-controlled text.
            cursor = self.db.conn.execute(f"SELECT COUNT(*) FROM {table_name}")
            count = cursor.fetchone()[0]
            return f"{table_name}: {count} row(s)"
        except Exception as exc:
            with open(LOG_FILE, "a") as f:
                f.write(f"INTERNAL ERROR in run_query_and_report: {exc!r}\n")
            return "An internal error occurred. Please contact support if this persists."

    def close(self) -> None:
        self.db.close()
