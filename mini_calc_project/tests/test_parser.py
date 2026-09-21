"""
test_parser.py
---------------
Unit tests for mini_calc.parser.

Grammar under test (documented here so the tests double as a spec),
precedence from loosest to tightest binding, designed to match
Python's own operator precedence exactly so results are unsurprising
to anyone with Python experience:

    expr     := term (('+' | '-') term)*
    term     := unary (('*' | '/' | '%') unary)*
    unary    := ('-' | '+') unary | power
    power    := primary ('**' unary)?      # right-associative
    primary  := NUMBER | '(' expr ')'

Most tests go through the `parse(text)` convenience function (tokenize
+ parse together) since that's the realistic way the parser is used
and keeps test expressions readable. A few tests construct token
lists by hand to isolate the parser from the tokenizer entirely.
"""

import unittest

from mini_calc.parser import parse
from mini_calc.ast_nodes import Number, UnaryOp, BinaryOp
from mini_calc.tokenizer import Token, TokenType
from mini_calc.errors import ParseError


class TestParseSingleValues(unittest.TestCase):
    def test_single_number(self):
        self.assertEqual(parse("2"), Number(2.0))

    def test_single_float(self):
        self.assertEqual(parse("3.5"), Number(3.5))

    def test_parenthesized_number(self):
        self.assertEqual(parse("(2)"), Number(2.0))

    def test_nested_parentheses(self):
        self.assertEqual(parse("((2))"), Number(2.0))


class TestParseBinaryPrecedence(unittest.TestCase):
    def test_addition(self):
        self.assertEqual(parse("2+3"), BinaryOp("+", Number(2), Number(3)))

    def test_multiplication_binds_tighter_than_addition(self):
        # 2 + 3 * 4  ==  2 + (3 * 4)
        self.assertEqual(
            parse("2+3*4"),
            BinaryOp("+", Number(2), BinaryOp("*", Number(3), Number(4))),
        )

    def test_parentheses_override_precedence(self):
        # (2 + 3) * 4
        self.assertEqual(
            parse("(2+3)*4"),
            BinaryOp("*", BinaryOp("+", Number(2), Number(3)), Number(4)),
        )

    def test_addition_is_left_associative(self):
        # 10 - 3 - 2  ==  (10 - 3) - 2, NOT 10 - (3 - 2)
        self.assertEqual(
            parse("10-3-2"),
            BinaryOp("-", BinaryOp("-", Number(10), Number(3)), Number(2)),
        )

    def test_multiplication_is_left_associative(self):
        self.assertEqual(
            parse("8/4/2"),
            BinaryOp("/", BinaryOp("/", Number(8), Number(4)), Number(2)),
        )

    def test_modulo_same_precedence_as_multiply_divide(self):
        self.assertEqual(
            parse("10%3*2"),
            BinaryOp("*", BinaryOp("%", Number(10), Number(3)), Number(2)),
        )


class TestParsePower(unittest.TestCase):
    def test_power_binds_tighter_than_multiplication(self):
        # 2 * 3 ** 2  ==  2 * (3 ** 2)
        self.assertEqual(
            parse("2*3**2"),
            BinaryOp("*", Number(2), BinaryOp("**", Number(3), Number(2))),
        )

    def test_power_is_right_associative(self):
        # 2 ** 3 ** 2  ==  2 ** (3 ** 2), matching Python
        self.assertEqual(
            parse("2**3**2"),
            BinaryOp("**", Number(2), BinaryOp("**", Number(3), Number(2))),
        )

    def test_power_with_unary_minus_exponent(self):
        # 2 ** -1
        self.assertEqual(
            parse("2**-1"),
            BinaryOp("**", Number(2), UnaryOp("-", Number(1))),
        )


class TestParseUnary(unittest.TestCase):
    def test_unary_minus(self):
        self.assertEqual(parse("-5"), UnaryOp("-", Number(5)))

    def test_unary_plus(self):
        self.assertEqual(parse("+5"), UnaryOp("+", Number(5)))

    def test_double_unary_minus(self):
        self.assertEqual(parse("--5"), UnaryOp("-", UnaryOp("-", Number(5))))

    def test_unary_minus_binds_looser_than_power(self):
        # -2 ** 2  ==  -(2 ** 2), matching Python (result is -4, not 4)
        self.assertEqual(
            parse("-2**2"),
            UnaryOp("-", BinaryOp("**", Number(2), Number(2))),
        )

    def test_binary_plus_followed_by_unary_plus(self):
        # "2++3" is a valid, if unusual, expression: binary + followed
        # by a unary + on the right operand -- exactly like Python
        # accepts "2 + +3". Documented explicitly since it's easy to
        # assume this should be a syntax error.
        self.assertEqual(
            parse("2++3"),
            BinaryOp("+", Number(2), UnaryOp("+", Number(3))),
        )


class TestParseErrors(unittest.TestCase):
    def test_empty_expression_raises(self):
        with self.assertRaises(ParseError):
            parse("")

    def test_whitespace_only_expression_raises(self):
        with self.assertRaises(ParseError):
            parse("   ")

    def test_trailing_operator_raises(self):
        with self.assertRaises(ParseError):
            parse("2+")

    def test_leading_binary_operator_raises(self):
        # "*" cannot start an expression (unlike "+"/"-", which are
        # also valid unary operators).
        with self.assertRaises(ParseError):
            parse("*5")

    def test_unclosed_parenthesis_raises(self):
        with self.assertRaises(ParseError):
            parse("(2+3")

    def test_unopened_parenthesis_raises(self):
        with self.assertRaises(ParseError):
            parse("2+3)")

    def test_empty_parentheses_raise(self):
        with self.assertRaises(ParseError):
            parse("()")

    def test_two_numbers_with_no_operator_raises(self):
        with self.assertRaises(ParseError):
            parse("2 3")

    def test_error_message_is_descriptive(self):
        with self.assertRaises(ParseError) as ctx:
            parse("2+")
        # Not checking exact wording (too brittle) -- just that some
        # useful detail beyond the bare exception type was included.
        self.assertGreater(len(str(ctx.exception)), 10)


class TestParserAgainstHandBuiltTokens(unittest.TestCase):
    """A few tests that bypass the tokenizer entirely, feeding a
    hand-built token list straight to the Parser class. This isolates
    the parser's grammar logic from the tokenizer's correctness --
    if these pass but a text-based test fails, the bug is in the
    tokenizer, not the parser (and vice versa)."""

    def test_hand_built_addition(self):
        from mini_calc.parser import Parser

        tokens = [
            Token(TokenType.NUMBER, 1.0),
            Token(TokenType.PLUS),
            Token(TokenType.NUMBER, 2.0),
            Token(TokenType.EOF),
        ]
        result = Parser(tokens).parse()
        self.assertEqual(result, BinaryOp("+", Number(1.0), Number(2.0)))

    def test_hand_built_trailing_garbage_token_raises(self):
        from mini_calc.parser import Parser

        # A well-formed "1" followed by a token that doesn't belong
        # (simulating e.g. a future token type the grammar doesn't
        # expect at the end of an expression).
        tokens = [
            Token(TokenType.NUMBER, 1.0),
            Token(TokenType.RPAREN),
            Token(TokenType.EOF),
        ]
        with self.assertRaises(ParseError):
            Parser(tokens).parse()


if __name__ == "__main__":
    unittest.main()
