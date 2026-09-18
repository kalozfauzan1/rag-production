"""Baca/tulis hasil ingestion di disk.

Tata letak:
    data/uploads/{doc_id}{ext}
    data/documents/{doc_id}/meta.json
    data/documents/{doc_id}/chunks.jsonl

Semua operasi berbasis path — tidak ada tipe HTTP di modul ini.
"""

from datetime import UTC, datetime
from pathlib import Path

from app.schemas.documents import Chunk, DocumentMeta


class DocumentStore:
    """Akses file untuk dokumen: metadata dan chunk."""

    def __init__(self, *, uploads_dir: Path, documents_dir: Path) -> None:
        self.uploads_dir = uploads_dir
        self.documents_dir = documents_dir

    def upload_path(self, doc_id: str, suffix: str) -> Path:
        return self.uploads_dir / f"{doc_id}{suffix}"

    def exists(self, doc_id: str) -> bool:
        return self._meta_path(doc_id).exists()

    def write_meta(self, meta: DocumentMeta) -> None:
        path = self._meta_path(meta.doc_id)
        path.parent.mkdir(parents=True, exist_ok=True)
        self._write_atomic(path, meta.model_dump_json(indent=2))

    def read_meta(self, doc_id: str) -> DocumentMeta:
        content = self._meta_path(doc_id).read_text(encoding="utf-8")
        return DocumentMeta.model_validate_json(content)

    def update_meta(self, doc_id: str, **fields: object) -> DocumentMeta:
        """Baca-ubah-tulis meta.json sekaligus memperbarui `updated_at`."""
        meta = self.read_meta(doc_id)
        updated = meta.model_copy(update={**fields, "updated_at": datetime.now(UTC)})
        self.write_meta(updated)
        return updated

    def list_meta(self) -> list[DocumentMeta]:
        """Semua dokumen, terbaru dulu; file rusak dilewati agar listing tetap hidup."""
        if not self.documents_dir.exists():
            return []
        metas: list[DocumentMeta] = []
        for meta_path in self.documents_dir.glob("*/meta.json"):
            try:
                metas.append(
                    DocumentMeta.model_validate_json(meta_path.read_text(encoding="utf-8"))
                )
            except (OSError, ValueError):
                continue
        return sorted(metas, key=lambda meta: meta.created_at, reverse=True)

    def write_chunks(self, doc_id: str, chunks: list[Chunk]) -> None:
        path = self.documents_dir / doc_id / "chunks.jsonl"
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("w", encoding="utf-8") as handle:
            for chunk in chunks:
                handle.write(chunk.model_dump_json() + "\n")

    def read_chunks(
        self, doc_id: str, *, offset: int = 0, limit: int = 20
    ) -> tuple[int, list[Chunk]]:
        path = self.documents_dir / doc_id / "chunks.jsonl"
        if not path.exists():
            return 0, []
        chunks = [
            Chunk.model_validate_json(line)
            for line in path.read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]
        return len(chunks), chunks[offset : offset + limit]

    def _meta_path(self, doc_id: str) -> Path:
        return self.documents_dir / doc_id / "meta.json"

    @staticmethod
    def _write_atomic(path: Path, content: str) -> None:
        """Lewat file sementara: meta.json tidak pernah terbaca setengah jadi."""
        temporary = path.with_name(f"{path.name}.tmp")
        temporary.write_text(content, encoding="utf-8")
        temporary.replace(path)
