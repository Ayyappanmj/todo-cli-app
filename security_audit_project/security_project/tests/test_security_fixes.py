"""
test_security_fixes.py
-------------------------
Automated tests verifying (a) every vulnerability fix actually holds,
programmatically, and (b) core application functionality still works
correctly after hardening -- a security fix that breaks the app isn't
a fix that should ship.
"""

import os
import sys
import time
import unittest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from secure_app.vault_cli import (
    VaultApp,
    generate_encryption_key,
    hash_password,
    verify_password,
    ValidationError,
    SecurityError,
)


class SecureVaultTestCase(unittest.TestCase):
    """Base class: fresh throwaway DB + encryption key per test."""

    def setUp(self):
        self.db_path = f"test_vault_{id(self)}.db"
        self._cleanup()
        self.app = VaultApp(self.db_path, encryption_key=generate_encryption_key())

    def tearDown(self):
        self.app.close()
        self._cleanup()

    def _cleanup(self):
        for f in (self.db_path, "vault_activity.log"):
            if os.path.exists(f):
                os.remove(f)


# ---------------------------------------------------------------------
# Core functionality still works (a security fix must not break the app)
# ---------------------------------------------------------------------
class TestFunctionalityPreserved(SecureVaultTestCase):
    def test_register_and_login(self):
        uid = self.app.register("alice", "correct-horse-battery")
        self.assertIsInstance(uid, int)
        self.assertEqual(self.app.login("alice", "correct-horse-battery"), uid)

    def test_wrong_password_rejected(self):
        self.app.register("alice", "correct-horse-battery")
        self.assertIsNone(self.app.login("alice", "wrong-password"))

    def test_add_and_search_notes(self):
        uid = self.app.register("alice", "correct-horse-battery")
        self.app.add_note(uid, "Groceries", "milk, eggs, bread")
        results = self.app.search_notes(uid, "Groceries")
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0].content, "milk, eggs, bread")

    def test_export_and_json_roundtrip(self):
        uid = self.app.register("alice", "correct-horse-battery")
        self.app.add_note(uid, "Note A", "content A")
        self.app.add_note(uid, "Note B", "content B")

        backup_path = self.app.export_notes_json(uid, "my_backup.json")
        self.assertTrue(os.path.exists(backup_path))

        # Import into a second, empty vault and confirm the notes arrive intact.
        other_db = f"test_vault_import_{id(self)}.db"
        if os.path.exists(other_db):
            os.remove(other_db)
        other_app = VaultApp(other_db, encryption_key=generate_encryption_key())
        try:
            other_uid = other_app.register("bob", "another-good-password")
            count = other_app.import_notes_json(backup_path)
            self.assertEqual(count, 2)
        finally:
            other_app.close()
            if os.path.exists(other_db):
                os.remove(other_db)
            if os.path.exists(backup_path):
                os.remove(backup_path)
            if os.path.isdir("exports") and not os.listdir("exports"):
                os.rmdir("exports")


# ---------------------------------------------------------------------
# VULN-01 / VULN-02: password hashing
# ---------------------------------------------------------------------
class TestPasswordHashing(unittest.TestCase):
    def test_hash_is_not_the_plaintext_password(self):
        h = hash_password("correct-horse-battery")
        self.assertNotIn("correct-horse-battery", h)

    def test_same_password_hashed_twice_gives_different_output(self):
        # Different random salts each time -> different stored hash,
        # even for the identical password.
        h1 = hash_password("same-password")
        h2 = hash_password("same-password")
        self.assertNotEqual(h1, h2)

    def test_verify_password_accepts_correct_password(self):
        h = hash_password("my-real-password")
        self.assertTrue(verify_password("my-real-password", h))

    def test_verify_password_rejects_wrong_password(self):
        h = hash_password("my-real-password")
        self.assertFalse(verify_password("guessed-password", h))

    def test_verify_password_handles_garbage_hash_safely(self):
        # Must not raise on a malformed stored value -- fail closed.
        self.assertFalse(verify_password("anything", "not-a-real-hash"))


