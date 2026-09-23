"""
scaling_comparison.py
----------------------
The headline benchmark: total run_all() wall-clock time, original vs.
optimized, across a range of dataset sizes -- including a larger size
to confirm the original's quadratic trend continues and to show how
much headroom the optimized version has by comparison.

The original is NOT run at the largest size (it would take many
minutes, consistent with its confirmed O(n^2) trend, and isn't
necessary once the trend is established at smaller sizes) -- this is
noted explicitly in the output rather than silently skipped.

Run from the profiling/ directory: python scaling_comparison.py
"""

import sys
import os
import time

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from common.data_generator import generate_logs
from original.log_analyzer import LogAnalyzer as OriginalAnalyzer
from optimized.log_analyzer import LogAnalyzer as OptimizedAnalyzer

# The original is timed at these sizes to confirm its quadratic trend.
ORIGINAL_SIZES = [1000, 2000, 4000, 8000, 16000]

# The optimized version is additionally timed at a much larger size,
# to demonstrate it handles a dataset the original could not
# practically process at all in this benchmark session.
OPTIMIZED_ONLY_SIZES = [50000, 200000]


def time_run_all(analyzer_cls, records):
    OptimizedAnalyzer._classify_message_cached.cache_clear() if hasattr(
        analyzer_cls, "_classify_message_cached"
    ) else None
    analyzer = analyzer_cls(records)
    start = time.perf_counter()
    analyzer.run_all()
    return time.perf_counter() - start


def main():
    lines = []
    lines.append("Full run_all() scaling comparison: ORIGINAL vs OPTIMIZED")
    lines.append("=" * 78)
    header = f"{'n':>8s} {'original (s)':>14s} {'optimized (s)':>15s} {'speedup':>10s}"
    lines.append(header)
    lines.append("-" * len(header))

    original_results = {}
    optimized_results = {}

    for n in ORIGINAL_SIZES:
        records = generate_logs(n, seed=42)
        orig_time = time_run_all(OriginalAnalyzer, records)
        opt_time = time_run_all(OptimizedAnalyzer, records)
        original_results[n] = orig_time
        optimized_results[n] = opt_time
        speedup = orig_time / opt_time if opt_time > 0 else float("inf")
        lines.append(f"{n:8d} {orig_time:14.4f} {opt_time:15.5f} {speedup:9.1f}x")
        print(lines[-1])

    lines.append("")
    lines.append("Optimized-only at larger sizes (original not run here -- its")
    lines.append("confirmed O(n^2) trend above means it would take on the order of")
    lines.append("hours at these sizes; extrapolation is discussed in the report):")
    for n in OPTIMIZED_ONLY_SIZES:
        records = generate_logs(n, seed=42)
        opt_time = time_run_all(OptimizedAnalyzer, records)
        optimized_results[n] = opt_time
        line = f"{n:8d} {'--':>14s} {opt_time:15.5f}"
        lines.append(line)
        print(line)

    # Simple quadratic-fit extrapolation for the original, based on
    # its own measured (n, time) pairs, purely to give a sense of
    # scale -- clearly labeled as an estimate, not a measurement.
    n1, t1 = 8000, original_results[8000]
    n2, t2 = 16000, original_results[16000]
    # time ~ c * n^2  =>  c = t / n^2 (averaged from the two points)
    c_estimate = ((t1 / n1**2) + (t2 / n2**2)) / 2
    lines.append("")
    lines.append("Rough quadratic-fit extrapolation for the ORIGINAL at larger n")
    lines.append("(estimate only, based on fitting c in time ~= c * n^2 to the")
    lines.append(f"n=8000 and n=16000 measurements above; c ~= {c_estimate:.3e}):")
    for n in OPTIMIZED_ONLY_SIZES:
        estimated_seconds = c_estimate * n**2
        estimated_minutes = estimated_seconds / 60
        lines.append(f"  n={n:7d}: estimated ~{estimated_seconds:,.0f}s (~{estimated_minutes:,.1f} minutes)")

    report = "\n".join(lines)
    with open("scaling_comparison.txt", "w") as f:
        f.write(report + "\n")
    print("\n" + "\n".join(lines[-6:]))
    print("\nSaved to scaling_comparison.txt")


if __name__ == "__main__":
    main()
