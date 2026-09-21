"""Lottie glyph vectorize — removed in focused build."""

from __future__ import annotations


class LottieGlyphError(RuntimeError):
    pass


def vectorize_lottie_animation(*_a, **_k):
    raise LottieGlyphError("Lottie export removed in focused build")