# ---------------------------------------------------------------------
# VULN-05: encryption at rest
# ---------------------------------------------------------------------
class TestEncryptionAtRest(SecureVaultTestCase):
    def test_note_content_is_encrypted_in_the_database_file(self):
        import sqlite3

        uid = self.app.register("alice", "correct-horse-battery")
        self.app.add_note(uid, "Secret", "my SSN is 123-45-6789")

        # Bypass the application entirely and read the raw DB file,
        # the way an attacker who stole the .db file would.
        raw_conn = sqlite3.connect(self.db_path)
        row = raw_conn.execute("SELECT content_encrypted FROM notes").fetchone()
        raw_conn.close()

        raw_bytes = row[0]
        self.assertNotIn(b"123-45-6789", raw_bytes)
        self.assertNotIn(b"SSN", raw_bytes)

    def test_wrong_key_cannot_decrypt(self):
        uid = self.app.register("alice", "correct-horse-battery")
        self.app.add_note(uid, "Secret", "sensitive content")

        wrong_key_app = VaultApp(self.db_path, encryption_key=generate_encryption_key())
        try:
            results = wrong_key_app.search_notes(uid, "Secret")
            # Should fail safe (a placeholder string), never raise AND
            # never return the real plaintext with the wrong key.
            self.assertEqual(len(results), 1)
            self.assertNotEqual(results[0].content, "sensitive content")
        finally:
            wrong_key_app.close()


# ---------------------------------------------------------------------
# VULN-02/03/04: SQL injection
# ---------------------------------------------------------------------
class TestSQLInjectionFixed(SecureVaultTestCase):
    def test_injection_in_username_does_not_bypass_login(self):
        alice_id = self.app.register("alice", "correct-horse-battery")
        with self.assertRaises(ValidationError):
            self.app.login("alice' --", "anything")
        # Confirm alice's real account is untouched and still requires
        # the real password.
        self.assertEqual(self.app.login("alice", "correct-horse-battery"), alice_id)

    def test_injection_in_search_keyword_does_not_leak_other_users_notes(self):
        alice_id = self.app.register("alice", "correct-horse-battery")
        bob_id = self.app.register("bob", "another-real-password")
        self.app.add_note(bob_id, "Private", "bob's secret")

        malicious_keyword = "' UNION SELECT id, 0, username, password_hash FROM users --"
        results = self.app.search_notes(alice_id, malicious_keyword)
        self.assertEqual(results, [])

    def test_special_characters_in_note_title_are_stored_literally(self):
        # A quote character in legitimate data should just work, not
        # be rejected or break anything -- proof the fix is real
        # parameterization, not a naive "reject quote characters" filter.
        uid = self.app.register("alice", "correct-horse-battery")
        self.app.add_note(uid, "It's a test", "content with a ' quote too")
        results = self.app.search_notes(uid, "It's")
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0].title, "It's a test")


# ---------------------------------------------------------------------
# VULN-06: hard-coded backdoor removed
# ---------------------------------------------------------------------
class TestBackdoorRemoved(SecureVaultTestCase):
    def test_former_backdoor_password_grants_no_access(self):
        self.app.register("alice", "correct-horse-battery")
        # The original backdoor password; must not log in as anyone.
        result = self.app.login("alice", "letmein123")
        self.assertIsNone(result)

    def test_no_hardcoded_credential_constant_exists(self):
        import secure_app.vault_cli as secure_module

        self.assertFalse(hasattr(secure_module, "ADMIN_BACKDOOR_PASSWORD"))


# ---------------------------------------------------------------------
# VULN-07: passwords no longer logged
# ---------------------------------------------------------------------
class TestLoggingDoesNotLeakPasswords(SecureVaultTestCase):
    def test_password_never_appears_in_log_file(self):
        self.app.register("alice", "super-secret-password-123")
        self.app.login("alice", "super-secret-password-123")
        self.app.login("alice", "wrong-guess-password-456")

        with open("vault_activity.log") as f:
            log_contents = f.read()

        self.assertNotIn("super-secret-password-123", log_contents)
        self.assertNotIn("wrong-guess-password-456", log_contents)
        # Username (non-secret, useful for monitoring) SHOULD still be there.
        self.assertIn("alice", log_contents)


# ---------------------------------------------------------------------
# VULN-08: reset tokens
# ---------------------------------------------------------------------
class TestResetTokenStrength(SecureVaultTestCase):
    def test_token_not_predictable_via_random_seed(self):
        import random

        random.seed(42)
        t1 = self.app.generate_password_reset_token()
        random.seed(42)
        t2 = self.app.generate_password_reset_token()
        self.assertNotEqual(t1, t2)

    def test_token_has_high_entropy_length(self):
        token = self.app.generate_password_reset_token()
        # 32 raw bytes, URL-safe base64 encoded -> at least 43 chars.
        self.assertGreaterEqual(len(token), 40)

    def test_many_tokens_are_all_unique(self):
        tokens = {self.app.generate_password_reset_token() for _ in range(1000)}
        self.assertEqual(len(tokens), 1000)


