"""
test_tokenizer.py
------------------
Unit tests for mini_calc.tokenizer.

The tokenizer's only job is lexical analysis: turning a raw string
into a flat list of Tokens. It deliberately knows nothing about
grammar (e.g. whether "-" means subtraction or negation) -- that
ambiguity is the parser's job, tested separately in test_parser.py.
Keeping that boundary strict is what makes each layer independently
testable.
"""

import unittest

from mini_calc.tokenizer import tokenize, Token, TokenType
from mini_calc.errors import TokenizeError


class TestTokenizeNumbers(unittest.TestCase):
    def test_single_integer(self):
        tokens = tokenize("42")
        self.assertEqual(tokens, [Token(TokenType.NUMBER, 42.0), Token(TokenType.EOF)])

    def test_single_float(self):
        tokens = tokenize("3.14")
        self.assertEqual(tokens[0], Token(TokenType.NUMBER, 3.14))

    def test_multi_digit_number(self):
        tokens = tokenize("12345")
        self.assertEqual(tokens[0].value, 12345.0)

    def test_zero(self):
        tokens = tokenize("0")
        self.assertEqual(tokens[0].value, 0.0)

    def test_number_with_trailing_zero_decimal(self):
        tokens = tokenize("5.0")
        self.assertEqual(tokens[0].value, 5.0)


class TestTokenizeOperatorsAndParens(unittest.TestCase):
    def test_all_single_char_operators(self):
        tokens = tokenize("+-*/%")
        types = [t.type for t in tokens]
        self.assertEqual(
            types,
            [
                TokenType.PLUS,
                TokenType.MINUS,
                TokenType.STAR,
                TokenType.SLASH,
                TokenType.PERCENT,
                TokenType.EOF,
            ],
        )

    def test_double_star_is_a_single_power_token(self):
        # "**" must be recognized as ONE token (power), not two STAR tokens.
        tokens = tokenize("**")
        self.assertEqual(tokens[0].type, TokenType.DOUBLE_STAR)
        self.assertEqual(len(tokens), 2)  # DOUBLE_STAR + EOF

    def test_star_star_star_is_power_then_star(self):
        # Greedy matching: "***" -> DOUBLE_STAR, STAR (not STAR, DOUBLE_STAR)
        tokens = tokenize("***")
        self.assertEqual(
            [t.type for t in tokens],
            [TokenType.DOUBLE_STAR, TokenType.STAR, TokenType.EOF],
        )

    def test_parentheses(self):
        tokens = tokenize("()")
        self.assertEqual(
            [t.type for t in tokens],
            [TokenType.LPAREN, TokenType.RPAREN, TokenType.EOF],
        )


class TestTokenizeWhitespaceAndEmpty(unittest.TestCase):
    def test_whitespace_is_ignored(self):
        tokens = tokenize("  2   +   3  ")
        self.assertEqual(
            [t.type for t in tokens],
            [TokenType.NUMBER, TokenType.PLUS, TokenType.NUMBER, TokenType.EOF],
        )

    def test_tabs_and_newlines_are_ignored(self):
        tokens = tokenize("2\t+\n3")
        self.assertEqual(len(tokens), 4)  # NUMBER, PLUS, NUMBER, EOF

    def test_empty_string_yields_only_eof(self):
        self.assertEqual(tokenize(""), [Token(TokenType.EOF)])

    def test_whitespace_only_yields_only_eof(self):
        self.assertEqual(tokenize("   "), [Token(TokenType.EOF)])


class TestTokenizeCombinedExpressions(unittest.TestCase):
    def test_realistic_expression(self):
        tokens = tokenize("2+3*4")
        self.assertEqual(
            [t.type for t in tokens],
            [
                TokenType.NUMBER,
                TokenType.PLUS,
                TokenType.NUMBER,
                TokenType.STAR,
                TokenType.NUMBER,
                TokenType.EOF,
            ],
        )

    def test_minus_before_number_is_two_separate_tokens(self):
        # The tokenizer does NOT understand unary minus -- "-5" is a
        # MINUS token followed by a NUMBER token. This is intentional
        # (see module docstring) and is asserted here to lock in the
        # boundary between tokenizer and parser responsibilities.
        tokens = tokenize("-5")
        self.assertEqual(
            [t.type for t in tokens],
            [TokenType.MINUS, TokenType.NUMBER, TokenType.EOF],
        )


class TestTokenizeErrors(unittest.TestCase):
    def test_invalid_character_raises(self):
        with self.assertRaises(TokenizeError):
            tokenize("2 & 3")

    def test_invalid_character_message_includes_the_character(self):
        with self.assertRaises(TokenizeError) as ctx:
            tokenize("2 & 3")
        self.assertIn("&", str(ctx.exception))

    def test_number_with_two_decimal_points_raises(self):
        with self.assertRaises(TokenizeError):
            tokenize("3.1.4")

    def test_leading_decimal_point_raises(self):
        # By design, numbers must start with a digit (".5" is not
        # supported -- write "0.5" instead). This is a documented
        # limitation, tested explicitly so it can't silently change.
        with self.assertRaises(TokenizeError):
            tokenize(".5")

    def test_letters_raise(self):
        with self.assertRaises(TokenizeError):
            tokenize("2 + x")

    def test_scientific_notation_is_not_supported(self):
        # Also a documented limitation -- "1e10" is NOT parsed as
        # scientific notation; the trailing "e10" raises.
        with self.assertRaises(TokenizeError):
            tokenize("1e10")


if __name__ == "__main__":
    unittest.main()
