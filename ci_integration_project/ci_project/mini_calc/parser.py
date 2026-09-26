"""
parser.py
---------
A recursive-descent parser that turns a list of Tokens into an AST.

Grammar (loosest to tightest precedence -- see test_parser.py's
module docstring for the full formal grammar and the reasoning behind
matching Python's own precedence rules):

    expr     := term (('+' | '-') term)*
    term     := unary (('*' | '/' | '%') unary)*
    unary    := ('-' | '+') unary | power
    power    := primary ('**' unary)?      # right-associative
    primary  := NUMBER | '(' expr ')'

Each grammar rule above is implemented as one method below with a
matching name, which is the standard structure for a recursive-descent
parser -- it makes the code and the grammar easy to compare side by
side, and makes it obvious where to look when a specific precedence
level needs to change.
"""

from __future__ import annotations

from typing import List

from .ast_nodes import ASTNode, Number, UnaryOp, BinaryOp
from .errors import ParseError
from .tokenizer import Token, TokenType, tokenize

# Maps each token type to its operator symbol. Defined once at module
# level (rather than rebuilt inside _term() on every loop iteration)
# for both clarity and a small efficiency win.
_TERM_OPERATORS = {
    TokenType.STAR: "*",
    TokenType.SLASH: "/",
    TokenType.PERCENT: "%",
}


class Parser:
    """Parses a fixed list of Tokens (produced by the tokenizer, or
    built by hand in tests) into a single ASTNode."""

    def __init__(self, tokens: List[Token]):
        self._tokens = tokens
        self._pos = 0

    # ------------------------------------------------------------------
    # Token-stream helpers
    # ------------------------------------------------------------------
    def _current(self) -> Token:
        return self._tokens[self._pos]

    def _advance(self) -> Token:
        token = self._tokens[self._pos]
        self._pos += 1
        return token

    def _expect(self, token_type: TokenType, what: str) -> Token:
        if self._current().type != token_type:
            raise ParseError(
                f"Expected {what} but found {self._current().type.name} "
                f"at token position {self._pos}."
            )
        return self._advance()

    # ------------------------------------------------------------------
    # Public entry point
    # ------------------------------------------------------------------
    def parse(self) -> ASTNode:
        """Parse the full token list into one ASTNode.

        Raises ParseError if the tokens don't form a complete, valid
        expression, or if there are leftover tokens afterward (e.g.
        an extra ')' with no matching '(').
        """
        node = self._expr()
        if self._current().type != TokenType.EOF:
            raise ParseError(
                f"Unexpected {self._current().type.name} after a complete "
                f"expression, at token position {self._pos}."
            )
        return node

    # ------------------------------------------------------------------
    # Grammar rules (one method per rule, loosest to tightest binding)
    # ------------------------------------------------------------------
    def _expr(self) -> ASTNode:
        """expr := term (('+' | '-') term)*"""
        node = self._term()
        while self._current().type in (TokenType.PLUS, TokenType.MINUS):
            op_token = self._advance()
            op = "+" if op_token.type == TokenType.PLUS else "-"
            right = self._term()
            node = BinaryOp(op, node, right)
        return node

    def _term(self) -> ASTNode:
        """term := unary (('*' | '/' | '%') unary)*"""
        node = self._unary()
        while self._current().type in (TokenType.STAR, TokenType.SLASH, TokenType.PERCENT):
            op_token = self._advance()
            op = _TERM_OPERATORS[op_token.type]
            right = self._unary()
            node = BinaryOp(op, node, right)
        return node

    def _unary(self) -> ASTNode:
        """unary := ('-' | '+') unary | power"""
        if self._current().type in (TokenType.PLUS, TokenType.MINUS):
            op_token = self._advance()
            op = "+" if op_token.type == TokenType.PLUS else "-"
            operand = self._unary()  # recurse, so "--5" and "-+5" both work
            return UnaryOp(op, operand)
        return self._power()

    def _power(self) -> ASTNode:
        """power := primary ('**' unary)?   (right-associative)"""
        base = self._primary()
        if self._current().type == TokenType.DOUBLE_STAR:
            self._advance()
            # The exponent recurses into `unary` (not `power`), which is
            # what lets "2**-1" and the right-associative chain
            # "2**3**2" both parse correctly -- see test_parser.py.
            exponent = self._unary()
            return BinaryOp("**", base, exponent)
        return base

    def _primary(self) -> ASTNode:
        """primary := NUMBER | '(' expr ')'"""
        token = self._current()

        if token.type == TokenType.NUMBER:
            self._advance()
            return Number(token.value)

        if token.type == TokenType.LPAREN:
            self._advance()
            node = self._expr()
            self._expect(TokenType.RPAREN, "')'")
            return node

        raise ParseError(
            f"Expected a number or '(' but found {token.type.name} "
            f"at token position {self._pos}."
        )


def parse(text: str) -> ASTNode:
    """Convenience function: tokenize + parse a raw expression string."""
    return Parser(tokenize(text)).parse()
