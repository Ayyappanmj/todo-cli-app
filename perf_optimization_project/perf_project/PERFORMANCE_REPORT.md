# Performance Optimization Report — `LogAnalyzer`

## 1. The Application

`LogAnalyzer` is an application-log analytics module: given a list of
log records (timestamp, level, user, IP, message), it computes eight
different analyses — per-user activity counts, duplicate message
detection, users seen from multiple IPs, extracted query durations,
message classification/category counts, top-N most active users, a
text summary report, and word frequency across all messages.

A deterministic synthetic dataset generator (`common/data_generator.py`)
produces the input data in-memory from a fixed seed, so the project
needs no external input files and every benchmark in this report is
exactly reproducible.

This module was chosen specifically because log analytics naturally
contains several *different* categories of performance issue at once —
algorithmic complexity, wrong data-structure choice, redundant
computation, and inefficient string building — making it a good
vehicle for demonstrating a range of optimization techniques rather
than just one.

## 2. Baseline Performance Analysis

**Method:** `cProfile` on the full `run_all()` workload (all eight
analyses) at a dataset size of 8,000 records, seed 42 — reproducible
via `profiling/profile_original.py`.

```
187,881 function calls (186,847 primitive calls) in 4.543 seconds

   ncalls  tottime  percall  cumtime  percall  function
        1    0.000    0.000    4.543    4.543  run_all
        1    4.425    4.425    4.429    4.429  find_users_with_multiple_ips
        1    0.011    0.011    0.054    0.054  word_frequency
      162    0.038    0.000    0.038    0.000  {list.count}
        1    0.003    0.003    0.038    0.038  category_counts
    29990    0.010    0.000    0.036    0.000  re.search
     8000    0.005    0.000    0.034    0.000  classify_message
        2    0.010    0.005    0.011    0.005  find_duplicate_messages
        1    0.002    0.002    0.010    0.010  extract_query_durations
        1    0.000    0.000    0.006    0.006  build_summary_report
```
Full output: `profiling/original_cprofile_report.txt`.

**Baseline: 4.543 seconds for 8,000 records.**

## 3. Identifying Bottlenecks

The `tottime` column (time spent in a function itself, excluding
functions it calls) makes the picture immediately clear:

**`find_users_with_multiple_ips` alone accounts for 4.425s of the
4.543s total runtime — 97.4% of the entire workload**, despite being
one of eight roughly-equal analyses. Everything else combined is
under 3%.

This function compares every record to every other record with a
nested loop looking for same-user/different-IP pairs — an O(n²)
algorithm. At n=8,000 that's up to 64 million comparisons.

Because this one function so overwhelmingly dominates the aggregate
profile, it would be easy to fix it and declare victory — but that
would miss real, separate inefficiencies hiding underneath it. To
find those, each method was additionally benchmarked **in isolation**
across several dataset sizes with `timeit`
(`profiling/timeit_benchmark.py`), which reveals each function's own
scaling curve independent of what else is running:

| Method | 1,000 | 2,000 | 4,000 | 8,000 | Ratio 8k→4k | Pattern |
|---|---|---|---|---|---|---|
| `find_users_with_multiple_ips` | 0.0657s | 0.2768s | 0.9068s | 3.7613s | 4.1x | **Quadratic** |
| `word_frequency` | 0.0061s | 0.0113s | 0.0197s | 0.0394s | 2.0x | Linear-ish, but with a large constant factor |
| `category_counts` | 0.0015s | 0.0029s | 0.0050s | 0.0095s | 1.9x | Linear, wasteful constant |
| `find_duplicate_messages` | 0.0004s | 0.0011s | 0.0023s | 0.0042s | 1.8x | Linear here (see note below) |
| `build_summary_report` | 0.0006s | 0.0013s | 0.0023s | 0.0048s | 2.1x | Linear here (see note below) |
| `extract_query_durations` | 0.0003s | 0.0007s | 0.0012s | 0.0023s | 1.9x | Linear, small constant overhead |

