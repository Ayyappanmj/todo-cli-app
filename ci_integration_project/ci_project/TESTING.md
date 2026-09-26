# Testing Documentation — mini_calc

This document explains the module under test, the testing methodology
followed, what each test file/case covers and why, and how to run the
suite yourself.

---

## 1. The Module: `mini_calc`

`mini_calc` is a small arithmetic expression evaluator. It takes a
string like `"2 + 3 * (4 - 1)"` and returns its numeric value.

It's built as a classic three-stage interpreter pipeline, each stage
in its own file, specifically because that structure is easy to test
in isolation:

| Stage | File | Responsibility |
|---|---|---|
| 1. Tokenizer | `mini_calc/tokenizer.py` | String → list of `Token`s (numbers, operators, parentheses) |
| 2. Parser | `mini_calc/parser.py` | List of `Token`s → an AST (Abstract Syntax Tree) |
| 3. Evaluator | `mini_calc/evaluator.py` | AST → a single numeric result |
| — | `mini_calc/ast_nodes.py` | The AST node types (`Number`, `UnaryOp`, `BinaryOp`) shared between stages 2 and 3 |
| — | `mini_calc/errors.py` | The exception hierarchy (`CalculatorError` and three subclasses) |
| — | `mini_calc/__init__.py` | The public API: `evaluate(text)`, wiring the three stages together |

Supported syntax: `+ - * / % **` (power, right-associative), unary
`+`/`-`, parentheses, and integer/decimal number literals — with
precedence matching Python's own, so results are unsurprising to
anyone with Python experience. Full grammar is documented in
`parser.py`'s module docstring.

**Why this design is easy to test:** each stage has a narrow, single
responsibility and communicates with the next stage through a simple
data structure (a list of tokens, then a tree of dataclasses). That
means each stage can be unit-tested completely independently of the
others — the parser tests never need the tokenizer to be bug-free, and
the evaluator tests never need the parser to be bug-free — while a
separate integration test layer confirms the three stages actually
fit together correctly end to end.

---

## 2. Methodology: Test-Driven Development

This module was built using real TDD, not tests written after the
fact. For **each** of the four layers (tokenizer, parser, evaluator,
package API), the process was:

1. **Design the API first** — decide the function/class signatures and
   what they should do, without writing the implementation body.
2. **Write the tests against that API** — covering normal cases, edge
   cases, and error conditions.
3. **Run the tests and confirm they fail** (red) — specifically with
   an `ImportError`/`ModuleNotFoundError`, since the implementation
   didn't exist yet. This confirms the tests are actually exercising
   real code paths and not silently passing for the wrong reason.
4. **Write the minimum implementation** to make the tests pass.
5. **Run the tests again and confirm they pass** (green).
6. Move to the next layer, repeat.
7. Once every layer was green, **review and refactor** (Section 6),
   then re-run the full suite to confirm nothing broke.

The actual terminal output from every red and green phase (a real,
un-edited transcript) is saved in the `tdd_evidence/` folder, numbered
in the order it happened:

```
tdd_evidence/
├── 01_tokenizer_red.log        # ModuleNotFoundError before tokenizer.py existed
├── 02_tokenizer_green.log      # 21/21 passing after implementing it
├── 03_parser_red.log           # ModuleNotFoundError before parser.py existed
├── 04_parser_green.log         # 29/29 passing after implementing it
├── 05_evaluator_red.log        # ModuleNotFoundError before evaluator.py existed
├── 06_evaluator_green.log      # 22/22 passing after implementing it
├── 07_integration_red.log      # ImportError before __init__.py exposed evaluate()
├── 08_integration_green.log    # 22/22 passing after implementing it
├── 09_full_suite_green.log     # all 94 tests together, before refactor
├── 10_after_refactor_green.log # all 94 tests together, after refactor (Section 6)
└── coverage/                   # per-module line-coverage reports (Section 5)
```

---

## 3. Test Suite Structure

```
tests/
├── test_tokenizer.py    (21 tests) — unit tests, tokenizer in isolation
├── test_parser.py       (29 tests) — unit tests, parser in isolation
├── test_evaluator.py    (22 tests) — unit tests, evaluator in isolation
└── test_integration.py  (22 tests) — integration tests, full pipeline together
```

