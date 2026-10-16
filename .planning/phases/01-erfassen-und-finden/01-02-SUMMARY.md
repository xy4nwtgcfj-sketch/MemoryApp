---
phase: 01-erfassen-und-finden
plan: 02
subsystem: ai
requirements-completed: [CAPT-01, CAPT-03, CAPT-04, CAPT-05, CAPT-06, COMP-01, COMP-02, COMP-03, SRCH-02]
completed: 2026-10-16
---

# Plan 01-02: KI-Strukturierung, Embeddings, Compliance

Claude über client.beta.messages.create mit Structured Outputs (json_schema, Bereich als Enum der aktiven Bereiche), effort low, server-seitige Refusal-Fallbacks (fallbacks="default"). Dublettenurteil im selben Call. Zweite Runde nach Rückfrage erzwingt leere Rückfrage. Jeder API-Fehler fällt auf manuellen Entwurf zurück. Embeddings: Voyage AI oder lokaler Hashing-Vektor. Compliance: Sperrliste, Rechtsformen, Anrede+Name, Kunde/Lager/Mieter+Name, Kontaktdaten, in Beruf Beträge und Zahlen.

**Abweichung:** "Claude-kompatibles Embedding-Modell" aus dem Konzept gibt es nicht; Voyage (Anthropic-Empfehlung) plus lokaler Fallback.
**Tests:** test_structuring.py (11, gemockter Client), test_embeddings.py (5), test_compliance.py (9).
