"""Test penghitung token."""

from app.core.tokens import count_tokens, tail_by_tokens


def test_empty_text_has_zero_tokens() -> None:
    assert count_tokens("") == 0


def test_longer_text_has_more_tokens() -> None:
    assert count_tokens("halo dunia") < count_tokens("halo dunia " * 20)


def test_special_token_literal_is_safe_to_count() -> None:
    # tiktoken melempar error untuk string yang menyerupai token spesial,
    # kecuali kalau disallowed_special dinonaktifkan.
    assert count_tokens("<|endoftext|>") > 0


def test_tail_returns_whole_words_from_the_end() -> None:
    text = "satu dua tiga empat lima enam tujuh delapan sembilan sepuluh"

    tail = tail_by_tokens(text, 6)

    assert text.endswith(tail)
    assert count_tokens(tail) <= 6


def test_tail_of_short_text_is_the_text_itself() -> None:
    assert tail_by_tokens("dua kata", 50) == "dua kata"


def test_tail_with_zero_budget_is_empty() -> None:
    assert tail_by_tokens("apa pun", 0) == ""
