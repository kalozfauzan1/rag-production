"""Test setelan ingestion di Settings."""

from pathlib import Path

from app.core.config import Settings


def test_defaults_match_spec() -> None:
    settings = Settings(_env_file=None)

    assert settings.max_upload_bytes == 20 * 1024 * 1024
    assert settings.chunk_max_tokens == 800
    assert settings.chunk_overlap_tokens == 96


def test_env_overrides_chunk_budget(monkeypatch) -> None:
    monkeypatch.setenv("CHUNK_MAX_TOKENS", "500")

    assert Settings(_env_file=None).chunk_max_tokens == 500


def test_derived_directories_follow_data_dir(tmp_path: Path) -> None:
    settings = Settings(_env_file=None, data_dir=tmp_path)

    assert settings.uploads_dir == tmp_path / "uploads"
    assert settings.documents_dir == tmp_path / "documents"
