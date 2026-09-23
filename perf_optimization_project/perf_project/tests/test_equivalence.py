"""
test_equivalence.py
--------------------
The core correctness safeguard for this project: proves the
optimized LogAnalyzer produces EXACTLY the same output as the
original, unoptimized one, across several dataset sizes and for every
individual method as well as the combined run_all() result.

This is what makes it safe to say "the optimizations are pure
performance improvements" rather than "the optimizations changed
behavior along with speed" -- every test here would fail immediately
if a fix altered results, not just execution time.
"""

import sys
import os
import unittest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from common.data_generator import generate_logs
from original.log_analyzer import LogAnalyzer as OriginalAnalyzer
from optimized.log_analyzer import LogAnalyzer as OptimizedAnalyzer


class TestEquivalenceAcrossSizes(unittest.TestCase):
    """Runs the full comparison at several sizes, including small edge
    cases (0 and 1 records) where quadratic-vs-linear bugs are easy to
    introduce accidentally while optimizing (e.g. off-by-one errors)."""

    SIZES = [0, 1, 2, 50, 500, 2000]

    def test_run_all_matches_at_every_size(self):
        for n in self.SIZES:
            with self.subTest(n=n):
                records = generate_logs(n)
                original_result = OriginalAnalyzer(records).run_all()
                optimized_result = OptimizedAnalyzer(records).run_all()
                self.assertEqual(
                    original_result,
                    optimized_result,
                    f"Mismatch at n={n}",
                )


class TestEquivalencePerMethod(unittest.TestCase):
    """Same comparison, but isolating each method individually so a
    failure immediately identifies which specific optimization (if
    any) changed behavior, rather than just failing on the combined
    run_all() dict."""

    def setUp(self):
        self.records = generate_logs(1000)
        self.original = OriginalAnalyzer(self.records)
        self.optimized = OptimizedAnalyzer(self.records)

    def test_count_by_user(self):
        self.assertEqual(self.original.count_by_user(), self.optimized.count_by_user())

    def test_find_duplicate_messages(self):
        self.assertEqual(
            sorted(self.original.find_duplicate_messages()),
            sorted(self.optimized.find_duplicate_messages()),
        )

    def test_find_users_with_multiple_ips(self):
        self.assertEqual(
            sorted(self.original.find_users_with_multiple_ips()),
            sorted(self.optimized.find_users_with_multiple_ips()),
        )

    def test_extract_query_durations(self):
        self.assertEqual(
            self.original.extract_query_durations(),
            self.optimized.extract_query_durations(),
        )

    def test_classify_message_agrees_for_every_distinct_message(self):
        distinct_messages = {r.message for r in self.records}
        for msg in distinct_messages:
            with self.subTest(msg=msg):
                self.assertEqual(
                    self.original.classify_message(msg),
                    self.optimized.classify_message(msg),
                )

    def test_category_counts(self):
        self.assertEqual(self.original.category_counts(), self.optimized.category_counts())

    def test_top_n_users_by_count(self):
        counts = self.original.count_by_user()
        for n in (0, 1, 5, 10, 1000):
            with self.subTest(n=n):
                # Compare as sets of (user, count) pairs rather than
                # exact list order: when multiple users are tied on
                # count, a full sort and a partial-selection algorithm
                # (heapq.nlargest) are not guaranteed to break ties in
                # the same order, and that's fine -- "top N by count"
                # doesn't promise a specific tie-break rule.
                original_top = self.original.top_n_users_by_count(counts, n)
                optimized_top = self.optimized.top_n_users_by_count(counts, n)
                self.assertEqual(len(original_top), len(optimized_top))
                self.assertEqual(set(original_top), set(optimized_top))
                # Both must still be correctly sorted descending by count.
                self.assertEqual(
                    [c for _, c in original_top],
                    sorted((c for _, c in original_top), reverse=True),
                )
                self.assertEqual(
                    [c for _, c in optimized_top],
                    sorted((c for _, c in optimized_top), reverse=True),
                )

    def test_build_summary_report(self):
        self.assertEqual(
            self.original.build_summary_report(),
            self.optimized.build_summary_report(),
        )

    def test_word_frequency(self):
        self.assertEqual(self.original.word_frequency(), self.optimized.word_frequency())


class TestOptimizedCacheDoesNotLeakBetweenDifferentMessages(unittest.TestCase):
    """A targeted test for the lru_cache-based optimization
    specifically: confirms the cache is keyed correctly per distinct
    message and doesn't return a stale/wrong classification for a
    different message that happens to be processed afterward."""

    def test_different_messages_classified_independently(self):
        analyzer = OptimizedAnalyzer([])
        self.assertEqual(
            analyzer.classify_message("database query executed duration=999ms"),
            "SLOW_OPERATION",
        )
        self.assertEqual(
            analyzer.classify_message("database query executed duration=15ms"),
            "TIMED_OPERATION",
        )
        self.assertEqual(
            analyzer.classify_message("request completed with status=500"),
            "ERROR_RESPONSE",
        )
        self.assertEqual(
            analyzer.classify_message("user logged in successfully"),
            "NORMAL_EVENT",
        )
        # Re-check the first one again after the cache has other
        # entries in it, to confirm no cross-contamination.
        self.assertEqual(
            analyzer.classify_message("database query executed duration=999ms"),
            "SLOW_OPERATION",
        )


if __name__ == "__main__":
    unittest.main()
