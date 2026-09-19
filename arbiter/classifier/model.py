"""
ARBITER Trained Lightweight ML Classifier (Module 2, Tier 2)
TF-IDF + SGDClassifier (with partial_fit support for online / self-training).
"""

import os
import re
import pickle
import logging
from typing import Optional, List, Tuple, Dict, Any
from arbiter.models.types import TaskCategory, ClassificationResult

logger = logging.getLogger(__name__)

# Seed data for bootstrapping the model across all categories
SEED_DATA: List[Tuple[str, str]] = [
    # code_generation
    ("write a python script to fetch weather data from an api", "code_generation"),
    ("напиши функцию на javascript для сортировки массива объектов", "code_generation"),
    ("implement a binary search tree in C++ with insert and delete methods", "code_generation"),
    ("создай FastAPI эндпоинт для загрузки файлов и валидации схемы", "code_generation"),
    ("how to implement quicksort algorithm in rust with memory safety", "code_generation"),
    ("напиши скрипт парсинга html страницы с помощью BeautifulSoup", "code_generation"),
    
    # code_review
    ("check this code for security vulnerabilities and sql injections", "code_review"),
    ("почему этот код падает с ошибкой IndexError в цикле for?", "code_review"),
    ("review this React component for memory leaks and extra re-renders", "code_review"),
    ("сделай рефакторинг этого метода, уменьши цикломатическую сложность", "code_review"),
    ("explain what this lambda function does and optimize its performance", "code_review"),
    ("найди баг в алгоритме бинарного поиска ниже", "code_review"),

    # creative_writing
    ("write a fantasy story about an ancient dragon guarding a forgotten library", "creative_writing"),
    ("сочини стихотворение про осенний дождь и чашку горячего кофе", "creative_writing"),
    ("compose an engaging sci-fi short story set on Europa", "creative_writing"),
    ("напиши сказку для детей про маленького робота, который мечтал рисовать", "creative_writing"),
    ("write a dramatic script for two characters arguing in an elevator", "creative_writing"),

    # data_analysis
    ("write an sql query to calculate 7-day rolling retention by user cohort", "data_analysis"),
    ("посчитай корреляцию между рекламными расходами и конверсией в pandas", "data_analysis"),
    ("calculate standard deviation and 95% confidence interval for this sample", "data_analysis"),
    ("построй сводную таблицу продаж по регионам и выведи топ-5 продуктов", "data_analysis"),
    ("explain how to handle missing values and outliers in this dataset", "data_analysis"),

    # translation
    ("translate this technical documentation from English into Russian", "translation"),
    ("переведи следующее деловое письмо на немецкий язык вежливо", "translation"),
    ("how do you say 'where is the nearest subway station' in French?", "translation"),
    ("переведи этот контракт на испанский сохранив юридические термины", "translation"),
    ("translate the following paragraph into natural sounding Japanese", "translation"),

    # summarization
    ("provide a concise 3-bullet summary of the following research paper", "summarization"),
    ("кратко изложи основные тезисы и выводы этой статьи", "summarization"),
    ("give me a tl;dr of this 10-page terms of service agreement", "summarization"),
    ("суммаризируй этот длинный диалог и выдели решения встречи", "summarization"),
    ("condense this news article into 50 words without losing key facts", "summarization"),

    # reasoning
    ("if all roses are flowers and some flowers fade quickly, do all roses fade quickly?", "reasoning"),
    ("реши логическую задачу про трех мудрецов в черных и белых колпаках", "reasoning"),
    ("calculate the probability of rolling at least one six in four dice throws", "reasoning"),
    ("докажи, что корень из двух является иррациональным числом", "reasoning"),
    ("solve this math puzzle: a bat and a ball cost $1.10 in total", "reasoning"),

    # conversation
    ("привет, расскажи что-нибудь интересное о космосе", "conversation"),
    ("hello! how is your day going? tell me about yourself", "conversation"),
    ("как дела? чем занимаешься сегодня?", "conversation"),
    ("thank you very much for your helpful answer earlier!", "conversation"),
    ("what do you think is the meaning of life?", "conversation"),

    # system_prompt
    ("You are an expert AI assistant specialized in enterprise software architecture.", "system_prompt"),
    ("Действуй как опытный HR-интервьюер и задавай мне вопросы по Python.", "system_prompt"),
    ("Always respond in JSON format conforming strictly to the provided schema.", "system_prompt"),
    ("You must follow these safety guidelines and never mention competitor names.", "system_prompt"),

    # multimodal
    ("describe what is shown in this attached image in detail", "multimodal"),
    ("что изображено на этой фотографии и какие цвета преобладают?", "multimodal"),
    ("extract text and numbers from this scanned receipt picture", "multimodal")
]


