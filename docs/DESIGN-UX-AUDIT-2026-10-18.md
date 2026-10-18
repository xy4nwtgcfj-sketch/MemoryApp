# Design- und UX-Audit Lessons Vault (18.10.2026)

Grundlage: 37 Screenshots (iPhone 390 px hell/dunkel, Erststart, Desktop), der Code in `lessons_vault/static/`,
Messungen mit Playwright (iPhone-13-Profil, Offline, Latenz, Zoom 200 %, Tab-Reihenfolge, Kontrastformel).
Fünf Rollen haben unabhängig geprüft: visuelles Design, Bedienabläufe, Barrierefreiheit (WCAG 2.2 AA),
Gewohnheitsbildung, iPhone-PWA. Ein Test auf einem echten iPhone steht aus (VoiceOver, Diktat in der
Home-Bildschirm-App, Statusleiste); diese Punkte sind aus Code und bekanntem WebKit-Verhalten abgeleitet.

## 1. Gesamturteil

| Rolle | Note | Kernsatz |
|---|---|---|
| Visuelles Design | 3- | Ruhige, warme Basis, wirkt aber wie ein sorgfältiger Prototyp: Emoji als Icons, keine Button-Hierarchie, überladene Karten, flache Typografie. |
| Bedienabläufe | 3 | Einstieg gut, nach dem Tippen wird es schwer: Entwurf als Formular mit 9 Feldern, Abruf auf drei Orte verteilt, Briefing etwa 4 Bildschirme lang. |
| Barrierefreiheit | nicht AA | 11 bis 13 AA-Kriterien verfehlt, vor allem dynamische Inhalte, Fokus, Toasts, Kontraste von Rahmen, iOS-Textgröße. Kein Totalblocker. |
| Gewohnheit | 25 bis 30 % | Geschätzte Chance auf wöchentliche Nutzung nach 3 Wochen. Mit den drei stärksten Maßnahmen 55 bis 65 %. |
| iPhone-PWA | gut, mit Bruch | Safe Area, 16-px-Felder, Foto-Weg gut. Bricht unterwegs bei schlechtem Netz: leerer Start, Eingaben nur im Speicher, offline stumme Knöpfe. |

Die wichtigste gemeinsame Aussage aller fünf Rollen: **Nicht neue Funktionen, sondern weniger Schritte nach dem
Tippen, eine klare Hauptaktion pro Ansicht und kein Datenverlust entscheiden, ob die App genutzt wird.**

## 2. Gefundene Fehler (keine Designfragen)

| # | Fehler | Fundstelle | Geprüft |
|---|---|---|---|
| F1 | "Entwurf prüfen" im Briefing schickt den Modus nicht mit; das Ergebnis ist immer kombiniert, auch wenn "Nur meine Erfahrung" markiert ist | app.js, `briefingMitFotos` (POST ohne `modus`) | ja |
| F2 | Moduswechsel im Ergebnis aktualisiert den Schalter oben nicht; Anzeige und Inhalt widersprechen sich | app.js, `modusWechsel` | ja |
| F3 | Offline bewirkt "Manuell" nichts: `showDraft` wartet auf `bereiche()`, der Fehler wird nicht abgefangen | app.js, `showDraft` | Messung Agent |
| F4 | Antwort auf die Rückfrage verwirft Änderungen, die schon im Formular gemacht wurden | app.js, Rückfrage-Handler | Messung Agent |
| F5 | Tab "Prüfen" zeichnet sich alle 10 s komplett neu; der Fokus springt an den Anfang | app.js, Polling in der Prüfen-Ansicht | Messung Agent |
| F6 | Button "beruflich/privat" liegt im Label der Bereichs-Checkbox; Tipp kann die Checkbox mit umschalten, VoiceOver liest beides zusammen | app.js, Einstellungen Bereiche | Messung Agent |
| F7 | Router verwirft Parameter: `#/erfassen?text=…` landet ohne Text | app.js, `route()` | Messung Agent |

## 3. Befunde nach Themen

### 3.1 Erfassen (wichtigster Hebel)

