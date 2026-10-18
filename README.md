# Lessons Vault

Ein zweites Gedächtnis für Erfahrungen. Lessons in unter 30 Sekunden erfassen (Text oder Sprache),
eine KI strukturiert sie, und du findest sie wieder, wenn eine ähnliche Situation bevorsteht.

Stand: Phase 1 "Erfassen und Finden", 1.1 "Lokale KI", 1.2 "Manuelles Briefing" und 1.3 "Fotos"
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

  Zwei Modi:
  - **Mit Claude-Wissen** (Standard): Claude baut aus seinem Fachwissen und deinen Lessons einen gegliederten
    Plan, z. B. für die Hypercare-Phase eines EWM-Projekts. Jeder Punkt zeigt seine Quelle ("Deine Erfahrung"
    oder "Allgemein (Claude)"). "Deine Besonderheiten" zeigt, wo deine Erfahrung vom üblichen Vorgehen
    abweicht. Allgemeinwissen ist nicht geprüft. Geht auch ohne passende Lessons, dann klar gekennzeichnet.
  - **Nur meine Erfahrung:** ausschließlich deine Lessons.

  Mit "Hilfreich" / "Nicht relevant" verbesserst du künftige Briefings zu ähnlichen Situationen.
  Frühere Briefings bleiben abrufbar.
- **Fotos:**
  - *Lessons aus Fotos:* Folie, Whiteboard oder Notiz fotografieren. Die App findet darin Erfahrungen,
    du wählst aus, und jede läuft einzeln durch die normale Erfassung. Das Foto hängt an jeder Lesson.
  - *Entwurf prüfen* (im Briefing): Foto eines Entwurfs, etwa eines Projektplans. Claude gleicht ihn mit
    deinen passenden Lessons ab: was fehlt, was schon berücksichtigt ist.
  - Fotos lassen sich auch nachträglich an eine Lesson hängen und in groß ansehen.
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

`.env` mit dem Editor bearbeiten (nicht per `echo ... > .env` in PowerShell, das erzeugt UTF-16).
Beim ersten Start wird eine eigene Python-Umgebung angelegt. Danach läuft die App unter
`http://127.0.0.1:8765`, nur am PC selbst erreichbar.

**Zugangstoken:** Ist in `.env` kein `LV_TOKEN` gesetzt, erzeugt die App beim ersten Start eines und legt
es in `data\zugangstoken.txt` ab. Beim ersten Öffnen fragt die App danach; einmal eintragen genügt.
Auf dem iPhone braucht die installierte Home-Bildschirm-App das Token einmal extra, auch wenn Safari es
schon kennt.

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

Danach ist die App unter `https://<pc-name>.<tailnet>.ts.net` erreichbar. `--bg` bleibt über Neustarts
bestehen. Voraussetzungen im Tailscale-Adminbereich unter "DNS": MagicDNS an und "HTTPS Certificates"
aktiviert. Der allererste Aufruf holt das Zertifikat und kann einige Sekunden dauern. Mikrofon und
App-Installation brauchen dieses HTTPS. iPhone: Safari → Teilen → "Zum Home-Bildschirm".
Android: Chrome → "App installieren".

Empfohlen: In den Tailscale-Zugriffsregeln (ACL) den Port 443 des PCs nur für deine eigenen Geräte
freigeben. Mit der Standardregel "alle dürfen alles" erreichen sonst auch geteilte oder fremde Geräte
in deinem Tailnet die App (das Zugangstoken schützt trotzdem).

### 6. Texterkennung für Fotos (Tesseract)

Für Fotos im Bereich Beruf erkennt die App den Text lokal, damit das Foto selbst nie den PC verlässt.

1. Tesseract-Installer für Windows von der Seite der UB Mannheim herunterladen
   (github.com/UB-Mannheim/tesseract/wiki).
2. Bei der Installation unter "Additional language data" **German** auswählen.
3. Standardpfad `C:\Program Files\Tesseract-OCR` beibehalten, dann findet die App Tesseract automatisch.
   Sonst den Pfad zu `tesseract.exe` als `LV_TESSERACT_CMD` in `.env` eintragen.

Unter Einstellungen → KI-Strukturierung steht, ob die Texterkennung bereit ist. Handschrift erkennt
Tesseract schlecht; für handschriftliche Notizen die Kernpunkte besser abtippen.

### 7. Autostart und tägliches Backup

```powershell
powershell -ExecutionPolicy Bypass -File scripts\install-autostart.ps1
```

Richtet zwei geplante Aufgaben ein:
- **Lessons Vault:** startet die App bei der Anmeldung unsichtbar (60 Sekunden verzögert, damit Ollama
  schon läuft). Stürzt sie ab, startet sie sich nach 10 Sekunden selbst neu. Protokoll: `data\server.log`
  (ohne Suchbegriffe, wird ab 5 MB rotiert).
