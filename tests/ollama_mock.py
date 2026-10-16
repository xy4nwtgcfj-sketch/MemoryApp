"""Nachbau der Ollama-HTTP-API für Tests."""

import json

import httpx

from lessons_vault.embeddings import HashingProvider

from .test_structuring import payload


class OllamaMock:
    def __init__(self, antwort=None, fehler_status=None, done_reason="stop"):
        self.antwort = antwort or payload()
        self.fehler_status = fehler_status
        self.done_reason = done_reason
        self.chat_requests = []
        self.embed_requests = []
        self._hash = HashingProvider()
        self.modelle = ["bge-m3:latest", "qwen2.5:7b"]

    def handler(self, request: httpx.Request) -> httpx.Response:
        body = json.loads(request.read() or b"{}")
        if self.fehler_status:
            return httpx.Response(self.fehler_status, text="kaputt")
        if request.url.path == "/api/embed":
            self.embed_requests.append(body)
            return httpx.Response(200, json={"embeddings": [v.tolist() for v in self._hash.embed(body["input"])]})
        if request.url.path == "/api/chat":
            self.chat_requests.append(body)
            return httpx.Response(200, json={
                "message": {"role": "assistant", "content": json.dumps(self.antwort)},
                "done_reason": self.done_reason,
                "total_duration": 42_000_000_000, "load_duration": 2_000_000_000,
                "prompt_eval_count": 900, "prompt_eval_duration": 30_000_000_000,
                "eval_count": 250, "eval_duration": 10_000_000_000,
            })
        if request.url.path == "/api/tags":
            return httpx.Response(200, json={"models": [{"name": m} for m in self.modelle]})
        if request.url.path == "/api/pull":
            self.modelle.append(body["model"])
            return httpx.Response(200, json={"status": "success"})
        return httpx.Response(404)

    def client(self) -> httpx.Client:
        return httpx.Client(transport=httpx.MockTransport(self.handler))
