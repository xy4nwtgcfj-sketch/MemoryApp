# Roadmap: Lessons Vault

## Overview

Drei Phasen, jeweils mit Abnahme vor der nächsten. Phase 1 liefert Erfassen und Finden und wird drei Wochen
real genutzt, bevor Briefings gebaut werden. So wird das Hauptrisiko (leere Datenbank, liegengebliebenes
Projekt) vor weiterer Investition geprüft.

## Phases

- [x] **Phase 1: Erfassen und Finden** - Datenmodell, KI-Erfassung per Text/Sprache, Volltext- und semantische Suche, Startbestand
- [x] **Phase 1.1: Lokale KI (INSERTED)** - Ollama für Embeddings und Hintergrund-Strukturierung, Routing pro Bereich, Messskript für Windows
- [x] **Phase 1.2: Manuelles Briefing (INSERTED)** - Situation beschreiben, Top 5 Lessons, Checkliste, Claude-Zusammenfassung, Feedback
- [x] **Phase 1.3: Fotos (INSERTED)** - Fotos als Input: Lessons aus Folien (A), Entwurf gegen Erfahrung prüfen (B), lokal gespeichert
- [ ] **Phase 1.4: Härtung (INSERTED)** - Neun Audit-Befunde vor der Inbetriebnahme, keine neuen Funktionen
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
- [x] 01-01: Datenmodell, SQLite-Schema mit FTS5, Repository und Statuslogik
- [x] 01-02: KI-Strukturierung, Embeddings, Compliance-Prüfung
- [x] 01-03: REST-API (Erfassen, CRUD, Bestätigen, Suche, Import/Export, Statistik)
- [x] 01-04: PWA-Frontend (Erfassen inkl. Sprache, Suche, Detail, Einstellungen)
- [x] 01-05: Startbestand-Vorlage, Betrieb auf Home-PC mit Tailscale, Doku

**Abnahme (manuell, nach Deployment):** Drei Wochen tatsächliche Nutzung, mindestens 10 neue Lessons zusätzlich zum Startbestand.

### Phase 1.1: Lokale KI (INSERTED)
**Goal**: Lessons lassen sich vollständig auf dem Home-PC (Bosgame E5, Ryzen 5 5300U, 32 GB, Windows 11) verarbeiten, ohne dass das 30-Sekunden-Ziel leidet.
**Depends on**: Phase 1
**Requirements**: LOCAL-01, LOCAL-02, LOCAL-03, LOCAL-04, LOCAL-05, LOCAL-06, LOCAL-07
**Success Criteria** (what must be TRUE):
  1. Mit Ollama und bge-m3 ist die semantische Suche echt semantisch, ohne Cloud-Dienst
  2. Im Modus "lokal" ist die Erfassung nach dem Absenden fertig; der Entwurf erscheint später unter "Prüfen"
  3. Für einen Bereich auf "lokal" geht kein Text dieses Bereichs an Claude, auch nicht als Dubletten-Kandidat
  4. Fällt Ollama aus, geht nichts verloren: Rohtext bleibt gespeichert, Embeddings werden nachgeholt
  5. Das Messskript liefert auf dem E5 Zeiten und Beispielergebnisse pro Modell und zeigt die RAM-Bestückung
**Plans**: 3 plans

Plans:
- [x] 01.1-01: Ollama-Anbindung (Embeddings, Strukturierung), thread-sichere DB, Entwurfs-Warteschlange mit Hintergrund-Worker
- [x] 01.1-02: API und UI für Routing (Standard und pro Bereich), Prüfen-Liste, Entwürfe in der Suche
- [x] 01.1-03: Messskript, Windows-Einrichtung (Ollama, Autostart), Doku

### Phase 1.2: Manuelles Briefing (INSERTED)
**Goal**: Vor einer Aufgabe ("Projektplanung für Welle 4 schreiben") holt Stefan mit einem Satz die 5 wichtigsten eigenen Erfahrungen samt Checkliste.
**Depends on**: Phase 1.1
**Requirements**: BRIEF-01, BRIEF-02, BRIEF-06, BRIEF-07
**Begründung (Abweichung vom Konzept)**: Ohne Abruf misst die Phase-1-Abnahme nur das Erfassen. Das Konzept sagt, der Wert entsteht beim Wiederfinden. Nur der manuelle Teil wird vorgezogen; Kalender und Erinnerungen bleiben in Phase 2. Entscheidung von Stefan am 2026-10-16.
**Success Criteria** (what must be TRUE):
  1. Eine Situationsbeschreibung liefert höchstens 5 Lessons, nie überholte, sortiert nach Relevanz × Schweregrad × Bestätigungen
  2. Aus den Lessons entsteht eine kopierbare Checkliste, ohne Cloud lokal aus den Maßnahmen, mit Claude auf die Situation zugeschnitten
  3. Claude-Zusammenfassung stützt sich nur auf die gelieferten Lessons; jeder Checklistenpunkt verweist auf seine Lesson
  4. Feedback hilfreich/nicht relevant verschiebt das Ranking bei ähnlichen Situationen
  5. Lessons aus Bereichen im Modus lokal gehen nicht an Claude
**Plans**: 2 plans

