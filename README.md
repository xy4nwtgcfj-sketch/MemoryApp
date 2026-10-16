# Lessons Vault

Ein zweites Gedächtnis für Erfahrungen. Lessons in unter 30 Sekunden erfassen (Text oder Sprache),
Claude strukturiert sie, und du findest sie wieder, wenn eine ähnliche Situation bevorsteht.

Stand: Phase 1 "Erfassen und Finden" (siehe `.planning/ROADMAP.md`). Briefings und Mustererkennung folgen
erst nach der Abnahme von Phase 1 (drei Wochen echte Nutzung, mindestens 10 neue Lessons).

## Funktionen

- **Erfassen:** Stichworte tippen oder diktieren → Claude füllt Titel, Situation, Ereignis, Regel, Maßnahme,
  Bereich, Tags und Schweregrad. Höchstens eine Rückfrage. Du prüfst und speicherst.
- **Dubletten:** Ähnliche bestehende Lessons werden erkannt; "Als Bestätigung zählen" erhöht den Zähler,
  ab 2× wird eine Lesson automatisch "bestätigt".
- **Suche:** Volltext (findet Wortteile: "Bank" findet "Finanzierungsbankgespräch", umlauttolerant),
  semantisch und hybrid. Filter nach Bereich, Status, Schweregrad, Zeitraum.
- **Datenschutz-Warnung:** Firmen, Personen, "Kunde X", Kontaktdaten und in "Beruf" auch Beträge und Zahlen
  lösen eine Warnung aus. Eigene Sperrliste (z. B. Kundennamen) unter Einstellungen.
- **Bestand:** JSON-Import (Startbestand) und Export (Backup). Erfolgskriterien unter Einstellungen.
- **Ohne Cloud nutzbar:** Ohne API-Keys funktioniert alles außer der KI-Strukturierung und der echten Semantik.

## Installation auf dem Home-PC

Voraussetzung: Python 3.11 oder neuer, Tailscale auf PC und Smartphone.

```bash
git clone <repo> lessons-vault && cd lessons-vault
cp .env.example .env          # Keys eintragen (siehe unten)
./scripts/start.sh            # Windows: powershell -File scripts\start.ps1
```

Die App läuft dann auf `http://127.0.0.1:8765`, nur lokal erreichbar.

### Zugriff vom Smartphone über Tailscale (HTTPS)

Mikrofon und PWA-Installation brauchen HTTPS. Tailscale liefert das ohne offenen Port:

```bash
tailscale serve --bg 8765
```

Danach ist die App unter `https://<pc-name>.<tailnet>.ts.net` erreichbar, nur für Geräte in deinem Tailnet.
(HTTPS-Zertifikate müssen im Tailscale-Adminbereich unter "DNS" aktiviert sein.)
Auf dem iPhone in Safari öffnen → Teilen → "Zum Home-Bildschirm". Auf Android in Chrome → "App installieren".

Optional zusätzlich `LV_TOKEN` in `.env` setzen und den Token in der App unter Einstellungen eintragen.

### Autostart

- **Linux:** systemd-User-Service mit `ExecStart=/pfad/lessons-vault/scripts/start.sh`.
- **Windows:** Aufgabenplanung → "Beim Anmelden" → `powershell -File C:\pfad\lessons-vault\scripts\start.ps1`.

### Backup

`scripts/backup.sh` erzeugt eine konsistente Kopie unter `backups/` und behält die letzten 30.
Zusätzlich regelmäßig "Exportieren" in der App nutzen (JSON, lesbar und versionsunabhängig).

## Konfiguration (`.env`)

| Variable | Bedeutung | Standard |
|---|---|---|
| `ANTHROPIC_API_KEY` | Claude für die Strukturierung | leer = manuelle Erfassung |
| `LV_CLAUDE_MODEL` | Claude-Modell | `claude-opus-5-5` |
| `LV_CLAUDE_EFFORT` | Denkaufwand (`low` bis `max`) | `low` (schnell) |
| `VOYAGE_API_KEY` | Voyage AI für semantische Suche | leer = lokaler Fallback |
| `LV_VOYAGE_MODEL` | Voyage-Modell | `voyage-3.5` |
| `LV_EMBEDDINGS` | `auto`, `voyage` oder `lokal` | `auto` |
| `LV_DB_PATH` | SQLite-Datei | `data/lessons.db` |
| `LV_TOKEN` | Optionaler Bearer-Token | leer |

**Zu Embeddings:** Anthropic bietet kein eigenes Embedding-Modell an und empfiehlt Voyage AI. Ohne Voyage-Key
nutzt die App einen lokalen Zeichen-n-Gramm-Vektor. Der ist tolerant für Wortteile und Tippfehler, versteht
aber keine Bedeutung ("Kredit" findet nicht "Darlehen"). Nach einem Wechsel des Anbieters in den
Einstellungen "Neu indexieren" drücken.

## Startbestand

`startbestand/vorlage.json` enthält drei als BEISPIEL markierte Lessons, die Form und Abstraktionsgrad
zeigen. Kopiere die Datei, ersetze die Beispiele durch deine 20 bis 30 eigenen Lessons (bisherige Wellen,
erster Objektkauf) und importiere sie unter Einstellungen → Importieren. Die Beispiel-Lessons danach in der
App löschen, falls du sie mitimportiert hast.

Felder: `titel` (max. 80 Zeichen), `situation`, `ereignis`, `lesson` (ein Satz als Regel), `bereich`,
`schweregrad` (1–5) sind Pflicht; `massnahme`, `tags`, `bestaetigungen` (wie oft erlebt) und `erstellt_am`
(`YYYY-MM-DD`) optional.

## Datenschutz und Compliance

- Daten liegen ausschließlich in der SQLite-Datei auf dem Home-PC.
- An die **Claude API** gehen: dein Erfassungstext, die Antwort auf eine Rückfrage sowie Titel und Regel von
  bis zu fünf ähnlichen bestehenden Lessons (für die Dublettenprüfung).
- An **Voyage AI** (falls aktiv) gehen die Texte der Lessons und deine Suchanfragen.
- **Spracherkennung** läuft über den Browser: Chrome schickt Audio an Google, Safari nutzt Apple-Dienste.
  Für berufliche Inhalte lieber tippen oder zuerst die Richtlinien prüfen.
- **Vor der Nutzung mit beruflichen Einträgen** mit den internen Deloitte-Richtlinien zu persönlichen
  Notizen und KI-Tools abgleichen. Die Eigennamen-Warnung ist eine Hilfe, keine Garantie.

## Entwicklung

```bash
pip install -r requirements-dev.txt
python -m pytest            # inkl. Browser-Test, falls Playwright + Chromium vorhanden
```

Aufbau: `lessons_vault/` (FastAPI, SQLite mit Trigram-FTS5, Claude-Strukturierung, Embeddings, Compliance),
`lessons_vault/static/` (PWA ohne Build-Schritt), `.planning/` (GSD-Planung: Projekt, Anforderungen,
Roadmap, Phasenpläne, Verifikation).
