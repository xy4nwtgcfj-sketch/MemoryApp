# Requirements: Lessons Vault

**Defined:** 2026-10-16
**Core Value:** Erfahrungen im richtigen Moment wiederfinden; dafür muss Erfassen schnell und Wiederfinden zuverlässig sein.

## v1 Requirements (Phase 1: Erfassen und Finden)

### Datenmodell (DATA)

- [x] **DATA-01**: Lesson mit allen Feldern aus Konzept Abschnitt 3 (id, titel ≤ 80, situation, ereignis, lesson, massnahme, bereich, tags, schweregrad 1–5, status, bestaetigungen, erstellt_am, geaendert_am, quelle, embedding) wird in SQLite gespeichert
- [x] **DATA-02**: Statuslogik: neu bei Anlage, automatisch bestätigt ab 2 Bestätigungen, überholt nur manuell
- [x] **DATA-03**: Bereiche sind konfigurierbar (anlegen, aktivieren, deaktivieren); Start: Beruf und Immobilien aktiv
- [x] **DATA-04**: Jede Bestätigung wird mit Datum protokolliert (Grundlage für Mustererkennung in Phase 3)

### Erfassung (CAPT)

- [x] **CAPT-01**: Nutzer kann Stichworte als Text eingeben und erhält einen strukturierten Entwurf
- [x] **CAPT-02**: Nutzer kann per Sprache diktieren (Browser-Spracherkennung, Deutsch); quelle = sprache
- [x] **CAPT-03**: KI schlägt Bereich, Tags und Schweregrad vor; Nutzer kann alles vor dem Speichern ändern
- [x] **CAPT-04**: Bei fehlenden Pflichtfeldern stellt die KI höchstens eine Rückfrage
- [x] **CAPT-05**: Vor dem Speichern Dublettenprüfung; bei Treffer Angebot "als Bestätigung zählen"
- [x] **CAPT-06**: Erfassung funktioniert ohne KI-Zugang (manuelles Formular)
- [x] **CAPT-07**: Erfassungsdauer wird gemessen und gespeichert (Erfolgskriterium unter 30 Sekunden)

### Compliance (COMP)

- [x] **COMP-01**: Warnung bei erkannten Eigennamen, Firmen, Personen, Kontaktdaten und Beträgen in beruflichen Einträgen
- [x] **COMP-02**: Persönliche Sperrliste (z. B. Kundennamen), deren Begriffe immer eine Warnung auslösen
- [x] **COMP-03**: KI wird angewiesen, berufliche Einträge abstrahiert zu formulieren und Hinweise zu liefern

### Suche (SRCH)

- [x] **SRCH-01**: Volltextsuche über alle Textfelder und Tags, tolerant für Komposita und Umlaute
- [x] **SRCH-02**: Semantische Suche über Embeddings ("Was weiß ich über Bankgespräche?")
- [x] **SRCH-03**: Filter: Bereich, Status, Schweregrad, Zeitraum
- [x] **SRCH-04**: Hybridmodus kombiniert Volltext und Semantik

### Bestand und Betrieb (OPS)

- [x] **OPS-01**: Import des Startbestands aus JSON (quelle = import), Export als JSON-Backup
- [x] **OPS-02**: Lessons ansehen, bearbeiten, bestätigen, als überholt markieren, löschen
- [x] **OPS-03**: Installierbar als PWA auf dem Smartphone, betrieben auf dem Home-PC über Tailscale
- [x] **OPS-04**: Statistik für die Erfolgskriterien (Anzahl gesamt, pro Woche, Ø Erfassungsdauer)
- [x] **OPS-05**: Embeddings können nach Anbieterwechsel neu berechnet werden

### Lokale KI (LOCAL), Phase 1.1

