"""
timeit_benchmark.py
--------------------
cProfile on run_all() shows the aggregate call graph for one dataset
size, but when one function (find_users_with_multiple_ips) dominates
so heavily, it masks how the OTHER functions individually scale.

This script isolates each method with timeit across several dataset
sizes, for both the original and optimized LogAnalyzer, to show each
bottleneck's own growth curve (quadratic vs. linear) independent of
what else is running -- this is the evidence for why every
identified issue was fixed, not just the single largest one in a
single aggregate profile.

Run from the profiling/ directory: python timeit_benchmark.py
(Takes roughly 1-2 minutes -- it deliberately re-runs the O(n^2)
original methods at increasing sizes to plot their curve.)
"""

import sys
import os
import timeit

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from common.data_generator import generate_logs
from original.log_analyzer import LogAnalyzer as OriginalAnalyzer
from optimized.log_analyzer import LogAnalyzer as OptimizedAnalyzer

SIZES = [1000, 2000, 4000, 8000]

METHODS = [
    "find_duplicate_messages",
    "find_users_with_multiple_ips",
    "extract_query_durations",
    "category_counts",
    "word_frequency",
    "build_summary_report",
]


def time_method(analyzer_cls, method_name, records, repeats=3):
    """Time one method call, taking the best of `repeats` runs (the
    standard timeit recommendation -- minimum, not average, since
    system noise only ever slows a run down, never speeds it up).

    IMPORTANT for fairness: the optimized analyzer's classify_message()
    uses an lru_cache that is shared across ALL instances (it's cached
    on the underlying function, not per-instance). If left warm across
    repeats, later repeats of category_counts() would benefit from
    cache entries populated by earlier repeats, making the reported
    "best of 3" number reflect a warm cache rather than the real
    per-call cost. To measure the honest, comparable-to-original cost,
    the cache is explicitly cleared before EVERY repeat here. The
    separate warm-cache benefit (which is real and matters in a
    long-running application) is measured on its own in
    demonstrate_warm_cache_benefit() below.
    """
    times = []
    for _ in range(repeats):
        if hasattr(OptimizedAnalyzer, "_classify_message_cached"):
            OptimizedAnalyzer._classify_message_cached.cache_clear()
        analyzer = analyzer_cls(records)
        method = getattr(analyzer, method_name)
        start = timeit.default_timer()
        method()
        elapsed = timeit.default_timer() - start
        times.append(elapsed)
    return min(times)


def demonstrate_warm_cache_benefit(n=8000, repeats=5):
    """A separate, honest demonstration of the OTHER real benefit of
    lru_cache: in a long-running application, the cache stays warm
    across many calls (e.g. repeated report generation), not just
    within a single call. This measures that directly: first call
    (cold) vs. every subsequent call (warm), on the SAME data.
    """
    records = generate_logs(n, seed=42)
    OptimizedAnalyzer._classify_message_cached.cache_clear()
    analyzer = OptimizedAnalyzer(records)

    lines = ["", "--- Warm-cache benefit (optimized only, same data, repeated calls) ---"]
    for i in range(repeats):
        start = timeit.default_timer()
        analyzer.category_counts()
        elapsed = timeit.default_timer() - start
        label = "cold cache" if i == 0 else f"warm cache (call #{i + 1})"
        lines.append(f"  category_counts() call {i + 1} [{label}]: {elapsed:.6f}s")

    info = OptimizedAnalyzer._classify_message_cached.cache_info()
    lines.append(f"  Final cache_info(): {info}")
    return "\n".join(lines)


def main():
    results = {}  # {method_name: {"original": {n: t}, "optimized": {n: t}}}
    for method_name in METHODS:
        results[method_name] = {"original": {}, "optimized": {}}

    lines = []
    lines.append("timeit benchmark -- each method run in isolation, best-of-3")
    lines.append("=" * 78)
    lines.append("")

    for n in SIZES:
        records = generate_logs(n, seed=42)
        lines.append(f"--- Dataset size n={n} ---")
        header = f"{'method':32s} {'original (s)':>14s} {'optimized (s)':>15s} {'speedup':>10s}"
        lines.append(header)
        lines.append("-" * len(header))

        for method_name in METHODS:
            # Fresh analyzer instances each time so the optimized
            # version's lru_cache doesn't carry warm state between
            # timed methods/sizes in a way that would misrepresent a
            # cold-cache first run.
            orig_time = time_method(OriginalAnalyzer, method_name, records)
            opt_time = time_method(OptimizedAnalyzer, method_name, records)
            speedup = orig_time / opt_time if opt_time > 0 else float("inf")

            results[method_name]["original"][n] = orig_time
            results[method_name]["optimized"][n] = opt_time

            lines.append(
                f"{method_name:32s} {orig_time:14.5f} {opt_time:15.5f} {speedup:9.1f}x"
            )
        lines.append("")

    report = "\n".join(lines)
    warm_cache_report = demonstrate_warm_cache_benefit()
    report = report + "\n" + warm_cache_report + "\n"

    print(report)
    with open("timeit_results.txt", "w") as f:
        f.write(report)
    print("\nSaved to timeit_results.txt")


if __name__ == "__main__":
    main()
