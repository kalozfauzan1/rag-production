"""Pembuat PDF minimal untuk test: tanpa dependency tambahan, tanpa biner di git.

Struktur: 1 catalog, 2 pages, 3 font, lalu per halaman: page object + content stream.
Tabel xref dihitung dari byte yang benar-benar ditulis, jadi PDF-nya valid.
"""


def build_pdf(pages: list[str]) -> bytes:
    """Setiap string di `pages` menjadi satu halaman berisi satu baris teks."""
    page_count = len(pages)
    first_page_object = 4
    first_content_object = first_page_object + page_count

    kids = " ".join(f"{first_page_object + index} 0 R" for index in range(page_count))
    objects: dict[int, bytes] = {
        1: b"<< /Type /Catalog /Pages 2 0 R >>",
        2: f"<< /Type /Pages /Kids [{kids}] /Count {page_count} >>".encode(),
        3: b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
    }

    for index, page_text in enumerate(pages):
        stream = _content_stream(page_text)
        contents_ref = first_content_object + index
        objects[first_page_object + index] = (
            f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] "
            f"/Resources << /Font << /F1 3 0 R >> >> /Contents {contents_ref} 0 R >>"
        ).encode()
        objects[first_content_object + index] = (
            f"<< /Length {len(stream)} >>\nstream\n".encode() + stream + b"\nendstream"
        )

    payload = bytearray(b"%PDF-1.4\n")
    offsets: dict[int, int] = {}
    for number in sorted(objects):
        offsets[number] = len(payload)
        payload += f"{number} 0 obj\n".encode() + objects[number] + b"\nendobj\n"

    size = max(objects) + 1
    xref_offset = len(payload)
    payload += f"xref\n0 {size}\n".encode()
    payload += b"0000000000 65535 f \n"
    for number in range(1, size):
        payload += f"{offsets[number]:010d} 00000 n \n".encode()
    payload += f"trailer\n<< /Size {size} /Root 1 0 R >>\n".encode()
    payload += f"startxref\n{xref_offset}\n%%EOF\n".encode()
    return bytes(payload)


def _content_stream(page_text: str) -> bytes:
    escaped = page_text.replace("\\", r"\\").replace("(", r"\(").replace(")", r"\)")
    return f"BT /F1 12 Tf 72 720 Td ({escaped}) Tj ET".encode()