# ---------------------------------------------------------------------
# VULN-09: path traversal
# ---------------------------------------------------------------------
class TestPathTraversalFixed(SecureVaultTestCase):
    def test_directory_traversal_filename_rejected_or_contained(self):
        uid = self.app.register("carol", "carol-password-123")
        self.app.add_note(uid, "Note", "content")

        marker = os.path.abspath("PROOF_OF_ESCAPE.txt")
        if os.path.exists(marker):
            os.remove(marker)

        try:
            self.app.export_notes(uid, "../PROOF_OF_ESCAPE.txt")
        except ValidationError:
            pass  # also an acceptable outcome

        self.assertFalse(os.path.exists(marker))

        if os.path.isdir("exports"):
            for f in os.listdir("exports"):
                os.remove(os.path.join("exports", f))
            os.rmdir("exports")

    def test_legitimate_filename_still_works(self):
        uid = self.app.register("carol", "carol-password-123")
        self.app.add_note(uid, "Note", "content")
        path = self.app.export_notes(uid, "my_export.txt")
        self.assertTrue(os.path.exists(path))
        self.assertTrue(path.endswith("my_export.txt"))
        os.remove(path)
        if os.path.isdir("exports") and not os.listdir("exports"):
            os.rmdir("exports")


# ---------------------------------------------------------------------
# VULN-10: insecure deserialization
# ---------------------------------------------------------------------
class TestInsecureDeserializationFixed(unittest.TestCase):
    def test_no_pickle_based_import_method_exists(self):
        import secure_app.vault_cli as secure_module

        self.assertFalse(hasattr(secure_module.VaultApp, "import_notes"))

    def test_pickle_is_not_imported_by_the_secure_module(self):
        import secure_app.vault_cli as secure_module

        self.assertNotIn("pickle", dir(secure_module))


# ---------------------------------------------------------------------
# VULN-11: verbose error messages
# ---------------------------------------------------------------------
class TestErrorMessagesAreGeneric(SecureVaultTestCase):
    def test_invalid_table_report_gives_generic_message(self):
        result = self.app.run_query_and_report("nonexistent_table; DROP TABLE users; --")
        self.assertNotIn("Traceback", result)
        self.assertNotIn("sqlite3", result.lower())
        self.assertEqual(result, "Invalid report request.")

    def test_valid_table_report_works_normally(self):
        result = self.app.run_query_and_report("users")
        self.assertIn("users", result)
        self.assertIn("row(s)", result)


# ---------------------------------------------------------------------
# Brute-force / account lockout (defense-in-depth addition)
# ---------------------------------------------------------------------
class TestAccountLockout(SecureVaultTestCase):
    def test_account_locks_after_repeated_failures(self):
        self.app.register("alice", "correct-horse-battery")
        for _ in range(5):
            self.app.login("alice", "wrong-password")

        with self.assertRaises(SecurityError):
            self.app.login("alice", "correct-horse-battery")

    def test_successful_login_resets_failure_count(self):
        self.app.register("alice", "correct-horse-battery")
        for _ in range(3):
            self.app.login("alice", "wrong-password")
        # A successful login before hitting the lockout threshold
        # should reset the counter.
        self.assertIsNotNone(self.app.login("alice", "correct-horse-battery"))
        for _ in range(3):
            self.app.login("alice", "wrong-password")
        # Still under the threshold again since the counter was reset.
        self.assertIsNotNone(self.app.login("alice", "correct-horse-battery"))


# ---------------------------------------------------------------------
# Input validation
# ---------------------------------------------------------------------
class TestInputValidation(SecureVaultTestCase):
    def test_short_password_rejected(self):
        with self.assertRaises(ValidationError):
            self.app.register("dave", "short")

    def test_invalid_username_characters_rejected(self):
        with self.assertRaises(ValidationError):
            self.app.register("dave; DROP TABLE users;", "a-fine-password")

    def test_empty_note_content_rejected(self):
        uid = self.app.register("dave", "a-fine-password")
        with self.assertRaises(ValidationError):
            self.app.add_note(uid, "Title", "")

    def test_duplicate_username_rejected(self):
        self.app.register("dave", "a-fine-password-1")
        with self.assertRaises(ValidationError):
            self.app.register("dave", "a-different-password-2")


if __name__ == "__main__":
    unittest.main()
