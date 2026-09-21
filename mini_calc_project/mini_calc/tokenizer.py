"""
tokenizer.py
------------
Lexical analysis: turns a raw expression string into a flat list of
Tokens.

Design choice: the tokenizer is deliberately "dumb" about grammar. It
does not know that "-5" might mean negative five, or that "2 3" is
invalid -- it only knows how to chop the string into the smallest
meaningful pieces (numbers, operators, parentheses) and flag any
character it doesn't recognize. Keeping grammar rules out of this
layer means it can be tested in complete isolation from the parser
(see test_tokenizer.py), and the parser can be tested against
hand-built token lists without needing the tokenizer to be correct.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum, auto
from typing import List, Optional

from .errors import TokenizeError


class TokenType(Enum):
    NUMBER = auto()
    PLUS = auto()
    MINUS = auto()
    STAR = auto()
    SLASH = auto()
    PERCENT = auto()
    DOUBLE_STAR = auto()
    LPAREN = auto()
    RPAREN = auto()
    EOF = auto()


@dataclass
class Token:
    type: TokenType
    value: Optional[float] = None


# Single-character tokens that need no special handling beyond a
# direct lookup. "*" is handled separately below since it needs to
# check for a following "*" to form DOUBLE_STAR first.
_SIMPLE_TOKENS = {
    "+": TokenType.PLUS,
    "-": TokenType.MINUS,
    "/": TokenType.SLASH,
    "%": TokenType.PERCENT,
    "(": TokenType.LPAREN,
    ")": TokenType.RPAREN,
}


def tokenize(text: str) -> List[Token]:
    """Convert an expression string into a list of Tokens, ending in EOF.

    Raises:
        TokenizeError: if the string contains a character (or
            malformed number) that cannot be turned into a valid token.
    """
    tokens: List[Token] = []
    i = 0
    n = len(text)

    while i < n:
        ch = text[i]

        if ch.isspace():
            i += 1
            continue

        if ch.isdigit():
            start = i
            seen_dot = False
            while i < n and (text[i].isdigit() or text[i] == "."):
                if text[i] == ".":
                    if seen_dot:
                        # A second "." in the same number is invalid,
                        # e.g. "3.1.4" -- report it clearly rather
                        # than silently truncating or misparsing.
                        raise TokenizeError(
                            f"Invalid number '{text[start:i + 1]}' at position {start}: "
                            "a number cannot contain more than one decimal point."
                        )
                    seen_dot = True
                i += 1
            number_text = text[start:i]
            tokens.append(Token(TokenType.NUMBER, float(number_text)))
            continue

        if ch == "*":
            if i + 1 < n and text[i + 1] == "*":
                tokens.append(Token(TokenType.DOUBLE_STAR))
                i += 2
            else:
                tokens.append(Token(TokenType.STAR))
                i += 1
            continue

        if ch in _SIMPLE_TOKENS:
            tokens.append(Token(_SIMPLE_TOKENS[ch]))
            i += 1
            continue

        # Anything else -- letters, symbols we don't support, a
        # leading "." with no digit before it, etc. -- is invalid.
        raise TokenizeError(f"Invalid character '{ch}' at position {i}.")

    tokens.append(Token(TokenType.EOF))
    return tokens
