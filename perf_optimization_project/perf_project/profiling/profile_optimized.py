"""
profile_optimized.py
---------------------
Profiles the OPTIMIZED LogAnalyzer's run_all() using cProfile, at the
SAME dataset size and seed as profile_original.py, for a direct
apples-to-apples comparison.

Run from the profiling/ directory: python profile_optimized.py
"""

import cProfile
import io
import pstats
import sys
import os

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from common.data_generator import generate_logs
from optimized.log_analyzer import LogAnalyzer

DATASET_SIZE = 8000


def main():
    records = generate_logs(DATASET_SIZE, seed=42)
    analyzer = LogAnalyzer(records)

    # Ensure a cold cache, for a fair comparison against the
    # original's necessarily-cold-every-time classify_message().
    LogAnalyzer._classify_message_cached.cache_clear()

    profiler = cProfile.Profile()
    profiler.enable()
    result = analyzer.run_all()
    profiler.disable()

    profiler.dump_stats("optimized_profile.pstats")

    buffer = io.StringIO()
    stats = pstats.Stats(profiler, stream=buffer)
    stats.sort_stats("cumulative")
    stats.print_stats(25)

    report = buffer.getvalue()
    with open("optimized_cprofile_report.txt", "w") as f:
        f.write(f"cProfile report -- OPTIMIZED LogAnalyzer, dataset size = {DATASET_SIZE}\n")
        f.write("=" * 80 + "\n\n")
        f.write(report)

    print(report)
    print(f"\nDataset size: {DATASET_SIZE} records")
    print(f"Distinct users in results: {len(result['counts_by_user'])}")
    print("Full report saved to optimized_cprofile_report.txt")
    print("Raw pstats saved to optimized_profile.pstats")


if __name__ == "__main__":
    main()
