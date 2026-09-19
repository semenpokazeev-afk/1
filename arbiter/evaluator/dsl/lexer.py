"""
ARBITER Evaluation DSL Lexer (Bonus 1)
Tokenizes custom evaluation DSL source code.
"""

import re
from enum import Enum, auto
from typing import List, NamedTuple, Any


class TokenType(Enum):
    RULE = auto()
    STRING = auto()
    LBRACE = auto()
    RBRACE = auto()
    WHEN = auto()
    CHECK = auto()
    SCORE = auto()
    IDENTIFIER = auto()
    NUMBER = auto()
    EQUALS = auto()
    NOT_EQUALS = auto()
    LT = auto()
    GT = auto()
    LTE = auto()
    GTE = auto()
    PLUS = auto()
    MINUS = auto()
    MULTIPLY = auto()
    DIVIDE = auto()
    LPAREN = auto()
    RPAREN = auto()
    LBRACKET = auto()
    RBRACKET = auto()
    COMMA = auto()
    DOT = auto()
    TRUE = auto()
    FALSE = auto()
    NOT = auto()
    EOF = auto()


class Token(NamedTuple):
    type: TokenType
    value: Any
    line: int


KEYWORDS = {
    "rule": TokenType.RULE,
    "when": TokenType.WHEN,
    "check": TokenType.CHECK,
    "score": TokenType.SCORE,
    "true": TokenType.TRUE,
    "false": TokenType.FALSE,
    "not": TokenType.NOT,
}


class DSLLexer:
    def __init__(self, code: str):
        self.code = code
        self.pos = 0
        self.line = 1
        self.length = len(code)

    def tokenize(self) -> List[Token]:
        tokens = []
        while self.pos < self.length:
            ch = self.code[self.pos]

            if ch in " \t\r":
                self.pos += 1
                continue
            elif ch == "\n":
                self.line += 1
                self.pos += 1
                continue
            elif ch == "#" or (ch == "/" and self.pos + 1 < self.length and self.code[self.pos+1] == "/"):
                # Single line comment
                while self.pos < self.length and self.code[self.pos] != "\n":
                    self.pos += 1
                continue
            elif ch == "{":
                tokens.append(Token(TokenType.LBRACE, "{", self.line))
                self.pos += 1
            elif ch == "}":
                tokens.append(Token(TokenType.RBRACE, "}", self.line))
                self.pos += 1
            elif ch == "(":
                tokens.append(Token(TokenType.LPAREN, "(", self.line))
                self.pos += 1
            elif ch == ")":
                tokens.append(Token(TokenType.RPAREN, ")", self.line))
                self.pos += 1
            elif ch == "[":
                tokens.append(Token(TokenType.LBRACKET, "[", self.line))
                self.pos += 1
            elif ch == "]":
                tokens.append(Token(TokenType.RBRACKET, "]", self.line))
                self.pos += 1
            elif ch == ",":
                tokens.append(Token(TokenType.COMMA, ",", self.line))
                self.pos += 1
            elif ch == ".":
                tokens.append(Token(TokenType.DOT, ".", self.line))
                self.pos += 1
            elif ch == "+":
                tokens.append(Token(TokenType.PLUS, "+", self.line))
                self.pos += 1
            elif ch == "-":
                tokens.append(Token(TokenType.MINUS, "-", self.line))
                self.pos += 1
            elif ch == "*":
                tokens.append(Token(TokenType.MULTIPLY, "*", self.line))
                self.pos += 1
            elif ch == "/":
                tokens.append(Token(TokenType.DIVIDE, "/", self.line))
                self.pos += 1
            elif ch == "=":
                if self.pos + 1 < self.length and self.code[self.pos+1] == "=":
                    tokens.append(Token(TokenType.EQUALS, "==", self.line))
                    self.pos += 2
                else:
                    self.pos += 1
            elif ch == "!":
                if self.pos + 1 < self.length and self.code[self.pos+1] == "=":
                    tokens.append(Token(TokenType.NOT_EQUALS, "!=", self.line))
                    self.pos += 2
                else:
                    tokens.append(Token(TokenType.NOT, "not", self.line))
                    self.pos += 1
            elif ch == "<":
                if self.pos + 1 < self.length and self.code[self.pos+1] == "=":
                    tokens.append(Token(TokenType.LTE, "<=", self.line))
                    self.pos += 2
                else:
                    tokens.append(Token(TokenType.LT, "<", self.line))
                    self.pos += 1
            elif ch == ">":
                if self.pos + 1 < self.length and self.code[self.pos+1] == "=":
                    tokens.append(Token(TokenType.GTE, ">=", self.line))
                    self.pos += 2
                else:
                    tokens.append(Token(TokenType.GT, ">", self.line))
                    self.pos += 1
            elif ch in ('"', "'"):
                quote = ch
                start = self.pos + 1
                self.pos += 1
                val = ""
                while self.pos < self.length and self.code[self.pos] != quote:
                    val += self.code[self.pos]
                    self.pos += 1
                self.pos += 1  # Skip closing quote
                tokens.append(Token(TokenType.STRING, val, self.line))
            elif ch.isdigit():
                start = self.pos
                while self.pos < self.length and (self.code[self.pos].isdigit() or self.code[self.pos] == "."):
                    self.pos += 1
                num_str = self.code[start:self.pos]
                num_val = float(num_str) if "." in num_str else int(num_str)
                tokens.append(Token(TokenType.NUMBER, num_val, self.line))
            elif ch.isalpha() or ch == "_":
                start = self.pos
                while self.pos < self.length and (self.code[self.pos].isalnum() or self.code[self.pos] == "_"):
                    self.pos += 1
                word = self.code[start:self.pos]
                token_type = KEYWORDS.get(word.lower(), TokenType.IDENTIFIER)
                tokens.append(Token(token_type, word, self.line))
            else:
                self.pos += 1

        tokens.append(Token(TokenType.EOF, None, self.line))
        return tokens
