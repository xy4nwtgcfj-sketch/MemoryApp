# Project State

## Project Reference

See: .planning/PROJECT.md (updated 2026-10-16)

**Core value:** Erfahrungen im richtigen Moment wiederfinden; dafür muss Erfassen schnell und Wiederfinden zuverlässig sein.
**Current focus:** Einrichtung auf dem E5, Startbestand, dann Phase-1-Abnahme (Nutzung inkl. Briefings)

## Current Position

Phase: 1.5 of 3 (Design und Bedienung, eingeschoben)
Plan: 3 of 3 in current phase
Status: Phase complete, Einrichtung und 3-Wochen-Abnahme ausstehend
Last activity: 2026-10-18: Phase 1.5 Design und Bedienung (186 Tests); als Nächstes Freeze, Einrichtung, Test auf dem iPhone

Progress: [███░░░░░░░] 33%

## Accumulated Context

### Decisions

Siehe PROJECT.md Key Decisions. Wichtigste: Voyage statt nicht existierendem "Claude-Embedding", Trigram-FTS für Komposita, Dublettenurteil im Strukturierungs-Call.

### Pending Todos

- Startbestand über "Startbestand anlegen" (Fragen) oder JSON-Import
- iOS-Kurzbefehl "Lesson merken" einrichten, Wochenrückblick in den Kalender
- Auf echtem iPhone prüfen: VoiceOver, Tastatur-Diktat, Statusleiste, Offline-Postausgang
- Auf E5 (Windows 11) einrichten: Python, Ollama, Modelle, .env, tailscale serve, Autostart
- benchmark_lokal.py ausführen und LV_OLLAMA_MODEL festlegen
- Tesseract (UB Mannheim, Sprachpaket German) installieren
- Vergleichstest in der Abnahme: 3 bis 5 Briefings gegen dieselbe Frage im normalen Claude-Chat; Mehrwert nur, wenn das Briefing Persönliches liefert
- Später: Whisper lokal statt Browser-Spracherkennung

### Blockers/Concerns

- Deloitte-Richtlinien-Check vor beruflichen Einträgen (organisatorisch, nicht technisch)
- Offene Fragen 1 (Teilen) und 3 (Integration in Dashboard) unbeantwortet, betreffen erst spätere Meilensteine

### Quick Tasks Completed

| # | Description | Date | Directory |
|---|---|---|---|
| 002 | Briefing kombiniert eigene Erfahrung mit Claude-Wissen, Quelle je Punkt, Besonderheiten | 2026-10-18 | .planning/quick/002-briefing-kombiniert |
| 001 | Spezifitäts-Check: Rückfrage nach dem persönlichen Teil, Markierung persönlich/allgemein, Statistik | 2026-10-16 | .planning/quick/001-spezifitaets-check |

## Session Continuity

Last session: 2026-10-16
Stopped at: Phase 1.4 complete
Resume file: None
