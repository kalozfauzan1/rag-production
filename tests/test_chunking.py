"""Test pemotongan dokumen menjadi chunk."""

from app.core.chunking import BLOCK_SEPARATOR, chunk_document
from app.core.tokens import count_tokens
from app.schemas.documents import Block


def make_text(tokens: int) -> str:
    """Teks yang panjangnya mendekati `tokens` token."""
    words: list[str] = []
    while count_tokens(" ".join(words)) < tokens:
        words.append("kata")
    return " ".join(words)


def make_blocks(*specs: tuple[str | None, int]) -> list[Block]:
    """(section, jumlah token) → daftar Block."""
    return [
        Block(text=make_text(tokens), order=index, section=section)
        for index, (section, tokens) in enumerate(specs)
    ]


def test_every_chunk_stays_within_max_tokens() -> None:
    blocks = make_blocks((None, 900), (None, 900), (None, 900))

    chunks = chunk_document(blocks, doc_id="d1", max_tokens=800, overlap_tokens=96)

    assert len(chunks) >= 2
    assert all(chunk.token_count <= 800 for chunk in chunks)
    assert [chunk.chunk_index for chunk in chunks] == list(range(len(chunks)))


def test_next_chunk_starts_with_tail_of_previous() -> None:
    blocks = make_blocks((None, 600), (None, 600))

    chunks = chunk_document(blocks, doc_id="d1", max_tokens=800, overlap_tokens=96)

    assert len(chunks) == 2
    previous_words = chunks[0].text.split()
    next_words = chunks[1].text.split()
    assert next_words[:5] == previous_words[-5:]


def test_chunks_do_not_cross_sections() -> None:
    # Dua section kecil: tanpa aturan batas section, keduanya akan jadi satu chunk.
    blocks = make_blocks(("Bab Satu", 200), ("Bab Dua", 200))

    chunks = chunk_document(blocks, doc_id="d1", max_tokens=800, overlap_tokens=96)

    assert [chunk.section for chunk in chunks] == ["Bab Satu", "Bab Dua"]


def test_giant_paragraph_is_split_at_sentence_boundaries() -> None:
    sentence = "Ini kalimat contoh yang cukup panjang. "
    blocks = [Block(text=sentence * 120, order=0, section=None)]

    chunks = chunk_document(blocks, doc_id="d1", max_tokens=800, overlap_tokens=96)

    assert len(chunks) >= 2
    assert all(chunk.token_count <= 800 for chunk in chunks)
    assert all(chunk.text.rstrip().endswith(".") for chunk in chunks)


def test_short_tail_stays_a_separate_chunk() -> None:
    # Dokumen lebih panjang dari budget: sisanya menjadi chunk pendek tersendiri.
    # Menggabungnya ke chunk sebelumnya akan melewati max_tokens, jadi tidak dilakukan.
    blocks = make_blocks((None, 750), (None, 200))

    chunks = chunk_document(blocks, doc_id="d1", max_tokens=800, overlap_tokens=96)

    assert len(chunks) == 2
    assert all(chunk.token_count <= 800 for chunk in chunks)


def test_char_offsets_point_at_new_content() -> None:
    blocks = make_blocks((None, 600), (None, 600))
    document_text = BLOCK_SEPARATOR.join(block.text for block in blocks)

    chunks = chunk_document(blocks, doc_id="d1", max_tokens=800, overlap_tokens=96)

    for chunk in chunks:
        assert document_text[chunk.char_start : chunk.char_end] in chunk.text


def test_unicode_text_is_not_mangled() -> None:
    blocks = [Block(text="Kafé Zürich 🎉 " * 80, order=0, section=None)]

    chunks = chunk_document(blocks, doc_id="d1", max_tokens=800, overlap_tokens=96)

    assert all("\ufffd" not in chunk.text for chunk in chunks)


def test_empty_document_produces_no_chunks() -> None:
    assert chunk_document([], doc_id="d1") == []
