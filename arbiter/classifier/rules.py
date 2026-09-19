"""
ARBITER Rule-Based Classification Engine (Module 2, Tier 1)
High-performance, zero-latency (0ms) multilingual (RU/EN) pattern matcher.
"""

import re
from typing import Dict, Any, Optional
from arbiter.models.types import TaskCategory, ClassificationResult


class RuleBasedClassifier:
    """
    Tier 1 classifier executing deterministic regex rules and feature thresholds.
    """

    def __init__(self):
        # Code generation patterns (English and Russian)
        self.code_gen_patterns = [
            r"\b(write|create|implement|generate|code|program|script|function|class)\b.*\b(code|function|class|script|api|algorithm|component)\b",
            r"\b(напиши|создай|реализуй|сделай|напиши код|напиши скрипт|разработай)\b.*\b(код|скрипт|функци|класс|алгоритм|парсер|компонент|эндпоинт|программ)\b",
            r"^```[a-zA-Z0-9_\-+]*\s*$",  # Pure code snippet requested
            r"\b(python|javascript|typescript|golang|c\+\+|rust|java|html|css|sql|bash)\b.*\b(код|функци|скрипт|пример)\b",
            r"\b(write a python|write a function|implement a class|generate an api)\b"
        ]

        # Code review patterns
        self.code_review_patterns = [
            r"\b(review|debug|refactor|fix|optimize|explain this code|find bug|why error|syntax error)\b",
            r"\b(проверь код|код ревью|найди баг|почему ошибка|исправь ошибку|рефакторинг|что не так с кодом|оптимизируй код)\b",
            r"\b(code review|lint|profiling)\b"
        ]

        # Translation patterns
        self.translation_patterns = [
            r"\b(translate|translation)\b.*\b(to|into|from)\b",
            r"\b(переведи|перевод|как сказать на|переведи на|переведи с)\b",
            r"\b(how to say .* in (english|russian|spanish|german|french|chinese|japanese))\b",
            r"\b(перевод текста|переведи предложение)\b"
        ]

        # Data analysis & SQL patterns
        self.data_patterns = [
            r"\b(SELECT\s+.*\s+FROM|INSERT\s+INTO|UPDATE\s+.*\s+SET|GROUP\s+BY|ORDER\s+BY|INNER\s+JOIN)\b",
            r"\b(dataframe|pandas|numpy|sql query|csv data|correlation|p-value|linear regression)\b",
            r"\b(анализ данных|сделай sql запрос|посчитай метрику|построй запрос к бд|сводная таблица|статистика)\b"
        ]

        # Summarization patterns
        self.summarization_patterns = [
            r"\b(summarize|summary|tl;?dr|brief overview|key takeaways|bullet points summary)\b",
            r"\b(суммаризируй|краткое содержание|выдели главное|перескажи кратко|сделай конспект|тезисы|суть статьи)\b"
        ]

        # Reasoning & Math patterns
        self.reasoning_patterns = [
            r"\b(solve|puzzle|riddle|proof|prove that|calculate|equation|probability|theorem)\b",
            r"\b(реши задачу|докажи теорему|логическая загадка|головоломка|сколько будет|вычисли вероятность|найди x|уравнение)\b",
            r"\b(step by step deduction|logical puzzle)\b"
        ]

        # Creative writing patterns
        self.creative_patterns = [
            r"\b(write a story|poem|poetry|essay|fiction|creative tale|script for a movie)\b",
            r"\b(сочини историю|напиши стих|стихотворение|рассказ|эссе|сказка|сценарий|художественный текст)\b"
        ]

    def classify(self, features: Dict[str, Any]) -> Optional[ClassificationResult]:
        """
        Runs rule-based classification against extracted features.
        Returns ClassificationResult or None if no high-confidence rule matched.
        """
        # 1. Multimodal check
        if features.get("is_multimodal", False):
            return ClassificationResult(
                category=TaskCategory.MULTIMODAL,
                confidence=0.99,
                method="rule_based",
                features=features
            )

        full_text = features.get("full_text", "")
        last_text = features.get("last_message_text", "")
        text_to_eval = (last_text + "\n" + full_text).lower()

        # 2. System prompt check
        if features.get("has_system_message", False) and features.get("history_turn_count", 0) <= 1:
            if re.search(r"\b(you are|act as|system prompt|твоя роль|действуй как)\b", text_to_eval):
                return ClassificationResult(
                    category=TaskCategory.SYSTEM_PROMPT,
                    confidence=0.95,
                    method="rule_based",
                    features=features
                )

        # 3. Edge Case: "напиши код который переводит" -> Priority CODE_GENERATION over TRANSLATION
        has_code_keywords = any(re.search(pat, text_to_eval) for pat in self.code_gen_patterns)
        
        # 4. Code Review vs Code Generation
        has_code_blocks = features.get("has_code_blocks", False) or features.get("code_ratio", 0) > 0.3
        has_review_keywords = any(re.search(pat, text_to_eval) for pat in self.code_review_patterns)

        if has_code_blocks and has_review_keywords:
            return ClassificationResult(
                category=TaskCategory.CODE_REVIEW,
                confidence=0.95,
                method="rule_based",
                features=features
            )

        if has_code_keywords:
            return ClassificationResult(
                category=TaskCategory.CODE_GENERATION,
                confidence=0.95,
                method="rule_based",
                features=features
            )

        # 5. Translation check
        if any(re.search(pat, text_to_eval) for pat in self.translation_patterns):
            return ClassificationResult(
                category=TaskCategory.TRANSLATION,
                confidence=0.92,
                method="rule_based",
                features=features
            )

        # 6. Data Analysis check
        if any(re.search(pat, text_to_eval, re.IGNORECASE) for pat in self.data_patterns):
            return ClassificationResult(
                category=TaskCategory.DATA_ANALYSIS,
                confidence=0.90,
                method="rule_based",
                features=features
            )

        # 7. Summarization check
        if any(re.search(pat, text_to_eval) for pat in self.summarization_patterns):
            return ClassificationResult(
                category=TaskCategory.SUMMARIZATION,
                confidence=0.92,
                method="rule_based",
                features=features
            )

        # 8. Reasoning check
        if any(re.search(pat, text_to_eval) for pat in self.reasoning_patterns):
            return ClassificationResult(
                category=TaskCategory.REASONING,
                confidence=0.90,
                method="rule_based",
                features=features
            )

        # 9. Creative Writing check
        if any(re.search(pat, text_to_eval) for pat in self.creative_patterns):
            return ClassificationResult(
                category=TaskCategory.CREATIVE_WRITING,
                confidence=0.90,
                method="rule_based",
                features=features
            )

        # 10. Short greetings / generic conversation check
        if re.match(r"^\s*(привет|здравствуй|добрый (день|вечер|утро)|hello|hi|hey|howdy|как дела|whats up)\s*$", text_to_eval):
            return ClassificationResult(
                category=TaskCategory.CONVERSATION,
                confidence=0.95,
                method="rule_based",
                features=features
            )

        # No deterministic rule matched
        return None
