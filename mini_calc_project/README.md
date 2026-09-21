# mini_calc — A Small Arithmetic Expression Evaluator

A Python module that parses and evaluates arithmetic expression
strings like `"2 + 3 * (4 - 1)"`, built with test-driven development.
No external dependencies — the module and its 94 automated tests use
only the Python standard library.

```python
>>> from mini_calc import evaluate
>>> evaluate("2 + 3 * 4")
14.0
>>> evaluate("(2 + 3) ** 2")
25.0
```

## What's in this repository

```
mini_calc_project/
├── mini_calc/                  # the module
│   ├── __init__.py             # public API: evaluate(), error classes
│   ├── tokenizer.py            # string -> tokens
│   ├── ast_nodes.py            # AST node types
│   ├── parser.py               # tokens -> AST (recursive descent)
│   ├── evaluator.py            # AST -> numeric result
│   └── errors.py               # exception hierarchy
├── tests/                      # 94 automated tests (unittest)
│   ├── test_tokenizer.py       # 21 unit tests
│   ├── test_parser.py          # 29 unit tests
│   ├── test_evaluator.py       # 22 unit tests
│   └── test_integration.py     # 22 integration tests
├── tdd_evidence/                # real red/green terminal output + coverage reports
├── TESTING.md                  # full test documentation & methodology (read this)
└── README.md                   # you are here
```

**For the full explanation of the testing methodology, what every
test covers and why, coverage results, and the refactor performed —
see [`TESTING.md`](TESTING.md).** This README covers the module itself
and how to run everything.

## Requirements

Python 3.8 or later. No pip installs needed.

## Installation

Just unzip/clone — there's nothing to install.

```bash
cd mini_calc_project
python -c "from mini_calc import evaluate; print(evaluate('1 + 1'))"
# 2.0
```

## Supported syntax

| Feature | Example | Result |
|---|---|---|
| Addition / subtraction | `2 + 3 - 1` | `4.0` |
| Multiplication / division | `4 * 5 / 2` | `10.0` |
| Modulo | `10 % 3` | `1.0` |
| Power (right-associative) | `2 ** 3 ** 2` | `512.0` |
| Parentheses | `(2 + 3) * 4` | `20.0` |
| Unary minus / plus | `-5`, `+5` | `-5.0`, `5.0` |
| Decimals | `3.5 + 1.5` | `5.0` |

Operator precedence matches Python's own, including the easy-to-get-
wrong case `-2 ** 2 == -4` (unary minus binds *looser* than `**`).
Full grammar is documented in `mini_calc/parser.py`.

**Known, deliberate limitations** (see `TESTING.md` §3.1 for why):
no scientific notation (`1e10`), numbers must start with a digit
(`.5` isn't accepted — write `0.5`), and no variables or functions —
this module evaluates a single arithmetic expression, nothing more.

## Error handling

Every error raised by the module is a `CalculatorError` (or one of
its three subclasses), so you can catch broadly or specifically:

```python
from mini_calc import evaluate, CalculatorError, TokenizeError, ParseError, EvaluationError

try:
    evaluate("10 / 0")
except EvaluationError as e:
    print(f"Math error: {e}")

try:
    evaluate("2 & 3")
except TokenizeError as e:
    print(f"Bad character: {e}")

try:
    evaluate("(2 + 3")
except ParseError as e:
    print(f"Malformed expression: {e}")

# Or catch anything the module can raise:
try:
    evaluate(some_user_input)
except CalculatorError as e:
    print(f"Invalid expression: {e}")
```

## Running the tests

```bash
python -m unittest discover -s tests -v
```

Expected output:
```
----------------------------------------------------------------------
Ran 94 tests in 0.003s

OK
```

Also works with `pytest tests/ -v` if you have it installed. See
[`TESTING.md`](TESTING.md) for how to run individual test files, what
each test covers, and the real TDD red/green evidence saved in
`tdd_evidence/`.

## Design notes

The module is split into four layers (tokenizer → parser → evaluator,
plus a thin `__init__.py` tying them together) specifically so each
layer can be unit-tested in complete isolation from the others, with
a separate integration test layer confirming they work correctly
together. This structure, the TDD process used to build it, and every
test case are explained in full in [`TESTING.md`](TESTING.md).
