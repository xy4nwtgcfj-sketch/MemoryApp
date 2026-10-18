---
quick: 002
slug: briefing-kombiniert
created: 2026-10-18
---

# Quick 002: Briefing kombiniert eigene Erfahrung mit Claude-Wissen

**Anlass:** Stefan möchte z. B. für "Plan für die Hypercare-Phase eines SAP-EWM-Projekts" Claudes Fachwissen mit seinen Lessons verbinden.

**Bewusste Änderung an Phase 1.2:** Bisher stützte sich die Zusammenfassung ausschließlich auf Lessons. Neu gibt es zwei Modi:
- "kombiniert" (Standard): Claude baut einen gegliederten Plan aus Fachwissen und Lessons.
- "eigen": wie bisher, nur Lessons.

**Leitplanken:**
1. Jeder Punkt trägt seine Quelle: "erfahrung" (mit Lesson-Bezug) oder "allgemein" (Claude). Ein Punkt mit ungültigem Lesson-Bezug wird als "allgemein" geführt, nie fälschlich als eigene Erfahrung.
2. Eigener Abschnitt "Deine Besonderheiten": wo die Lessons vom Standardvorgehen abweichen oder es verschärfen. Das ist der Mehrwert gegenüber einem normalen Claude-Chat.
3. Allgemeinwissen wird als ungeprüft gekennzeichnet.
4. Im Modus kombiniert ist ein Briefing auch ohne passende Lessons möglich, mit klarem Hinweis.
5. Datenschutz unverändert: lokal-Bereiche nie an Claude.
6. Eigene Effort-Einstellung LV_BRIEFING_EFFORT (Standard medium), weil ein Plan mehr Tiefe braucht als die Strukturierung.
7. Statistik: Anteil der Planpunkte aus eigener Erfahrung (Frühindikator für den Mehrwert).

## Verify
pytest (Schema, Quellenzuordnung, Modiwechsel, ohne Treffer, Datenschutz, E2E)