**Total: 94 automated tests, all passing.**

### 3.1 `test_tokenizer.py` — unit tests

Tests `tokenize(text)` in complete isolation. Grouped by:

- **`TestTokenizeNumbers`** — integers, floats, multi-digit numbers,
  zero, trailing-zero decimals (`5.0`). *Why:* numbers are the most
  varied input the tokenizer handles; these confirm the digit/decimal
  scanning loop is correct at its boundaries.
- **`TestTokenizeOperatorsAndParens`** — every single-character
  operator, and specifically that `**` is recognized as *one* token
  (not two `*` tokens), including the greedy-matching case `***` →
  `DOUBLE_STAR, STAR`. *Why:* this is the one place the tokenizer has
  to look ahead more than one character, so it's the most likely spot
  for an off-by-one bug.
- **`TestTokenizeWhitespaceAndEmpty`** — spaces, tabs, newlines, empty
  string, whitespace-only string. *Why:* real-world input is rarely
  perfectly formatted; users will type extra spaces.
- **`TestTokenizeCombinedExpressions`** — a realistic multi-token
  expression, and the explicit assertion that `"-5"` tokenizes as
  `MINUS, NUMBER` (two tokens), never a single "negative number"
  token. *Why:* this locks in the deliberate boundary between the
  tokenizer (lexical only) and the parser (grammar, including what
  `-` means in context) — see the module docstring in
  `tokenizer.py` for the reasoning.
- **`TestTokenizeErrors`** — an invalid character, an invalid
  character's message content, a number with two decimal points
  (`3.1.4`), a leading decimal point (`.5`, unsupported by design),
  a letter, and scientific notation (`1e10`, unsupported by design).
  *Why:* every unsupported input should fail clearly and
  predictably rather than silently misparsing or crashing with an
  unrelated exception type.

### 3.2 `test_parser.py` — unit tests

Tests `parse(text)` (and, in a few cases, the `Parser` class directly
against hand-built token lists — see `TestParserAgainstHandBuiltTokens`
below). Grouped by:

- **`TestParseSingleValues`** — a bare number, a float, a
  parenthesized number, doubly-nested parentheses. *Why:* the simplest
  possible inputs, confirming the base case of the recursive grammar
  works before testing anything that recurses into it.
- **`TestParseBinaryPrecedence`** — addition, `*` binding tighter than
  `+`, parentheses overriding precedence, left-associativity of `+`/`-`
  and `*`/`/`, and that `%` shares precedence with `*`/`/`. *Why:*
  precedence and associativity are the two things most likely to be
  subtly wrong in a hand-written parser, and wrong precedence produces
  a *plausible-looking but incorrect* answer rather than a crash — the
  most dangerous kind of bug, so it gets the most test coverage.
- **`TestParsePower`** — `**` binding tighter than `*`, `**` being
  right-associative (`2**3**2` == `2**(3**2)`, not `(2**3)**2`), and
  `**` accepting a unary-minus exponent (`2**-1`). *Why:* `**` is the
  only right-associative operator and the only one whose right-hand
  side can itself start with a unary operator — both are easy to get
  backwards.
- **`TestParseUnary`** — unary `-`, unary `+`, double unary (`--5`),
  unary minus binding *looser* than `**` (`-2**2` == `-4`, matching
  Python — not `4`), and the specific case `"2++3"` (binary `+`
  followed by a unary `+`), which is valid and explicitly documented
  as such rather than assumed to be an error. *Why:* unary-vs-binary
  ambiguity around `+`/`-` is the single trickiest part of this
  grammar, and `-2**2` is a classic "looks obvious, is easy to get
  backwards" case (many hand-written calculators get this wrong).
- **`TestParseErrors`** — empty expression, whitespace-only expression,
  trailing operator (`"2+"`), a binary-only operator at the start
  (`"*5"`), unclosed parenthesis, an unopened (extra) parenthesis,
  empty parentheses (`"()"`), two numbers with no operator between
  them (`"2 3"`), and a check that the error message isn't empty/
  useless. *Why:* malformed input is the normal case for a parser
  used interactively — these confirm every kind of malformed input
  fails predictably with `ParseError`, not a raw `IndexError` from
  walking off the end of the token list.
