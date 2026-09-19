"""
Tests for Zero-LLM Task Classifier (Module 2)
"""

import time
import pytest
from arbiter.models.schemas import ChatMessage
from arbiter.models.types import TaskCategory
from arbiter.classifier import TaskClassifier


@pytest.fixture(scope="session")
def classifier():
    c = TaskClassifier()
    # Warm-up cold start imports & regex caches
    c.classify_messages([ChatMessage(role="user", content="warmup")])
    return c


def test_code_generation_classification(classifier):
    msg = [ChatMessage(role="user", content="напиши функцию на python для быстрой сортировки списка")]
    start = time.monotonic()
    result = classifier.classify_messages(msg)
    elapsed_ms = (time.monotonic() - start) * 1000

    assert result.category == TaskCategory.CODE_GENERATION
    assert elapsed_ms < 50.0  # Challenge requirement: < 50ms overhead


def test_edge_case_code_vs_translation(classifier):
    # Edge case from prompt: "напиши код который переводит текст" -> Must be code_generation
    msg = [ChatMessage(role="user", content="напиши код который переводит текст с английского на немецкий")]
    result = classifier.classify_messages(msg)
    assert result.category == TaskCategory.CODE_GENERATION


def test_code_review_classification(classifier):
    msg = [
        ChatMessage(
            role="user",
            content="найди баг и сделай код ревью следующего фрагмента:\n```python\ndef bad(x):\n  return x[99]\n```"
        )
    ]
    result = classifier.classify_messages(msg)
    assert result.category == TaskCategory.CODE_REVIEW


def test_translation_classification(classifier):
    msg = [ChatMessage(role="user", content="переведи это техническое описание на русский язык")]
    result = classifier.classify_messages(msg)
    assert result.category == TaskCategory.TRANSLATION


def test_data_analysis_classification(classifier):
    msg = [ChatMessage(role="user", content="SELECT department_id, AVG(salary) FROM employees GROUP BY department_id")]
    result = classifier.classify_messages(msg)
    assert result.category == TaskCategory.DATA_ANALYSIS


def test_summarization_classification(classifier):
    msg = [ChatMessage(role="user", content="суммаризируй этот длинный текст в 3 тезиса и выдели главное")]
    result = classifier.classify_messages(msg)
    assert result.category == TaskCategory.SUMMARIZATION


def test_reasoning_classification(classifier):
    msg = [ChatMessage(role="user", content="реши логическую задачу: у фермера есть волк, коза и капуста")]
    result = classifier.classify_messages(msg)
    assert result.category == TaskCategory.REASONING


def test_conversation_classification(classifier):
    msg = [ChatMessage(role="user", content="Привет! Как твои дела сегодня?")]
    result = classifier.classify_messages(msg)
    assert result.category == TaskCategory.CONVERSATION
