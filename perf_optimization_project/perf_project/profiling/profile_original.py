"""
profile_original.py
--------------------
Profiles the ORIGINAL LogAnalyzer's run_all() using cProfile, and
saves both the raw pstats binary (for later programmatic inspection)
and a human-readable sorted text report.

Run from the profiling/ directory: python profile_original.py
"""

import cProfile
import io
import pstats
import sys
import os

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from common.data_generator import generate_logs
from original.log_analyzer import LogAnalyzer

DATASET_SIZE = 8000


def main():
    records = generate_logs(DATASET_SIZE, seed=42)
    analyzer = LogAnalyzer(records)

    profiler = cProfile.Profile()
    profiler.enable()
    result = analyzer.run_all()
    profiler.disable()

    # Save the raw stats for programmatic use (e.g. a future comparison script).
    profiler.dump_stats("original_profile.pstats")

    # Save a human-readable report sorted by cumulative time (the most
    # useful ordering for "which function is the actual bottleneck",
    # since it includes time spent in everything that function calls).
    buffer = io.StringIO()
    stats = pstats.Stats(profiler, stream=buffer)
    stats.sort_stats("cumulative")
    stats.print_stats(25)

    report = buffer.getvalue()
    with open("original_cprofile_report.txt", "w") as f:
        f.write(f"cProfile report -- ORIGINAL LogAnalyzer, dataset size = {DATASET_SIZE}\n")
        f.write("=" * 80 + "\n\n")
        f.write(report)

    print(report)
    print(f"\nDataset size: {DATASET_SIZE} records")
    print(f"Distinct users in results: {len(result['counts_by_user'])}")
    print("Full report saved to original_cprofile_report.txt")
    print("Raw pstats saved to original_profile.pstats")


if __name__ == "__main__":
    main()