- **Entwurf ist ein Formular statt einer Bestätigungskarte.** 9 offene Felder, "Speichern" etwa 1.000 px unter dem
  Entwurfsbeginn, Bereich doppelt (Chip und Auswahlliste), Titel im Feld abgeschnitten.
  Vorschlag: Karte mit der Regel groß, darunter Titel, Bereich, Schwere als Chips, Rest unter "Details",
  "Speichern" fixiert über der Tabbar.
- **Rückfrage bestraft die gewünschte Handlung.** Zweiter Claude-Aufruf, einzeiliges Feld ohne Diktat, Eingaben gehen
  verloren (F4), Text belehrt ("was Claude ohnehin weiß"). Vorschlag: erst speichern, dann optional
  "Schärfen? Ein Satz genügt" mit mehrzeiligem Feld.
- **Kein Erfassungsweg außerhalb der App.** Manifest-Shortcuts wirken auf iOS nicht. `/api/erfassen` speichert im
  Claude-Modus nichts, es liefert nur einen Entwurf. Vorschlag: Endpunkt "Schnellnotiz", der den Rohtext immer sofort
  als Entwurf sichert (Strukturierung danach im Hintergrund), dazu ein iOS-Kurzbefehl "Lesson merken"
  (Siri, Action-Taste, Rückseiten-Tippen, Widget). Ziel unter 10 s ohne App-Start.
- **Datenverlust möglich.** Rohtext und Entwurf liegen nur im Speicher; iOS beendet Home-Bildschirm-Apps im
  Hintergrund häufig. Kein Rückgängig nach Speichern oder Verwerfen, kein Abbrechen während Claude rechnet.
- **Datenschutz-Vorabprüfung wirkt wie ein Fehler** (gelber Kasten). Als Schutz richtig und vertrauensbildend, bei
  häufiger Wiederholung aber eine Strafe. Vorschlag: Treffer im Text mit einem Tap ersetzen, danach automatisch senden;
  positive Vertrauenszeile statt "Verarbeitung: Claude, sofort".
- **Bewertende Elemente:** Badge "allgemein", Checkbox-Text "kein Lehrbuch und kein KI-Assistent", Sekundenanzeige im
  Toast wirkt wie eine Stoppuhr. Vorschlag: Badge nur in der Statistik, Checkbox "Eigene Erfahrung", Messung still im
  Hintergrund.

Ablauf heute und Ziel (ab Start vom Home-Bildschirm):

| Aufgabe | Heute | Ziel |
|---|---|---|
| Text erfassen | 35 bis 50 s, 4 bis 5 Taps, Scrollen | 15 bis 20 s |
| Diktat | 40 bis 60 s | 15 bis 20 s (Kurzbefehl unter 10 s) |
| mit Rückfrage | 60 bis 100 s | 35 bis 45 s |
| Foto mit 3 Lessons | 2,5 bis 4 min | 60 bis 75 s ("Alle übernehmen") |
| Briefing bis kopierte Checkliste | 50 bis 90 s | 30 bis 40 s |
| alte Lesson wiederfinden | 10 bis 60 s | 8 bis 15 s |

### 3.2 Abrufen (Briefing und Suche)

- Ergebnis zu lang, das Wichtigste nicht oben: Eingabe bleibt ausgeklappt, dann Zusammenfassung, Besonderheiten,
  Plan, Karten. Vorschlag: Eingabe zu einer Zeile einklappen, Plan mit Kopieren oben, schwache oder bereichsfremde
  Treffer hinter "Weitere (2)".
- **Eigene Erfahrung geht unter.** Bei kleinem Bestand besteht der Plan überwiegend aus Claude-Wissen. Der Nutzen wird
  Claude zugeschrieben, nicht dem Archiv, und das schwächt den Grund zu erfassen. Vorschlag: eigene Erfahrung zuerst
  und visuell markiert (Gold), Lücken als Einladung ("Dazu hast du noch nichts").
- Begriffe überschneiden sich: "Entwurf" (KI-Entwurf und Foto eines Projektplans), "Prüfen" (Tab, Gegenchecken,
  OCR-Text). Vorschlag: "Plan gegenchecken" und Tab "Eingang".
