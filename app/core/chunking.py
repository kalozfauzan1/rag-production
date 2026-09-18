"""Pemotongan dokumen menjadi chunk berbasis token.

Pendekatan: semua block digabung menjadi satu teks ternormalisasi, lalu dipotong
berdasarkan **offset karakter**. Batas tiap chunk dicari dengan `count_tokens` pada
slice aslinya.

Kenapa tidak menjumlahkan token per potongan kecil: tokenisasi BPE **tidak aditif**.
`count_tokens("kata ")` sendirian ≈ 3 token, tetapi di dalam teks panjang kontribusinya
≈ 1 token, karena BPE menggabungkan pasangan yang sering muncul bersama. Menjumlahkan
angka per potongan membuat chunk jauh lebih pendek dari anggaran (terukur: 234 token
padahal anggarannya 704). Karena itu setiap kandidat batas dihitung dari teks aslinya.

Tahap: flatten → cari batas per chunk → geser ke separator terdekat → tambahkan overlap.
"""

from dataclasses import dataclass

from app.core.tokens import count_tokens, tail_by_tokens
from app.schemas.documents import Block, Chunk

# Dari yang paling semantik ke paling halus. String kosong = tidak ada separator lagi.
SEPARATORS: tuple[str, ...] = ("\n\n", "\n", ". ", " ", "")

# Pemisah antar block di teks dokumen ternormalisasi — dipakai juga saat menghitung
# offset karakter, jadi jangan diubah sepihak.
BLOCK_SEPARATOR = "\n\n"

# Separator hanya dipakai kalau posisinya masuk dalam bagian terakhir rentang yang
# tersedia. Tanpa ini, satu paragraf baru di awal chunk bisa membuat chunk jadi pendek.
SNAP_MARGIN = 0.6


@dataclass(frozen=True)
class _Span:
    """Rentang satu block di dalam teks dokumen."""

    start: int
    end: int
    page: int | None
    section: str | None


def chunk_document(
    blocks: list[Block],
    *,
    doc_id: str,
    max_tokens: int = 800,
    overlap_tokens: int = 96,
) -> list[Chunk]:
    """Ubah block menjadi chunk ≤ max_tokens dengan overlap antar-chunk."""
    if not blocks:
        return []

    budget = max(1, max_tokens - overlap_tokens)
    text, spans, hard_bounds = _flatten(blocks)
    if not text.strip():
        return []

    # Perkiraan awal berapa karakter per token di dokumen ini; hanya untuk mempersempit
    # ruang pencarian, keputusan akhirnya tetap dari count_tokens.
    chars_per_token = len(text) / max(1, count_tokens(text))

    chunks: list[Chunk] = []
    previous_text = ""
    cursor = 0
    while cursor < len(text):
        limit = _largest_fitting_end(text, cursor, budget, chars_per_token)
        # Kalau sisa dokumen masih muat dalam satu chunk, ambil semuanya: memotong di
        # separator hanya akan menyisakan serpihan beberapa karakter sebagai chunk baru.
        end = len(text) if limit >= len(text) else _snap_to_separator(text, cursor, limit)
        end = min(end, _next_hard_bound(cursor, hard_bounds, len(text)))
        if end <= cursor:
            end = min(cursor + 1, len(text))

        raw = text[cursor:end]
        body = raw.strip()
        if body:
            span = _span_at(spans, cursor)
            overlap = tail_by_tokens(previous_text, overlap_tokens) if chunks else ""
            chunk_text = f"{overlap}\n\n{body}" if overlap else body
            leading = len(raw) - len(raw.lstrip())
            chunks.append(
                Chunk(
                    doc_id=doc_id,
                    chunk_index=len(chunks),
                    text=chunk_text,
                    token_count=count_tokens(chunk_text),
                    char_start=cursor + leading,
                    char_end=cursor + leading + len(body),
                    page=span.page if span else None,
                    section=span.section if span else None,
                )
            )
            previous_text = chunk_text
        cursor = end

    return chunks


def _flatten(blocks: list[Block]) -> tuple[str, list[_Span], list[int]]:
    """Gabung block jadi satu teks; catat rentang tiap block dan batas section keras.

    Batas keras ditaruh tepat di awal block yang section-nya berbeda: chunk tidak boleh
    melintasi pergantian section, karena itu batas makna yang paling jelas.
    """
    parts: list[str] = []
    spans: list[_Span] = []
    hard_bounds: list[int] = []
    cursor = 0
    previous_section: str | None = None

    for index, block in enumerate(blocks):
        if index > 0:
            parts.append(BLOCK_SEPARATOR)
            cursor += len(BLOCK_SEPARATOR)
            if block.section != previous_section:
                hard_bounds.append(cursor)
        spans.append(
            _Span(
                start=cursor,
                end=cursor + len(block.text),
                page=block.page,
                section=block.section,
            )
        )
        parts.append(block.text)
        cursor += len(block.text)
        previous_section = block.section

    return "".join(parts), spans, hard_bounds


def _largest_fitting_end(text: str, start: int, budget: int, chars_per_token: float) -> int:
    """Offset terjauh (eksklusif) yang isinya masih ≤ `budget` token dari `start`."""
    estimated = max(1, int(budget * chars_per_token))
    low = start + 1
    high = min(len(text), start + estimated * 2)
    best = low
    while low <= high:
        middle = (low + high) // 2
        if count_tokens(text[start:middle]) <= budget:
            best = middle
            low = middle + 1
        else:
            high = middle - 1
    return best


def _snap_to_separator(text: str, start: int, limit: int) -> int:
    """Geser akhir mundur ke separator paling semantik yang dekat dengan `limit`."""
    minimum = start + int((limit - start) * SNAP_MARGIN)
    for separator in SEPARATORS:
        if not separator:
            break
        position = text.rfind(separator, start, limit)
        if position != -1 and position + len(separator) >= minimum:
            return position + len(separator)
    return limit


def _next_hard_bound(cursor: int, hard_bounds: list[int], text_length: int) -> int:
    """Batas section berikutnya setelah `cursor` (atau akhir teks)."""
    for bound in hard_bounds:
        if bound > cursor:
            return bound
    return text_length


def _span_at(spans: list[_Span], cursor: int) -> _Span | None:
    """Block yang memuat `cursor`; kalau cursor jatuh di celah, pakai block sebelumnya."""
    found: _Span | None = None
    for span in spans:
        if span.start > cursor:
            break
        found = span
    return found
