"""
evaluator.py
------------
Walks an AST (built by parser.py) and computes its numeric value.

Design choice: implemented as a simple recursive tree-walk rather
than, say, compiling to bytecode or using a visitor-pattern class
hierarchy. For a calculator's AST (three node types, no variables or
statements) a plain recursive function is the clearest and most
directly testable option -- there's no indirection between "what the
code does" and "what the grammar rule means."
"""

from __future__ import annotations

from .ast_nodes import ASTNode, Number, UnaryOp, BinaryOp
from .errors import EvaluationError

_BINARY_OPS = {
    "+": lambda a, b: a + b,
    "-": lambda a, b: a - b,
    "*": lambda a, b: a * b,
    "**": lambda a, b: a ** b,
    # "/" and "%" are handled separately below since they need their
    # own zero-check before doing the division.
}

_UNARY_OPS = {
    "-": lambda a: -a,
    "+": lambda a: +a,
}


def evaluate_ast(node: ASTNode) -> float:
    """Recursively evaluate an AST node to a single float.

    Raises:
        EvaluationError: for a runtime failure such as division or
            modulo by zero, or (defensively) an operator symbol the
            evaluator doesn't recognize.
    """
    if isinstance(node, Number):
        return float(node.value)

    if isinstance(node, UnaryOp):
        operand_value = evaluate_ast(node.operand)
        func = _UNARY_OPS.get(node.op)
        if func is None:
            raise EvaluationError(f"Unknown unary operator '{node.op}'.")
        return func(operand_value)

    if isinstance(node, BinaryOp):
        left_value = evaluate_ast(node.left)
        right_value = evaluate_ast(node.right)

        if node.op == "/":
            if right_value == 0:
                raise EvaluationError("Division by zero is undefined.")
            return left_value / right_value

        if node.op == "%":
            if right_value == 0:
                raise EvaluationError("Modulo by zero is undefined.")
            return left_value % right_value

        func = _BINARY_OPS.get(node.op)
        if func is None:
            raise EvaluationError(f"Unknown binary operator '{node.op}'.")
        return func(left_value, right_value)

    raise EvaluationError(f"Unknown AST node type: {type(node).__name__}")
