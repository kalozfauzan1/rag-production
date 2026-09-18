"""Normalisasi teks hasil ekstraksi.

Aturannya sengaja sedikit dan bisa diperiksa: tujuannya membuang artefak ekstraksi
(hyphen pecah baris, spasi ganda), bukan menulis ulang kalimat.
"""

import re

_HYPHEN_LINEBREAK = re.compile(r"(\w)-\n(\w)")
_TRAILING_SPACES = re.compile(r"[ \t]+\n")
_REPEATED_SPACES = re.compile(r"[ \t]{2,}")
_BLANK_LINES = re.compile(r"\n{3,}")


def normalize_text(text: str) -> str:
    """Rapikan teks satu blok."""
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = _HYPHEN_LINEBREAK.sub(r"\1\2", text)
    text = _TRAILING_SPACES.sub("\n", text)
    text = _REPEATED_SPACES.sub(" ", text)
    text = _BLANK_LINES.sub("\n\n", text)
    return text.strip()


def split_paragraphs(text: str) -> list[str]:
    """Pecah teks menjadi paragraf berdasarkan baris kosong."""
    normalized = normalize_text(text)
    return [paragraph.strip() for paragraph in normalized.split("\n\n") if paragraph.strip()]
