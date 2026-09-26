"""
mini_calc
=========
A small arithmetic expression evaluator.

    >>> from mini_calc import evaluate
    >>> evaluate("2 + 3 * 4")
    14.0
    >>> evaluate("(2 + 3) * 4")
    20.0

Supports +, -, *, /, % (modulo), ** (power, right-associative),
unary +/-, parentheses, and standard operator precedence matching
Python's own (see mini_calc.parser's module docstring for the full
grammar).

Public API:
    evaluate(text)          -- parse and evaluate an expression string
    CalculatorError         -- base class for every exception this package raises
    TokenizeError           -- invalid character or malformed number
    ParseError              -- grammatically invalid expression
    EvaluationError         -- valid expression that fails at runtime (e.g. divide by zero)
"""

from .errors import CalculatorError, TokenizeError, ParseError, EvaluationError
from .parser import parse
from .evaluator import evaluate_ast

__all__ = [
    "evaluate",
    "CalculatorError",
    "TokenizeError",
    "ParseError",
    "EvaluationError",
]


def evaluate(text: str) -> float:
    """Parse and evaluate an arithmetic expression string, returning a float.

    This is the package's main entry point: it wires together
    tokenizing, parsing, and evaluation so a caller doesn't need to
    touch those layers individually for ordinary use.

    Raises:
        TokenizeError: the string contains an invalid character or
            malformed number.
        ParseError: the tokens don't form a valid expression (e.g.
            unbalanced parentheses, a missing operand).
        EvaluationError: the expression is valid but fails at
            evaluation time (e.g. division by zero).
    """
    tree = parse(text)
    return evaluate_ast(tree)
