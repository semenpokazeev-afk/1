"""
Tests for Custom Evaluation DSL (Bonus 1)
"""

import pytest
from arbiter.evaluator.dsl import DSLLexer, DSLParser, DSLInterpreter


def test_dsl_lexer_and_parser():
    rule_src = """
    rule "code_must_parse" {
      when task_category == "code_generation"
      check ast_parse(response.code_blocks[0]) == true
      score +2.0
    }
    """
    lexer = DSLLexer(rule_src)
    tokens = lexer.tokenize()
    parser = DSLParser(tokens)
    rules = parser.parse_all_rules()

    assert len(rules) == 1
    assert rules[0].name == "code_must_parse"
    assert rules[0].score_delta == 2.0


def test_dsl_interpreter_execution():
    rules_src = """
    rule "code_must_parse" {
      when task_category == "code_generation"
      check ast_parse(response.code_blocks[0]) == true
      score +1.5
    }

    rule "no_hallucination_markers" {
      when true
      check not contains(response.text, ["as an AI", "I cannot verify"])
      score +0.5
    }
    """
    interpreter = DSLInterpreter()

    # Context with valid python and no hallucination
    ctx_good = {
        "task_category": "code_generation",
        "response": {
            "text": "Here is the code: def foo(): return 1",
            "code_blocks": ["def foo(): return 1"]
        }
    }
    delta, applied = interpreter.evaluate_rules(rules_src, ctx_good)
    assert delta == 2.0
    assert len(applied) == 2

    # Context with hallucination and broken python
    ctx_bad = {
        "task_category": "code_generation",
        "response": {
            "text": "As an AI, I cannot verify this: def broken(",
            "code_blocks": ["def broken("]
        }
    }
    delta_bad, applied_bad = interpreter.evaluate_rules(rules_src, ctx_bad)
    assert delta_bad == 0.0
    assert len(applied_bad) == 0
