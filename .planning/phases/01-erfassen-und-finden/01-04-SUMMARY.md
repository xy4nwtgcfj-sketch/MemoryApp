---
phase: 01-erfassen-und-finden
plan: 04
subsystem: ui
requirements-completed: [CAPT-01, CAPT-02, CAPT-03, CAPT-04, CAPT-05, CAPT-06, CAPT-07, SRCH-03, OPS-02, OPS-03]
completed: 2026-10-16
---

# Plan 01-04: PWA-Frontend

Vanilla-JS-PWA ohne Build: Erfassen (Text, Web-Speech-Diktat de-DE, Rückfrage, Dublettenkarte, Live-Compliance-Prüfung, Pflichtfeldsperre, Zeitmessung), Suche mit Modus und Filtern, Detail mit Erneut-erlebt, Bearbeiten, Überholt, Löschen, Einstellungen mit Erfolgskriterien, Bereichen, Sperrliste, Import/Export, Reindex, Token. Service Worker cached nur die Shell. Hell/Dunkel über Tokens.

**Bug während Ausführung gefunden und behoben:** DOM-Helfer flachte verschachtelte Listen nur eine Ebene ab; null wurde als Text gerendert.
**Tests:** test_e2e.py (Playwright, 390 px Breite, gemockter Claude-Client, prüft auch keine horizontale Scrollbar und keine JS-Fehler).
