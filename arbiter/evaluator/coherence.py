"""
ARBITER Coherence and Hallucination Marker Evaluator (Module 5)
Detects semantic relevance to prompt, repetition loops, and disclaimers/hedging.
"""

import re
import math
from typing import Dict, Any, Tuple, Set


# Common hallucination and robotic hedging phrases
HALLUCINATION_MARKERS = [
    r"as an ai (language )?model",
    r"i do not have access to real-time",
    r"i cannot verify",
    r"as of my knowledge cutoff",
    r"i am only an ai",
    r"as a large language model",
    r"как языковая модель ии",
    r"я всего лишь языковая модель",
    r"у меня нет доступа к актуальным",
    r"я не могу подтвердить"
]


class CoherenceEvaluator:
    """
    Computes lexical overlap similarity with prompt and penalizes robotic disclaimers.
    """

    @classmethod
    def evaluate(cls, prompt: str, response: str) -> Tuple[float, Dict[str, Any]]:
        score = 0.8  # Neutral good baseline
        details: Dict[str, Any] = {}

        # 1. Hallucination / robotic marker penalty
        response_lower = response.lower()
        found_markers = []
        for marker in HALLUCINATION_MARKERS:
            if re.search(marker, response_lower):
                found_markers.append(marker)

        if found_markers:
            score -= 0.30 * min(len(found_markers), 2)
            details["hallucination_markers"] = found_markers

        # 2. Semantic relevance (Jaccard / Token overlap with prompt)
        prompt_words = set(re.findall(r"\w{3,}", prompt.lower()))
        resp_words = set(re.findall(r"\w{3,}", response_lower))

        if prompt_words:
            overlap = len(prompt_words.intersection(resp_words))
            relevance_ratio = overlap / len(prompt_words)
            details["keyword_overlap_ratio"] = round(relevance_ratio, 3)

            # If prompt has several keywords but response has zero overlap
            if len(prompt_words) >= 4 and overlap == 0:
                score -= 0.25
            elif relevance_ratio > 0.25:
                score += 0.10

        # 3. Repetition loop detection
        # Split text into 3-word n-grams and check for repetitive loops
        words = re.findall(r"\w+", response_lower)
        if len(words) >= 15:
            ngrams = [tuple(words[i:i+3]) for i in range(len(words)-2)]
            unique_ngrams = set(ngrams)
            repetition_ratio = len(unique_ngrams) / len(ngrams)
            details["repetition_diversity"] = round(repetition_ratio, 3)
            if repetition_ratio < 0.50:
                # High repetition / infinite generation loop
                score -= 0.40
                details["high_repetition_penalty"] = True

        final_score = max(0.0, min(1.0, score))
        return round(final_score, 4), details