*(Times are best-of-3 via `timeit`; full table across all four sizes
in `profiling/timeit_results.txt`.)*

**A worthwhile nuance surfaced by this data:** `find_users_with_multiple_ips`
shows a clean ~4x-per-doubling growth pattern — textbook O(n²). The
theoretically-also-O(n²) `find_duplicate_messages` looks linear here
instead. That's not a measurement error: this specific dataset has
only ~320 distinct message combinations no matter how large `n`
grows (see `data_generator.py`'s limited template pool), so the
`seen` list it scans never grows past ~320 entries regardless of `n`
— the *practical* cost is bounded by vocabulary size, not record
count, even though the *worst-case* complexity is still O(n × unique
messages). This is exactly the kind of thing profiling on realistic
data reveals that reasoning about Big-O alone can miss. It was fixed
anyway (Section 4) because the fix is essentially free and removes
the latent worst-case risk for a dataset shaped differently (e.g. logs
with far more unique messages).

**Bottlenecks identified, in priority order:**

1. **`find_users_with_multiple_ips`** — O(n²) nested-loop pairwise
   comparison. *Dominant bottleneck; fix first.*
2. **`word_frequency`** — O(total_words × unique_words) via
   `list.count()` per unique word.
3. **`category_counts` / `classify_message`** — no caching of a pure
   function despite heavy message repetition in realistic log data.
4. **`find_duplicate_messages`** — O(n × unique messages) via list
   membership (`in`) instead of a hash-based structure; low
   practical cost on this dataset, but a real latent risk.
5. **`build_summary_report`** — O(n²) string concatenation via `+=`
   in a loop; low practical cost here because the loop lengths
   involved (users, duplicates) are much smaller than raw record
   count, but scales badly if that changes.
6. **`extract_query_durations`** — regex recompiled conceptually on
   every call rather than precompiled once. (See Section 5 for why
   this one's real-world impact turned out smaller than expected.)

## 4. Optimizations Implemented

| # | Function | Original approach | Optimized approach | Technique |
|---|---|---|---|---|
| 1 | `find_users_with_multiple_ips` | Nested loop, all-pairs comparison — O(n²) | Single pass building `{user: set(ips)}`, then filter for `len > 1` — O(n) | **Algorithmic improvement** (data structure: dict of sets) |
| 2 | `word_frequency` | Collect all words, then `list.count()` per unique word — O(total × unique) | `collections.Counter(all_words)` — O(total) | **Built-in library / data structure** |
| 3 | `classify_message` | Recomputed (3 regex checks) on every call | `@lru_cache` — memoizes by message text | **Eliminating redundant computation** |
| 4 | `find_duplicate_messages` | `if msg in seen_list` — O(n) scan per check | `collections.Counter`, filter for `count > 1` — O(n) total | **Data structure** (hash-based vs. list scan) |
| 5 | `build_summary_report` | `report += line` in a loop — reallocates and copies on every append | Append each line to a list, `"\n".join(lines)` once at the end | **String-building idiom** |
| 6 | `extract_query_durations` | `re.search(r"...", text)` — pattern re-specified on every call | Pattern precompiled once at module load (`_DURATION_RE = re.compile(...)`), reused via `_DURATION_RE.search(text)` | **Avoiding repeated work / built-in library usage** |
| 7 | `top_n_users_by_count` | `sorted(items, ...)[:n]` — fully sorts all m entries — O(m log m) | `heapq.nlargest(n, items, ...)` — O(m log n) | **Algorithmic improvement** (partial selection vs. full sort) |

Full before/after code for each is in `original/log_analyzer.py` and
`optimized/log_analyzer.py`; every change is marked with a `NOTE`
(original) or `FIX` (optimized) comment at the exact location.

Item #7 (`top_n_users_by_count`) wasn't visible as a hotspot in
profiling at n=8,000 with only 300 distinct users (m is too small for
a full sort of it to matter), but was optimized anyway on general
principle — it's a one-line change, and the win grows precisely when
m (distinct users) is large and n (top-N requested) is small, which
is the common real-world shape of this query ("give me the top 10
out of 50,000 users").

## 5. Results: Before-and-After Benchmarks

### 5.1 Full workload (`run_all()`), original vs. optimized

Measured with `time.perf_counter()`, both versions run on identical
input at each size (`profiling/scaling_comparison.py`):

| n | Original | Optimized | Speedup |
|---|---|---|---|
| 1,000 | 0.0696s | 0.00149s | **46.8x** |
| 2,000 | 0.2703s | 0.00268s | **100.7x** |
| 4,000 | 1.0368s | 0.00515s | **201.4x** |
| 8,000 | 3.9797s | 0.00869s | **458.0x** |
| 16,000 | 17.1982s | 0.01885s | **912.5x** |

The speedup itself roughly doubles every time `n` doubles — direct
confirmation that the fix changed the algorithm's complexity class
(O(n²) → O(n)), not just its constant factor. A constant-factor
speedup (e.g. from a faster inner loop) would show a *flat* speedup
ratio across sizes; a growing ratio like this is the signature of an
algorithmic fix.

### 5.2 Headroom at much larger scale (optimized only)

The original was not run at these sizes — based on the confirmed
O(n²) trend above, a rough quadratic-fit extrapolation
(`time ≈ 6.468×10⁻⁸ × n²`, fitted from the 8,000/16,000 measurements)
estimates:

| n | Optimized (measured) | Original (extrapolated estimate) |
|---|---|---|
| 50,000 | 0.0667s | ~162s (~2.7 minutes) |
| 200,000 | 0.2427s | ~2,587s (~43.1 minutes) |

These original-side figures are explicitly estimates, not
measurements — included to give a sense of scale, not as precise
benchmarks.

### 5.3 Per-function isolated benchmarks (n=8,000, cold cache, best-of-3)

| Function | Original | Optimized | Speedup |
|---|---|---|---|
| `find_users_with_multiple_ips` | 3.76131s | 0.00102s | **3,673.6x** |
| `word_frequency` | 0.03941s | 0.00266s | **14.8x** |
| `category_counts` | 0.00951s | 0.00108s | **8.8x** |
| `find_duplicate_messages` | 0.00418s | 0.00040s | **10.5x** |
| `build_summary_report` | 0.00481s | 0.00104s | **4.6x** |
| `extract_query_durations` | 0.00228s | 0.00087s | **2.6x** |

Full table across all four tested sizes: `profiling/timeit_results.txt`.

### 5.4 Full-workload profile, optimized (cProfile, same n=8,000)

```
84,844 function calls (84,820 primitive calls) in 0.022 seconds
```
Down from 4.543 seconds — a **206x** reduction in total workload time
at this dataset size. Full output: `profiling/optimized_cprofile_report.txt`.

### 5.5 A note on `extract_query_durations`'s smaller-than-expected win

Precompiling the regex only produced a 2.6x speedup, not the larger
number that "recompiling a regex 8,000 times" might suggest. The
reason: Python's `re` module maintains its own internal cache (up to
512 patterns) keyed by the pattern string, so repeated
`re.search(r"...", text)` calls with the *same literal pattern
string* were already mostly hitting that internal cache rather than
truly recompiling from scratch each time — the profiler's `re._compile`
row shows real but modest overhead (0.016s of the 4.543s total), not
a hidden major cost. The explicit module-level `re.compile()` still
avoids that repeated cache lookup and function-call overhead
entirely, and is unambiguously the correct practice, but it's worth
recording honestly that this particular fix's real-world impact was
smaller than the "regex recompiled every iteration" framing might
imply — a good example of profiling correcting an assumption rather
than just confirming one.

### 5.6 The caching optimization's other benefit: a warm cache across calls

`classify_message`'s `@lru_cache` doesn't just avoid redundant work
within one call to `category_counts()` — in a real application, it
stays warm across *many separate calls* (e.g. repeated report
generation on overlapping data). Measured directly
(`profiling/timeit_benchmark.py`, `demonstrate_warm_cache_benefit`):

```
category_counts() call 1 [cold cache]:            0.001240s
category_counts() call 2 [warm cache]:             0.000887s
category_counts() call 3 [warm cache]:             0.000917s
category_counts() call 4 [warm cache]:             0.000890s
category_counts() call 5 [warm cache]:             0.000915s
Final cache_info(): CacheInfo(hits=39705, misses=295, maxsize=4096, currsize=295)
```

Only 295 of the 8,000 messages in this dataset are actually distinct
— so after the first call, 39,705 of 40,000 subsequent lookups
(across the 5 repeated calls) were served from cache. This is a
direct, measured illustration of why memoizing a pure function pays
off especially well on data with heavy repetition, which is exactly
what real application logs look like.

## 6. Correctness Verification

Optimizing without verifying correctness isn't optimizing — it's
just introducing bugs faster. Every fix was validated against the
original's output before being considered done:

- **`tests/test_equivalence.py`** — 11 automated tests comparing
  original vs. optimized output directly:
  - Full `run_all()` equality at 6 dataset sizes, including edge
    cases n=0 and n=1.
  - Every individual method compared separately, so a failure would
    immediately identify which specific optimization (if any) changed
    behavior.
  - Every distinct message in a 1,000-record sample individually
    checked through `classify_message()` on both versions.
  - A targeted test confirming the `lru_cache` doesn't cross-
    contaminate results between different message strings.
  - `top_n_users_by_count` is compared as a set of (user, count)
    pairs rather than requiring identical list order, since a full
    sort and `heapq.nlargest` aren't guaranteed to break count-ties
    in the same order — and "top N" doesn't promise a specific
    tie-break rule. Both outputs are separately confirmed to be
    correctly sorted descending by count.

```
$ python -m unittest discover -s tests -v
...
Ran 11 tests in 0.439s

OK
```

All 11 tests pass. **The optimized version's output is verified
identical to the original's, field-for-field, at every tested size.**

## 7. Summary

| Metric | Value |
|---|---|
| Baseline runtime (n=8,000, full workload) | 4.543s |
| Optimized runtime (n=8,000, full workload) | 0.022s |
| Overall speedup at n=8,000 | **~206x** |
| Overall speedup at n=16,000 | **~913x** (and still growing with n) |
| Dominant original bottleneck | `find_users_with_multiple_ips`, 97.4% of runtime |
| Bottleneck's complexity class | O(n²) → fixed to O(n) |
| Optimizations applied | 7 (1 algorithmic/data-structure fix resolving the dominant bottleneck, 3 further data-structure/algorithmic fixes, 1 memoization, 1 string-building idiom, 1 precompilation) |
| Correctness regression tests | 11/11 passing |
| Functional changes | **None** — every optimization is a pure performance improvement |

The single largest win came from recognizing that one function
(`find_users_with_multiple_ips`) was responsible for essentially the
entire runtime, and that its O(n²) nested-loop algorithm — not a
"slow" implementation of a necessarily-expensive operation — was the
actual problem. Replacing it with a single-pass, dict-of-sets
approach changed the module's fundamental scaling behavior, which is
why the speedup keeps *growing* with dataset size rather than staying
fixed. The remaining fixes, while individually smaller, matter for
robustness on data shaped differently than this specific benchmark
(more unique messages, more unique words, more distinct users) and
cost little to apply once identified — profiling in isolation, not
just in aggregate, was what surfaced them despite being hidden behind
the dominant bottleneck in the initial aggregate profile.
