"""
ARBITER Response Merge Engine for Consensus Mode (Module 5)
Synthesizes parallel model completions via statistical outlier selection or structural section merge.
"""

import math
import re
import numpy as np
from typing import List, Dict, Any, Tuple
from arbiter.providers.multiplexer import CandidateResult
from arbiter.evaluator.structural import StructuralEvaluator
from arbiter.evaluator.code_eval import CodeQualityEvaluator
from arbiter.evaluator.coherence import CoherenceEvaluator


class EvaluatedCandidate:
    def __init__(self, candidate: CandidateResult, quality_score: float, details: Dict[str, Any]):
        self.candidate = candidate
        self.quality_score = quality_score
        self.details = details


class MergeEngine:
    """
    Evaluates N candidates and returns either a standout winner or an assembled structural merge.
    """

    @classmethod
    def evaluate_response(cls, prompt: str, text: str) -> Tuple[float, Dict[str, Any]]:
        struct_score, struct_meta = StructuralEvaluator.evaluate(prompt, text)
        code_score, code_meta = CodeQualityEvaluator.evaluate(text)
        coh_score, coh_meta = CoherenceEvaluator.evaluate(prompt, text)

        # Weighting: if code is present, code quality matters more
        if code_meta.get("has_code", False):
            composite = 0.30 * struct_score + 0.45 * code_score + 0.25 * coh_score
        else:
            composite = 0.50 * struct_score + 0.50 * coh_score

        details = {
            "composite_score": round(composite, 4),
            "structural": struct_meta,
            "code": code_meta,
            "coherence": coh_meta
        }
        return round(composite, 4), details

    @classmethod
    def merge_candidates(
        cls,
        prompt: str,
        candidates: List[CandidateResult]
    ) -> Tuple[str, float, str, List[Dict[str, Any]]]:
        """
        Returns: (merged_text, chosen_quality_score, selection_strategy, candidates_metadata)
        """
        if not candidates:
            return "", 0.0, "empty", []

        if len(candidates) == 1:
            score, meta = cls.evaluate_response(prompt, candidates[0].text)
            return candidates[0].text, score, "single_candidate", [{"model": candidates[0].model, "score": score}]

        # 1. Evaluate all candidates
        evaluated: List[EvaluatedCandidate] = []
        scores = []
        for cand in candidates:
            score, meta = cls.evaluate_response(prompt, cand.text)
            evaluated.append(EvaluatedCandidate(cand, score, meta))
            scores.append(score)

        scores_arr = np.array(scores)
        mean_score = float(np.mean(scores_arr))
        std_score = float(np.std(scores_arr))

        # Sort descending by score
        evaluated.sort(key=lambda x: x.quality_score, reverse=True)
        top = evaluated[0]

        candidates_meta = [
            {"model": e.candidate.model, "score": e.quality_score, "latency": e.candidate.latency_ms}
            for e in evaluated
        ]

        # 2. Rule: Statistical Outlier (> 2σ above mean)
        if len(evaluated) >= 3 and std_score > 0.05:
            if top.quality_score >= mean_score + 2.0 * std_score:
                return top.candidate.text, top.quality_score, "statistical_outlier_winner", candidates_meta

        # 3. Check if responses have code vs non-code
        # Prefer the one with syntactically valid code if prompt asked for code
        has_code_in_prompt = bool(re.search(r"\b(code|python|function|код|скрипт)\b", prompt.lower()))
        if has_code_in_prompt:
            for e in evaluated:
                if e.details["code"].get("has_code") and e.details["code"].get("blocks_results"):
                    if all(b.get("syntax_valid") for b in e.details["code"]["blocks_results"]):
                        return e.candidate.text, e.quality_score, "valid_code_winner", candidates_meta

        # 4. Structural Merge: if scores are close (delta < 0.15) and text has multiple sections
        if (evaluated[0].quality_score - evaluated[1].quality_score) < 0.15:
            merged_text = cls._structural_section_merge(evaluated[0].candidate.text, evaluated[1].candidate.text)
            if merged_text and len(merged_text) >= len(evaluated[0].candidate.text):
                merged_score, _ = cls.evaluate_response(prompt, merged_text)
                return merged_text, merged_score, "structural_section_merge", candidates_meta

        # 5. Default highest score
        return top.candidate.text, top.quality_score, "highest_quality_score", candidates_meta

    @staticmethod
    def _structural_section_merge(text_a: str, text_b: str) -> str:
        """
        Combines non-redundant sections and picks the cleanest code block.
        """
        # Split by double newlines into logical paragraphs/sections
        sections_a = [s.strip() for s in text_a.split("\n\n") if s.strip()]
        sections_b = [s.strip() for s in text_b.split("\n\n") if s.strip()]

        merged_sections = list(sections_a)

        # Append complementary sections from B not already present in A
        for s_b in sections_b:
            words_b = set(re.findall(r"\w+", s_b.lower()))
            is_redundant = False
            for s_a in sections_a:
                words_a = set(re.findall(r"\w+", s_a.lower()))
                if words_a and words_b:
                    overlap = len(words_a.intersection(words_b)) / min(len(words_a), len(words_b))
                    if overlap > 0.65:
                        is_redundant = True
                        break
            if not is_redundant and len(s_b) > 40:
                merged_sections.append(s_b)

        return "\n\n".join(merged_sections)
