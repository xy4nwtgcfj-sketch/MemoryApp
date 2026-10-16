# Lessons Vault

## What This Is

Ein persönliches zweites Gedächtnis für Erfahrungen, nicht für Informationen. Stefan erfasst Lessons Learned
aus Beruf (SAP-EWM-Rollouts), Immobilien, Trading, eigenen Projekten und Alltag mit minimalem Aufwand
(Text oder Sprache, unter 30 Sekunden) und findet sie wieder, wenn eine ähnliche Situation bevorsteht.
Läuft als mobile PWA auf dem Home-PC, erreichbar über Tailscale.

## Core Value

Der Wert entsteht beim Wiederfinden im richtigen Moment: Eine Lesson, die vor einer ähnlichen Situation
auftaucht und eine Entscheidung oder Checkliste ändert. Wenn alles andere scheitert, müssen schnelles
Erfassen und zuverlässiges Wiederfinden funktionieren.

## Requirements

### Validated

(None yet, ship to validate. Abnahme Phase 1: drei Wochen echte Nutzung, mindestens 10 neue Lessons zusätzlich zum Startbestand.)

### Active

- [ ] Erfassen per Text und Sprache in unter 30 Sekunden, KI strukturiert ins Datenmodell
- [ ] Dublettenprüfung mit "als Bestätigung zählen"
- [ ] Volltext- und semantische Suche mit Filtern
- [ ] Startbestand von 20 bis 30 Lessons importierbar
- [ ] Eigennamen-/Kundendaten-Warnung bei der Erfassung

### Out of Scope (Phase 1)

- Briefings, Kalenderanbindung, Erinnerungen: Phase 2, erst nach Abnahme Phase 1
- Mustererkennung und Dashboard: Phase 3
- Mehrbenutzer, Teilen mit Familie oder Team: offene Frage 1, bewusst nicht modelliert (Single-User), siehe Key Decisions
- Postgres/pgvector: erst bei Bedarf, SQLite reicht für einige tausend Lessons locker
- Offline-Erfassung mit Sync-Queue: Zugriff läuft ohnehin über Tailscale zum Home-PC

## Context

- Owner: Stefan Neubert, Berater (Deloitte), SAP-EWM-Rollouts, nebenbei Buy-to-Let-Immobilien in NRW und Trading.
- Hauptrisiko laut Konzept: Die Datenbank bleibt leer. Jede Designentscheidung wird daran gemessen, ob sie Erfassung beschleunigt.
- Bestehendes Tailscale-Setup auf dem Home-PC.
- Berufliche Einträge müssen abstrahiert sein (keine Kunden-, Lager-, Personen-, Systemnamen, keine Kundenzahlen).

## Constraints

- **Tech stack**: Python (FastAPI), SQLite mit FTS5, Vanilla-JS-PWA ohne Build-Schritt. Begründung: Wartbar an einem Wochenende, keine Node-Toolchain auf dem Home-PC nötig.
- **Datenschutz**: Daten bleiben lokal. Nur Erfassungstexte (und Titel/Regel ähnlicher Lessons für die Dublettenprüfung) gehen an die Claude API, nur Lesson-Texte an den Embedding-Anbieter.
- **Compliance**: Abgleich mit internen Deloitte-Richtlinien zu persönlichen Notizen und KI-Tools steht aus und ist eine Voraussetzung vor Produktivnutzung mit beruflichen Einträgen (Blocker, nicht durch Code lösbar).
- **Sicherheit**: Kein öffentlicher Port. Zugriff nur über Tailscale, optional zusätzlich Bearer-Token.
- **Funktioniert ohne Cloud**: Ohne API-Keys muss die App benutzbar bleiben (manuelle Erfassung, lokale Suche).

## Key Decisions

| Decision | Rationale | Outcome |
|----------|-----------|---------|
| Embeddings über Voyage AI (Anthropic-Empfehlung), Fallback lokaler Hashing-Vektor | Anthropic bietet kein eigenes Embedding-Modell an; "Claude-kompatibles Embedding-Modell" aus dem Konzept existiert so nicht. Voyage ist der von Anthropic empfohlene Anbieter. Der lokale Fallback ist nur unscharf-lexikalisch, nicht semantisch. | — Pending |
| Trigram-FTS5 statt Wort-Tokenizer | Deutsche Komposita: "Bank" findet "Finanzierungsbankgespräch". Umlaute werden normalisiert. | — Pending |
| Hybrid-Suche per Reciprocal Rank Fusion | Robust ohne Score-Kalibrierung zwischen BM25 und Kosinus. | — Pending |
| Dublettenprüfung zweistufig: Embedding-Kandidaten, dann Urteil durch Claude im selben Strukturierungs-Call | Kein zusätzlicher API-Call, Erfassung bleibt schnell. | — Pending |
| Claude-Modell `claude-opus-5-5` mit effort `low`, konfigurierbar | Strukturierung ist einfach, Latenz zählt (30-Sekunden-Ziel). Modell per Umgebungsvariable tauschbar. | — Pending |
| Lokale KI über Ollama: Embeddings bge-m3, Strukturierung asynchron im Hintergrund | Bosgame E5 (Ryzen 5 5300U, 32 GB DDR4, keine GPU) ist für interaktive lokale Strukturierung zu langsam; im Hintergrund zählt Qualität vor Tempo. Erfassung bleibt unter 30 s. | — Pending (Messung) |
| Strukturierungsmodus pro Bereich; lokal-Bereiche nie an Claude, auch nicht als Kandidaten | Ermöglicht z. B. Beruf lokal (Compliance) und Immobilien über Claude (Qualität, Rückfrage) | — Pending |
| Manuelles Briefing aus Phase 2 vorgezogen (Phase 1.2), Kalender/Erinnerungen bleiben in Phase 2 | Ohne Abruf misst die Abnahme nur das Erfassen; Wert entsteht laut Konzept beim Wiederfinden. Entscheidung Stefan. | — Pending |
| Strukturierung vorerst über Claude, lokal umschaltbar | Qualität und Rückfrage im Dialog; Umstieg später ohne Umbau. Entscheidung Stefan. | — Pending |
| Rückfrage darf auch nach dem persönlichen Teil fragen (Abweichung von Konzept 4.1), weiter max. eine Frage, optional | Allgemeine Lessons liefert Claude ohnehin; der Mehrwert der App liegt im persönlichen Wissen. Entscheidung Stefan. | — Pending |
| Single-User ohne Rechtemodell | Offene Frage 1 unbeantwortet; Teilen später ist ein eigener Meilenstein. Datenmodell enthält keine Owner-Spalte. | ⚠️ Revisit |
| Sprache über Browser-Spracherkennung (Web Speech API), Whisper später | Kein zusätzlicher Dienst. Einschränkung: Chrome schickt Audio an Google, Safari/iOS nutzt Apple-Dienste. Für berufliche Inhalte kritisch, siehe Compliance. | ⚠️ Revisit |
| Alle fünf Bereiche angelegt, nur Beruf und Immobilien aktiv | Konzept fordert Fokus in Phase 1, Bereiche bleiben konfigurierbar. | — Pending |

---
*Last updated: 2026-10-16 after Phase 1.2 (Manuelles Briefing)*