- **Lessons Vault Backup:** sichert täglich um 12:17 Datenbank und Fotos (holt verpasste Läufe nach).

Es läuft immer nur eine Instanz. Willst du die App von Hand starten, erst die Aufgabe beenden:
`Stop-ScheduledTask -TaskName "Lessons Vault"`.

### 8. Energie und Neustarts

Damit die App unterwegs erreichbar ist, darf der PC nicht schlafen (PowerShell als Administrator):

```powershell
powercfg /change standby-timeout-ac 0     # Energiesparmodus bei Netzbetrieb: nie
powercfg /h off                           # Ruhezustand aus
```

Unter Einstellungen → Windows Update eine Nutzungszeit setzen, damit Update-Neustarts nachts passieren.
Die App startet erst nach der Anmeldung. Für Neustarts ohne dich: automatische Anmeldung einrichten
(z. B. mit Sysinternals Autologon) oder den PC nach Updates einmal anmelden.

### Backup und Wiederherstellung

- **Automatisch:** Die tägliche Sicherung schreibt `lessons-<zeit>.db` und die Fotos nach `backups\`
  (letzte 30 Stände). Besser ein Ordner außerhalb des PCs: `LV_BACKUP_ZIEL` in `.env`, z. B. ein
  OneDrive- oder NAS-Ordner.
- **Von Hand:** `powershell -File scripts\backup.ps1`. Prüfen einer Sicherung:
  `.venv\Scripts\python scripts\backup.py --pruefen backups\lessons-<zeit>.db`.
- **Vor Updates:** Vor jeder Datenbank-Migration legt die App selbst eine Kopie unter `data\sicherungen\` an.
- **Wiederherstellen:** `Stop-ScheduledTask -TaskName "Lessons Vault"`, die gewünschte `lessons-<zeit>.db`
  nach `data\lessons.db` kopieren (vorher `data\lessons.db-wal` und `-shm` löschen), Fotos aus
  `backups\bilder\` nach `data\bilder\` kopieren, `Start-ScheduledTask -TaskName "Lessons Vault"`.
- Der JSON-Export unter Einstellungen enthält nur Lessons und Bereiche, keine Fotos und Briefings.
  Er ist gut zum Weitergeben oder Archivieren, ersetzt aber kein Backup.

### Aktualisieren

```powershell
Stop-ScheduledTask -TaskName "Lessons Vault"
powershell -File scripts\backup.ps1
git pull
Start-ScheduledTask -TaskName "Lessons Vault"
```

Beim Start werden fehlende Pakete nachinstalliert und die Datenbank migriert (mit Sicherung vorher).
Die App auf dem Handy lädt die neue Version beim nächsten Öffnen.

## KI-Einstellungen

Unter Einstellungen → KI-Strukturierung:

- **Standard:** Automatisch (Claude, wenn ein API-Key da ist, sonst lokal, sonst manuell), Claude, Lokal, Manuell.
- **Pro Bereich überschreibbar**, zum Beispiel Beruf → Lokal, Immobilien → Claude.
- Bereiche auf **Lokal** werden **nie** an Claude geschickt, auch nicht als Vergleichskandidaten für die
  Dublettenprüfung anderer Bereiche.
- Steht **irgendein Bereich** auf Lokal, geht eine Erfassung **ohne Bereichswahl** ebenfalls nicht an Claude
  (sie wird lokal oder manuell verarbeitet). Für Claude also den Bereich antippen.
- Unter Einstellungen → Bereiche markierst du Bereiche als **beruflich**: strengere Prüfung auf Namen,
  Beträge und Zahlen, Fotos nur per Texterkennung.

Wenn Ollama mal nicht läuft, geht nichts verloren: Entwürfe warten, Embeddings werden automatisch
nachgeholt, die Suche fällt auf Volltext zurück.

## Konfiguration (`.env`)

| Variable | Bedeutung | Standard |
|---|---|---|
| `ANTHROPIC_API_KEY` | Claude für die sofortige Strukturierung | leer = keine Cloud-KI |
| `LV_CLAUDE_MODEL` / `LV_CLAUDE_EFFORT` | Claude-Modell und Denkaufwand | `claude-opus-5-5` / `low` |
| `LV_BRIEFING_EFFORT` | Denkaufwand für kombinierte Briefing-Pläne | `medium` |
| `LV_OLLAMA_URL` | Adresse von Ollama | `http://127.0.0.1:11434` |
| `LV_OLLAMA_MODEL` | Lokales Modell für die Strukturierung, leer = aus | `qwen2.5:7b` |
| `LV_OLLAMA_EMBED_MODEL` | Lokales Embedding-Modell | `bge-m3` |
| `LV_EMBEDDINGS` | `ollama`, `voyage`, `lokal` oder `auto` (Ollama vor Voyage; bleibt beim bisher genutzten Anbieter) | `auto` (Vorlage: `ollama`) |
| `VOYAGE_API_KEY` / `LV_VOYAGE_MODEL` | Alternative: Embeddings über Voyage AI | leer / `voyage-3.5` |
| `LV_DB_PATH` | SQLite-Datei | `data/lessons.db` |
| `LV_TOKEN` | Zugangstoken; leer = automatisch erzeugt in `data/zugangstoken.txt` | automatisch |
| `LV_HOSTS` | Erlaubte Host-Namen (Schutz gegen DNS-Rebinding) | `127.0.0.1,localhost,*.ts.net` |
| `LV_BACKUP_ZIEL` | Zielordner der täglichen Sicherung | `backups` |
| `LV_TESSERACT_CMD` | Pfad zu `tesseract.exe`, falls nicht im Standardpfad | automatisch |
| `LV_BILDER_PATH` | Ordner für Fotos | `data/bilder` |

