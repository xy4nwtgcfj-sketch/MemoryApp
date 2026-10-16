import httpx
import numpy as np
import pytest

from lessons_vault.embeddings import EmbeddingFehler, HashingProvider, VoyageProvider, create_provider


def test_hashing_aehnlichkeit():
    p = HashingProvider()
    a, b, c = p.embed(["Unterlagen fürs Bankgespräch", "Bankgespräche vorbereiten", "Cutover Rollback am Wochenende"])
    assert a @ b > a @ c
    assert abs(np.linalg.norm(a) - 1) < 1e-5


def test_umlaute_normalisiert():
    p = HashingProvider()
    a, b = p.embed(["Übergabe", "Uebergabe"])
    assert a @ b > 0.99


def test_voyage_request():
    def handler(request):
        assert request.headers["Authorization"] == "Bearer k"
        body = request.read().decode()
        assert '"input_type":"query"' in body.replace(" ", "")
        return httpx.Response(200, json={"data": [{"index": 1, "embedding": [0, 2]}, {"index": 0, "embedding": [3, 4]}]})

    provider = VoyageProvider("k", "voyage-3.5", client=httpx.Client(transport=httpx.MockTransport(handler)))
    first, second = provider.embed(["a", "b"], "query")
    assert np.allclose(first, [0.6, 0.8]) and np.allclose(second, [0, 1])
    assert provider.name == "voyage:voyage-3.5"


def test_voyage_fehler():
    provider = VoyageProvider("k", "m", client=httpx.Client(transport=httpx.MockTransport(lambda r: httpx.Response(500))))
    with pytest.raises(EmbeddingFehler):
        provider.embed(["a"])


def test_factory():
    assert isinstance(create_provider("auto", "", "m"), HashingProvider)
    assert isinstance(create_provider("auto", "k", "m"), VoyageProvider)
    assert isinstance(create_provider("lokal", "k", "m"), HashingProvider)
