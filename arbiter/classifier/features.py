"""
ARBITER Zero-LLM Feature Extractor (Module 2)
Extracts lexical, structural, statistical, and readability features from prompts.
"""

import re
import math
from typing import List, Dict, Any
from arbiter.models.schemas import ChatMessage


def count_syllables_ru_en(word: str) -> int:
    """
    Approximates syllable count for both English and Russian words.
    English vowels: a, e, i, o, u, y
    Russian vowels: а, е, ё, и, о, у, ы, э, ю, я
    """
    word = word.lower()
    vowels = "aeiouyаеёиоуыэюя"
    count = sum(1 for char in word if char in vowels)
    return max(1, count)


def extract_features_from_messages(messages: List[ChatMessage]) -> Dict[str, Any]:
    """
    Extracts numerical and structural features from a list of chat messages.
    """
    full_text_parts: List[str] = []
    is_multimodal = False
    has_system_message = False

    for msg in messages:
        if msg.role == "system":
            has_system_message = True
        
        if isinstance(msg.content, str):
            full_text_parts.append(msg.content)
        elif isinstance(msg.content, list):
            # Check for multimodal contents
            for item in msg.content:
                if isinstance(item, dict):
                    if item.get("type") in ("image_url", "image", "input_audio", "file"):
                        is_multimodal = True
                    elif item.get("type") == "text":
                        full_text_parts.append(item.get("text", ""))

    full_text = "\n".join(full_text_parts)
    last_text = full_text_parts[-1] if full_text_parts else ""

    # Token and lexical analysis
    words = re.findall(r"\w+", full_text)
    total_words = len(words)
    total_chars = len(full_text)

    # Word length
    avg_word_length = (sum(len(w) for w in words) / total_words) if total_words > 0 else 0.0

    # Code fences
    code_blocks = re.findall(r"```[\s\S]*?```", full_text)
    code_block_count = len(code_blocks)
    has_code_blocks = code_block_count > 0

    # Line-based code ratio
    lines = full_text.splitlines()
    code_lines = 0
    in_code_block = False
    for line in lines:
        if line.strip().startswith("```"):
            in_code_block = not in_code_block
            code_lines += 1
        elif in_code_block:
            code_lines += 1
    code_ratio = (code_lines / len(lines)) if lines else 0.0

    # Language / script ratios
    ascii_chars = sum(1 for c in full_text if ord(c) < 128)
    cyrillic_chars = sum(1 for c in full_text if '\u0400' <= c <= '\u04FF')
    ascii_ratio = (ascii_chars / total_chars) if total_chars > 0 else 0.0
    cyrillic_ratio = (cyrillic_chars / total_chars) if total_chars > 0 else 0.0

    # Tables / Numbers
    has_markdown_table = bool(re.search(r"\|.*\|.*\|", full_text))
    numbers = re.findall(r"\b\d+(?:\.\d+)?\b", full_text)
    number_density = (len(numbers) / total_words) if total_words > 0 else 0.0

    # Sentences and Readability (Adapted Flesch Reading Ease)
    sentences = re.split(r"[.!?]+", full_text)
    sentence_count = max(1, len([s for s in sentences if s.strip()]))
    words_per_sentence = total_words / sentence_count

    total_syllables = sum(count_syllables_ru_en(w) for w in words)
    syllables_per_word = (total_syllables / total_words) if total_words > 0 else 1.0

    # Flesch-Kincaid / Reading ease approximation
    # 206.835 - 1.015*(words/sentence) - 84.6*(syllables/word)
    reading_ease = 206.835 - (1.015 * words_per_sentence) - (84.6 * syllables_per_word)
    reading_ease = max(0.0, min(100.0, reading_ease))

    # Conversation history
    history_turn_count = len(messages)

    return {
        "total_chars": total_chars,
        "total_words": total_words,
        "avg_word_length": round(avg_word_length, 2),
        "has_code_blocks": has_code_blocks,
        "code_block_count": code_block_count,
        "code_ratio": round(code_ratio, 3),
        "ascii_ratio": round(ascii_ratio, 3),
        "cyrillic_ratio": round(cyrillic_ratio, 3),
        "has_markdown_table": has_markdown_table,
        "number_density": round(number_density, 3),
        "reading_ease": round(reading_ease, 2),
        "history_turn_count": history_turn_count,
        "has_system_message": has_system_message,
        "is_multimodal": is_multimodal,
        "last_message_text": last_text,
        "full_text": full_text
    }
