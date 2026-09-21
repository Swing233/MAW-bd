"""Manuscript loading: TXT / Markdown / DOCX / paste → unified model.

PDF is intentionally unsupported.
"""

from __future__ import annotations

import re
import zipfile
from dataclasses import dataclass
from pathlib import Path
from xml.etree import ElementTree as ET

from maw.bdversion.normalize import normalize_for_match

SCRIPT_EXTENSIONS = frozenset({".txt", ".md", ".markdown", ".docx"})

_MD_FENCE_RE = re.compile(r"^```.*?```", re.MULTILINE | re.DOTALL)
_MD_HEADING_RE = re.compile(r"^(#{1,6})\s+", re.MULTILINE)
_MD_BOLD_RE = re.compile(r"\*\*(.+?)\*\*|__(.+?)__")
_MD_ITALIC_RE = re.compile(r"(?<!\*)\*([^*\n]+?)\*(?!\*)|(?<!_)_([^_\n]+?)_(?!_)")
_MD_STRIKE_RE = re.compile(r"~~(.+?)~~")
_MD_CODE_RE = re.compile(r"`([^`]+)`")
_MD_HIGHLIGHT_RE = re.compile(r"==(.+?)==")
_MD_LINK_RE = re.compile(r"\[([^\]]+)\]\([^)]+\)")
_MD_IMAGE_RE = re.compile(r"!\[([^\]]*)\]\([^)]+\)")
_MD_FRONT_MATTER_RE = re.compile(r"^---\r?\n.*?\r?\n---\r?\n", re.DOTALL)

_WORD_NS = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"


class ManuscriptError(ValueError):
    """Raised when a manuscript cannot be loaded or is empty after cleaning."""


@dataclass(frozen=True, slots=True)
class ManuscriptSource:
    origin: str  # txt | markdown | docx | paste
    raw_text: str
    path: Path | None = None


@dataclass(frozen=True, slots=True)
class ManuscriptUnit:
    index: int
    display_text: str
    match_key: str
    char_span: tuple[int, int]


@dataclass(frozen=True, slots=True)
class ManuscriptDocument:
    source: ManuscriptSource
    display_text: str
    units: tuple[ManuscriptUnit, ...]

    @property
    def unit_count(self) -> int:
        return len(self.units)


def clean_markdown_inline(text: str) -> str:
    """Strip common Markdown markup for matching/display; keep visible characters."""

    cleaned = _MD_FENCE_RE.sub(lambda m: m.group(0).strip("`"), text)
    cleaned = _MD_FRONT_MATTER_RE.sub("", cleaned)
    cleaned = _MD_IMAGE_RE.sub(lambda m: m.group(1), cleaned)
    cleaned = _MD_LINK_RE.sub(lambda m: m.group(1), cleaned)
    cleaned = _MD_BOLD_RE.sub(lambda m: m.group(1) or m.group(2) or "", cleaned)
    cleaned = _MD_ITALIC_RE.sub(lambda m: m.group(1) or m.group(2) or "", cleaned)
    cleaned = _MD_STRIKE_RE.sub(lambda m: m.group(1), cleaned)
    cleaned = _MD_HIGHLIGHT_RE.sub(lambda m: m.group(1), cleaned)
    cleaned = _MD_CODE_RE.sub(lambda m: m.group(1), cleaned)
    cleaned = _MD_HEADING_RE.sub("", cleaned)
    cleaned = re.sub(r"^\s*[-*+]\s+", "", cleaned, flags=re.MULTILINE)
    cleaned = re.sub(r"^\s*\d+\.\s+", "", cleaned, flags=re.MULTILINE)
    return cleaned


