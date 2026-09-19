"""
ARBITER Code Quality Evaluator (Module 5)
Performs multi-language AST parsing, syntax validation, and cyclomatic complexity scoring without LLM.
"""

import re
import ast
from typing import Dict, Any, Tuple, List


class CodeQualityEvaluator:
    """
    Evaluates code snippets inside responses using AST parsers and lexical linting.
    """

    @staticmethod
    def extract_code_blocks(text: str) -> List[Tuple[str, str]]:
        """
        Extracts (language, code_snippet) pairs from markdown code blocks.
        """
        pattern = r"```([a-zA-Z0-9_\-+]*)\n([\s\S]*?)```"
        matches = re.findall(pattern, text)
        return [(lang.strip().lower(), code) for lang, code in matches]

    @classmethod
    def evaluate(cls, response_text: str) -> Tuple[float, Dict[str, Any]]:
        blocks = cls.extract_code_blocks(response_text)
        if not blocks:
            # If no code block in response, neutral/pass
            return 0.5, {"has_code": False}

        scores = []
        details = {"has_code": True, "blocks_count": len(blocks), "blocks_results": []}

        for lang, code in blocks:
            block_score, block_detail = cls._evaluate_single_block(lang, code)
            scores.append(block_score)
            details["blocks_results"].append(block_detail)

        avg_score = sum(scores) / len(scores) if scores else 0.5
        return round(avg_score, 4), details

    @classmethod
    def _evaluate_single_block(cls, lang: str, code: str) -> Tuple[float, Dict[str, Any]]:
        detail: Dict[str, Any] = {"lang": lang, "lines": len(code.splitlines())}

        # 1. Python AST parsing
        if lang in ("python", "py", ""):
            try:
                tree = ast.parse(code)
                detail["syntax_valid"] = True
                detail["error"] = None

                # Compute cyclomatic complexity
                complexity = cls._calculate_ast_complexity(tree)
                detail["cyclomatic_complexity"] = complexity

                # Check imports presence
                has_imports = any(isinstance(node, (ast.Import, ast.ImportFrom)) for node in ast.walk(tree))
                detail["has_imports"] = has_imports

                # Score: 1.0 for valid parse, slightly penalized if extreme complexity (> 25)
                score = 1.0
                if complexity > 25:
                    score -= 0.15
                return score, detail
            except SyntaxError as e:
                # If language was empty, it might be JS or bash, don't penalize as strictly
                if lang == "":
                    # Try fallback JS/general validator
                    return cls._evaluate_general_syntax(code, detail)
                detail["syntax_valid"] = False
                detail["error"] = f"SyntaxError at line {e.lineno}: {e.msg}"
                return 0.20, detail
            except Exception as e:
                detail["syntax_valid"] = False
                detail["error"] = str(e)
                return 0.30, detail

        # 2. JavaScript / TypeScript / Other Languages
        return cls._evaluate_general_syntax(code, detail)

    @staticmethod
    def _calculate_ast_complexity(tree: ast.AST) -> int:
        """
        Estimates cyclomatic complexity: 1 + count of decision points (if, for, while, try, bool_op).
        """
        complexity = 1
        for node in ast.walk(tree):
            if isinstance(node, (ast.If, ast.For, ast.While, ast.ExceptHandler, ast.With)):
                complexity += 1
            elif isinstance(node, ast.BoolOp):
                complexity += len(node.values) - 1
        return complexity

    @staticmethod
    def _evaluate_general_syntax(code: str, detail: Dict[str, Any]) -> Tuple[float, Dict[str, Any]]:
        """
        Syntactic integrity check for JS, C++, Go, etc. using balanced brackets, quotes, and indentation.
        """
        score = 1.0
        # Check matching curly braces, parens, brackets
        stack = []
        mapping = {'}': '{', ')': '(', ']': '['}
        quotes = {'"': '"', "'": "'"}
        
        in_string = None
        for i, ch in enumerate(code):
            if in_string:
                if ch == in_string and (i == 0 or code[i-1] != '\\'):
                    in_string = None
                continue
            if ch in quotes:
                in_string = ch
            elif ch in mapping.values():
                stack.append(ch)
            elif ch in mapping.keys():
                if not stack or stack[-1] != mapping[ch]:
                    score -= 0.4
                    detail["unbalanced_braces"] = True
                    break
                stack.pop()

        if stack and "unbalanced_braces" not in detail:
            score -= 0.3
            detail["unclosed_braces"] = True

        detail["syntax_valid"] = score > 0.6
        return max(0.2, min(1.0, score)), detail
