"""Ubah teks bergaya Markdown menjadi Block.

Dipakai dua tempat: file `.md`/`.txt` langsung, dan hasil HTML yang sudah dibersihkan
trafilatura (diminta dalam format markdown supaya heading-nya bisa jadi metadata section).
"""

import re

from app.schemas.documents import Block

_HEADING = re.compile(r"^(#{1,6})\s+(.*)$")
_FENCE = re.compile(r"^\s*(```|~~~)")
_INLINE_PATTERNS: tuple[tuple[re.Pattern[str], str], ...] = (
    (re.compile(r"!\[(.*?)\]\((.*?)\)"), r"\1"),
    (re.compile(r"\[(.*?)\]\((.*?)\)"), r"\1"),
    (re.compile(r"\*\*(.+?)\*\*"), r"\1"),
    (re.compile(r"__(.+?)__"), r"\1"),
    (re.compile(r"(?<!\*)\*(?!\*)(.+?)(?<!\*)\*(?!\*)"), r"\1"),
    (re.compile(r"(?<!_)_(?!_)(.+?)(?<!_)_(?!_)"), r"\1"),
    (re.compile(r"`(.+?)`"), r"\1"),
)


def markdown_to_blocks(markdown: str, *, page: int | None = None) -> list[Block]:
    """Heading jadi `section`; paragraf jadi block; isi blok kode dibiarkan utuh."""
    blocks: list[Block] = []
    section: str | None = None
    buffer: list[str] = []
    in_fence = False

    def flush() -> None:
        text = "\n".join(buffer).strip()
        buffer.clear()
        if text:
            blocks.append(Block(text=text, order=len(blocks), page=page, section=section))

    for line in markdown.splitlines():
        if _FENCE.match(line):
            in_fence = not in_fence
            buffer.append(line)
            continue

        if not in_fence:
            heading = _HEADING.match(line)
            if heading:
                flush()
                section = heading.group(2).strip() or section
                continue
            if not line.strip():
                flush()
                continue
            buffer.append(_strip_inline(line))
            continue

        buffer.append(line)

    flush()
    return blocks


def _strip_inline(line: str) -> str:
    """Buang penanda inline (`**tebal**`, `` `kode` ``, link) supaya teksnya bersih."""
    for pattern, replacement in _INLINE_PATTERNS:
        line = pattern.sub(replacement, line)
    return line