- Suche: drei Suchmodi und der Hinweis "Ohne VOYAGE_API_KEY …" stehen auf der Nutzeroberfläche (bei laufendem Ollama
  sogar falsch). Vorschlag: immer Hybrid, Modi unter "Erweitert", Technikhinweise nur in den Einstellungen.
- Transparenz: Quelle je Planpunkt ist gut. Es fehlt, welche Lesson-Texte an Claude gingen, und wie sicher eine
  Zuordnung ist. Vorschlag: Fußzeile "An Claude gesendet: Situation + 4 Lessons (Titel, Regel)", Quellenmarke
  antippbar mit "Passt nicht".

### 3.3 Visuelles Design

- **Emoji und Unicode als Icons** (🎤 📷 👍 ＋ ☰ ⌕ ⚙): unterschiedlich groß, bunt, ☰ heißt auf iOS "Menü". Stärkster
  Prototyp-Marker. Vorschlag: Inline-SVG-Sprite im Lucide-Stil (ISC-Lizenz, kein Build-Schritt).
- **Keine Button-Hierarchie:** vier Aktionen in drei Varianten, verwaiste Umbrüche. Vorschlag: Diktieren und Foto als
  Icon-Buttons am Textfeld, "Manuell" als Text-Link, eine vollbreite Hauptaktion.
- **Karten überladen:** bis zu sechs Badges plus Meta-Zeile, die Teile wiederholt. Vorschlag: höchstens zwei Badges,
  eine Meta-Zeile "Beruf · ●●●●○ · 3× · 18.10.", Feedback als Icon-Paar.
- **Typografie ohne Hierarchie:** Ansichtstitel 16,8 px bei 16 px Fließtext, in der Detailansicht ist der Titel kleiner
  als die Regel. Kopfzeile doppelt ("Lessons Vault" plus kleiner Ansichtstitel). Vorschlag: iOS-Large-Title (28 px),
  Skala unten, Silbentrennung, deutsche Anführungszeichen.
- **Farbsemantik unscharf:** Gold steht für Schwere, "in Arbeit", Zähler und Besonderheiten; Grün für "deine Erfahrung"
  und "bestätigt". Vorschlag: Gold = eigene Erfahrung, Schiefergrau mit Funkel-Icon = Claude, Grün = Erfolg,
  Gelb = Warnung, Rot = destruktiv.
- **Dunkelmodus:** Primär-Buttons pastellblau mit dunkler Schrift wirken wie deaktiviert. Vorschlag: gefüllt #3567A6
  mit weißer Schrift, Pastell nur für Text und aktive Tabs.
- **App-Icon** zeigt einen Kalender mit Plus ("Termin anlegen"), hat eigene Rundungen und Transparenz (iOS füllt
  schwarz), 192 statt 180 px. Vorschlag: deckendes Quadrat, Notizbuch mit goldenem Lesezeichen.
- Native Controls nicht angeglichen (System-Blau bei Checkboxen, lauter Fokusring beim Öffnen, Resize-Griff),
  Aufklappbereiche ohne Pfeil, Einstellungen als Matrix über etwa 4 Bildschirme.

**Design-System (Kurzfassung):**

- Farben hell: `--bg #F7F6F3`, `--surface #FFF`, `--text #1A1D21`, `--text-2 #4F5660`, `--primary #1F3A5F`,
  `--own #8A5A10 / --own-tint #F8EEDC / --own-line #D9A441`, `--ai #5A6472 / --ai-tint #EEF0F3`,
  `--success #1E6B3F`, `--warning #7A5200`, `--danger #B42318`, `--control-border #8A8F96`.
- Farben dunkel: `--bg #0E1116`, `--surface #161B22`, `--text #E8EAED`, `--primary #8DB4E8` (Text),
  `--primary-fill #3567A6` (Flächen), `--own #E8B45C`, `--control-border #6B7A8C`.
- Typo: Large Title 28/34 700, Titel 22/28, Kartentitel 17/22 600, Text 16/24, Regel 18/26 500, Meta 13/18,
  Overline 12/16 600 Großbuchstaben. Schrift über `font: -apple-system-body` (übernimmt die iOS-Textgröße).
