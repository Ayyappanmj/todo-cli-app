"""
errors.py
---------
Custom exception hierarchy for mini_calc.

All exceptions raised by this package inherit from CalculatorError,
so a caller who doesn't care about the distinction can catch just
that one type, while a caller who does care (e.g. to give a more
specific message to an end user) can catch the more specific
subclasses.
"""


class CalculatorError(Exception):
    """Base class for every error raised by mini_calc."""


class TokenizeError(CalculatorError):
    """Raised when the input string contains characters that cannot
    be turned into valid tokens (e.g. an unsupported symbol, or a
    malformed number like '3.1.4')."""


class ParseError(CalculatorError):
    """Raised when the sequence of tokens does not form a
    grammatically valid expression (e.g. unbalanced parentheses, a
    missing operand, or trailing tokens after a complete expression)."""


class EvaluationError(CalculatorError):
    """Raised when an expression is syntactically valid but fails at
    evaluation time (e.g. division by zero)."""
