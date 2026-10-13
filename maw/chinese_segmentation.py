"""Chinese clause boundaries inspired by VideoLingo's staged NLP splitter.

Independent jieba POS adaptation: retains every source character and only cuts
at supplied item boundaries. No spaCy models or translated text are required.
"""
from __future__ import annotations

from collections.abc import Sequence

CONNECTORS = frozenset({'因为', '所以', '但是', '而且', '虽然', '如果', '即使', '尽管', '然而', '不过', '因此'})
PUNCTUATION = frozenset('，,、：:；;。.!！？?\n')
Token = tuple[int, int, str, str]


def _complete_clause(tokens: Sequence[Token]) -> bool:
    words = [token for token in tokens if token[2].strip() and not all(c in PUNCTUATION for c in token[2])]
    # A predicate followed by 的 + a noun can be a relative modifier,
    # rather than an independent clause (例如：因为这个原因造成的变化).
    modifier = next((i for i in range(len(words) - 1, -1, -1) if words[i][2] == '的'), None)
    if modifier is not None and modifier + 1 < len(words):
        nominal_tail = all(t[3].startswith('n') or t[3] == 'vn' for t in words[modifier + 1:])
        independent_copula = any(t[2] in {'是', '有', '包括'} for t in words[:modifier])
        if nominal_tail and not independent_copula:
            return False
    for index, token in enumerate(words):
        flag = token[3]
        if not (flag.startswith('v') or flag in {'a', 'ad', 'an'}):
            continue
        has_subject = any(t[3].startswith(('n', 'r')) for t in words[:index])
        # Chinese frequently omits the subject of an instruction or a linked clause.
        implied_subject = flag.startswith('v') and all(t[3].startswith(('c', 'd')) for t in words[:index])
        if has_subject or implied_subject:
            return True
    return False


def analyze_clauses(text: str, tokens: Sequence[Token] | None = None) -> tuple[set[int], dict[int, float]]:
    """Return character cut positions and semantic scores, without rejoining text."""
    if tokens is None:
        try:
            import jieba.posseg as pseg
        except ImportError:
            return set(), {}
        parsed = []
        cursor = 0
        for word, flag in pseg.cut(text):
            value = str(word)
            parsed.append((cursor, cursor + len(value), value, str(flag)))
            cursor += len(value)
        tokens = parsed
    cuts: set[int] = set()
    scores: dict[int, float] = {}
    clause_start = 0
    for index, (start, end, word, _flag) in enumerate(tokens):
        if word in {'，', ','}:
            left = [t for t in tokens[:index] if t[0] >= clause_start]
            right = []
            for token in tokens[index + 1:]:
                if any(c in PUNCTUATION for c in token[2]):
                    break
                right.append(token)
            valid = _complete_clause(left) and _complete_clause(right)
            scores[end] = 18.0 if valid else -25.0
            if valid:
                cuts.add(end)
                clause_start = end
        elif word in CONNECTORS:
            left = [t for t in tokens[:index] if t[0] >= clause_start]
            right = []
            for token in tokens[index + 1:]:
                if any(c in PUNCTUATION for c in token[2]) or token[2] in CONNECTORS:
                    break
                right.append(token)
            scores[end] = -25.0  # Keep the connector with its following clause.
            if _complete_clause(left) and _complete_clause(right):
                scores[start] = 18.0
                cuts.add(start)
                clause_start = start
    return cuts, scores


def split_clauses(items: list[dict]) -> list[list[dict]]:
    """Apply semantic cuts only at exact original item edges; preserve timing."""
    text = ''.join(str(item.get('text') or '') for item in items)
    cuts, _scores = analyze_clauses(text)
    groups = []
    current = []
    position = 0
    for item in items:
        current.append(item)
        position += len(str(item.get('text') or ''))
        if position in cuts:
            groups.append(current)
            current = []
    if current:
        groups.append(current)
    return groups