class TrainedClassifier:
    """
    Tier 2 ML Classifier backed by TF-IDF and SGDClassifier.
    Supports warm-up bootstrap and online partial_fit incremental updates.
    """

    def __init__(self, model_path: str = "arbiter/classifier/model_cache.pkl"):
        self.model_path = model_path
        self.vectorizer = None
        self.classifier = None
        self.is_trained = False
        self._initialize()

    def _initialize(self) -> None:
        # Check if pickled model exists
        if os.path.exists(self.model_path):
            try:
                with open(self.model_path, "rb") as f:
                    data = pickle.load(f)
                    self.vectorizer = data["vectorizer"]
                    self.classifier = data["classifier"]
                    self.is_trained = True
                logger.info("TrainedClassifier loaded from disk cache.")
                return
            except Exception as e:
                logger.warning(f"Failed to load cached classifier: {e}")

        # Train on bootstrap seed data
        self.bootstrap_train()

    def bootstrap_train(self) -> None:
        """Trains the initial model using scikit-learn on seed samples."""
        try:
            from sklearn.feature_extraction.text import TfidfVectorizer
            from sklearn.linear_model import SGDClassifier

            texts = [item[0] for item in SEED_DATA]
            labels = [item[1] for item in SEED_DATA]

            self.vectorizer = TfidfVectorizer(ngram_range=(1, 2), min_df=1, max_features=5000)
            X = self.vectorizer.fit_transform(texts)

            self.classifier = SGDClassifier(loss="log_loss", random_state=42, max_iter=1000)
            self.classifier.fit(X, labels)
            self.is_trained = True

            self.save_model()
            logger.info("TrainedClassifier successfully bootstrapped with seed dataset.")
        except Exception as e:
            logger.warning(f"Scikit-learn not ready or failed to bootstrap: {e}")
            self.is_trained = False

    def predict(self, text: str, features: Dict[str, Any]) -> Optional[ClassificationResult]:
        """
        Runs ML inference (~2-5ms). Returns ClassificationResult with probabilities.
        """
        if not self.is_trained or self.vectorizer is None or self.classifier is None:
            return None

        try:
            X = self.vectorizer.transform([text])
            probs = self.classifier.predict_proba(X)[0]
            classes = self.classifier.classes_

            best_idx = probs.argmax()
            best_cat = classes[best_idx]
            confidence = float(probs[best_idx])

            return ClassificationResult(
                category=TaskCategory(best_cat),
                confidence=round(confidence, 4),
                method="trained_model",
                features=features
            )
        except Exception as e:
            logger.error(f"Error during ML classifier prediction: {e}")
            return None

    def partial_fit(self, texts: List[str], labels: List[str]) -> None:
        """
        Online learning step called by SelfTrainer loop.
        """
        if not self.is_trained or self.vectorizer is None or self.classifier is None:
            return

        try:
            X = self.vectorizer.transform(texts)
            self.classifier.partial_fit(X, labels)
            self.save_model()
            logger.info(f"TrainedClassifier incrementally updated with {len(texts)} new samples.")
        except Exception as e:
            logger.error(f"Failed to run partial_fit on classifier: {e}")

    def save_model(self) -> None:
        try:
            os.makedirs(os.path.dirname(self.model_path), exist_ok=True)
            with open(self.model_path, "wb") as f:
                pickle.dump({
                    "vectorizer": self.vectorizer,
                    "classifier": self.classifier
                }, f)
        except Exception as e:
            logger.error(f"Failed to save trained classifier to disk: {e}")
