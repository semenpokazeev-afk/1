"""
ARBITER Evaluation DSL Parser and AST Nodes (Bonus 1)
"""

from typing import List, Any, Optional
from arbiter.evaluator.dsl.lexer import Token, TokenType, DSLLexer


# AST Nodes
class ASTNode:
    pass


class LiteralNode(ASTNode):
    def __init__(self, value: Any):
        self.value = value


class IdentifierNode(ASTNode):
    def __init__(self, name: str):
        self.name = name


class MemberAccessNode(ASTNode):
    def __init__(self, obj_name: str, prop_name: str, index: Optional[int] = None):
        self.obj_name = obj_name
        self.prop_name = prop_name
        self.index = index


class FunctionCallNode(ASTNode):
    def __init__(self, name: str, args: List[ASTNode]):
        self.name = name
        self.args = args


class UnaryOpNode(ASTNode):
    def __init__(self, op: str, operand: ASTNode):
        self.op = op
        self.operand = operand


class BinaryOpNode(ASTNode):
    def __init__(self, left: ASTNode, op: str, right: ASTNode):
        self.left = left
        self.op = op
        self.right = right


class RuleNode(ASTNode):
    def __init__(self, name: str, when_expr: ASTNode, check_expr: ASTNode, score_delta: float):
        self.name = name
        self.when_expr = when_expr
        self.check_expr = check_expr
        self.score_delta = score_delta


class DSLParser:
    def __init__(self, tokens: List[Token]):
        self.tokens = tokens
        self.pos = 0

    def current(self) -> Token:
        return self.tokens[self.pos]

    def consume(self, expected_type: TokenType) -> Token:
        tok = self.current()
        if tok.type != expected_type:
            raise SyntaxError(f"Expected {expected_type} but got {tok.type} ('{tok.value}') at line {tok.line}")
        self.pos += 1
        return tok

    def match(self, *types: TokenType) -> bool:
        if self.current().type in types:
            self.pos += 1
            return True
        return False

    def parse_all_rules(self) -> List[RuleNode]:
        rules = []
        while self.current().type != TokenType.EOF:
            if self.current().type == TokenType.RULE:
                rules.append(self.parse_rule())
            else:
                self.pos += 1
        return rules

    def parse_rule(self) -> RuleNode:
        self.consume(TokenType.RULE)
        name_tok = self.consume(TokenType.STRING)
        rule_name = name_tok.value
        self.consume(TokenType.LBRACE)

        when_expr = None
        check_expr = None
        score_delta = 0.0

        while self.current().type != TokenType.RBRACE and self.current().type != TokenType.EOF:
            tok = self.current()
            if tok.type == TokenType.WHEN:
                self.consume(TokenType.WHEN)
                when_expr = self.parse_expression()
            elif tok.type == TokenType.CHECK:
                self.consume(TokenType.CHECK)
                check_expr = self.parse_expression()
            elif tok.type == TokenType.SCORE:
                self.consume(TokenType.SCORE)
                # Could be '+', '-', or number
                sign = 1.0
                if self.match(TokenType.PLUS):
                    sign = 1.0
                elif self.match(TokenType.MINUS):
                    sign = -1.0
                num_tok = self.consume(TokenType.NUMBER)
                score_delta = sign * float(num_tok.value)
            else:
                self.pos += 1

        self.consume(TokenType.RBRACE)
        return RuleNode(
            name=rule_name,
            when_expr=when_expr or LiteralNode(True),
            check_expr=check_expr or LiteralNode(True),
            score_delta=score_delta
        )

    def parse_expression(self) -> ASTNode:
        return self.parse_comparison()

    def parse_comparison(self) -> ASTNode:
        left = self.parse_term()
        while self.current().type in (TokenType.EQUALS, TokenType.NOT_EQUALS, TokenType.LT, TokenType.GT, TokenType.LTE, TokenType.GTE):
            op_tok = self.current()
            self.pos += 1
            right = self.parse_term()
            left = BinaryOpNode(left, op_tok.value, right)
        return left

    def parse_term(self) -> ASTNode:
        left = self.parse_factor()
        while self.current().type in (TokenType.PLUS, TokenType.MINUS):
            op_tok = self.current()
            self.pos += 1
            right = self.parse_factor()
            left = BinaryOpNode(left, op_tok.value, right)
        return left

    def parse_factor(self) -> ASTNode:
        left = self.parse_unary()
        while self.current().type in (TokenType.MULTIPLY, TokenType.DIVIDE):
            op_tok = self.current()
            self.pos += 1
            right = self.parse_unary()
            left = BinaryOpNode(left, op_tok.value, right)
        return left

    def parse_unary(self) -> ASTNode:
        if self.match(TokenType.NOT):
            operand = self.parse_unary()
            return UnaryOpNode("not", operand)
        return self.parse_primary()

    def parse_primary(self) -> ASTNode:
        tok = self.current()

        if self.match(TokenType.TRUE):
            return LiteralNode(True)
        if self.match(TokenType.FALSE):
            return LiteralNode(False)
        if tok.type == TokenType.NUMBER:
            self.pos += 1
            return LiteralNode(tok.value)
        if tok.type == TokenType.STRING:
            self.pos += 1
            return LiteralNode(tok.value)
        if tok.type == TokenType.LBRACKET:
            # Array literal
            self.consume(TokenType.LBRACKET)
            elements = []
            while self.current().type != TokenType.RBRACKET and self.current().type != TokenType.EOF:
                elements.append(self.parse_expression())
                if not self.match(TokenType.COMMA):
                    break
            self.consume(TokenType.RBRACKET)
            return LiteralNode(elements)
        if tok.type == TokenType.LPAREN:
            self.consume(TokenType.LPAREN)
            expr = self.parse_expression()
            self.consume(TokenType.RPAREN)
            return expr

        if tok.type == TokenType.IDENTIFIER:
            ident_name = tok.value
            self.pos += 1

            # Function call
            if self.match(TokenType.LPAREN):
                args = []
                while self.current().type != TokenType.RPAREN and self.current().type != TokenType.EOF:
                    args.append(self.parse_expression())
                    if not self.match(TokenType.COMMA):
                        break
                self.consume(TokenType.RPAREN)
                return FunctionCallNode(ident_name, args)

            # Member access: e.g. response.text or response.code_blocks[0]
            if self.match(TokenType.DOT):
                prop_tok = self.consume(TokenType.IDENTIFIER)
                index = None
                if self.match(TokenType.LBRACKET):
                    idx_tok = self.consume(TokenType.NUMBER)
                    index = int(idx_tok.value)
                    self.consume(TokenType.RBRACKET)
                return MemberAccessNode(ident_name, prop_tok.value, index)

            return IdentifierNode(ident_name)

        raise SyntaxError(f"Unexpected token {tok.type} ('{tok.value}') at line {tok.line}")
