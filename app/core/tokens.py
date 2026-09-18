"""Penghitung token berbasis tiktoken.

Tokenizer yang dipakai `cl100k_base` — sama dengan `text-embedding-3-*`, kandidat utama
task 3. Model embedding lain punya tokenizer berbeda, jadi angka "token" di sini tidak
otomatis berlaku untuk mereka (risiko yang dicatat di spec task 2).

Catatan operasional: `tiktoken.get_encoding()` mengunduh kosakata pada pemakaian pertama
(~1,7 MB) lalu menyimpannya di cache; setelah itu bisa dipakai offline.
"""

import tiktoken

_ENCODING_NAME = "cl100k_base"
_encoding: tiktoken.Encoding | None = None


def get_encoding() -> tiktoken.Encoding:
    """Encoding dipakai ulang; memuatnya butuh IO, jadi jangan per panggilan."""
    global _encoding
    if _encoding is None:
        _encoding = tiktoken.get_encoding(_ENCODING_NAME)
    return _encoding


def count_tokens(text: str) -> int:
    """Jumlah token `cl100k_base` untuk teks ini."""
    if not text:
        return 0
    return len(get_encoding().encode(text, disallowed_special=()))


def tail_by_tokens(text: str, max_tokens: int) -> str:
    """Ambil ekor teks (utuh per kata) sebanyak maksimal `max_tokens` token.

    Dipakai untuk overlap antar-chunk. Bekerja per kata, bukan per potongan token,
    supaya tidak pernah memotong karakter di tengah — tiktoken akan menghasilkan
    U+FFFD untuk potongan byte yang tidak valid.
    """
    if max_tokens <= 0 or not text:
        return ""

    picked: list[str] = []
    used = 0
    for word in reversed(text.split()):
        cost = count_tokens(word) + (1 if picked else 0)  # +1 untuk spasi pemisah
        if used + cost > max_tokens:
            break
        picked.append(word)
        used += cost
    return " ".join(reversed(picked))
