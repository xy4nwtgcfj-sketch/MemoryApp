import numpy as np
import pytest

from lessons_vault.embeddings import EmbeddingFehler, OllamaEmbeddings, create_provider, modell_installiert
from lessons_vault.models import Bereich, DublettenKandidat
from lessons_vault.structuring import OllamaStrukturierer

from .ollama_mock import OllamaMock
from .test_structuring import payload

BEREICHE = [Bereich(name="Beruf"), Bereich(name="Immobilien")]


def kandidat(i):
    return DublettenKandidat(id=f"k{i}", titel="t", lesson="l", bereich="Beruf", status="neu", bestaetigungen=1, aehnlichkeit=0.6)


def test_embeddings():
    mock = OllamaMock()
    provider = OllamaEmbeddings("http://ollama", "bge-m3", client=mock.client())
    a, b = provider.embed(["Bankgespräch", "Bankgespräche"], "query")
    assert provider.name == "ollama:bge-m3"
    assert mock.embed_requests[0]["model"] == "bge-m3"
    assert abs(np.linalg.norm(a) - 1) < 1e-5 and a @ b > 0.5


def test_embeddings_fehler():
    provider = OllamaEmbeddings("http://ollama", "bge-m3", client=OllamaMock(fehler_status=500).client())
    with pytest.raises(EmbeddingFehler):
        provider.embed(["x"])


def test_modell_installiert():
    assert modell_installiert("bge-m3", ["bge-m3:latest"])
    assert modell_installiert("qwen2.5:7b", ["qwen2.5:7b"])
    assert not modell_installiert("qwen2.5:7b", ["qwen2.5:14b"])


def test_factory_ollama_explizit():
    assert isinstance(create_provider("ollama", "", "", "http://x", "bge-m3"), OllamaEmbeddings)


def test_strukturierer_request_und_metriken():
    mock = OllamaMock()
    s = OllamaStrukturierer("http://ollama", "qwen2.5:7b", client=mock.client())
    entwurf = s.strukturieren("Bank Unterlagen", "text", BEREICHE, [kandidat(i) for i in range(5)])
    req = mock.chat_requests[0]
    assert req["model"] == "qwen2.5:7b" and req["stream"] is False
    assert req["format"]["properties"]["bereich"]["enum"] == ["Beruf", "Immobilien"]
    assert req["messages"][0]["role"] == "system"
    assert req["messages"][1]["content"].count('"id"') == 3  # max. 3 Kandidaten lokal
    assert entwurf.ki_verwendet and entwurf.ki_modell == "ollama:qwen2.5:7b"
    assert s.letzte_metriken["antwort_tokens"] == 250 and s.letzte_metriken["gesamt_s"] == 42


def test_strukturierer_fehler_ergibt_manuellen_entwurf():
    s = OllamaStrukturierer("http://ollama", "m", client=OllamaMock(fehler_status=500).client())
    entwurf = s.strukturieren("Bank", "text", BEREICHE, [])
    assert not entwurf.ki_verwendet and "Ollama-Fehler 500" in entwurf.ki_fehler


def test_strukturierer_abgeschnitten():
    s = OllamaStrukturierer("http://ollama", "m", client=OllamaMock(done_reason="length").client())
    assert "abgeschnitten" in s.strukturieren("Bank", "text", BEREICHE, []).ki_fehler


def test_strukturierer_kaputtes_json():
    mock = OllamaMock()
    mock.antwort = "kein json"
    s = OllamaStrukturierer("http://ollama", "m", client=mock.client())
    # json.dumps("kein json") ist gültiges JSON (String), aber kein Objekt
    assert not s.strukturieren("Bank", "text", BEREICHE, []).ki_verwendet


def test_payload_unveraendert():
    assert payload()["bereich"] == "Immobilien"
