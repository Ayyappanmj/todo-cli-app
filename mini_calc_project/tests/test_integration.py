"""
test_integration.py
--------------------
Integration tests for mini_calc's top-level `evaluate(text)` function.

Unlike test_tokenizer.py / test_parser.py / test_evaluator.py, which
each isolate ONE layer, these tests exercise the full pipeline
(tokenizer -> parser -> evaluator) together, the same way a real
caller of the library would use it. This catches integration bugs
that unit tests can miss -- e.g. a mismatch in how one layer's output
is shaped versus what the next layer expects, even if each layer
passes its own unit tests in isolation.
"""

import unittest

import mini_calc
from mini_calc import evaluate, CalculatorError, TokenizeError, ParseError, EvaluationError


class TestEndToEndArithmetic(unittest.TestCase):
    def test_simple_addition(self):
        self.assertEqual(evaluate("2 + 3"), 5)

    def test_operator_precedence(self):
        self.assertEqual(evaluate("2 + 3 * 4"), 14)

    def test_parentheses_override_precedence(self):
        self.assertEqual(evaluate("(2 + 3) * 4"), 20)

    def test_power_right_associativity(self):
        self.assertEqual(evaluate("2 ** 3 ** 2"), 512)

    def test_unary_minus_vs_power_precedence(self):
        self.assertEqual(evaluate("-2 ** 2"), -4)

    def test_division_returns_float(self):
        self.assertAlmostEqual(evaluate("10 / 4"), 2.5)

    def test_modulo(self):
        self.assertEqual(evaluate("10 % 3"), 1)

    def test_generous_whitespace(self):
        self.assertEqual(evaluate("   ( 1 +  2  )   *   3  "), 9)

    def test_floats(self):
        self.assertAlmostEqual(evaluate("3.5 + 1.5"), 5.0)

    def test_binary_plus_then_unary_plus(self):
        self.assertEqual(evaluate("2++3"), 5)

    def test_nested_parens_with_unary(self):
        self.assertEqual(evaluate("-(-5)"), 5)

    def test_deeply_nested_expression(self):
        self.assertEqual(evaluate("((1 + 2) * (3 + 4)) - 5"), 16)


class TestEndToEndErrorPropagation(unittest.TestCase):
    """Confirms errors raised deep in one layer (e.g. the tokenizer)
    correctly propagate all the way out through evaluate(), rather
    than being swallowed or converted into the wrong exception type
    somewhere in the pipeline."""

    def test_invalid_character_raises_tokenize_error(self):
        with self.assertRaises(TokenizeError):
            evaluate("2 & 3")

    def test_unbalanced_parens_raises_parse_error(self):
        with self.assertRaises(ParseError):
            evaluate("(2 + 3")

    def test_empty_expression_raises_parse_error(self):
        with self.assertRaises(ParseError):
            evaluate("")

    def test_division_by_zero_raises_evaluation_error(self):
        with self.assertRaises(EvaluationError):
            evaluate("10 / 0")

    def test_division_by_zero_inside_parens_raises(self):
        with self.assertRaises(EvaluationError):
            evaluate("10 / (5 - 5)")

    def test_all_error_types_are_calculator_errors(self):
        # Confirms the exception hierarchy is intact end-to-end: a
        # caller who only wants to catch "something about this
        # expression is invalid" can catch just CalculatorError.
        for expr in ("2 & 3", "(2+3", "1/0"):
            with self.assertRaises(CalculatorError):
                evaluate(expr)


class TestEndToEndAgainstPythonAsOracle(unittest.TestCase):
    """Cross-checks a battery of expressions against Python's own
    `eval()` as an independent reference implementation, for the
    subset of syntax the two languages share. This adds an extra
    layer of confidence beyond hand-computed expected values -- if
    mini_calc's precedence/associativity design ever drifted from
    Python's, these would catch it even without updating expectations
    by hand."""

    EXPRESSIONS = [
        "2+3*4",
        "(2+3)*4",
        "2**3**2",
        "-2**2",
        "10/4",
        "7%3",
        "2**-1",
        "-(-3)",
        "1+2-3+4",
        "100/(10-10+2)",
        "2*3+4*5",
        "(1+1)**(1+1)",
        "10-2*3",
    ]

    def test_matches_python_eval_for_each_expression(self):
        for expr in self.EXPRESSIONS:
            with self.subTest(expr=expr):
                mini_calc_result = evaluate(expr)
                python_result = eval(expr)  # noqa: S307 - trusted, hard-coded literals only
                self.assertAlmostEqual(mini_calc_result, python_result, places=9)


class TestPackageExports(unittest.TestCase):
    """A light contract test confirming the public API surface stays
    stable -- these are the names documented in the README as what a
    caller should import."""

    def test_evaluate_is_exported(self):
        self.assertTrue(callable(mini_calc.evaluate))

    def test_error_types_are_exported(self):
        for name in ("CalculatorError", "TokenizeError", "ParseError", "EvaluationError"):
            self.assertTrue(hasattr(mini_calc, name), f"mini_calc.{name} should be importable")

    def test_error_hierarchy(self):
        self.assertTrue(issubclass(TokenizeError, CalculatorError))
        self.assertTrue(issubclass(ParseError, CalculatorError))
        self.assertTrue(issubclass(EvaluationError, CalculatorError))


if __name__ == "__main__":
    unittest.main()
