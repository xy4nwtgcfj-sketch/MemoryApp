"""Minimaler MCP-Server (Model Context Protocol, Transport "Streamable HTTP" ohne Sitzungen und ohne Streaming).

Claude Code und andere MCP-Clients können so den Vault direkt durchsuchen, Einträge und Themenseiten lesen und
Notizen in den Eingang legen. Zugriff nur mit dem App-Token (Authorization: Bearer ...). Einträge aus lokal
verarbeiteten Bereichen liefert der Server nie aus, denn ein MCP-Client gibt sie an sein Sprachmodell weiter.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from typing import Any, Callable

log = logging.getLogger(__name__)

PROTOKOLLE = ("2025-06-18", "2025-03-26", "2024-11-05")


@dataclass
class Werkzeug:
    name: str
    beschreibung: str
    schema: dict[str, Any]
    ausfuehren: Callable[[dict[str, Any]], Any]
    nur_lesen: bool = True


class WerkzeugFehler(Exception):
    """Fachlicher Fehler, den der Client als Werkzeugergebnis (isError) sieht, nicht als Protokollfehler."""


class McpServer:
    def __init__(self, name: str, version: str, werkzeuge: list[Werkzeug], anleitung: str = ""):
        self.name = name
        self.version = version
        self.werkzeuge = {w.name: w for w in werkzeuge}
        self.anleitung = anleitung

    def _liste(self) -> list[dict[str, Any]]:
        return [
            {
                "name": w.name,
                "description": w.beschreibung,
                "inputSchema": w.schema,
                "annotations": {"readOnlyHint": w.nur_lesen, "destructiveHint": False, "openWorldHint": False},
            }
            for w in self.werkzeuge.values()
        ]

    def _aufruf(self, params: dict[str, Any]) -> dict[str, Any]:
        werkzeug = self.werkzeuge.get(str(params.get("name", "")))
        if werkzeug is None:
            raise KeyError(f"Unbekanntes Werkzeug: {params.get('name')}")
        try:
            ergebnis = werkzeug.ausfuehren(params.get("arguments") or {})
        except WerkzeugFehler as exc:
            return {"content": [{"type": "text", "text": str(exc)}], "isError": True}
        text = ergebnis if isinstance(ergebnis, str) else json.dumps(ergebnis, ensure_ascii=False, indent=1, default=str)
        return {"content": [{"type": "text", "text": text}], "isError": False}

    def behandeln(self, nachricht: Any) -> dict[str, Any] | None:
        """Eine JSON-RPC-Nachricht. None bei Benachrichtigungen (keine Antwort)."""
        if not isinstance(nachricht, dict) or nachricht.get("jsonrpc") != "2.0" or "method" not in nachricht:
            return {"jsonrpc": "2.0", "id": None, "error": {"code": -32600, "message": "Ungültige Anfrage"}}
        methode, params, kennung = nachricht["method"], nachricht.get("params") or {}, nachricht.get("id")
        if kennung is None:
            return None  # Benachrichtigung, z. B. notifications/initialized
        try:
            if methode == "initialize":
                gewuenscht = params.get("protocolVersion")
                ergebnis: Any = {
                    "protocolVersion": gewuenscht if gewuenscht in PROTOKOLLE else PROTOKOLLE[0],
                    "capabilities": {"tools": {"listChanged": False}},
                    "serverInfo": {"name": self.name, "version": self.version},
                    "instructions": self.anleitung,
                }
            elif methode == "ping":
                ergebnis = {}
            elif methode == "tools/list":
                ergebnis = {"tools": self._liste()}
            elif methode == "tools/call":
                ergebnis = self._aufruf(params)
            else:
                return {"jsonrpc": "2.0", "id": kennung, "error": {"code": -32601, "message": f"Methode unbekannt: {methode}"}}
        except KeyError as exc:
            return {"jsonrpc": "2.0", "id": kennung, "error": {"code": -32602, "message": str(exc).strip("'\"")}}
        except Exception as exc:  # noqa: BLE001 - Protokoll bleibt stabil, Details ins Log
            log.exception("MCP-Aufruf %s fehlgeschlagen", methode)
            return {"jsonrpc": "2.0", "id": kennung, "error": {"code": -32603, "message": str(exc) or exc.__class__.__name__}}
        return {"jsonrpc": "2.0", "id": kennung, "result": ergebnis}
