---
phase: 01-erfassen-und-finden
plan: 01
subsystem: data
requirements-completed: [DATA-01, DATA-02, DATA-03, DATA-04]
completed: 2026-10-16
---

# Plan 01-01: Datenmodell und Persistenz

SQLite-Schema mit Migrationen über PRAGMA user_version, Tabellen bereiche, lessons, bestaetigungen (Protokoll für Phase 3), einstellungen. Trigram-FTS5 mit remove_diacritics, per Trigger synchron. Repository mit Statuslogik (neu → bestätigt ab 2, überholt nur manuell, Bestätigung ändert überholt nicht).

**Abweichung:** Zusätzliche Spalte erfassung_sekunden (für Erfolgskriterium) und embedding_modell (Reindex nach Anbieterwechsel).
**Tests:** tests/test_repository.py (12).
