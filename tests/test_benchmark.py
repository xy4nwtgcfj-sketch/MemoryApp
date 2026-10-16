import importlib.util
from pathlib import Path

from .ollama_mock import OllamaMock

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("benchmark_lokal", ROOT / "scripts" / "benchmark_lokal.py")
benchmark = importlib.util.module_from_spec(spec)
spec.loader.exec_module(benchmark)


def test_bericht(tmp_path, monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    mock = OllamaMock()
    ziel = benchmark.run(
        ["--url", "http://ollama", "--modelle", "qwen2.5:7b", "gemma3:4b", "--ausgabe", str(tmp_path / "b.md")],
        client=mock.client(),
    )
    text = ziel.read_text(encoding="utf-8")
    assert "## Embeddings" in text and "| Synonym |" in text.replace(" / Darlehenskonditionen besprechen", "")
    assert "| qwen2.5:7b |" in text
    assert "gemma3:4b" not in text.split("## Strukturierung")[1]  # fehlt und ohne --pull übersprungen
    assert "### Abstraktion" in text


def test_pull(tmp_path):
    mock = OllamaMock()
    benchmark.run(["--url", "http://ollama", "--modelle", "gemma3:4b", "--pull", "--ausgabe", str(tmp_path / "b.md")], client=mock.client())
    assert "gemma3:4b" in mock.modelle and mock.chat_requests[0]["model"] == "gemma3:4b"


def test_ram_bewertung():
    gb = 2**30
    assert "Single-Channel" in benchmark.ram_bewertung([{"Capacity": 32 * gb, "Speed": 3200}])
    assert "Dual-Channel, gut" in benchmark.ram_bewertung([{"Capacity": 16 * gb, "Speed": 3200}] * 2)
    assert "nicht ermittelbar" in benchmark.ram_bewertung([])


def test_ollama_nicht_erreichbar(tmp_path):
    mock = OllamaMock(fehler_status=503)
    text = benchmark.run(["--url", "http://ollama", "--ausgabe", str(tmp_path / "b.md")], client=mock.client()).read_text(encoding="utf-8")
    assert "nicht erreichbar" in text
