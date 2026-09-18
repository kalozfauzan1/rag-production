"""Konfigurasi aplikasi dari environment / file .env."""

from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Semua knob runtime; default-nya nilai dev yang aman."""

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    cors_origins: str = "http://localhost:3000"
    fake_token_delay_ms: int = 60
    sse_ping_interval_seconds: float = 15.0

    data_dir: Path = Path("data")
    max_upload_bytes: int = 20 * 1024 * 1024
    chunk_max_tokens: int = 800
    chunk_overlap_tokens: int = 96

    @property
    def cors_origin_list(self) -> list[str]:
        """CORS_ORIGINS boleh berisi beberapa origin, dipisah koma."""
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]

    @property
    def uploads_dir(self) -> Path:
        """File asli hasil upload."""
        return self.data_dir / "uploads"

    @property
    def documents_dir(self) -> Path:
        """Metadata + chunk hasil ingestion."""
        return self.data_dir / "documents"


@lru_cache
def get_settings() -> Settings:
    """Dibaca sekali per proses; di test di-override lewat dependency_overrides."""
    return Settings()
