"""Test extractor per format."""

from pathlib import Path

import pytest

from app.services.ingestion.errors import ScannedPdfError, UnsupportedFormatError
from app.services.ingestion.extractors import SUPPORTED_EXTENSIONS, get_extractor
from tests.pdf_factory import build_pdf

ARTICLE_HTML = """<!doctype html>
<html lang="id">
  <head><title>Panduan RAG</title></head>
  <body>
    <nav><a href="/">Beranda</a> | <a href="/tentang">Tentang</a></nav>
    <article>
      <h1>Panduan RAG</h1>
      <p>Isi artikel yang sebenarnya menjelaskan cara kerja retrieval augmented
      generation untuk pembaca yang baru mulai.</p>
      <p>Paragraf kedua menambahkan detail tentang chunking, embedding, dan
      bagaimana keduanya bertemu di tahap retrieval.</p>
      <p>Paragraf ketiga menutup dengan catatan tentang evaluasi kualitas
      jawaban supaya sistem tidak sekadar terlihat jalan.</p>
    </article>
    <footer>Hak cipta 2026</footer>
  </body>
</html>
"""


def test_pdf_extraction_keeps_page_numbers(tmp_path: Path) -> None:
    path = tmp_path / "dua-halaman.pdf"
    path.write_bytes(
        build_pdf(
            [
                "Halaman pertama berisi teks yang cukup panjang untuk diuji.",
                "Halaman kedua berisi teks yang berbeda dari halaman sebelumnya.",
            ]
        )
    )

    document = get_extractor(path)(path)

    assert document.page_count == 2
    assert {block.page for block in document.blocks} == {1, 2}
    assert "Halaman pertama" in " ".join(block.text for block in document.blocks)


def test_pdf_without_text_layer_is_reported_as_scanned(tmp_path: Path) -> None:
    path = tmp_path / "scan.pdf"
    path.write_bytes(build_pdf([""]))

    with pytest.raises(ScannedPdfError):
        get_extractor(path)(path)


def test_html_extraction_drops_boilerplate(tmp_path: Path) -> None:
    path = tmp_path / "artikel.html"
    path.write_text(ARTICLE_HTML, encoding="utf-8")

    document = get_extractor(path)(path)
    text = " ".join(block.text for block in document.blocks)

    assert document.title == "Panduan RAG"
    assert "Isi artikel yang sebenarnya" in text
    assert "Beranda" not in text
    assert "Hak cipta" not in text


def test_markdown_headings_become_sections(tmp_path: Path) -> None:
    path = tmp_path / "catatan.md"
    path.write_text(
        "# Bab Satu\n\nIsi bab **pertama** dengan `kode`.\n\n## Sub Bab\n\nIsi sub bab.\n",
        encoding="utf-8",
    )

    document = get_extractor(path)(path)

    assert [block.section for block in document.blocks] == ["Bab Satu", "Sub Bab"]
    assert document.blocks[0].text == "Isi bab pertama dengan kode."


def test_plain_text_file_still_produces_blocks(tmp_path: Path) -> None:
    path = tmp_path / "catatan.txt"
    path.write_text("Paragraf satu.\n\nParagraf dua.\n", encoding="utf-8")

    document = get_extractor(path)(path)

    assert [block.text for block in document.blocks] == ["Paragraf satu.", "Paragraf dua."]


def test_unknown_extension_is_rejected(tmp_path: Path) -> None:
    with pytest.raises(UnsupportedFormatError):
        get_extractor(tmp_path / "data.xlsx")

    assert ".pdf" in SUPPORTED_EXTENSIONS
