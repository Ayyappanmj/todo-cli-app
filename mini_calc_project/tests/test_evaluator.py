"""
test_evaluator.py
------------------
Unit tests for mini_calc.evaluator.

These tests construct AST nodes BY HAND (Number, UnaryOp, BinaryOp)
rather than going through the parser. This isolates the evaluator
from both the tokenizer and the parser -- if a test here fails, the
bug is in evaluate_ast() itself, not in how an expression string got
turned into a tree.
"""

import unittest

from mini_calc.evaluator import evaluate_ast
from mini_calc.ast_nodes import Number, UnaryOp, BinaryOp
from mini_calc.errors import EvaluationError


class TestEvaluateNumber(unittest.TestCase):
    def test_positive_number(self):
        self.assertEqual(evaluate_ast(Number(5)), 5)

    def test_zero(self):
        self.assertEqual(evaluate_ast(Number(0)), 0)

    def test_float(self):
        self.assertAlmostEqual(evaluate_ast(Number(3.5)), 3.5)


class TestEvaluateUnary(unittest.TestCase):
    def test_unary_minus(self):
        self.assertEqual(evaluate_ast(UnaryOp("-", Number(5))), -5)

    def test_unary_plus_is_a_no_op(self):
        self.assertEqual(evaluate_ast(UnaryOp("+", Number(5))), 5)

    def test_double_unary_minus_cancels_out(self):
        self.assertEqual(evaluate_ast(UnaryOp("-", UnaryOp("-", Number(5)))), 5)


class TestEvaluateBinaryArithmetic(unittest.TestCase):
    def test_addition(self):
        self.assertEqual(evaluate_ast(BinaryOp("+", Number(2), Number(3))), 5)

    def test_subtraction(self):
        self.assertEqual(evaluate_ast(BinaryOp("-", Number(5), Number(3))), 2)

    def test_multiplication(self):
        self.assertEqual(evaluate_ast(BinaryOp("*", Number(4), Number(3))), 12)

    def test_division(self):
        self.assertAlmostEqual(evaluate_ast(BinaryOp("/", Number(7), Number(2))), 3.5)

    def test_division_result_is_always_float(self):
        # Matches Python 3's "/" behavior: even an exact division
        # returns a float, not an int, for consistent typing.
        result = evaluate_ast(BinaryOp("/", Number(10), Number(2)))
        self.assertIsInstance(result, float)
        self.assertEqual(result, 5.0)

    def test_modulo(self):
        self.assertEqual(evaluate_ast(BinaryOp("%", Number(10), Number(3))), 1)

    def test_power(self):
        self.assertEqual(evaluate_ast(BinaryOp("**", Number(2), Number(10))), 1024)

    def test_power_with_zero_exponent(self):
        self.assertEqual(evaluate_ast(BinaryOp("**", Number(5), Number(0))), 1)

    def test_power_with_negative_exponent(self):
        self.assertAlmostEqual(
            evaluate_ast(BinaryOp("**", Number(2), UnaryOp("-", Number(1)))), 0.5
        )


class TestEvaluateNestedTrees(unittest.TestCase):
    def test_nested_binary_ops(self):
        # (2 + 3) * 4  ==  20
        tree = BinaryOp("*", BinaryOp("+", Number(2), Number(3)), Number(4))
        self.assertEqual(evaluate_ast(tree), 20)

    def test_unary_wrapped_around_binary(self):
        # -(2 ** 2) == -4
        tree = UnaryOp("-", BinaryOp("**", Number(2), Number(2)))
        self.assertEqual(evaluate_ast(tree), -4)


class TestEvaluateErrors(unittest.TestCase):
    def test_division_by_zero_raises(self):
        with self.assertRaises(EvaluationError):
            evaluate_ast(BinaryOp("/", Number(1), Number(0)))

    def test_modulo_by_zero_raises(self):
        with self.assertRaises(EvaluationError):
            evaluate_ast(BinaryOp("%", Number(1), Number(0)))

    def test_division_by_zero_message_is_descriptive(self):
        with self.assertRaises(EvaluationError) as ctx:
            evaluate_ast(BinaryOp("/", Number(1), Number(0)))
        self.assertIn("zero", str(ctx.exception).lower())

    def test_unknown_binary_operator_raises(self):
        # A malformed AST that the parser could never actually
        # produce (it only ever emits '+','-','*','/','%','**'), used
        # here to test the evaluator's own defensive handling of an
        # unexpected node -- useful if the AST is ever constructed by
        # something other than this package's parser.
        bad_tree = BinaryOp("^", Number(2), Number(3))
        with self.assertRaises(EvaluationError):
            evaluate_ast(bad_tree)

    def test_unknown_unary_operator_raises(self):
        bad_tree = UnaryOp("~", Number(2))
        with self.assertRaises(EvaluationError):
            evaluate_ast(bad_tree)


if __name__ == "__main__":
    unittest.main()
