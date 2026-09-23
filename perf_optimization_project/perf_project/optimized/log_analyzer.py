"""
log_analyzer.py  (OPTIMIZED VERSION)
--------------------------------------
Same public API and identical output as original/log_analyzer.py
(verified by tests/test_equivalence.py), with every bottleneck
identified during profiling fixed. See PERFORMANCE_REPORT.md for the
full before/after profiling data behind each change; each fix below
is commented with which NOTE in the original it addresses.
"""

from __future__ import annotations

import heapq
import re
from collections import Counter
from functools import lru_cache
from typing import Dict, List, Tuple

from common.data_generator import LogRecord

# FIX for original's classify_message() re.search() calls, and
# extract_query_durations(): compiled ONCE at import time and reused,
# instead of being implicitly re-parsed by the `re` module's pattern
# cache pressure across many distinct call sites and repeated
# re.search(pattern_string, ...) calls with a fresh pattern string
# each time.
_DURATION_RE = re.compile(r"duration=(\d+)ms")
_STATUS_RE = re.compile(r"status=(4\d\d|5\d\d)")
_WARNING_RE = re.compile(r"fail|invalid|exceed", re.IGNORECASE)


class LogAnalyzer:
    def __init__(self, records: List[LogRecord]):
        self.records = records

    # ------------------------------------------------------------------
    def count_by_user(self) -> Dict[str, int]:
        """Return {username: number of log records for that user}.

        Unchanged from the original -- this was already an O(n)
        single pass using dict lookups, and wasn't a profiling
        hotspot, so it's left as-is (see PERFORMANCE_REPORT.md
        Section 4 on avoiding unnecessary changes).
        """
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

        FIX (was O(n^2)): uses collections.Counter to tally every
        message in a single O(n) pass, then filters for counts > 1.
        Membership/counting against a Counter (backed by a hash
        table) is O(1) average case, versus O(n) for a growing list.
        """
        message_counts = Counter(record.message for record in self.records)
        return [message for message, count in message_counts.items() if count > 1]

    # ------------------------------------------------------------------
    def find_users_with_multiple_ips(self) -> List[str]:
        """Return usernames that appear in the logs from more than one
        distinct IP address.

        FIX (was O(n^2)): groups IPs by user in a single O(n) pass
        using a dict of sets, then checks which users have more than
        one distinct IP -- no pairwise comparison needed at all.
        """
        ips_by_user: Dict[str, set] = {}
        for record in self.records:
            ips_by_user.setdefault(record.user, set()).add(record.ip)
        return [user for user, ips in ips_by_user.items() if len(ips) > 1]

    # ------------------------------------------------------------------
    def extract_query_durations(self) -> List[int]:
        """Return the list of millisecond durations found in messages
        that contain a 'duration=NNNms' fragment.

        FIX (was recompiling per call): uses the module-level
        precompiled _DURATION_RE instead of a fresh pattern.
        """
        durations: List[int] = []
        for record in self.records:
            match = _DURATION_RE.search(record.message)
            if match:
                durations.append(int(match.group(1)))
        return durations

    # ------------------------------------------------------------------
    @staticmethod
    @lru_cache(maxsize=4096)
    def _classify_message_cached(message: str) -> str:
        """The actual classification logic, memoized.

        FIX (was recomputed on every call): classify_message() is a
        pure function of `message` alone, and real log messages
        repeat heavily (see data_generator.py). @lru_cache means each
        distinct message string is classified once; every repeat
        occurrence after that is an O(1) cache lookup instead of
        redoing three regex searches from scratch.

        Implemented as a @staticmethod so lru_cache's cache key is
        just the message string, not (self, message) -- keying on
        `self` would create a separate cache per LogAnalyzer instance
        and defeat the point, and would also keep every past instance
        alive as long as the cache holds a reference to it.
        """
        duration_match = _DURATION_RE.search(message)
        if duration_match:
            duration = int(duration_match.group(1))
            if duration > 400:
                return "SLOW_OPERATION"
            return "TIMED_OPERATION"
        if _STATUS_RE.search(message):
            return "ERROR_RESPONSE"
        if _WARNING_RE.search(message):
            return "WARNING_EVENT"
        return "NORMAL_EVENT"

    def classify_message(self, message: str) -> str:
        """Public wrapper kept for API compatibility with the original."""
        return self._classify_message_cached(message)

    def category_counts(self) -> Dict[str, int]:
        """Return {category: count} across all records.

        Benefits automatically from classify_message()'s caching
        above -- no change needed to this method itself.
        """
        counts: Dict[str, int] = {}
        for record in self.records:
            category = self.classify_message(record.message)
            counts[category] = counts.get(category, 0) + 1
        return counts

    # ------------------------------------------------------------------
    def top_n_users_by_count(self, counts: Dict[str, int], n: int) -> List[Tuple[str, int]]:
        """Return the top `n` (username, count) pairs, highest first.

        FIX (was a full O(m log m) sort): uses heapq.nlargest, which
        is O(m log n) -- a real win whenever n is much smaller than
        the number of distinct users m, since it never needs to fully
        order the entries it's not going to return.
        """
        return heapq.nlargest(n, counts.items(), key=lambda item: item[1])

    # ------------------------------------------------------------------
    def build_summary_report(self) -> str:
        """Build a human-readable multi-line text summary of the logs.

        FIX (was O(n^2) via string +=): accumulates every line in a
        list and joins once at the end. list.append() is O(1)
        amortized, and a single str.join() over the whole list is
        O(total length) -- versus reallocating and copying a growing
        string on every single append.
        """
        lines: List[str] = []
        lines.append("LOG SUMMARY REPORT")
        lines.append("===================")
        lines.append("")

        counts = self.count_by_user()
        lines.append(f"Total records: {len(self.records)}")
        lines.append(f"Distinct users: {len(counts)}")
        lines.append("")

        lines.append("Per-user activity:")
        for user in sorted(counts):
            lines.append(f"  {user}: {counts[user]} record(s)")

        duplicates = self.find_duplicate_messages()
        lines.append("")
        lines.append(f"Duplicate messages found: {len(duplicates)}")
        for msg in sorted(duplicates):
            lines.append(f"  - {msg}")

        return "\n".join(lines) + "\n"

    # ------------------------------------------------------------------
    def word_frequency(self) -> Dict[str, int]:
        """Return {word: number of occurrences} across every message.

        FIX (was O(total_words * unique_words) via list.count()):
        collections.Counter tallies every word in a single O(total_words)
        pass using hash-table increments, instead of scanning the
        entire word list once per unique word.
        """
        all_words: List[str] = []
        for record in self.records:
            all_words.extend(record.message.lower().split())
        return dict(Counter(all_words))

    # ------------------------------------------------------------------
    def run_all(self) -> dict:
        """Run every analysis and return a single results dict.
        Identical shape/contents to the original's run_all()."""
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
