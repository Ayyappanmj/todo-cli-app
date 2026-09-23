"""
log_analyzer.py  (ORIGINAL / UNOPTIMIZED VERSION)
---------------------------------------------------
A small analytics module for application log records: counts
activity per user, finds duplicate messages, flags users seen from
multiple IPs, extracts query durations, classifies messages, ranks
the most active users, builds a text summary report, and computes
word frequencies across all messages.

This is the BASELINE version, written the way a reasonable first pass
often looks: functionally correct, but with several patterns that
scale poorly as the log grows. Each one is flagged with a NOTE
comment; PERFORMANCE_REPORT.md documents the profiling evidence for
each and the fix applied in optimized/log_analyzer.py.
"""

from __future__ import annotations

import re
from typing import Dict, List, Tuple

from common.data_generator import LogRecord


class LogAnalyzer:
    def __init__(self, records: List[LogRecord]):
        self.records = records

    # ------------------------------------------------------------------
    def count_by_user(self) -> Dict[str, int]:
        """Return {username: number of log records for that user}."""
        counts: Dict[str, int] = {}
        for record in self.records:
            if record.user in counts:
                counts[record.user] += 1
            else:
                counts[record.user] = 1
        return counts

    # ------------------------------------------------------------------
    def find_duplicate_messages(self) -> List[str]:
        """Return the list of distinct message strings that occur more
        than once across all records.

        NOTE (performance): tracks "seen" messages in a plain list and
        checks membership with `in`, which is an O(n) scan on every
        call for a list of length up to n -- making this whole
        function O(n^2) overall.
        """
        seen: List[str] = []
        duplicates: List[str] = []
        for record in self.records:
            if record.message in seen:
                if record.message not in duplicates:
                    duplicates.append(record.message)
            else:
                seen.append(record.message)
        return duplicates

    # ------------------------------------------------------------------
    def find_users_with_multiple_ips(self) -> List[str]:
        """Return usernames that appear in the logs from more than one
        distinct IP address.

        NOTE (performance): compares every record to every other
        record with a nested loop (O(n^2)) to find same-user,
        different-IP pairs, instead of grouping IPs by user in a
        single pass.
        """
        flagged: List[str] = []
        for i in range(len(self.records)):
            for j in range(len(self.records)):
                if i == j:
                    continue
                a, b = self.records[i], self.records[j]
                if a.user == b.user and a.ip != b.ip:
                    if a.user not in flagged:
                        flagged.append(a.user)
        return flagged

    # ------------------------------------------------------------------
    def extract_query_durations(self) -> List[int]:
        """Return the list of millisecond durations found in messages
        that contain a 'duration=NNNms' fragment.

        NOTE (performance): the regex pattern is compiled fresh on
        every single call to this function's inner loop iteration,
        via re.search with a raw pattern string, instead of being
        compiled once and reused.
        """
        durations: List[int] = []
        for record in self.records:
            match = re.search(r"duration=(\d+)ms", record.message)
            if match:
                durations.append(int(match.group(1)))
        return durations

    # ------------------------------------------------------------------
    def classify_message(self, message: str) -> str:
        """Classify a single message string into a category.

        Deliberately does a bit of "work" (several regex checks) to
        stand in for realistic per-message processing (e.g. this
        might be a more expensive NLP or rule-engine call in a real
        system). Pure function of `message` alone.
        """
        if re.search(r"duration=(\d+)ms", message):
            duration = int(re.search(r"duration=(\d+)ms", message).group(1))
            if duration > 400:
                return "SLOW_OPERATION"
            return "TIMED_OPERATION"
        if re.search(r"status=(4\d\d|5\d\d)", message):
            return "ERROR_RESPONSE"
        if re.search(r"fail|invalid|exceed", message, re.IGNORECASE):
            return "WARNING_EVENT"
        return "NORMAL_EVENT"

    def category_counts(self) -> Dict[str, int]:
        """Return {category: count} across all records, using
        classify_message() on each record's message.

        NOTE (performance): classify_message() is a pure function of
        the message text, and log messages repeat heavily in
        practice (see data_generator.py's limited template/value
        pool) -- but this calls it fresh for every single record with
        no caching, redoing identical regex work over and over for
        messages it has already classified.
        """
        counts: Dict[str, int] = {}
        for record in self.records:
            category = self.classify_message(record.message)
            counts[category] = counts.get(category, 0) + 1
        return counts

    # ------------------------------------------------------------------
    def top_n_users_by_count(self, counts: Dict[str, int], n: int) -> List[Tuple[str, int]]:
        """Return the top `n` (username, count) pairs, highest first.

        NOTE (performance): sorts the ENTIRE counts dictionary by
        value (O(m log m), m = number of distinct users) just to keep
        the first n entries, even when n is much smaller than m.
        """
        sorted_items = sorted(counts.items(), key=lambda item: item[1], reverse=True)
        return sorted_items[:n]

    # ------------------------------------------------------------------
    def build_summary_report(self) -> str:
        """Build a human-readable multi-line text summary of the logs.

        NOTE (performance): builds the report by repeatedly
        concatenating onto a string with `+=` inside a loop. Since
        strings are immutable in Python, each `+=` allocates an
        entirely new string and copies everything seen so far into
        it, making this O(n^2) in the number of lines appended.
        """
        report = "LOG SUMMARY REPORT\n"
        report += "===================\n\n"

        counts = self.count_by_user()
        report += f"Total records: {len(self.records)}\n"
        report += f"Distinct users: {len(counts)}\n\n"

        report += "Per-user activity:\n"
        for user in sorted(counts):
            report += f"  {user}: {counts[user]} record(s)\n"

        duplicates = self.find_duplicate_messages()
        report += f"\nDuplicate messages found: {len(duplicates)}\n"
        for msg in sorted(duplicates):
            report += f"  - {msg}\n"

        return report

    # ------------------------------------------------------------------
    def word_frequency(self) -> Dict[str, int]:
        """Return {word: number of occurrences} across every message.

        NOTE (performance): first collects every word into one flat
        list, then for each *unique* word calls list.count() on that
        whole list to find its frequency. list.count() itself scans
        the entire list, so this is O(total_words * unique_words) --
        quadratic-ish in practice, versus a single linear pass.
        """
        all_words: List[str] = []
        for record in self.records:
            all_words.extend(record.message.lower().split())

        unique_words = []
        for word in all_words:
            if word not in unique_words:
                unique_words.append(word)

        freq: Dict[str, int] = {}
        for word in unique_words:
            freq[word] = all_words.count(word)
        return freq

    # ------------------------------------------------------------------
    def run_all(self) -> dict:
        """Run every analysis and return a single results dict.

        Used both as the "realistic full workload" for profiling, and
        by the equivalence tests to compare original vs. optimized
        output in one call.
        """
        counts = self.count_by_user()
        return {
            "counts_by_user": counts,
            "duplicate_messages": sorted(self.find_duplicate_messages()),
            "users_with_multiple_ips": sorted(self.find_users_with_multiple_ips()),
            "query_durations": self.extract_query_durations(),
            "category_counts": self.category_counts(),
            "top_10_users": self.top_n_users_by_count(counts, 10),
            "summary_report": self.build_summary_report(),
            "word_frequency": self.word_frequency(),
        }
