"""Backward-compatible imports for the shared MAW segmentation core."""

from maw.bdversion.segment import (  # noqa: F401
    DEFAULT_GAP_SPLIT_MS,
    DEFAULT_MAX_LEN,
    DEFAULT_MIN_LEN,
    resegment_segments,
    split_coarse_segments_sentence_aware,
    split_items_sentence_aware,
)

__all__ = [
    "DEFAULT_GAP_SPLIT_MS",
    "DEFAULT_MAX_LEN",
    "DEFAULT_MIN_LEN",
    "resegment_segments",
    "split_coarse_segments_sentence_aware",
    "split_items_sentence_aware",
]