Plans:
- [x] 01.2-01: Ranking, Speicherung, Feedback, Claude-Zusammenfassung, API
- [x] 01.2-02: Briefing-Ansicht, Verlauf, Erfolgskriterium in der Statistik

### Phase 1.3: Fotos (INSERTED)
**Goal**: Stefan fotografiert eine Folie oder einen Entwurf und bekommt daraus Lesson-Entwürfe (A) oder einen Abgleich mit seinen Erfahrungen (B). Das Foto bleibt lokal an der Lesson bzw. am Briefing.
**Depends on**: Phase 1.2
**Requirements**: FOTO-01, FOTO-02, FOTO-03, FOTO-04, FOTO-05, FOTO-06, FOTO-07
**Success Criteria** (what must be TRUE):
  1. Fotos werden lokal ohne Metadaten (EXIF, Standort) gespeichert und an Lesson oder Briefing angezeigt
  2. Bereich Beruf (und ohne Bereichswahl): Bild verlässt nie den PC; nur der lokal erkannte, vom Nutzer geprüfte Text geht an Claude
  3. Private Bereiche: Claude wertet das Bild direkt aus
  4. Bereiche auf "lokal": nichts geht an Claude, auch kein erkannter Text
  5. Aus einer Lessons-Learned-Folie entstehen mehrere auswählbare Kandidaten, die einzeln den normalen Erfassungsablauf durchlaufen
  6. Ein fotografierter Entwurf wird gegen passende Lessons abgeglichen: Lücken und bereits Berücksichtigtes, jeweils mit Lesson-Bezug
**Plans**: 4 plans

Plans:
- [x] 01.3-01: Bildspeicher, Metadaten-Entfernung, Vorschaubilder, Texterkennung (Tesseract)
- [x] 01.3-02: Lessons aus Fotos (Kandidaten, Routing Bild/Text, Verknüpfung mit Lesson und Entwurf)
- [x] 01.3-03: Entwurf gegen Erfahrung prüfen (Briefing mit Foto)
- [x] 01.3-04: Oberfläche, Einstellungen, Windows-Einrichtung Tesseract

### Phase 1.4: Härtung (INSERTED)
**Goal**: Die App ist sicher in Betrieb zu nehmen: Datenschutzzusagen technisch durchgesetzt, kein Datenverlust, keine hängenden oder unstartbaren Zustände.
**Depends on**: Audit 2026-10-18 (docs/AUDIT-2026-10-18.md, Befunde H1 bis H9)
**Requirements**: HART-01 bis HART-09
**Success Criteria** (what must be TRUE):
  1. Steht irgendein Bereich auf "lokal", geht ohne Bereichswahl nichts an Claude (Erfassung, Rückfrage, Fotos); globaler Standard "lokal" gilt überall
  2. Vor jedem Claude-Aufruf mit Nutzertext läuft die Namensprüfung; Sperrlistentreffer blockieren, andere Treffer brauchen eine Bestätigung
  3. Die Rückfrage fragt bei beruflichen Lessons nach Relationen und Faustregeln, nie nach absoluten Projektwerten
  4. Eine abgebrochene Migration hinterlässt den alten, startbaren Stand; vor jeder Migration entsteht eine Sicherung
  5. Claude-Aufrufe enden spätestens nach 90 s (Pläne 180 s), das Frontend bricht nach 150 s ab
  6. Ist Ollama aus, warten Entwürfe statt als Fehler zu enden
  7. Ein langsamer Ollama-Start überschreibt keine semantischen Embeddings
  8. Ohne Token startet die App nur mit erzeugtem Zugangstoken; fremde Host- und Origin-Header werden abgewiesen
  9. Tägliches Backup unter Windows inkl. Fotos, Neustart nach Absturz, nur eine Instanz
**Plans**: 3 plans

Plans:
- [ ] 01.4-01: Datenbank und Betrieb (H4, H6, H7, H9, Einzelinstanz)
- [ ] 01.4-02: Zugriff und Timeouts (H5, H8)
- [ ] 01.4-03: Datenschutz-Durchsetzung und Prompt (H1, H2, H3) inkl. Oberfläche

### Phase 2: Briefings
**Goal**: Vor einem relevanten Termin bekommt Stefan die 5 wichtigsten Lessons, ohne danach zu suchen.
**Depends on**: Phase 1 (inkl. Abnahme)
**Requirements**: BRIEF-03, BRIEF-04, BRIEF-05 (BRIEF-01/02 vorgezogen in 1.2)
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

**Execution Order:** 1 → 1.1 → 1.2 → 1.3 → 1.4 → Design-/UX-Audit → Freeze und Abnahme → 2 → 3

| Phase | Plans Complete | Status | Completed |
|-------|----------------|--------|-----------|
| 1. Erfassen und Finden | 5/5 | Built, Abnahme ausstehend | 2026-10-16 |
| 1.1 Lokale KI | 3/3 | Built, Messung auf E5 ausstehend | 2026-10-16 |
| 1.2 Manuelles Briefing | 2/2 | Built, Nutzung ausstehend | 2026-10-16 |
| 1.3 Fotos | 4/4 | Built, Test mit echten Fotos ausstehend | 2026-10-16 |
| 1.4 Härtung | 0/3 | In progress | - |
| 2. Briefings | 0/TBD | Not started | - |
| 3. Muster | 0/TBD | Not started | - |
