"""Konfiguration aus Umgebungsvariablen (optional über .env)."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path


def _load_dotenv(path: Path) -> None:
    """Minimaler .env-Loader, damit keine weitere Abhängigkeit nötig ist."""
    if not path.is_file():
        return
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


@dataclass
class Settings:
    db_path: Path = field(default_factory=lambda: Path(os.environ.get("LV_DB_PATH", "data/lessons.db")))
    token: str = field(default_factory=lambda: os.environ.get("LV_TOKEN", ""))
    anthropic_api_key: str = field(default_factory=lambda: os.environ.get("ANTHROPIC_API_KEY", ""))
    claude_model: str = field(default_factory=lambda: os.environ.get("LV_CLAUDE_MODEL", "claude-opus-5-5"))
    claude_effort: str = field(default_factory=lambda: os.environ.get("LV_CLAUDE_EFFORT", "low"))
    voyage_api_key: str = field(default_factory=lambda: os.environ.get("VOYAGE_API_KEY", ""))
    voyage_model: str = field(default_factory=lambda: os.environ.get("LV_VOYAGE_MODEL", "voyage-3.5"))
    embedding_provider: str = field(default_factory=lambda: os.environ.get("LV_EMBEDDINGS", "auto"))

    @property
    def ki_aktiv(self) -> bool:
        return bool(self.anthropic_api_key)


def load_settings() -> Settings:
    _load_dotenv(Path(os.environ.get("LV_ENV_FILE", ".env")))
    return Settings()
