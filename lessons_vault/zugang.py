"""Zugangsschutz: Zugangstoken, Same-Origin-Prüfung, Sicherheits-Header."""

from __future__ import annotations

import logging
import secrets
from pathlib import Path
from urllib.parse import urlparse

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

log = logging.getLogger(__name__)

CSP = (
    # Schriften (Inter, Space Grotesk) kommen von Google Fonts; alles andere bleibt beim eigenen Ursprung.
    "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; "
    "font-src 'self' https://fonts.gstatic.com; img-src 'self' blob:; "
    "connect-src 'self'; manifest-src 'self'; worker-src 'self'; frame-ancestors 'none'; base-uri 'none'; form-action 'self'"
)


# Ohne leicht verwechselbare Zeichen (I, L, 1, O, 0), damit es sich auf dem iPhone abtippen lässt.
ZEICHEN = "ABCDEFGHJKMNPQRSTUVWXYZ23456789"


def lesbares_token(gruppen: int = 4) -> str:
    """Token wie K7QM-W4TX-9HPR-N3VD: 16 Zeichen aus 31, rund 79 Bit."""
    return "-".join("".join(secrets.choice(ZEICHEN) for _ in range(4)) for _ in range(gruppen))


def zugangstoken(ordner: Path) -> str:
    """Liest oder erzeugt das Zugangstoken in <ordner>/zugangstoken.txt."""
    datei = ordner / "zugangstoken.txt"
    if datei.exists():
        token = datei.read_text(encoding="utf-8").strip()
        if token:
            return token
    ordner.mkdir(parents=True, exist_ok=True)
    token = lesbares_token()
    datei.write_text(token + "\n", encoding="utf-8")
    log.warning("Neues Zugangstoken erzeugt: %s (einmalig in der App eintragen)", datei)
    return token


class SicherheitsMiddleware(BaseHTTPMiddleware):
    """Schreibende Anfragen nur von der eigenen Origin (gegen CSRF); Sicherheits-Header für alle Antworten."""

    async def dispatch(self, request: Request, call_next) -> Response:
        if request.method in ("POST", "PUT", "PATCH", "DELETE"):
            origin = request.headers.get("origin")
            if origin and urlparse(origin).netloc != request.headers.get("host", ""):
                return JSONResponse({"detail": "Anfrage von fremder Seite abgewiesen"}, status_code=403)
        response = await call_next(request)
        response.headers.setdefault("Content-Security-Policy", CSP)
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("X-Frame-Options", "DENY")
        response.headers.setdefault("Referrer-Policy", "no-referrer")
        if not request.url.path.startswith("/api/"):
            # App-Shell immer beim Server nachfragen, damit Updates sofort ankommen
            response.headers.setdefault("Cache-Control", "no-cache")
        return response