- Raster 4 px, Abstand zwischen Sektionen 32, nach Aktionszeilen 24, Radien 8/12/16/Pille, Ziele mindestens 44 px.
- Buttons: primär (gefüllt, einer pro Bereich), tonal, Text, Gefahr, Icon-Button 44×44.

### 3.4 iPhone-PWA

- Service Worker wartet ohne Zeitlimit zuerst auf das Netz: bei Tailscale-Neuverbindung leerer Bildschirm.
  Vorschlag: Shell aus dem Cache, im Hintergrund aktualisieren.
- Erfassen-Seite zeichnet erst nach Serverantwort (gemessen 4,3 s bei 4 s Latenz). Vorschlag: sofort zeichnen,
  Bereiche aus dem lokalen Speicher, GET-Zeitlimit etwa 10 s.
- Offline irreführend ("Verarbeitung: manuell"), F3. Vorschlag: Offline-Hinweis, Notiz lokal halten und später senden.
- Eigenes Diktat (Web Speech) ist in der Home-Bildschirm-App unzuverlässig; die Diktiertaste der iOS-Tastatur ist
  robuster. Vorschlag: auf iOS zur Tastatur-Diktat-Hilfe umbauen.
- Statusleiste passt farblich nicht (theme-color dunkelblau, Kopfzeile hell). Tastatur verdeckt Toasts, Tabbar springt.
  Kein Zurück-Knopf (Standalone hat keine Wischgeste), keine Aktualisierung beim Zurückkehren aus dem Hintergrund.
  Token muss abgetippt werden (Vorschlag: "Aus Zwischenablage einfügen"). Keine GZip-Kompression.

### 3.5 Barrierefreiheit (WCAG 2.2 AA)

- Ladezustände und Ergebnisse werden nicht angesagt; nach "Strukturieren" und "Briefing erstellen" fällt der Fokus
  an den Seitenanfang. Vorschlag: eine globale Live-Region, Fokus auf die neue Überschrift.
- Toasts enthalten Links und Fehlermeldungen und verschwinden nach 4 bis 9 s. Vorschlag: Toasts nur für
  Bestätigungen, Fehler und Links bleibend in der Ansicht.
- Lightbox ohne Fokusfalle. Vorschlag: natives `<dialog>` mit `showModal()`.
- Kontraste unter Soll: Gold-Badges 3,1:1, Zähler 3,6 und 2,1:1, Rahmen von Eingabefeldern 1,3 bis 1,5:1 (Soll 3:1),
  ausgegraute Karten 1,9 bis 2,6:1, Placeholder. Draußen im Sonnenlicht besonders spürbar.
- iOS-Textgröße wird ignoriert; bei 200 % läuft Suche und Einstellungen über, "Einstellungen" wird zu "Eins".
- Fokus unter der Tabbar verdeckt, Pflichtfelder nicht markiert ("Speichern, abgeblendet" ohne Grund),
  Emoji werden mitgesprochen ("Fotoapparat Foto"), Kartentitel sind keine Überschriften, Seitentitel immer gleich.

### 3.6 Gewohnheit und Motivation

- **Kaltstart:** 0 Lessons, leeres Briefing, Startbestand nur als JSON am PC. Ohne Bestand kein Aha-Moment.
  Vorschlag: "Ernte-Modus" bei unter 20 Lessons: eine Impulsfrage nach der anderen je Bereich
  ("Was lief beim letzten Cutover anders als geplant?"), Diktat, Serienspeichern, Fortschritt zu 20.
- **Kein Auslöser** außer dem eigenen Gedächtnis. Ohne Push möglich: Kalenderserie "Freitag, 10 min Lessons" als
  .ics-Datei, iOS-Kurzbefehl-Automationen (Freitag 16:30; täglich 17:30 mit den heutigen Terminen).
  Web Push geht ab iOS 16.4 nur für installierte PWAs und braucht VAPID auf dem PC: erst Phase 2.