Nach einem Wechsel des Embedding-Modells werden alle Lessons im Hintergrund automatisch neu indexiert.
Ein einfacheres Ersatzverfahren (wenn Ollama beim Start noch nicht läuft) überschreibt dabei nie
vorhandene semantische Embeddings.

## Startbestand

`startbestand/vorlage.json` enthält drei als BEISPIEL markierte Lessons, die Form und Abstraktionsgrad
zeigen. Ersetze sie durch deine 20 bis 30 eigenen Lessons und importiere die Datei unter
Einstellungen → Importieren. Pflicht: `titel` (max. 80 Zeichen), `situation`, `ereignis`, `lesson`
(ein Satz als Regel), `bereich`, `schweregrad` (1–5). Optional: `massnahme`, `tags`, `bestaetigungen`,
`erstellt_am` (`YYYY-MM-DD`).

## Datenschutz und Compliance

- Daten liegen ausschließlich in der SQLite-Datei auf dem Home-PC.
- **Lokal-Modus:** Nichts verlässt den PC (Ollama läuft lokal).
- **Prüfung vor dem Senden:** Bevor Text an Claude geht (Erfassung, Rückfrage, Foto-Text und Notiz,
  Briefing-Situation), prüft die App ihn lokal auf Namen, Firmen, Kontaktdaten und, in beruflichen
  Bereichen, auf Beträge und Zahlen. Bei Treffern zeigt sie, was erkannt wurde; gesendet wird erst nach
  "Trotzdem senden". Begriffe aus der Sperrliste werden nie gesendet. Die Prüfung ist musterbasiert:
  Firmennamen ohne Rechtsform oder Städtenamen erkennt sie nur über die Sperrliste. Pflege sie.
- **Claude-Modus:** An die Claude API gehen der Erfassungstext, eine Rückfrage-Antwort sowie Titel und Regel
  von bis zu fünf ähnlichen Lessons aus Bereichen, die nicht auf "lokal" stehen. Lehnt Claude eine Anfrage
  aus Sicherheitsgründen ab, beantwortet sie serverseitig ein anderes Claude-Modell (Fallback).
- **Briefing-Zusammenfassung:** An Claude gehen die Situationsbeschreibung und die vollständigen Texte der
  gefundenen Lessons, ausgenommen Lessons aus Bereichen auf "lokal". Ist ein lokaler Bereich als Filter
  gewählt oder der Standard "lokal", gibt es keine Zusammenfassung; Lessons und Checkliste kommen dann
  rein lokal.
- **Voyage** (nur falls aktiv): alle Lesson-Texte und Suchanfragen, auch aus lokalen Bereichen. Wer
  "lokal" ernst meint, nutzt Ollama für Embeddings (Vorlage `.env.example`).
- **Fotos:**
  - Werden lokal unter `data\bilder\` gespeichert, ohne Metadaten (Standort, Kamera, Zeit), schon im
    Browser verkleinert.
  - *Berufliche Bereiche und ohne Bereichswahl:* Das Foto bleibt auf dem PC. Der Text wird lokal erkannt,
    du prüfst und kürzt ihn, und nur dieser Text (plus deine Notiz, ebenfalls geprüft) geht an Claude.
    Für berufliche Bereiche lässt sich das nicht auf "Claude sieht das Foto" umstellen.
  - *Private Bereiche:* Claude sieht das Foto selbst (umstellbar unter Einstellungen).
  - *Bereiche auf "lokal":* Weder Foto noch Text gehen an Claude.
  - Fotos, die nie an einer Lesson oder einem Briefing hingen, werden nach 2 Tagen gelöscht.
  - **Hinweis:** Fotos von Kundenfolien auf dem privaten PC zu speichern, gehört ausdrücklich in deinen
    Abgleich mit den Deloitte-Richtlinien.
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
