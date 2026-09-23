"""
data_generator.py
------------------
Generates a synthetic, deterministic dataset of "application log
records" used to benchmark the LogAnalyzer module (original vs.
optimized). Deterministic (seeded) so the original and optimized
implementations are always compared on byte-for-byte identical input,
and so profiling runs are reproducible.

No external files are read or written here -- the dataset is
generated entirely in memory from a fixed seed, keeping the whole
project self-contained.
"""

from __future__ import annotations

import random
from collections import namedtuple
from typing import List

LogRecord = namedtuple("LogRecord", ["timestamp", "level", "user", "ip", "message"])

_LEVELS = ["INFO", "INFO", "INFO", "WARN", "ERROR", "DEBUG"]

# A deliberately limited pool of usernames and IPs -- in a real
# application, many log lines come from a comparatively small set of
# users and machines, which is exactly what creates the duplication
# and repeated-value patterns that make certain naive algorithms slow
# (and certain optimizations, like caching, effective).
_NUM_USERS = 300
_USERS = [f"user_{i:04d}" for i in range(_NUM_USERS)]

_NUM_IPS = 120
_IPS = [f"10.0.{i // 256}.{i % 256}" for i in range(_NUM_IPS)]

# A bank of message templates. Many records will share the exact same
# rendered message text (e.g. "cache miss for key=..." with the same
# key appearing repeatedly across the log), which is realistic for
# application logs and is what makes memoizing per-message work
# worthwhile.
_MESSAGE_TEMPLATES = [
    "user logged in successfully",
    "user logged out",
    "cache miss for key=session_{n}",
    "cache hit for key=session_{n}",
    "database query executed duration={dur}ms",
    "slow database query detected duration={dur}ms",
    "failed to connect to upstream service",
    "request completed with status=200",
    "request completed with status=404",
    "request completed with status=500",
    "rate limit exceeded for endpoint=/api/v1/{n}",
    "background job started job_id={n}",
    "background job finished job_id={n} duration={dur}ms",
    "configuration reloaded successfully",
    "invalid authentication token provided",
    "password reset email sent",
    "file upload completed size={n}kb",
    "webhook delivery failed after retries",
    "scheduled task executed task={n}",
    "memory usage warning threshold exceeded",
]

# Only a handful of distinct "n" and "dur" values, so many rendered
# messages are exact duplicates of each other (again, realistic for
# real application logs, and load-bearing for the caching benchmark).
_N_VALUES = list(range(20))
_DUR_VALUES = [15, 42, 87, 120, 250, 480, 999, 1500]


def generate_logs(count: int, seed: int = 42) -> List[LogRecord]:
    """Generate `count` synthetic LogRecords, deterministically.

    The same (count, seed) pair always produces byte-for-byte the
    same list of records, which is what lets the original and
    optimized LogAnalyzer implementations be benchmarked on identical
    input, and lets the equivalence tests compare their outputs
    directly.
    """
    rng = random.Random(seed)
    records: List[LogRecord] = []

    for i in range(count):
        user = rng.choice(_USERS)
        ip = rng.choice(_IPS)
        level = rng.choice(_LEVELS)
        template = rng.choice(_MESSAGE_TEMPLATES)
        message = template.format(
            n=rng.choice(_N_VALUES),
            dur=rng.choice(_DUR_VALUES),
        )
        timestamp = f"2026-01-{1 + (i % 28):02d}T{(i % 24):02d}:{(i % 60):02d}:{(i % 60):02d}Z"
        records.append(LogRecord(timestamp, level, user, ip, message))

    return records
