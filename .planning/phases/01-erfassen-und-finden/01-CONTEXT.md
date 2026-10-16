# Phase 1: Erfassen und Finden - Context

**Gathered:** 2026-10-16 (discuss mode: assumptions, aus Konzept v0.1 abgeleitet)
**Status:** Ready for planning

<domain>
## Phase Boundary

Lessons erfassen (Text, Sprache, Import) und wiederfinden (Volltext, semantisch, Filter). Keine Briefings,
keine Kalender, keine Erinnerungen, keine Auswertungen.
</domain>

<decisions>
## Implementation Decisions

### Erfassungsfluss
- Zwei Schritte: "Entwurf erzeugen" (KI) → Formular prüfen → "Speichern". Kein Auto-Save ohne Blick des Nutzers, weil Compliance-Warnungen gesehen werden müssen.
- Rückfrage: KI liefert höchstens eine Frage; die Antwort wird an den Ursprungstext angehängt und erneut strukturiert. Danach keine weitere Frage (Server erzwingt das).
- Pflichtfelder fehlen ohne KI → Formular blockiert Speichern bis titel, situation, ereignis, lesson, bereich gefüllt sind.

### Dubletten
- Kandidaten: Top 5 nach Embedding-Ähnlichkeit, ohne überholte Lessons.
- Mit KI: Claude entscheidet im selben Call, ob einer davon inhaltlich dieselbe Regel ist.
- Ohne KI: Schwellwert auf Ähnlichkeit (anbieterabhängig).
- "Als Bestätigung zählen" verwirft den Entwurf und erhöht bestaetigungen der bestehenden Lesson.

### Suche
- Trigram-FTS5 (remove_diacritics), OR-Verknüpfung der Suchbegriffe ab 3 Zeichen, deutsche Stoppwörter entfernt, BM25-Ranking.
- Semantik: Kosinus über alle Embeddings in numpy (Bestand im Hunderterbereich).
- Hybrid: Reciprocal Rank Fusion (k = 60).

### Compliance
- Warnen, nicht blockieren. Die Verantwortung bleibt beim Nutzer, aber die Warnung muss vor dem Speichern sichtbar sein.

### Claude's Discretion
- UI-Details, Farben, Komponentenaufteilung.
</decisions>

<specifics>
## Specific Ideas

- Konzeptbeispiel Regel-Format: "Vor X immer Y prüfen".
- Konzeptbeispiel Abstraktion: "Bei großen EWM-Rollouts..." statt "Bei Kunde X in Lager Y...".
</specifics>

<deferred>
## Deferred Ideas

- Offline-Erfassung mit Sync-Queue
- Whisper lokal statt Browser-Spracherkennung
- Teilen / Mehrbenutzer
</deferred>

---
*Phase: 01-erfassen-und-finden*
