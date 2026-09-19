"""
Tests for Zero-LLM Response Evaluator and Merge Engine (Module 5)
"""

import pytest
from arbiter.evaluator.structural import StructuralEvaluator
from arbiter.evaluator.code_eval import CodeQualityEvaluator
from arbiter.evaluator.coherence import CoherenceEvaluator
from arbiter.evaluator.merge_engine import MergeEngine
from arbiter.providers.multiplexer import CandidateResult


def test_code_evaluator_ast_parse():
    valid_python = """
```python
def fibonacci(n: int) -> int:
    if n <= 1:
        return n
    return fibonacci(n - 1) + fibonacci(n - 2)
```
"""
    score, details = CodeQualityEvaluator.evaluate(valid_python)
    assert score >= 0.85
    assert details["blocks_results"][0]["syntax_valid"] is True


def test_code_evaluator_syntax_error():
    broken_python = """
```python
def broken():
    if True
        return 42
```
"""
    score, details = CodeQualityEvaluator.evaluate(broken_python)
    assert score < 0.50
    assert details["blocks_results"][0]["syntax_valid"] is False


def test_coherence_hallucination_penalty():
    hedged_text = "As an AI language model, I cannot verify this information and I am only an AI."
    clean_text = "Here is the exact solution with step-by-step implementation."

    score_hedged, _ = CoherenceEvaluator.evaluate("How to do X?", hedged_text)
    score_clean, _ = CoherenceEvaluator.evaluate("How to do X?", clean_text)

    assert score_hedged < score_clean


def test_merge_engine_selection():
    prompt = "Write a python function to compute factorial"
    c1 = CandidateResult("mock", "m1")
    c1.text = "```python\ndef fact(n):\n    return 1 if n <= 1 else n * fact(n-1)\n```"
    c1.latency_ms = 100

    c2 = CandidateResult("mock", "m2")
    c2.text = "```python\ndef broken(n\n    return n\n```"  # Syntax error
    c2.latency_ms = 120

    merged, score, mode, meta = MergeEngine.merge_candidates(prompt, [c1, c2])
    assert "fact(n)" in merged
    assert score > 0.70
    assert mode in ("valid_code_winner", "highest_quality_score")
