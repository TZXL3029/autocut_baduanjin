import logging
import re
from functools import lru_cache
from typing import Tuple

from pypinyin import lazy_pinyin

try:
    import jieba

    jieba.setLogLevel(logging.WARNING)
except ImportError:  # pragma: no cover - segmentation can fall back to regex
    jieba = None

CHINESE_RE = re.compile(r"[\u4e00-\u9fff]")
GENERIC_SHARED_CHARS = set("上下左右前后第个动作式势气")


def normalize_text(text: str) -> str:
    text = text.lower()
    text = re.sub(r"\s+", "", text)
    return re.sub(r"[^\w\u4e00-\u9fff]+", "", text)


def has_chinese(text: str) -> bool:
    return bool(CHINESE_RE.search(text))


@lru_cache(maxsize=4096)
def text_to_pinyin(text: str) -> str:
    normalized = normalize_text(text)
    if not normalized:
        return ""
    return "".join(lazy_pinyin(normalized, errors="default"))


@lru_cache(maxsize=4096)
def _segment_text(text: str) -> Tuple[str, ...]:
    normalized = normalize_text(text)
    if not normalized:
        return ()
    if jieba:
        return tuple(token for token in jieba.lcut(normalized) if token)
    return tuple(re.findall(r"[a-z0-9_]+|[\u4e00-\u9fff]", normalized))


@lru_cache(maxsize=4096)
def text_to_pinyin_tokens(text: str) -> Tuple[str, ...]:
    return tuple(
        pinyin
        for pinyin in (text_to_pinyin(token) for token in _segment_text(text))
        if pinyin
    )


def contains_by_text(text: str, term: str) -> bool:
    return normalize_text(term) in normalize_text(text)


def contains_by_pinyin(text: str, term: str) -> bool:
    if not has_chinese(term):
        return False
    term_pinyin = text_to_pinyin(term)
    if len(term_pinyin) < 4:
        return False
    text_terms = _segment_text(text)
    text_tokens = tuple(text_to_pinyin(token) for token in text_terms if token)
    term_tokens = text_to_pinyin_tokens(term)
    if text_tokens and term_tokens:
        max_window = min(len(text_tokens), len(term_tokens) + 1)
        for window_size in range(1, max_window + 1):
            for start in range(0, len(text_tokens) - window_size + 1):
                window_pinyin = "".join(text_tokens[start : start + window_size])
                window_text = "".join(text_terms[start : start + window_size])
                if (
                    term_pinyin == window_pinyin or term_pinyin in window_pinyin
                ) and _shares_distinctive_chinese_char(term, window_text):
                    return True
    return False


def _shares_distinctive_chinese_char(term: str, text: str) -> bool:
    term_chars = {char for char in normalize_text(term) if has_chinese(char)}
    text_chars = {char for char in normalize_text(text) if has_chinese(char)}
    return any(
        char not in GENERIC_SHARED_CHARS
        for char in term_chars.intersection(text_chars)
    )