- [x] **LOCAL-01**: Embeddings über Ollama (Standard bge-m3), Anbieter wählbar; Lessons ohne passendes Embedding werden automatisch nachindexiert
- [x] **LOCAL-02**: Strukturierung über ein lokales Ollama-Modell mit JSON-Schema, gleicher Prompt wie Claude
- [x] **LOCAL-03**: Lokale Strukturierung läuft im Hintergrund; Erfassung endet mit dem Speichern des Rohtexts
- [x] **LOCAL-04**: Strukturierungsmodus global (automatisch, Claude, lokal, manuell) und pro Bereich überschreibbar; Bereich bei der Erfassung optional vorwählbar
- [x] **LOCAL-05**: Bereiche im Modus lokal werden nie an Claude gesendet, auch nicht als Dubletten-Kandidaten
- [x] **LOCAL-06**: Liste "Prüfen" mit Zähler; Entwürfe übernehmen, als Bestätigung zählen, Rückfrage beantworten, neu strukturieren, verwerfen; Rohtexte sind durchsuchbar
- [x] **LOCAL-07**: Messskript für Windows (RAM-Bestückung, Embedding-, Strukturierungszeiten, Beispielergebnisse je Modell, optional Claude-Vergleich)

### Manuelles Briefing (BRIEF), Phase 1.2 (vorgezogen)

- [x] **BRIEF-01**: Manuelles Briefing aus Freitext, Top 5 nach Relevanz × Schweregrad × Bestätigungen, überholte ausgeschlossen
- [x] **BRIEF-02**: Feedback hilfreich / nicht relevant pro Lesson, fließt bei ähnlichen Situationen ins Ranking ein
- [x] **BRIEF-06**: Checkliste aus den Lessons, kopierbar; mit Claude auf die Situation zugeschnitten und mit Quellenverweis
- [x] **BRIEF-07**: Claude-Zusammenfassung "Worauf du achten solltest"; Briefings werden gespeichert und sind wieder aufrufbar

### Fotos (FOTO), Phase 1.3

- [x] **FOTO-01**: Fotos (Kamera oder Galerie, bis 5 auf einmal) werden auf dem Handy verkleinert, auf dem PC ohne Metadaten gespeichert und an Lesson, Entwurf oder Briefing gehängt; Fotos lassen sich auch nachträglich an eine Lesson hängen und entfernen
- [x] **FOTO-02**: Lokale Texterkennung (Tesseract, Deutsch und Englisch) mit editierbarer Vorschau und Namensprüfung vor dem Senden
- [x] **FOTO-03**: Auswertungsweg pro Bereich: Texterkennung (Standard Beruf und ohne Bereich) oder Claude-Bild (Standard private Bereiche); Bereiche auf "lokal" nie an Claude
- [x] **FOTO-04**: Lessons aus Fotos: bis zu 8 Kandidaten, Auswahl, jeder Kandidat durchläuft die normale Erfassung, Foto hängt an jeder entstandenen Lesson
- [x] **FOTO-05**: Entwurf prüfen: Foto eines Entwurfs im Briefing, Abgleich mit passenden Lessons (fehlt / schon berücksichtigt), mit Lesson-Bezug
- [x] **FOTO-06**: Verwaiste Fotos (nie verknüpft) werden nach 2 Tagen gelöscht; mit einer Lesson gelöschte Fotos werden mit entfernt
- [x] **FOTO-07**: Export enthält Fotos optional nicht (JSON bleibt schlank); Hinweis im Backup-Abschnitt

## v2 Requirements

### Briefing (BRIEF), Phase 2

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
| DATA-01..04 | Phase 1 | Built (UAT ausstehend) |
| CAPT-01..07 | Phase 1 | Built (UAT ausstehend) |
| COMP-01..03 | Phase 1 | Built (UAT ausstehend) |
| SRCH-01..04 | Phase 1 | Built (UAT ausstehend) |
| OPS-01..05 | Phase 1 | Built (UAT ausstehend) |
| LOCAL-01..07 | Phase 1.1 | Built (UAT ausstehend) |
| BRIEF-01, 02, 06, 07 | Phase 1.2 | Built (UAT ausstehend) |
| FOTO-01..07 | Phase 1.3 | Built (UAT ausstehend) |
| BRIEF-03..05 | Phase 2 | Deferred |
| PATT-01..04 | Phase 3 | Deferred |

**Coverage:**
- v1 requirements: 41 total
- Mapped to phases: 41
- Unmapped: 0

---
*Requirements defined: 2026-10-16*
*Last updated: 2026-10-16 after initialization*
