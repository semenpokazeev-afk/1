"""
ARBITER Structural Quality Evaluator (Module 5)
Evaluates completeness, formatting integrity (markdown, lists, brackets), and length appropriateness without LLM.
"""

import re
from typing import Dict, Any, Tuple


class StructuralEvaluator:
    """
    Evaluates markdown structure, formatting syntax, and verbosity without calling any LLM.
    Returns a score between [0.0, 1.0].
    """

    @staticmethod
    def evaluate(prompt: str, response: str) -> Tuple[float, Dict[str, Any]]:
        score = 0.5  # Base neutral score
        details: Dict[str, Any] = {}

        if not response or not response.strip():
            return 0.0, {"error": "Empty response"}

        resp_len = len(response.strip())
        words = re.findall(r"\w+", response)
        word_count = len(words)

        # 1. Length penalties and rewards
        # Responses < 20 words usually too terse unless simple greeting
        if word_count < 10:
            length_score = 0.3
        elif 25 <= word_count <= 800:
            length_score = 1.0
        elif word_count > 1500:
            # Overly verbose / run-on
            length_score = 0.7
        else:
            length_score = 0.85
        details["length_score"] = length_score

        # 2. Markdown formatting integrity
        formatting_score = 1.0
        # Check code block fences balance (even number of ```)
        fence_count = response.count("```")
        if fence_count % 2 != 0:
            formatting_score -= 0.35  # Broken unclosed code fence
            details["broken_code_fence"] = True

        # Check balanced brackets/parentheses
        brackets_balanced = True
        stack = []
        mapping = {')': '(', ']': '[', '}': '{'}
        for ch in response:
            if ch in mapping.values():
                stack.append(ch)
            elif ch in mapping.keys():
                if not stack or stack[-1] != mapping[ch]:
                    brackets_balanced = False
                    break
                stack.pop()
        
        # If bracket imbalance is severe
        if len(stack) > 3 or not brackets_balanced:
            formatting_score -= 0.15
            details["unbalanced_brackets"] = True

        # Presence of structured elements (lists, headers)
        has_lists = bool(re.search(r"^\s*([*\-+]|\d+\.)\s+", response, re.MULTILINE))
        has_headers = bool(re.search(r"^#{1,4}\s+", response, re.MULTILINE))
        if has_lists or has_headers:
            formatting_score = min(1.0, formatting_score + 0.1)

        details["formatting_score"] = max(0.0, min(1.0, formatting_score))

        # 3. Completeness check
        # If prompt asked for "X things" or numbered items, did response deliver?
        completeness_score = 1.0
        number_match = re.search(r"\b(\d+)\s+(ways|steps|tips|reasons|examples|пункт|способ|шаг|причин|пример)\b", prompt.lower())
        if number_match:
            expected_n = int(number_match.group(1))
            found_items = len(re.findall(r"^\s*(\d+\.|\*|\-)\s+", response, re.MULTILINE))
            if found_items < expected_n:
                completeness_score = max(0.4, found_items / max(expected_n, 1))
        details["completeness_score"] = completeness_score

        # Combine
        total_structural = (
            0.35 * length_score +
            0.35 * details["formatting_score"] +
            0.30 * completeness_score
        )
        return round(total_structural, 4), details