- **`TestParserAgainstHandBuiltTokens`** — two tests that construct a
  `Token` list by hand and feed it directly to the `Parser` class,
  bypassing `tokenize()` entirely. *Why:* this is true unit isolation
  — if one of these fails, the bug is definitively in the parser's
  grammar logic, not in how text got turned into tokens.

### 3.3 `test_evaluator.py` — unit tests

Tests `evaluate_ast(node)` against **hand-built AST nodes**
(`Number`, `UnaryOp`, `BinaryOp`), never going through the parser.
Grouped by:

- **`TestEvaluateNumber`** — a positive number, zero, a float.
- **`TestEvaluateUnary`** — unary minus, unary plus (confirmed to be a
  true no-op), double unary minus (confirmed to cancel out).
- **`TestEvaluateBinaryArithmetic`** — each of the six operators
  individually, plus the specific check that `/` always returns a
  `float` even for an exact division (`10 / 2` → `5.0`, not `5`,
  matching Python 3 semantics), and `**` with a zero exponent and a
  negative exponent.
- **`TestEvaluateNestedTrees`** — a tree with a `BinaryOp` nested
  inside another `BinaryOp`, and a `UnaryOp` wrapped around a
  `BinaryOp`. *Why:* confirms the evaluator's recursion actually
  recurses correctly on real multi-level trees, not just flat
  one-operator trees.
- **`TestEvaluateErrors`** — division by zero, modulo by zero, that
  the division-by-zero message actually mentions "zero" (not just
  that *some* error occurred), and two defensive tests
  (`test_unknown_binary_operator_raises`,
  `test_unknown_unary_operator_raises`) that hand the evaluator an AST
  node with an operator symbol the real parser could never produce
  (e.g. `BinaryOp("^", ...)`). *Why the defensive tests matter:* the
  evaluator's `op` field is a plain string, not a restricted enum, so
  nothing at the type level stops a future caller (or a bug elsewhere)
  from constructing a `BinaryOp("^", ...)`. These tests document and
  lock in that the evaluator fails safely (`EvaluationError`) rather
  than crashing with a raw `KeyError` if that ever happens.

### 3.4 `test_integration.py` — integration tests

Tests the **full pipeline together** through the public `evaluate(text)`
function — the same way a real caller uses the library. Grouped by:

- **`TestEndToEndArithmetic`** — a broad set of realistic expressions
  exercising precedence, associativity, parentheses, whitespace,
  floats, and the `"2++3"` edge case, all through the complete
  pipeline at once. *Why:* unit tests prove each stage is correct in
  isolation, but only an end-to-end test proves the stages are wired
  together correctly — e.g. that the parser is actually being handed
  the tokenizer's real output, and the evaluator the parser's real
  output, with no mismatch at the boundaries.
- **`TestEndToEndErrorPropagation`** — confirms a `TokenizeError` from
  deep inside the tokenizer, a `ParseError` from the parser, and an
  `EvaluationError` from the evaluator (including one nested inside
  parentheses, `"10 / (5 - 5)"`) all correctly propagate all the way
  out through `evaluate()` without being caught, swallowed, or
  converted into the wrong type anywhere in the pipeline. A final test
  confirms all three can be caught via the shared `CalculatorError`
  base class.
