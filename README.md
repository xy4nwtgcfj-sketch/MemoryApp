# Lessons Vault

Ein zweites Gedächtnis für Erfahrungen. Lessons in unter 30 Sekunden erfassen (Text oder Sprache),
eine KI strukturiert sie, und du findest sie wieder, wenn eine ähnliche Situation bevorsteht.

Stand: Phase 1 "Erfassen und Finden", Phase 1.1 "Lokale KI" und Phase 1.2 "Manuelles Briefing"
(siehe `.planning/ROADMAP.md`). Kalender-Briefings, Erinnerungen und Mustererkennung folgen nach der
Abnahme von Phase 1 (drei Wochen echte Nutzung, mindestens 10 neue Lessons).

## Funktionen

- **Erfassen:** Stichworte tippen oder diktieren, optional einen Bereich antippen. Je nach Einstellung:
  - **Claude (sofort):** Entwurf in wenigen Sekunden, höchstens eine Rückfrage. Klingt eine Lesson nach
    Lehrbuchwissen, das Claude ohnehin kennt ("Puffer einplanen"), fragt Claude nach deinem persönlichen Teil:
    Was war bei dir anders, welches eigene Muster, welche Größenordnung? Die Frage ist optional.
    Im Formular markiert "Persönliche Erfahrung", ob die Lesson Wissen enthält, das nur du hast.
  - **Lokal (Hintergrund):** Der Rohtext ist sofort gespeichert. Ein lokales Modell auf dem PC strukturiert
    ihn in 1 bis 3 Minuten, der Entwurf landet unter **Prüfen**.
  - **Manuell:** Formular selbst ausfüllen.
