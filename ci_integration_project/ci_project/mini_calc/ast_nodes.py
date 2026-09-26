"""
ast_nodes.py
------------
The Abstract Syntax Tree (AST) node types produced by the parser and
consumed by the evaluator.

Using @dataclass gives each node value-based equality "for free" (two
Number(2) instances compare equal), which is what makes the parser
tests readable -- a test can assert `parse("2+3") == BinaryOp("+",
Number(2), Number(3))` instead of manually walking the tree.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Union


@dataclass
class Number:
    """A literal numeric value, e.g. the `5` in `5 + 1`."""
    value: float


@dataclass
class UnaryOp:
    """A prefix operator applied to a single operand, e.g. `-5` or `+5`."""
    op: str  # '-' or '+'
    operand: "ASTNode"


@dataclass
class BinaryOp:
    """An infix operator applied to two operands, e.g. `2 + 3`."""
    op: str  # '+', '-', '*', '/', '%', or '**'
    left: "ASTNode"
    right: "ASTNode"


ASTNode = Union[Number, UnaryOp, BinaryOp]
