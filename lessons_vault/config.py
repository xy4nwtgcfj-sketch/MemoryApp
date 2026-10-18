"""Konfiguration aus Umgebungsvariablen (optional über .env)."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path


def _load_dotenv(path: Path) -> None:
    """Minimaler .env-Loader, damit keine weitere Abhängigkeit nötig ist."""
    if not path.is_file():
        return
    daten = path.read_bytes()
    # PowerShell 5.1 schreibt mit ">" UTF-16; Editor oft UTF-8 mit BOM. Beides tolerieren.
    if daten.startswith((b"\xff\xfe", b"\xfe\xff")):
        text = daten.decode("utf-16")
    else:
        try:
            text = daten.decode("utf-8-sig")
        except UnicodeDecodeError as exc:
            raise SystemExit(f".env ist nicht als UTF-8 lesbar ({exc}). Bitte im Editor als UTF-8 speichern.") from exc
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


@dataclass
class Settings:
    db_path: Path = field(default_factory=lambda: Path(os.environ.get("LV_DB_PATH", "data/lessons.db")))
    token: str = field(default_factory=lambda: os.environ.get("LV_TOKEN", ""))
    # Ohne LV_TOKEN wird ein Zugangstoken erzeugt und in data/zugangstoken.txt abgelegt (nur Tests schalten das ab).
    token_erzwingen: bool = field(default_factory=lambda: os.environ.get("LV_TOKEN_ERZWINGEN", "1") != "0")
    # Erlaubte Host-Header (Schutz gegen DNS-Rebinding); *.ts.net deckt "tailscale serve" ab.
    erlaubte_hosts: list[str] = field(
        default_factory=lambda: [h.strip() for h in os.environ.get("LV_HOSTS", "127.0.0.1,localhost,*.ts.net").split(",") if h.strip()]
    )
    anthropic_api_key: str = field(default_factory=lambda: os.environ.get("ANTHROPIC_API_KEY", ""))
    claude_model: str = field(default_factory=lambda: os.environ.get("LV_CLAUDE_MODEL", "claude-opus-5-5"))
    claude_effort: str = field(default_factory=lambda: os.environ.get("LV_CLAUDE_EFFORT", "low"))
    # Ein Plan aus Fachwissen und Erfahrung braucht mehr Tiefe als die Strukturierung einer Notiz.
    briefing_effort: str = field(default_factory=lambda: os.environ.get("LV_BRIEFING_EFFORT", "medium"))
    voyage_api_key: str = field(default_factory=lambda: os.environ.get("VOYAGE_API_KEY", ""))
    voyage_model: str = field(default_factory=lambda: os.environ.get("LV_VOYAGE_MODEL", "voyage-3.5"))
    embedding_provider: str = field(default_factory=lambda: os.environ.get("LV_EMBEDDINGS", "auto"))
    ollama_url: str = field(default_factory=lambda: os.environ.get("LV_OLLAMA_URL", "http://127.0.0.1:11434"))
    ollama_model: str = field(default_factory=lambda: os.environ.get("LV_OLLAMA_MODEL", "qwen2.5:7b"))
    ollama_embed_model: str = field(default_factory=lambda: os.environ.get("LV_OLLAMA_EMBED_MODEL", "bge-m3"))
    tesseract_cmd: str = field(default_factory=lambda: os.environ.get("LV_TESSERACT_CMD", ""))
    bilder_pfad: str = field(default_factory=lambda: os.environ.get("LV_BILDER_PATH", ""))
    worker_aktiv: bool = field(default_factory=lambda: os.environ.get("LV_WORKER", "1") != "0")

    @property
    def ki_aktiv(self) -> bool:
        return bool(self.anthropic_api_key)


def load_settings() -> Settings:
    _load_dotenv(Path(os.environ.get("LV_ENV_FILE", ".env")))
    return Settings()
