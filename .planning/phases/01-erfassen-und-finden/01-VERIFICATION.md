---
phase: 01-erfassen-und-finden
verified: 2026-10-16
status: human_needed
score: 6/6 automatisch prüfbare Kriterien erfüllt
---

# Phase 1 Verification

## Success Criteria

| # | Kriterium | Status | Nachweis |
|---|---|---|---|
| 1 | Drei Stichworte → vollständiger, editierbarer Entwurf | ✓ (gemockt) | test_e2e, test_structuring; **echter Claude-Call nicht getestet, kein API-Key in der Build-Umgebung** |
| 2 | Dublette erkannt, Bestätigung mit einem Klick, ab 2× bestätigt | ✓ | test_api::test_entwurf_ohne_ki_mit_dublette, test_repository, test_e2e |
| 3 | "Bank" findet "Finanzierungsbankgespräch"; Frage liefert Treffer | ✓ | test_search::test_kompositum, test_frage_hybrid |
| 4 | "Kunde Müller GmbH" löst Warnung aus | ✓ | test_compliance, test_api |
| 5 | JSON-Startbestand importierbar und exportierbar | ✓ | test_api::test_import_export_roundtrip |
| 6 | Läuft ohne API-Keys, als PWA installierbar | ✓ / manuell | Server-Smoke ohne Keys; Installation auf dem Handy braucht HTTPS via tailscale serve |

Testlauf: 60 passed.

## Human Verification Needed

1. Echter Claude-Call mit eigenem ANTHROPIC_API_KEY: Qualität der Strukturierung und Latenz (Ziel: Gesamterfassung < 30 s).
2. Voyage-Key: semantische Suche "Was weiß ich über Bankgespräche?" mit echtem Bestand.
3. Diktat auf dem eigenen Smartphone (iOS Safari / Android Chrome) über tailscale serve.
4. Abgleich mit Deloitte-Richtlinien vor beruflichen Einträgen.
5. **Abnahme Phase 1:** drei Wochen Nutzung, mindestens 10 neue Lessons zusätzlich zum Startbestand.

## Known Limitations

- Lokaler Embedding-Fallback ist nicht semantisch.
- Eigennamen-Erkennung ist musterbasiert; ein Name ohne Kontextwort ("Brenntag hat ...") wird nur über die Sperrliste erkannt.
- Keine Offline-Erfassung.
