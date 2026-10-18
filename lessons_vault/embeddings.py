"""Embedding-Anbieter.

Anthropic bietet kein eigenes Embedding-Modell an und empfiehlt Voyage AI. Ohne
VOYAGE_API_KEY greift ein lokaler Hashing-Vektor über Zeichen-n-Gramme. Der ist
unscharf-lexikalisch (tolerant für Tippfehler und Wortteile), aber nicht semantisch:
"Kredit" findet damit nicht "Darlehen".
"""

from __future__ import annotations

import hashlib
import re
from typing import Literal, Protocol

import httpx
import numpy as np

InputType = Literal["document", "query"]


class EmbeddingProvider(Protocol):
    name: str
    semantisch: bool
    dublettenschwelle: float
    kandidatenschwelle: float

    def embed(self, texts: list[str], input_type: InputType) -> list[np.ndarray]: ...


class EmbeddingFehler(Exception):
    pass


class HashingProvider:
    """Lokaler Fallback ohne Netzwerk: Zeichen-3/4-Gramme, Feature-Hashing, L2-normiert."""

    name = "lokal-hashing-v1"
    semantisch = False
    dublettenschwelle = 0.6
    kandidatenschwelle = 0.25

    def __init__(self, dim: int = 1024):
        self.dim = dim

    @staticmethod
    def _normalize(text: str) -> str:
        text = text.lower()
        for src, dst in (("ä", "ae"), ("ö", "oe"), ("ü", "ue"), ("ß", "ss")):
            text = text.replace(src, dst)
        return re.sub(r"[^a-z0-9]+", " ", text).strip()

    def _vector(self, text: str) -> np.ndarray:
        vec = np.zeros(self.dim, dtype=np.float32)
        for word in self._normalize(text).split():
            padded = f" {word} "
            for n in (3, 4):
                for i in range(len(padded) - n + 1):
                    digest = hashlib.blake2b(padded[i : i + n].encode(), digest_size=8).digest()
                    h = int.from_bytes(digest, "little")
                    vec[h % self.dim] += 1.0 if (h >> 63) & 1 else -1.0
        norm = np.linalg.norm(vec)
        return vec / norm if norm else vec

    def embed(self, texts: list[str], input_type: InputType = "document") -> list[np.ndarray]:
        return [self._vector(t) for t in texts]


class VoyageProvider:
    """Voyage AI Embeddings (von Anthropic empfohlener Anbieter)."""

    semantisch = True
    dublettenschwelle = 0.82
    kandidatenschwelle = 0.45
    URL = "https://api.voyageai.com/v1/embeddings"

    def __init__(self, api_key: str, model: str, client: httpx.Client | None = None):
        self.api_key = api_key
        self.model = model
        self.name = f"voyage:{model}"
        self._client = client or httpx.Client(timeout=20.0)

    def embed(self, texts: list[str], input_type: InputType = "document") -> list[np.ndarray]:
        if not texts:
            return []
        try:
            response = self._client.post(
                self.URL,
                headers={"Authorization": f"Bearer {self.api_key}"},
                json={"input": texts, "model": self.model, "input_type": input_type},
            )
            response.raise_for_status()
        except httpx.HTTPError as exc:
            raise EmbeddingFehler(f"Voyage-Embedding fehlgeschlagen: {exc}") from exc
        items = sorted(response.json()["data"], key=lambda item: item["index"])
        vectors = [np.asarray(item["embedding"], dtype=np.float32) for item in items]
        return [v / (np.linalg.norm(v) or 1.0) for v in vectors]


