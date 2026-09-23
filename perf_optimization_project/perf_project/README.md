# LogAnalyzer — Performance Optimization Project

`LogAnalyzer` is a Python application-log analytics module. This
project contains its **original (unoptimized)** implementation, an
**optimized** implementation with identical behavior, the profiling
data behind every optimization decision, and the automated tests
proving both versions produce the same results.

See **[`PERFORMANCE_REPORT.md`](PERFORMANCE_REPORT.md)** for the full
write-up: baseline profiling, bottleneck identification, every
optimization applied and why, and before/after benchmarks
(**~206x** faster at 8,000 records, **~913x** at 16,000, and the gap
keeps growing with data size).

## What's in this repository

```
perf_project/
├── common/
│   └── data_generator.py       # deterministic synthetic log dataset (no external files needed)
├── original/
│   └── log_analyzer.py         # baseline implementation, with NOTE comments marking each bottleneck
├── optimized/
│   └── log_analyzer.py         # optimized implementation, with FIX comments marking each change
├── tests/
│   └── test_equivalence.py     # 11 tests proving original and optimized produce identical output
├── profiling/
│   ├── profile_original.py         # cProfile run on the original
│   ├── profile_optimized.py        # cProfile run on the optimized version
│   ├── timeit_benchmark.py         # per-method isolated timeit benchmarks across sizes
│   ├── scaling_comparison.py       # full run_all() timing comparison across sizes
│   ├── original_cprofile_report.txt   # saved output of the above
│   ├── optimized_cprofile_report.txt
│   ├── timeit_results.txt
│   ├── scaling_comparison.txt
│   ├── original_profile.pstats      # raw cProfile stats (for pstats.Stats() / snakeviz, etc.)
│   └── optimized_profile.pstats
├── PERFORMANCE_REPORT.md       # the full report — read this for the analysis
└── README.md                   # you are here
```

## Requirements

Python 3.8 or later. No third-party packages required — everything
uses only the standard library (`cProfile`, `pstats`, `timeit`,
`unittest`, `collections`, `functools`, `heapq`, `re`).

## Running the tests

```bash
cd perf_project
python -m unittest discover -s tests -v
```

Expected output: `Ran 11 tests ... OK` — confirms the optimized
version's output is identical to the original's.

## Reproducing the profiling and benchmarks

All scripts generate their own input data (deterministically, via
`common/data_generator.py`) — nothing else needs to be provided.

```bash
cd perf_project/profiling

python profile_original.py       # ~5 seconds; saves original_cprofile_report.txt + .pstats
python profile_optimized.py      # <1 second; saves optimized_cprofile_report.txt + .pstats
python timeit_benchmark.py       # ~1-2 minutes; per-method scaling curves, saves timeit_results.txt
python scaling_comparison.py     # ~25 seconds; full-workload comparison, saves scaling_comparison.txt
```

To inspect a saved `.pstats` file interactively:

```python
import pstats
stats = pstats.Stats("original_profile.pstats")
stats.sort_stats("cumulative").print_stats(15)
```

## Quick usage example

```python
from common.data_generator import generate_logs
from optimized.log_analyzer import LogAnalyzer

records = generate_logs(5000)          # deterministic synthetic dataset
analyzer = LogAnalyzer(records)
results = analyzer.run_all()

print(results["summary_report"])
print("Top 5 users:", results["top_10_users"][:5])
```

## The short version

One function, `find_users_with_multiple_ips`, was responsible for
**97.4% of total runtime** due to an O(n^2) nested-loop algorithm.
Replacing it with a single-pass dict-of-sets approach -- plus six
smaller fixes (memoization, correct data structures, efficient string
building, and precompiled regex) found via per-function isolated
profiling -- brought an 8,000-record workload from **4.543s down to
0.022s**, with every optimization verified to produce byte-for-byte
identical output via 11 automated regression tests. See
[`PERFORMANCE_REPORT.md`](PERFORMANCE_REPORT.md) for the complete
analysis.
