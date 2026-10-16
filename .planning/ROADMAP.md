# Roadmap: Lessons Vault

## Overview

Drei Phasen, jeweils mit Abnahme vor der nächsten. Phase 1 liefert Erfassen und Finden und wird drei Wochen
real genutzt, bevor Briefings gebaut werden. So wird das Hauptrisiko (leere Datenbank, liegengebliebenes
Projekt) vor weiterer Investition geprüft.

## Phases

- [ ] **Phase 1: Erfassen und Finden** - Datenmodell, KI-Erfassung per Text/Sprache, Volltext- und semantische Suche, Startbestand
- [ ] **Phase 2: Briefings** - Manuelles und kalenderbasiertes Briefing, Erinnerungen, alle Bereiche
- [ ] **Phase 3: Muster** - Monatliche Auswertung und Dashboard

## Phase Details

### Phase 1: Erfassen und Finden
**Goal**: Stefan erfasst eine Lesson in unter 30 Sekunden vom Smartphone und findet sie per Stichwort oder Frage wieder.
**Depends on**: Nothing (first phase)
**Requirements**: DATA-01, DATA-02, DATA-03, DATA-04, CAPT-01, CAPT-02, CAPT-03, CAPT-04, CAPT-05, CAPT-06, CAPT-07, COMP-01, COMP-02, COMP-03, SRCH-01, SRCH-02, SRCH-03, SRCH-04, OPS-01, OPS-02, OPS-03, OPS-04, OPS-05
**Success Criteria** (what must be TRUE):
  1. Drei Stichworte ergeben nach einem Klick einen vollständigen, editierbaren Entwurf mit Bereich, Tags und Schweregrad
  2. Eine ähnliche bestehende Lesson wird erkannt und kann mit einem Klick bestätigt werden; ab 2 Bestätigungen ist sie "bestätigt"
  3. "Bank" findet Lessons mit "Finanzierungsbankgespräch"; "Was weiß ich über Bankgespräche?" liefert passende Lessons
  4. Eigennamen wie "Kunde Müller GmbH" lösen eine sichtbare Warnung aus
  5. Ein JSON-Startbestand lässt sich importieren und wieder exportieren
  6. Die App läuft ohne API-Keys (eingeschränkt) und ist als PWA installierbar
**Plans**: 5 plans

Plans:
- [ ] 01-01: Datenmodell, SQLite-Schema mit FTS5, Repository und Statuslogik
- [ ] 01-02: KI-Strukturierung, Embeddings, Compliance-Prüfung
- [ ] 01-03: REST-API (Erfassen, CRUD, Bestätigen, Suche, Import/Export, Statistik)
- [ ] 01-04: PWA-Frontend (Erfassen inkl. Sprache, Suche, Detail, Einstellungen)
- [ ] 01-05: Startbestand-Vorlage, Betrieb auf Home-PC mit Tailscale, Doku

**Abnahme (manuell, nach Deployment):** Drei Wochen tatsächliche Nutzung, mindestens 10 neue Lessons zusätzlich zum Startbestand.

### Phase 2: Briefings
**Goal**: Vor einem relevanten Termin bekommt Stefan die 5 wichtigsten Lessons, ohne danach zu suchen.
**Depends on**: Phase 1 (inkl. Abnahme)
**Requirements**: BRIEF-01, BRIEF-02, BRIEF-03, BRIEF-04, BRIEF-05
**Success Criteria** (what must be TRUE):
  1. "Besichtigung Wuppertal morgen" liefert 5 Lessons, überholte nie
  2. Feedback verschiebt das Ranking messbar
  3. Ein Kalendertermin mit Schlagwort erzeugt am Vorabend automatisch ein Briefing
  4. Freitag 17:00 kommt eine Erfassungs-Erinnerung
**Plans**: TBD

### Phase 3: Muster
**Goal**: Wiederkehrende Fehler und wirkungslose Lessons werden sichtbar.
**Depends on**: Phase 2
**Requirements**: PATT-01, PATT-02, PATT-03, PATT-04
**Success Criteria** (what must be TRUE):
  1. Monatsbericht nennt wiederholte Fehlerarten pro Bereich
  2. Lessons ohne Massnahme und Bereiche ohne Einträge (30 Tage) werden angezeigt
**Plans**: TBD

## Progress

**Execution Order:** 1 → 2 → 3

| Phase | Plans Complete | Status | Completed |
|-------|----------------|--------|-----------|
| 1. Erfassen und Finden | 0/5 | Not started | - |
| 2. Briefings | 0/TBD | Not started | - |
| 3. Muster | 0/TBD | Not started | - |