class OllamaEmbeddings:
    """Lokale Embeddings über Ollama (Standard: bge-m3, mehrsprachig)."""

    semantisch = True
    # Erfahrungswerte für bge-m3; mit scripts/benchmark_lokal.py am eigenen Bestand prüfen.
    dublettenschwelle = 0.85
    kandidatenschwelle = 0.5

    def __init__(self, url: str, model: str, client: httpx.Client | None = None, query_timeout: float = 8.0):
        self.url = url.rstrip("/")
        self.model = model
        self.name = f"ollama:{model}"
        self.query_timeout = query_timeout
        self._client = client or httpx.Client(timeout=120.0)

    def embed(self, texts: list[str], input_type: InputType = "document") -> list[np.ndarray]:
        if not texts:
            return []
        # Suchanfragen mit kurzem Timeout: Läuft gerade eine lokale Strukturierung, wartet Ollama
        # sonst womöglich minutenlang. Die Suche fällt dann auf Volltext zurück.
        timeout = self.query_timeout if input_type == "query" else 120.0
        try:
            response = self._client.post(
                f"{self.url}/api/embed",
                json={"model": self.model, "input": texts, "keep_alive": "30m"},
                timeout=timeout,
            )
            response.raise_for_status()
            vectors = [np.asarray(v, dtype=np.float32) for v in response.json()["embeddings"]]
        except (httpx.HTTPError, KeyError, ValueError) as exc:
            raise EmbeddingFehler(f"Ollama-Embedding fehlgeschlagen: {exc}") from exc
        if len(vectors) != len(texts):
            raise EmbeddingFehler("Ollama lieferte eine unerwartete Anzahl Embeddings")
        return [v / (np.linalg.norm(v) or 1.0) for v in vectors]


def ollama_status(url: str, timeout: float = 2.0) -> dict[str, object]:
    """Ist Ollama erreichbar, welche Modelle sind installiert?"""
    try:
        response = httpx.get(f"{url.rstrip('/')}/api/tags", timeout=timeout)
        response.raise_for_status()
        modelle = [m["name"] for m in response.json().get("models", [])]
        return {"erreichbar": True, "modelle": modelle}
    except (httpx.HTTPError, KeyError, ValueError):
        return {"erreichbar": False, "modelle": []}


def modell_installiert(name: str, modelle: list[str]) -> bool:
    """Ollama meldet 'bge-m3:latest', konfiguriert ist oft nur 'bge-m3'."""
    return any(m == name or m == f"{name}:latest" for m in modelle)


def create_provider(
    kind: str,
    voyage_api_key: str,
    voyage_model: str,
    ollama_url: str = "",
    ollama_embed_model: str = "",
) -> EmbeddingProvider:
    if kind == "voyage":
        if not voyage_api_key:
            raise ValueError("LV_EMBEDDINGS=voyage erfordert VOYAGE_API_KEY")
        return VoyageProvider(voyage_api_key, voyage_model)
    if kind == "ollama":
        return OllamaEmbeddings(ollama_url, ollama_embed_model)
    if kind == "lokal":
        return HashingProvider()
    # auto: lokal vor Cloud. Ollama, wenn erreichbar; sonst Voyage, wenn ein Key da ist; sonst Hashing.
    if ollama_url and ollama_embed_model:
        status = ollama_status(ollama_url)
        if status["erreichbar"] and modell_installiert(ollama_embed_model, status["modelle"]):  # type: ignore[arg-type]
            return OllamaEmbeddings(ollama_url, ollama_embed_model)
    if voyage_api_key:
        return VoyageProvider(voyage_api_key, voyage_model)
    return HashingProvider()


def provider_fuer_bestand(
    bestand: str, voyage_api_key: str, voyage_model: str, ollama_url: str, ollama_embed_model: str
) -> EmbeddingProvider | None:
    """Im Modus auto beim bisher genutzten Anbieter bleiben, auch wenn er beim Start noch nicht erreichbar ist.

    Sonst würde ein langsamer Ollama-Start den ganzen Bestand auf ein schwächeres Verfahren umindexieren.
    """
    if bestand.startswith("ollama:") and ollama_url:
        return OllamaEmbeddings(ollama_url, bestand.split(":", 1)[1])
    if bestand.startswith("voyage:") and voyage_api_key:
        return VoyageProvider(voyage_api_key, bestand.split(":", 1)[1])
    return None


def lesson_text(titel: str, situation: str, ereignis: str, lesson: str, massnahme: str = "", tags: list[str] | None = None) -> str:
    """Text, der für eine Lesson eingebettet wird. Regel und Titel zuerst, weil sie am aussagekräftigsten sind."""
    parts = [titel, lesson, situation, ereignis, massnahme, " ".join(tags or [])]
    return "\n".join(p for p in parts if p)


def cosine_scores(query: np.ndarray, matrix: np.ndarray) -> np.ndarray:
    if matrix.size == 0:
        return np.zeros(0, dtype=np.float32)
    return matrix @ query
