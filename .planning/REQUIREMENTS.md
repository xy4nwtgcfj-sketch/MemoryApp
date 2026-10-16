# Requirements: Lessons Vault

**Defined:** 2026-10-16
**Core Value:** Erfahrungen im richtigen Moment wiederfinden; dafür muss Erfassen schnell und Wiederfinden zuverlässig sein.

## v1 Requirements (Phase 1: Erfassen und Finden)

### Datenmodell (DATA)

- [ ] **DATA-01**: Lesson mit allen Feldern aus Konzept Abschnitt 3 (id, titel ≤ 80, situation, ereignis, lesson, massnahme, bereich, tags, schweregrad 1–5, status, bestaetigungen, erstellt_am, geaendert_am, quelle, embedding) wird in SQLite gespeichert
- [ ] **DATA-02**: Statuslogik: neu bei Anlage, automatisch bestätigt ab 2 Bestätigungen, überholt nur manuell
- [ ] **DATA-03**: Bereiche sind konfigurierbar (anlegen, aktivieren, deaktivieren); Start: Beruf und Immobilien aktiv
- [ ] **DATA-04**: Jede Bestätigung wird mit Datum protokolliert (Grundlage für Mustererkennung in Phase 3)

### Erfassung (CAPT)

- [ ] **CAPT-01**: Nutzer kann Stichworte als Text eingeben und erhält einen strukturierten Entwurf
- [ ] **CAPT-02**: Nutzer kann per Sprache diktieren (Browser-Spracherkennung, Deutsch); quelle = sprache
- [ ] **CAPT-03**: KI schlägt Bereich, Tags und Schweregrad vor; Nutzer kann alles vor dem Speichern ändern
- [ ] **CAPT-04**: Bei fehlenden Pflichtfeldern stellt die KI höchstens eine Rückfrage
- [ ] **CAPT-05**: Vor dem Speichern Dublettenprüfung; bei Treffer Angebot "als Bestätigung zählen"
- [ ] **CAPT-06**: Erfassung funktioniert ohne KI-Zugang (manuelles Formular)
- [ ] **CAPT-07**: Erfassungsdauer wird gemessen und gespeichert (Erfolgskriterium unter 30 Sekunden)

### Compliance (COMP)

- [ ] **COMP-01**: Warnung bei erkannten Eigennamen, Firmen, Personen, Kontaktdaten und Beträgen in beruflichen Einträgen
- [ ] **COMP-02**: Persönliche Sperrliste (z. B. Kundennamen), deren Begriffe immer eine Warnung auslösen
- [ ] **COMP-03**: KI wird angewiesen, berufliche Einträge abstrahiert zu formulieren und Hinweise zu liefern

### Suche (SRCH)

- [ ] **SRCH-01**: Volltextsuche über alle Textfelder und Tags, tolerant für Komposita und Umlaute
- [ ] **SRCH-02**: Semantische Suche über Embeddings ("Was weiß ich über Bankgespräche?")
- [ ] **SRCH-03**: Filter: Bereich, Status, Schweregrad, Zeitraum
- [ ] **SRCH-04**: Hybridmodus kombiniert Volltext und Semantik

### Bestand und Betrieb (OPS)

- [ ] **OPS-01**: Import des Startbestands aus JSON (quelle = import), Export als JSON-Backup
- [ ] **OPS-02**: Lessons ansehen, bearbeiten, bestätigen, als überholt markieren, löschen
- [ ] **OPS-03**: Installierbar als PWA auf dem Smartphone, betrieben auf dem Home-PC über Tailscale
- [ ] **OPS-04**: Statistik für die Erfolgskriterien (Anzahl gesamt, pro Woche, Ø Erfassungsdauer)
- [ ] **OPS-05**: Embeddings können nach Anbieterwechsel neu berechnet werden

## v2 Requirements

### Briefing (BRIEF), Phase 2

- **BRIEF-01**: Manuelles Briefing aus Freitext ("Besichtigung Wuppertal morgen"), Top 5 nach Relevanz × Schweregrad × Bestätigungen, überholte ausgeschlossen
- **BRIEF-02**: Feedback hilfreich / nicht relevant pro Lesson, fließt ins Ranking ein
- **BRIEF-03**: Google-Calendar-Anbindung, automatisches Vorabend-Briefing
- **BRIEF-04**: Wöchentliche Erfassungs-Erinnerung (Freitag 17:00) und 5-Minuten-Erinnerung nach Terminen mit Schlagwort
- **BRIEF-05**: Alle Bereiche aktiv

### Muster (PATT), Phase 3

- **PATT-01**: Monatliche Auswertung wiederkehrender Fehlerarten pro Bereich
- **PATT-02**: Hinweis auf Lessons ohne Massnahme
- **PATT-03**: Hinweis auf Bereiche ohne Einträge in 30 Tagen
- **PATT-04**: Dashboard: Lessons pro Bereich, Wiederholungen, offene Massnahmen

## Out of Scope

| Feature | Reason |
|---------|--------|
| Mehrbenutzer / Teilen | Offene Frage 1, bewusst vertagt |
| Postgres + pgvector | SQLite reicht für das erwartete Volumen (Hunderte Lessons) |
| Whisper-Server | Browser-Spracherkennung zuerst; Whisper, falls Datenschutz es erfordert |
| Native App | PWA reicht |

## Traceability

| Requirement | Phase | Status |
|-------------|-------|--------|
| DATA-01..04 | Phase 1 | Pending |
| CAPT-01..07 | Phase 1 | Pending |
| COMP-01..03 | Phase 1 | Pending |
| SRCH-01..04 | Phase 1 | Pending |
| OPS-01..05 | Phase 1 | Pending |
| BRIEF-01..05 | Phase 2 | Deferred |
| PATT-01..04 | Phase 3 | Deferred |

**Coverage:**
- v1 requirements: 23 total
- Mapped to phases: 23
- Unmapped: 0

---
*Requirements defined: 2026-10-16*
*Last updated: 2026-10-16 after initialization*
