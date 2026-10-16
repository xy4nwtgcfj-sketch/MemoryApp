---
phase: 01-erfassen-und-finden
plan: 03
subsystem: api
requirements-completed: [CAPT-05, CAPT-07, SRCH-01, SRCH-02, SRCH-03, SRCH-04, OPS-01, OPS-02, OPS-04, OPS-05]
completed: 2026-10-16
---

# Plan 01-03: REST-API und Suche

FastAPI-App-Factory, alle Endpunkte unter /api, optionaler Bearer-Token (konstantzeitiger Vergleich), App-Shell bleibt ohne Token ladbar. Hybrid-Suche per Reciprocal Rank Fusion, FTS mit grober Stammbildung und Stoppwörtern. Import akzeptiert Liste oder Export-Format, überspringt bekannte IDs, Embeddings im Batch.

**Tests:** test_api.py (14), test_search.py (8).