- **Fortschritt unsichtbar:** Erfolgskriterien stehen in den Einstellungen. Vorschlag: "23 / 60 · Woche ✓" im Kopf,
  pro Lesson "3× im Briefing geholfen", Bestätigungen zählen als Aktivität.
- **Keine Streaks, Punkte, Abzeichen**, jetzt nicht und später nicht: Lessons entstehen unregelmäßig; ein Streak-Abbruch
  ist oft der Moment des Ausstiegs. Höchstens "4 der letzten 6 Wochen".

## 4. Wo die Rollen sich widersprechen und wie ich entscheiden würde

| Frage | Positionen | Empfehlung |
|---|---|---|
| Rückfrage vor oder nach dem Speichern | Abläufe: "Ergänzen & speichern" in einem Schritt. Gewohnheit: erst speichern, dann optional schärfen. | Erst speichern. Das sichert die Lesson in jedem Fall; Schärfen bleibt ein Angebot. |
| Tabs zusammenlegen (Briefing + Suche = "Abrufen", 3 Tabs) | Abläufe dafür, andere Rollen nicht gefordert. | Nicht vor dem Freeze. Großer Umbau mit Testaufwand; die Umbenennungen bringen den Großteil. |
| Foto und "Entwurf prüfen" bis 20 Lessons ausblenden | Gewohnheit dafür. | Nur optisch zurücknehmen (Icon statt Button), nicht verstecken. Du hast Fotos ausdrücklich gewollt. |
| Web Push | iPhone-PWA: hoher Nutzen. Gewohnheit: erst Phase 2. | Phase 2. Kurzbefehl-Automationen testen, ob sie reichen. |

## 5. Vorschlag für den Umfang vor dem Freeze

Faustregel: Vor dem Freeze nur, was Reibung beim Erfassen senkt, Datenverlust verhindert, den Startbestand füllt
oder Wirkung sichtbar macht. Alles, was einen neuen Anwendungsfall eröffnet, wartet auf die Abnahme.

**Paket 1: Erfassen ohne Reibung und ohne Verlust (empfohlen, höchste Wirkung)**
Kompakte Entwurfskarte mit fixiertem Speichern; Rückfrage nach dem Speichern; Autosave im lokalen Speicher und
"Weiter mit deiner letzten Notiz?"; Rückgängig nach Speichern und Verwerfen; "Ohne KI sichern" während des Wartens;
Fehler F3, F4. Schnellnotiz-Endpunkt plus Anleitung für den iOS-Kurzbefehl (F7 mit).

**Paket 2: Visuelles System (empfohlen, größter Sprung bei "schön")**
SVG-Icons, Design-Tokens hell/dunkel mit Farbsemantik, Typo-Skala und Large Title, eine Hauptaktion pro Ansicht,
entschlackte Karten, neues App-Icon, Statusleiste, Kontraste und 44-px-Ziele.

**Paket 3: Abruf klarer (empfohlen)**
Briefing-Eingabe einklappen, Plan oben, eigene Erfahrung zuerst und markiert, schwache Treffer einklappen,
Fehler F1, F2, Begriffe ("Plan gegenchecken", "Eingang"), Suchmodi und Technikhinweise unter "Erweitert",
Hinweis "An Claude gesendet".

**Paket 4: Start und Motivation (empfohlen, aber neue Oberfläche)**
Ernte-Modus für den Startbestand, Erststart-Karte, Fortschritt im Kopf, Freitags-Termin als .ics,
Einstellungen auf eine "Datenschutz-Stufe pro Bereich" verdichten.

**Paket 5: Robustheit iPhone und Barrierefreiheit (empfohlen, unsichtbar aber wichtig)**
Service Worker Cache zuerst, sofort zeichnen, Offline-Hinweis, Tastatur und Rückkehr aus dem Hintergrund,
Zurück-Knopf, Live-Region und Fokus, Toasts, Lightbox als Dialog, iOS-Textgröße, F5, F6.

**Nicht vor dem Freeze:** Web Push und App-Badge, Kalender-API, Tabs zusammenlegen, Streaks/Punkte,
Dashboard, weitere Foto- oder Briefing-Funktionen, Whisper.

## 6. Kritische Anmerkung