- **Briefing:** Vor einer Aufgabe die Situation in einem Satz beschreiben ("Projektplanung für Rollout
  Welle 4 schreiben"). Du bekommst:
  - die bis zu 5 wichtigsten eigenen Lessons, sortiert nach Relevanz × Schweregrad × wie oft erlebt,
    überholte nie, mit Begründung je Lesson,
  - eine Checkliste zum Abhaken und Kopieren (aus deinen Maßnahmen, mit Claude auf die Situation
    zugeschnitten und mit Quellenangabe je Punkt),
  - eine kurze Claude-Zusammenfassung "Worauf du achten solltest", nur aus deinen Lessons.

  Mit "Hilfreich" / "Nicht relevant" verbesserst du künftige Briefings zu ähnlichen Situationen.
  Frühere Briefings bleiben abrufbar.
- **Prüfen** (nur sichtbar, wenn ein Bereich lokal strukturiert wird): Lokal strukturierte Entwürfe übernehmen, korrigieren, Rückfrage beantworten, neu strukturieren
  oder verwerfen. Der Zähler in der Leiste zeigt offene Entwürfe.
- **Dubletten:** Ähnliche Lessons werden erkannt; "Als Bestätigung zählen" erhöht den Zähler, ab 2× wird
  eine Lesson "bestätigt".
- **Suche:** Volltext (findet Wortteile: "Bank" findet "Finanzierungsbankgespräch"), semantisch, hybrid,
  mit Filtern. Ungeprüfte Entwürfe werden mit durchsucht.
- **Datenschutz-Warnung** bei Firmen, Personen, "Kunde X", Kontaktdaten, in "Beruf" auch Beträge und Zahlen.
  Eigene Sperrliste unter Einstellungen.

## Einrichtung auf dem Home-PC (Windows 11)

### 1. Programme installieren

- **Python 3.11 oder neuer** von python.org (Haken bei "Add python.exe to PATH" setzen)
- **Git** (oder das Projekt als ZIP herunterladen)
- **Ollama für Windows** von ollama.com. Startet danach automatisch mit Windows (Symbol im Infobereich).
- **Tailscale** auf PC und Smartphone

### 2. Modelle laden (PowerShell)

```powershell
ollama pull bge-m3        # Embeddings für die semantische Suche, ca. 1,2 GB
ollama pull qwen2.5:7b    # Strukturierung im Hintergrund, ca. 4,7 GB
```

### 3. App einrichten und starten

```powershell
git clone <repo> C:\LessonsVault
cd C:\LessonsVault
copy .env.example .env    # öffnen und ggf. ANTHROPIC_API_KEY eintragen
powershell -ExecutionPolicy Bypass -File scripts\start.ps1
```

Beim ersten Start wird eine eigene Python-Umgebung angelegt. Danach läuft die App unter
`http://127.0.0.1:8765`, nur am PC selbst erreichbar.

### 4. Messung auf deinem PC

```powershell
.venv\Scripts\python scripts\benchmark_lokal.py --pull
```

Lädt fehlende Testmodelle (gemma3:4b, qwen2.5:7b, gemma3:12b, zusammen ca. 16 GB), misst Zeiten und schreibt
`benchmark-ergebnis-<datum>.md` mit den Ergebnissen jedes Modells zum Vergleichen. Prüft außerdem die
RAM-Bestückung: Ein einzelner Riegel (Single-Channel) halbiert die Geschwindigkeit lokaler Modelle.
Mit `--claude` wird Claude als Referenz mitgemessen. Das bessere Modell trägst du danach als
`LV_OLLAMA_MODEL` in `.env` ein.

### 5. Zugriff vom Smartphone (HTTPS über Tailscale)

```powershell
tailscale serve --bg 8765
```

Danach ist die App unter `https://<pc-name>.<tailnet>.ts.net` erreichbar, nur für deine Geräte.
(HTTPS-Zertifikate müssen im Tailscale-Adminbereich unter "DNS" aktiviert sein.) Mikrofon und
App-Installation brauchen dieses HTTPS. iPhone: Safari → Teilen → "Zum Home-Bildschirm".
Android: Chrome → "App installieren".

### 6. Autostart

```powershell
powershell -ExecutionPolicy Bypass -File scripts\install-autostart.ps1
```

Startet die App bei der Anmeldung unsichtbar (60 Sekunden verzögert, damit Ollama schon läuft).
Protokoll: `data\server.log`. Entfernen: `Unregister-ScheduledTask -TaskName "Lessons Vault"`.
Damit die App auch ohne Anmeldung nach einem Neustart läuft, in Windows die automatische Anmeldung
aktivieren oder den Rechner nicht herunterfahren.

### Backup

Regelmäßig "Exportieren" unter Einstellungen (JSON). Zusätzlich die Datei `data\lessons.db`
in ein Cloud- oder NAS-Backup aufnehmen, am besten, während die App nicht schreibt.

## KI-Einstellungen

Unter Einstellungen → KI-Strukturierung:

- **Standard:** Automatisch (Claude, wenn ein API-Key da ist, sonst lokal, sonst manuell), Claude, Lokal, Manuell.
- **Pro Bereich überschreibbar**, zum Beispiel Beruf → Lokal, Immobilien → Claude.
- Bereiche auf **Lokal** werden **nie** an Claude geschickt, auch nicht als Vergleichskandidaten für die
  Dublettenprüfung anderer Bereiche.

Wenn Ollama mal nicht läuft, geht nichts verloren: Entwürfe warten, Embeddings werden automatisch
nachgeholt, die Suche fällt auf Volltext zurück.

## Konfiguration (`.env`)

| Variable | Bedeutung | Standard |
|---|---|---|
| `ANTHROPIC_API_KEY` | Claude für die sofortige Strukturierung | leer = keine Cloud-KI |
| `LV_CLAUDE_MODEL` / `LV_CLAUDE_EFFORT` | Claude-Modell und Denkaufwand | `claude-opus-5-5` / `low` |
| `LV_OLLAMA_URL` | Adresse von Ollama | `http://127.0.0.1:11434` |
| `LV_OLLAMA_MODEL` | Lokales Modell für die Strukturierung, leer = aus | `qwen2.5:7b` |
| `LV_OLLAMA_EMBED_MODEL` | Lokales Embedding-Modell | `bge-m3` |
| `LV_EMBEDDINGS` | `ollama`, `voyage`, `lokal` oder `auto` | `auto` (Vorlage: `ollama`) |
| `VOYAGE_API_KEY` / `LV_VOYAGE_MODEL` | Alternative: Embeddings über Voyage AI | leer / `voyage-3.5` |
| `LV_DB_PATH` | SQLite-Datei | `data/lessons.db` |
| `LV_TOKEN` | Optionaler Bearer-Token zusätzlich zu Tailscale | leer |

Nach einem Wechsel des Embedding-Modells werden alle Lessons im Hintergrund automatisch neu indexiert.

## Startbestand

`startbestand/vorlage.json` enthält drei als BEISPIEL markierte Lessons, die Form und Abstraktionsgrad
zeigen. Ersetze sie durch deine 20 bis 30 eigenen Lessons und importiere die Datei unter
Einstellungen → Importieren. Pflicht: `titel` (max. 80 Zeichen), `situation`, `ereignis`, `lesson`
(ein Satz als Regel), `bereich`, `schweregrad` (1–5). Optional: `massnahme`, `tags`, `bestaetigungen`,
`erstellt_am` (`YYYY-MM-DD`).

## Datenschutz und Compliance

- Daten liegen ausschließlich in der SQLite-Datei auf dem Home-PC.
- **Lokal-Modus:** Nichts verlässt den PC (Ollama läuft lokal).
- **Claude-Modus:** An die Claude API gehen der Erfassungstext, eine Rückfrage-Antwort sowie Titel und Regel
  von bis zu fünf ähnlichen Lessons aus Bereichen, die nicht auf "lokal" stehen.
- **Briefing-Zusammenfassung:** An Claude gehen die Situationsbeschreibung und die vollständigen Texte der
  gefundenen Lessons, ausgenommen Lessons aus Bereichen auf "lokal". Ist ein lokaler Bereich als Filter
  gewählt, gibt es keine Zusammenfassung; Lessons und Checkliste kommen dann rein lokal.
- **Voyage** (nur falls statt Ollama gewählt): Lesson-Texte und Suchanfragen.
- **Spracherkennung** läuft über den Browser: Chrome schickt Audio an Google, Safari nutzt Apple-Dienste.
  Für vertrauliche Inhalte tippen. Lokales Whisper ist als nächster Schritt vorgemerkt.
- Vor der Nutzung mit beruflichen Einträgen mit den internen Deloitte-Richtlinien abgleichen.
  Die Eigennamen-Warnung ist eine Hilfe, keine Garantie.

## Entwicklung

```bash
pip install -r requirements-dev.txt
python -m pytest            # inkl. Browser-Test, falls Playwright + Chromium vorhanden
```

Linux/macOS: `./scripts/start.sh`. Aufbau: `lessons_vault/` (FastAPI, SQLite mit Trigram-FTS5,
Claude- und Ollama-Strukturierung, Hintergrund-Worker, Embeddings, Compliance),
`lessons_vault/static/` (PWA ohne Build-Schritt), `scripts/` (Start, Autostart, Messung, Backup),
`.planning/` (GSD-Planung).