- **`TestEndToEndAgainstPythonAsOracle`** — a table of 13 expressions,
  each checked against Python's own built-in `eval()` as an
  independent reference implementation (`assertAlmostEqual`, using
  `subTest` so one mismatch doesn't hide the others). *Why:* this adds
  a layer of confidence beyond hand-computed expected values — since
  `mini_calc`'s precedence and associativity were deliberately
  designed to match Python's, cross-checking against Python's real
  interpreter would catch a design drift that a hand-written
  "expected" value might not (if the hand-written value were
  computed with the same mistaken assumption baked in).
- **`TestPackageExports`** — confirms `evaluate` and all four
  exception classes are actually importable from `mini_calc` (not just
  from a submodule), and that the exception hierarchy
  (`TokenizeError`/`ParseError`/`EvaluationError` all subclass
  `CalculatorError`) is intact. *Why:* this is a contract test for the
  public API surface documented in the README — it would fail if a
  future refactor accidentally stopped exporting something callers
  depend on.

---

## 4. Edge Cases and Error Conditions Covered

A consolidated view of what's tested, since "comprehensiveness" is
easier to judge as one list:

- Empty input, whitespace-only input
- Single-token input (just a number)
- Every operator individually, and every documented pairwise
  precedence relationship between them (`+`/`-` vs `*`/`/`/`%` vs `**`
  vs unary)
- Left-associativity (`+`, `-`, `*`, `/`) and right-associativity
  (`**`) — including a 3-operator chain for each, since 2-operator
  chains can't distinguish left- from right-associative
- Unary `+`/`-`, including doubled (`--5`) and combined with `**`
  (the `-2**2 == -4` case)
- Deep nesting: parentheses inside parentheses, multiple binary ops
  inside a single expression
- Division and modulo by zero
- Malformed expressions: trailing operator, leading binary-only
  operator, unbalanced parentheses (both directions), empty
  parentheses, two operands with no operator between them
- Malformed numbers: two decimal points, leading decimal point
- Invalid characters and unsupported syntax (letters, scientific
  notation)
- Whitespace tolerance (spaces, tabs, newlines, in any position)
- Type consistency (`/` always returns `float`)
- Defensive handling of AST shapes the parser itself could never
  produce
- Public API surface and exception hierarchy stability

---

## 5. Coverage

Since this environment has no network access to install `coverage.py`,
line coverage was measured using Python's standard-library `trace`
module instead (`python -m trace --count --coverdir=...`). The
per-module annotated output is saved in `tdd_evidence/coverage/`
(a `>>>>>>` marker would flag any line the test suite never executed).

**Result: every line of every module in `mini_calc/` is covered by
the test suite — zero uncovered lines.**

---

## 6. Review & Refactor

After all 94 tests were green, the code was reviewed for
maintainability. One improvement was made and verified not to break
anything:

- **`parser.py`** — the token-type → operator-symbol mapping inside
  `_term()` was being rebuilt as a fresh dict literal on every loop
  iteration. It was hoisted to a module-level constant
  (`_TERM_OPERATORS`), matching the style already used for the
  equivalent mapping in `evaluator.py`. This is a pure refactor (same
  behavior, slightly clearer and marginally more efficient) — the full
  suite was re-run immediately after and confirmed still at 94/94
  (`tdd_evidence/10_after_refactor_green.log`).

No other changes were made: the rest of the codebase was judged
already at a reasonable clarity/performance balance for a module this
size (each function implements exactly one grammar rule or one
responsibility, docstrings explain *why* non-obvious decisions were
made, and there's no premature abstraction).

---

## 7. How to Run the Tests

No external dependencies are required — everything uses only the
Python standard library.

**Requirements:** Python 3.8 or later.

From the project root:

```bash
# Run everything
python -m unittest discover -s tests -v

# Run just one layer
python -m unittest tests.test_tokenizer -v
python -m unittest tests.test_parser -v
python -m unittest tests.test_evaluator -v
python -m unittest tests.test_integration -v
```

Expected final output:
```
----------------------------------------------------------------------
Ran 94 tests in 0.003s

OK
```

If you have `pytest` installed, the same test files run under it
without any changes (pytest can discover and run standard
`unittest.TestCase` classes):

```bash
pytest tests/ -v
```

### Trying the module directly

```bash
python -c "from mini_calc import evaluate; print(evaluate('2 + 3 * 4'))"
# 14.0
```

Or interactively:

```python
>>> from mini_calc import evaluate
>>> evaluate("(2 + 3) * 4")
20.0
>>> evaluate("10 / 0")
Traceback (most recent call last):
    ...
mini_calc.errors.EvaluationError: Division by zero is undefined.
```
