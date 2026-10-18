from fastapi.testclient import TestClient

from lessons_vault import main
from lessons_vault.config import Settings
from lessons_vault.embeddings import HashingProvider
from lessons_vault.main import create_app
from lessons_vault.structuring import Strukturierer


def app_fuer(tmp_path, monkeypatch, **kw):
    monkeypatch.setattr(main, "ollama_status", lambda url, timeout=2.0: {"erreichbar": False, "modelle": []})
    settings = Settings(db_path=tmp_path / "t.db", anthropic_api_key="", ollama_model="", **kw)
    return create_app(settings, Strukturierer(None, "m"), HashingProvider())


def test_token_wird_erzeugt_und_verlangt(tmp_path, monkeypatch):
    client = TestClient(app_fuer(tmp_path, monkeypatch, token="", token_erzwingen=True))
    datei = tmp_path / "zugangstoken.txt"
    token = datei.read_text().strip()
    assert len(token) >= 24
    assert client.get("/api/status").status_code == 401
    assert client.get("/api/status", headers={"Authorization": f"Bearer {token}"}).status_code == 200
    # Beim nächsten Start dasselbe Token
    app_fuer(tmp_path, monkeypatch, token="", token_erzwingen=True)
    assert datei.read_text().strip() == token
    assert client.get("/").status_code == 200  # App-Shell lädt, damit die Anmeldung erscheinen kann


def test_fremder_host_abgewiesen(tmp_path, monkeypatch):
    client = TestClient(app_fuer(tmp_path, monkeypatch, erlaubte_hosts=["127.0.0.1", "*.ts.net"]))
    assert client.get("/api/status", headers={"Host": "rebind.angreifer.example"}).status_code == 400
    assert client.get("/api/status", headers={"Host": "pc.tail1234.ts.net"}).status_code == 200


def test_fremde_origin_bei_schreibzugriff(tmp_path, monkeypatch):
    client = TestClient(app_fuer(tmp_path, monkeypatch))
    r = client.post("/api/reindex", headers={"Origin": "https://evil.example"})
    assert r.status_code == 403
    assert client.post("/api/reindex", headers={"Origin": "http://testserver"}).status_code == 200
    assert client.post("/api/reindex").status_code == 200  # ohne Origin (z. B. curl) erlaubt


def test_sicherheitsheader_und_keine_doku(tmp_path, monkeypatch):
    client = TestClient(app_fuer(tmp_path, monkeypatch))
    r = client.get("/")
    assert "frame-ancestors 'none'" in r.headers["content-security-policy"]
    assert r.headers["x-content-type-options"] == "nosniff" and r.headers["cache-control"] == "no-cache"
    for pfad in ("/docs", "/openapi.json", "/redoc"):
        assert client.get(pfad).status_code == 404


def test_claude_timeout_konfiguriert():
    from lessons_vault.structuring import create_strukturierer
    s = create_strukturierer("sk-test", "claude-opus-5-5", "low")
    assert s.client.max_retries == 1
    assert s.client.timeout.read == 90.0 and s.client.timeout.connect == 5.0
    assert s.client.with_options(timeout=180.0).timeout == 180.0