Die Pakete 1 bis 5 zusammen sind etwa so viel Arbeit wie eine eigene Phase. Das Konzept nennt selbst das Risiko
"Projekt bleibt liegen", und vier Phasen ohne echte Nutzung deuten in diese Richtung. Die Messlatte für die Abnahme
sind 10 echte Lessons in drei Wochen, nicht ein perfektes Design. Wenn nur ein Teil möglich ist: Paket 1 und die
Kurzfassung von Paket 2 (Icons, Tokens, eine Hauptaktion) bringen den größten Teil der Wirkung. Danach einfrieren
und nutzen; die Wochenbilanz "Was hat dich gebremst?" liefert dann echte Daten statt Vermutungen.

## 7. Umsetzungsstand (18.10.2026)

Auf Wunsch umgesetzt: alle Pakete 1 bis 5 und die Fehler F1 bis F7. Strittige Punkte nach Abschnitt 4
entschieden (Schärfen nach dem Sichern, keine Tab-Zusammenlegung, Fotos sichtbar). Nicht umgesetzt wie
empfohlen: Web Push und App-Badge, Kalender-API, Streaks, Briefing zweispaltig auf dem Desktop,
Startbilder für iOS.

| Bereich | Umsetzung |
|---|---|
| Erfassen | `/api/notiz` sichert sofort; kompakte Entwurfskarte mit fixiertem Sichern; Pflicht nur Regel und Bereich; Rückgängig nach Sichern und Verwerfen; "Später" in den Eingang; Schärfen nach dem Sichern; Autosave; Postausgang offline; Deep Link `#/erfassen?text=&bereich=` |
| Datenschutz | Ersetzen mit einem Tipp, danach automatisch senden; Namensprüfung auch im Hintergrund (nichts wird gesendet, Entwurf trägt die Hinweise); lokale Absicht bleibt dauerhaft lokal |
| Eingang | Immer sichtbarer Tab mit Zähler; Übernehmen mit einem Tipp, "Alle übernehmen"; Aktualisierung ohne Fokusverlust (F5) |
| Briefing | Eingabe klappt ein; eigene Erfahrung zuerst; Plan mit Quellen, eigene Quelle antippbar mit "Passt nicht"; Modusschalter und Kopieren im Ergebniskopf (F1, F2); schwache Treffer eingeklappt; Transparenzzeile; Lücken-Einladung; offene Frage am nächsten Tag |
| Gewohnheit | Startbestand per Fragen (Ernte); Kopfzeile "x / 60 · Woche ✓"; Wochenrückblick mit Leitfragen und "Was hat dich gebremst?"; "Erinnerst du dich?"; Kalenderserie (.ics); Kurzbefehl-Anleitung |
| Design | Tokens hell/dunkel mit Farbsemantik, SVG-Icons (Lucide), Typo-Skala mit Large Title, eine Hauptaktion je Ansicht, Meta-Zeile statt Badges, neues App-Icon, iOS-Listen in den Einstellungen, Seitenleiste auf dem Desktop |
| iPhone | Service Worker Cache zuerst; Erfassen zeichnet sofort; GET-Zeitlimit 10 s; Statusleiste passend; Tabbar und Toasts bei offener Tastatur; Zurück-Knopf; Aktualisierung bei Rückkehr; Token einfügen; GZip; Tastatur-Diktat statt Web Speech auf iOS |
| Barrierefreiheit | Live-Region und Fokus auf neue Inhalte; Toasts pausierbar, Fehler bleiben; Dialoge und Lightbox als `<dialog>`; Kontraste (Rahmen, Gold, Zähler, Placeholder); iOS-Textgröße; scroll-padding; 44-px-Ziele; Seitentitel je Ansicht; Emoji entfernt; F6 |
| Fehler | F1 bis F7 behoben, dazu ein "null"-Text in Briefing-Karten (beim Umbau gefunden) |

Tests: 186 (davon 12 Browser-Tests der neuen Abläufe). Offen: Test auf einem echten iPhone (VoiceOver,
Tastatur-Diktat, Statusleiste, Offline-Postausgang, Kurzbefehl).
