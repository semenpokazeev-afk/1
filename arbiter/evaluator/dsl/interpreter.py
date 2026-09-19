"""
ARBITER Evaluation DSL Interpreter (Bonus 1)
Executes AST rules against an execution context and returns adjusted quality scores.
"""

import re
import ast
from typing import Dict, Any, List, Tuple
from arbiter.evaluator.dsl.lexer import DSLLexer
from arbiter.evaluator.dsl.parser import (
    DSLParser, ASTNode, LiteralNode, IdentifierNode,
    MemberAccessNode, FunctionCallNode, UnaryOpNode, BinaryOpNode, RuleNode
)


class DSLInterpreter:
    """
    Executes compiled DSL rules on evaluation contexts.
    """

    def __init__(self):
        self.builtins = {
            "ast_parse": self._builtin_ast_parse,
            "contains": self._builtin_contains,
            "len": lambda x: len(x) if x is not None else 0
        }

    def evaluate_rules(self, rules_source: str, context: Dict[str, Any]) -> Tuple[float, List[Dict[str, Any]]]:
        """
        Parses rules_source and runs against context.
        Returns: (total_score_delta, triggered_rules_summary)
        """
        lexer = DSLLexer(rules_source)
        tokens = lexer.tokenize()
        parser = DSLParser(tokens)
        rules = parser.parse_all_rules()

        score_delta = 0.0
        applied_rules = []

        for rule in rules:
            # 1. Evaluate 'when' condition
            when_val = self._eval_node(rule.when_expr, context)
            if not when_val:
                continue

            # 2. Evaluate 'check' condition
            check_val = self._eval_node(rule.check_expr, context)
            if check_val:
                score_delta += rule.score_delta
                applied_rules.append({
                    "rule": rule.name,
                    "passed": True,
                    "delta": rule.score_delta
                })

        return score_delta, applied_rules

    def _eval_node(self, node: ASTNode, ctx: Dict[str, Any]) -> Any:
        if isinstance(node, LiteralNode):
            if isinstance(node.value, list):
                return [self._eval_node(elem, ctx) for elem in node.value]
            return node.value

        if isinstance(node, IdentifierNode):
            return ctx.get(node.name)

        if isinstance(node, MemberAccessNode):
            obj = ctx.get(node.obj_name)
            if obj is None:
                return None
            val = getattr(obj, node.prop_name, None) if not isinstance(obj, dict) else obj.get(node.prop_name)
            if node.index is not None and isinstance(val, (list, tuple)):
                if 0 <= node.index < len(val):
                    return val[node.index]
                return ""
            return val

        if isinstance(node, UnaryOpNode):
            val = self._eval_node(node.operand, ctx)
            if node.op == "not":
                return not bool(val)
            elif node.op == "-":
                return -val
            return val

        if isinstance(node, BinaryOpNode):
            left = self._eval_node(node.left, ctx)
            right = self._eval_node(node.right, ctx)
            return self._eval_binary(left, node.op, right)

        if isinstance(node, FunctionCallNode):
            func = self.builtins.get(node.name)
            if not func:
                raise NameError(f"Unknown DSL function: {node.name}")
            args = [self._eval_node(a, ctx) for a in node.args]
            return func(*args)

        return None

    def _eval_binary(self, left: Any, op: str, right: Any) -> Any:
        if op == "==":
            return left == right
        elif op == "!=":
            return left != right
        elif op == "<":
            return left < right
        elif op == ">":
            return left > right
        elif op == "<=":
            return left <= right
        elif op == ">=":
            return left >= right
        elif op == "+":
            return left + right
        elif op == "-":
            return left - right
        elif op == "*":
            return left * right
        elif op == "/":
            return left / right if right != 0 else 0
        return False

    @staticmethod
    def _builtin_ast_parse(code: str) -> bool:
        if not code or not isinstance(code, str):
            return False
        try:
            ast.parse(code)
            return True
        except Exception:
            return False

    @staticmethod
    def _builtin_contains(text: str, targets: Any) -> bool:
        if not text or not targets:
            return False
        if isinstance(targets, list):
            return any(t.lower() in text.lower() for t in targets)
        return str(targets).lower() in text.lower()
