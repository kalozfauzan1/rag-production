"""Test normalisasi teks hasil ekstraksi."""

from app.services.ingestion.normalize import normalize_text, split_paragraphs


def test_joins_words_split_by_hyphen_at_line_end() -> None:
    assert normalize_text("infor-\nmation penting") == "information penting"


def test_collapses_repeated_spaces() -> None:
    assert normalize_text("halo    dunia") == "halo dunia"


def test_collapses_three_or_more_blank_lines() -> None:
    assert normalize_text("a\n\n\n\nb") == "a\n\nb"


def test_removes_trailing_spaces_at_line_end() -> None:
    assert normalize_text("baris satu   \nbaris dua") == "baris satu\nbaris dua"


def test_normalizes_windows_line_endings() -> None:
    assert normalize_text("a\r\nb") == "a\nb"


def test_split_paragraphs_drops_empty_ones() -> None:
    assert split_paragraphs("Paragraf satu.\n\n\n\nParagraf dua.\n") == [
        "Paragraf satu.",
        "Paragraf dua.",
    ]


def test_split_paragraphs_of_blank_text_is_empty() -> None:
    assert split_paragraphs("   \n\n  ") == []