def _extract_docx_text(path: Path) -> str:
    """Minimal DOCX text extract via stdlib zip + OOXML (no hard python-docx dep)."""

    try:
        with zipfile.ZipFile(path) as archive:
            xml_bytes = archive.read("word/document.xml")
    except (OSError, zipfile.BadZipFile, KeyError) as error:
        raise ManuscriptError(f"无法读取 DOCX：{path.name}: {error}") from error

    try:
        root = ET.fromstring(xml_bytes)
    except ET.ParseError as error:
        raise ManuscriptError(f"DOCX XML 解析失败：{path.name}: {error}") from error

    paragraphs: list[str] = []
    for paragraph in root.iter(f"{_WORD_NS}p"):
        parts: list[str] = []
        for node in paragraph.iter():
            if node.tag == f"{_WORD_NS}t" and node.text:
                parts.append(node.text)
            elif node.tag == f"{_WORD_NS}tab":
                parts.append("\t")
        line = "".join(parts).strip()
        if line:
            paragraphs.append(line)
    return "\n".join(paragraphs)


def _normalize_newlines(text: str) -> str:
    return text.replace("\r\n", "\n").replace("\r", "\n")


def _split_units(display_text: str) -> tuple[ManuscriptUnit, ...]:
    """Split cleaned manuscript into sequential units for monotonic matching.

    优先按行；空行忽略。超长行再按中文/英文句末标点切开，便于跨 cue 对齐。
    """

    units: list[ManuscriptUnit] = []
    cursor = 0
    for raw_line in display_text.split("\n"):
        line = raw_line.strip()
        if not line:
            continue
        # locate original span in display_text (search from cursor)
        start = display_text.find(line, cursor)
        if start < 0:
            start = cursor
        end = start + len(line)
        cursor = end
        pieces = _split_long_line(line)
        piece_offset = start
        for piece in pieces:
            if not piece.strip():
                piece_offset += len(piece)
                continue
            key = normalize_for_match(piece)
            if not key:
                piece_offset += len(piece)
                continue
            units.append(
                ManuscriptUnit(
                    index=len(units),
                    display_text=piece.strip(),
                    match_key=key,
                    char_span=(piece_offset, piece_offset + len(piece)),
                )
            )
            piece_offset += len(piece)
    return tuple(units)


_SENTENCE_SPLIT_RE = re.compile(r"(?<=[。！？!?；;])")


def _split_long_line(line: str, max_len: int = 80) -> list[str]:
    if len(line) <= max_len:
        return [line]
    parts = [part for part in _SENTENCE_SPLIT_RE.split(line) if part]
    if len(parts) <= 1:
        # hard wrap for extremely long continuous scripts
        return [line[i : i + max_len] for i in range(0, len(line), max_len)]
    return parts


def build_manuscript(origin: str, raw_text: str, path: Path | None = None) -> ManuscriptDocument:
    if origin == "markdown" or (path is not None and path.suffix.lower() in {".md", ".markdown"}):
        display = clean_markdown_inline(raw_text)
    elif origin == "docx" or (path is not None and path.suffix.lower() == ".docx"):
        display = raw_text  # already extracted
    else:
        display = raw_text
    display = _normalize_newlines(display).strip()
    units = _split_units(display)
    if not units:
        raise ManuscriptError("文稿为空或规范化后没有可用于匹配的单元")
    return ManuscriptDocument(
        source=ManuscriptSource(origin=origin, raw_text=raw_text, path=path),
        display_text=display,
        units=units,
    )


def manuscript_from_paste(text: str) -> ManuscriptDocument:
    return build_manuscript("paste", text, path=None)


def load_manuscript(path: Path | str) -> ManuscriptDocument:
    source_path = Path(path).expanduser()
    if not source_path.is_file():
        raise ManuscriptError(f"文稿文件不存在：{source_path}")
    suffix = source_path.suffix.lower()
    if suffix == ".pdf":
        raise ManuscriptError("不支持 PDF 文稿，请提供 TXT / Markdown / DOCX 或直接粘贴")
    if suffix not in SCRIPT_EXTENSIONS:
        raise ManuscriptError(f"不支持的文稿类型：{suffix or '(无扩展名)'}")

    if suffix == ".docx":
        raw = _extract_docx_text(source_path)
        return build_manuscript("docx", raw, path=source_path)

    try:
        raw = source_path.read_text(encoding="utf-8-sig")
    except (OSError, UnicodeError) as error:
        raise ManuscriptError(f"无法读取文稿：{source_path.name}: {error}") from error

    if suffix in {".md", ".markdown"}:
        return build_manuscript("markdown", raw, path=source_path)
    return build_manuscript("txt", raw, path=source_path)
