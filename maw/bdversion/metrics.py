"""Structural similarity helpers for manuscript ↔ ASR matching."""

from __future__ import annotations

from collections import Counter


def levenshtein(a: str, b: str) -> int:
    if a == b:
        return 0
    if not a:
        return len(b)
    if not b:
        return len(a)
    if len(a) < len(b):
        a, b = b, a
    previous = list(range(len(b) + 1))
    for i, ca in enumerate(a, start=1):
        current = [i]
        for j, cb in enumerate(b, start=1):
            current.append(
                min(
                    previous[j] + 1,
                    current[j - 1] + 1,
                    previous[j - 1] + (ca != cb),
                )
            )
        previous = current
    return previous[-1]


def levenshtein_similarity(a: str, b: str) -> float:
    if not a and not b:
        return 1.0
    distance = levenshtein(a, b)
    longest = max(len(a), len(b))
    return 1.0 - distance / longest


def lcs_length(a: str, b: str) -> int:
    if not a or not b:
        return 0
    if len(a) < len(b):
        a, b = b, a
    previous = [0] * (len(b) + 1)
    for ca in a:
        current = [0]
        for j, cb in enumerate(b, start=1):
            if ca == cb:
                current.append(previous[j - 1] + 1)
            else:
                current.append(max(previous[j], current[j - 1]))
        previous = current
    return previous[-1]


def lcs_similarity(a: str, b: str) -> float:
    if not a and not b:
        return 1.0
    if not a or not b:
        return 0.0
    return lcs_length(a, b) / max(len(a), len(b))


def char_ngrams(text: str, n: int = 2) -> Counter[str]:
    if not text:
        return Counter()
    if len(text) < n:
        return Counter([text])
    return Counter(text[i : i + n] for i in range(len(text) - n + 1))


def token_similarity(a: str, b: str, n: int = 2) -> float:
    """Dice coefficient over character n-grams (token-like for CJK/Latin mix)."""

    if not a and not b:
        return 1.0
    if not a or not b:
        return 0.0
    left = char_ngrams(a, n)
    right = char_ngrams(b, n)
    overlap = sum((left & right).values())
    total = sum(left.values()) + sum(right.values())
    if total == 0:
        return 0.0
    return (2.0 * overlap) / total


def composite_similarity(asr_key: str, script_key: str) -> float:
    """Blend Lev / LCS / n-gram scores into one match score in [0, 1]."""

    if not asr_key and not script_key:
        return 1.0
    if not asr_key or not script_key:
        return 0.0
    lev = levenshtein_similarity(asr_key, script_key)
    lcs = lcs_similarity(asr_key, script_key)
    tok = token_similarity(asr_key, script_key)
    return 0.4 * lev + 0.35 * lcs + 0.25 * tok
