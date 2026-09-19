"""
ARBITER Unified Zero-LLM Task Classifier (Module 2)
Combines Rule-Based (Tier 1, 0ms) with Trained ML (Tier 2, ~5ms) and Fallback.
"""

from typing import List, Dict, Any
from arbiter.models.schemas import ChatMessage
from arbiter.models.types import TaskCategory, ClassificationResult
from arbiter.classifier.features import extract_features_from_messages
from arbiter.classifier.rules import RuleBasedClassifier
from arbiter.classifier.model import TrainedClassifier
from arbiter.classifier.self_trainer import SelfTrainer


class TaskClassifier:
    """
    Main Classifier Interface for the Gateway & Router.
    Adheres strictly to the requirement: NO LLMs used for classification.
    """

    def __init__(self):
        self.rule_engine = RuleBasedClassifier()
        self.ml_model = TrainedClassifier()
        self.self_trainer = SelfTrainer(self.ml_model)

    def classify_messages(self, messages: List[ChatMessage]) -> ClassificationResult:
        # Step 1: Feature Extraction (< 1ms)
        features = extract_features_from_messages(messages)

        # Step 2: Tier 1 - Rule-Based Check (0ms)
        rule_result = self.rule_engine.classify(features)
        if rule_result is not None:
            return rule_result

        # Step 3: Tier 2 - Trained ML Model (~2-5ms)
        last_message = features.get("last_message_text", "")
        if last_message:
            ml_result = self.ml_model.predict(last_message, features)
            if ml_result is not None and ml_result.confidence >= 0.40:
                return ml_result

        # Step 4: Fallback to General Conversation
        return ClassificationResult(
            category=TaskCategory.CONVERSATION,
            confidence=0.50,
            method="fallback",
            features=features
        )


# Global singleton
classifier = TaskClassifier()
