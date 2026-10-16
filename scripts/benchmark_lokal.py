"""Messskript für lokale KI auf dem Home-PC.

Misst auf deiner Hardware, wie schnell und wie gut lokale Modelle über Ollama arbeiten, und schreibt
einen Bericht (Markdown) zum Vergleichen. Nutzt denselben Prompt wie die App.

Aufruf (Windows, im Projektordner):
    .venv\\Scripts\\python scripts\\benchmark_lokal.py
    .venv\\Scripts\\python scripts\\benchmark_lokal.py --modelle gemma3:4b qwen2.5:7b gemma3:12b --pull
    .venv\\Scripts\\python scripts\\benchmark_lokal.py --claude      (zusätzlich Claude als Referenz, braucht ANTHROPIC_API_KEY)
"""

from __future__ import annotations

import argparse
import json
import os
import platform
import statistics
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import httpx  # noqa: E402
import numpy as np  # noqa: E402

from lessons_vault.compliance import pruefen  # noqa: E402
from lessons_vault.config import load_settings  # noqa: E402
from lessons_vault.embeddings import EmbeddingFehler, OllamaEmbeddings, modell_installiert  # noqa: E402
from lessons_vault.models import Bereich  # noqa: E402
from lessons_vault.structuring import OllamaStrukturierer, create_strukturierer  # noqa: E402

STANDARD_MODELLE = ["gemma3:4b", "qwen2.5:7b", "gemma3:12b"]
BEREICHE = [
    Bereich(name="Beruf", beispiele="Rollout-Wellen, Cutover, Stakeholder, Eskalationen, Steering Committees"),
    Bereich(name="Immobilien", beispiele="Besichtigungen, Bankgespräche, Sanierung, Mieter, Notar"),
]
# Fiktive Testeingaben. Nr. 2 enthält absichtlich erfundene Namen und Zahlen, um die Abstraktion zu prüfen.
TESTFAELLE = [
    ("Stichworte", "Bankgespräch, Gehaltsnachweise vergessen, zweiter Termin nötig"),
    ("Abstraktion", "Welle 3 Cutover bei Kunde Müller Logistik GmbH im Lager Hamm, Herr Schulz hatte keine Schichtleiter "
                    "eingeplant, Inventur 6 Stunden verspätet, 4500 Lagerplätze betroffen"),
    ("Sehr knapp", "Notar"),
]
EMBED_PAARE = [
    ("Unterlagen für das Bankgespräch vollständig mitbringen", "Was weiß ich über Bankgespräche?", "ähnlich"),
    ("Kredit bei der Hausbank verhandeln", "Darlehenskonditionen besprechen", "Synonym"),
    ("Cutover-Plan mit dem Lager abstimmen", "Was weiß ich über Bankgespräche?", "unähnlich"),
    ("Vor jedem Bankgespräch die Unterlagenliste anfordern",
     "Vor Bankterminen immer zuerst die Liste der benötigten Unterlagen anfragen", "Dublette"),
]


def ram_module() -> list[dict[str, Any]]:
    """Liest die RAM-Bestückung unter Windows aus (leer auf anderen Systemen oder bei Fehlern)."""
    if platform.system() != "Windows":
        return []
    cmd = [
        "powershell", "-NoProfile", "-Command",
        "Get-CimInstance Win32_PhysicalMemory | Select-Object BankLabel,DeviceLocator,Capacity,Speed,ConfiguredClockSpeed | ConvertTo-Json",
    ]
    try:
        out = subprocess.run(cmd, capture_output=True, text=True, timeout=20, check=True).stdout
        data = json.loads(out)
        return data if isinstance(data, list) else [data]
    except (OSError, subprocess.SubprocessError, ValueError):
        return []


def ram_bewertung(module: list[dict[str, Any]]) -> str:
    if not module:
        return "RAM-Bestückung nicht ermittelbar (nur unter Windows automatisch)."
    groessen = [int(m.get("Capacity") or 0) // 2**30 for m in module]
    takt = {m.get("ConfiguredClockSpeed") or m.get("Speed") for m in module}
    text = f"{len(module)} Modul(e): {' + '.join(f'{g} GB' for g in groessen)}, Takt {', '.join(str(t) for t in takt)} MT/s. "
    if len(module) == 1:
        return text + "WARNUNG: Nur ein Riegel = Single-Channel. Lokale Modelle laufen damit etwa halb so schnell wie mit zwei gleichen Riegeln."
    if len(set(groessen)) > 1:
        return text + "Hinweis: Unterschiedlich große Riegel laufen nur teilweise im Dual-Channel."
    return text + "Dual-Channel, gut."


def ollama_modelle(client: httpx.Client, url: str) -> list[str] | None:
    try:
        r = client.get(f"{url}/api/tags", timeout=5)
        r.raise_for_status()
        return [m["name"] for m in r.json().get("models", [])]
    except (httpx.HTTPError, KeyError, ValueError):
        return None


def ollama_pull(client: httpx.Client, url: str, modell: str) -> bool:
    print(f"  Lade {modell} herunter (kann einige Minuten dauern) …", flush=True)
    try:
        r = client.post(f"{url}/api/pull", json={"model": modell, "stream": False}, timeout=3600)
        r.raise_for_status()
        return True
    except httpx.HTTPError as exc:
        print(f"  Download fehlgeschlagen: {exc}")
        return False


def embedding_test(client: httpx.Client, url: str, modell: str) -> dict[str, Any]:
    provider = OllamaEmbeddings(url, modell, client=client)
    t0 = time.perf_counter()
    provider.embed(["Aufwärmen"], "document")
    kalt = time.perf_counter() - t0
    texte = [t for paar in EMBED_PAARE for t in paar[:2]]
    t0 = time.perf_counter()
    vektoren = provider.embed(texte, "document")
    batch = time.perf_counter() - t0
    t0 = time.perf_counter()
    provider.embed(["Was weiß ich über Bankgespräche?"], "query")
    einzel = time.perf_counter() - t0
    paare = []
    for i, (a, b, art) in enumerate(EMBED_PAARE):
        paare.append({"a": a, "b": b, "art": art, "aehnlichkeit": float(np.dot(vektoren[2 * i], vektoren[2 * i + 1]))})
    return {"kalt_s": kalt, "batch_s": batch, "batch_n": len(texte), "abfrage_s": einzel, "paare": paare}


def strukturierung_test(strukturierer: Any, metriken: bool = True) -> list[dict[str, Any]]:
    ergebnisse = []
    for name, text in TESTFAELLE:
        t0 = time.perf_counter()
        entwurf = strukturierer.strukturieren(text, "text", BEREICHE, [])
        dauer = time.perf_counter() - t0
        ausgabe = "\n".join([entwurf.titel, entwurf.situation, entwurf.ereignis, entwurf.lesson, entwurf.massnahme])
        lecks = pruefen(ausgabe, entwurf.bereich or "Beruf")
        ergebnisse.append({
            "fall": name,
            "eingabe": text,
            "dauer_s": dauer,
            "metriken": dict(getattr(strukturierer, "letzte_metriken", {})) if metriken else {},
            "entwurf": entwurf,
            "namen_im_ergebnis": lecks,
        })
        status = "Fehler: " + entwurf.ki_fehler if entwurf.ki_fehler else f"{dauer:.0f} s"
        print(f"    {name}: {status}", flush=True)
    return ergebnisse


def tok_s(tokens: float, sekunden: float) -> str:
    return f"{tokens / sekunden:.1f}" if sekunden else "–"


def bericht(info: dict[str, Any], embed: dict[str, Any] | None, laeufe: dict[str, list[dict[str, Any]]]) -> str:
    z = [f"# Messung lokale KI, {info['zeit']}", ""]
    z += ["## System", "", f"- CPU: {info['cpu']} ({info['kerne']} Threads)", f"- RAM: {info['ram']}", f"- Ollama: {info['ollama']}", ""]
    if embed:
        z += ["## Embeddings", "", f"- Modell laden (erster Aufruf): {embed['kalt_s']:.1f} s",
              f"- {embed['batch_n']} Texte am Stück: {embed['batch_s']:.1f} s",
              f"- Eine Suchanfrage: {embed['abfrage_s']:.2f} s", "",
              "| Paar | Art | Ähnlichkeit |", "|---|---|---|"]
        for p in embed["paare"]:
            z.append(f"| {p['a']} / {p['b']} | {p['art']} | {p['aehnlichkeit']:.2f} |")
        z += ["", "Die App zählt ab 0.85 als mögliche Dublette und zeigt ab 0.50 ähnliche Lessons. "
                  "Liegt \"Dublette\" deutlich darunter oder \"unähnlich\" darüber, sag Bescheid, dann passe ich die Schwellen an.", ""]
    z += ["## Strukturierung: Übersicht", "",
          "| Modell | Median gesamt | Laden (1. Aufruf) | Prompt Tok/s | Antwort Tok/s | Fehler | Namen/Zahlen im Ergebnis |",
          "|---|---|---|---|---|---|---|"]
    for modell, ergebnisse in laeufe.items():
        dauern = [e["dauer_s"] for e in ergebnisse]
        m = [e["metriken"] for e in ergebnisse if e["metriken"]]
        fehler = sum(1 for e in ergebnisse if e["entwurf"].ki_fehler)
        lecks = sum(len(e["namen_im_ergebnis"]) for e in ergebnisse)
        prompt = tok_s(sum(x.get("prompt_tokens", 0) for x in m), sum(x.get("prompt_s", 0) for x in m)) if m else "–"
        antwort = tok_s(sum(x.get("antwort_tokens", 0) for x in m), sum(x.get("antwort_s", 0) for x in m)) if m else "–"
        laden = f"{m[0].get('laden_s', 0):.0f} s" if m else "–"
        z.append(f"| {modell} | {statistics.median(dauern):.0f} s | {laden} | {prompt} | {antwort} | {fehler}/{len(ergebnisse)} | {lecks} |")
    z += ["", "Im Hintergrund-Modus sind bis etwa 3 Minuten pro Lesson unproblematisch. Entscheidend ist die Qualität unten.", ""]
    for modell, ergebnisse in laeufe.items():
        z += [f"## {modell}", ""]
        for e in ergebnisse:
            d = e["entwurf"]
            z += [f"### {e['fall']} ({e['dauer_s']:.0f} s)", "", f"Eingabe: _{e['eingabe']}_", ""]
            if d.ki_fehler:
                z += [f"**Fehler:** {d.ki_fehler}", ""]
                continue
            z += [f"- **Titel:** {d.titel}", f"- **Lesson:** {d.lesson}", f"- **Situation:** {d.situation}",
                  f"- **Ereignis:** {d.ereignis}", f"- **Maßnahme:** {d.massnahme or '–'}",
                  f"- **Bereich / Schwere / Tags:** {d.bereich} / {d.schweregrad} / {', '.join(d.tags)}",
                  f"- **Rückfrage:** {d.rueckfrage or '–'}",
                  f"- **Compliance-Hinweise des Modells:** {'; '.join(d.compliance_hinweise) or '–'}"]
            if e["namen_im_ergebnis"]:
                z.append(f"- **Noch im Ergebnis gefunden:** {'; '.join(e['namen_im_ergebnis'])}")
            z.append("")
    return "\n".join(z)


def run(argv: list[str] | None = None, client: httpx.Client | None = None) -> Path:
    settings = load_settings()
    parser = argparse.ArgumentParser(description="Lokale KI auf diesem PC messen")
    parser.add_argument("--modelle", nargs="+", default=STANDARD_MODELLE, help="Ollama-Modelle für die Strukturierung")
    parser.add_argument("--embed-modell", default=settings.ollama_embed_model)
    parser.add_argument("--url", default=settings.ollama_url)
    parser.add_argument("--pull", action="store_true", help="Fehlende Modelle automatisch herunterladen")
    parser.add_argument("--claude", action="store_true", help="Claude als Referenz mitmessen (ANTHROPIC_API_KEY nötig)")
    parser.add_argument("--ausgabe", default=None, help="Pfad für den Bericht")
    args = parser.parse_args(argv)
    client = client or httpx.Client(timeout=900)
    url = args.url.rstrip("/")

    print("System …", flush=True)
    module = ram_module()
    info = {
        "zeit": datetime.now().strftime("%Y-%m-%d %H:%M"),
        "cpu": platform.processor() or platform.machine(),
        "kerne": os.cpu_count(),
        "ram": ram_bewertung(module),
    }
    print(f"  {info['ram']}")

    installiert = ollama_modelle(client, url)
    if installiert is None:
        info["ollama"] = f"nicht erreichbar unter {url}"
        print(f"Ollama ist unter {url} nicht erreichbar. Ist die Ollama-App gestartet?")
        laeufe: dict[str, list[dict[str, Any]]] = {}
        embed = None
    else:
        info["ollama"] = f"erreichbar, installiert: {', '.join(installiert) or 'keine Modelle'}"
        embed = None
        print(f"Embeddings mit {args.embed_modell} …", flush=True)
        if not modell_installiert(args.embed_modell, installiert) and args.pull:
            ollama_pull(client, url, args.embed_modell)
            installiert = ollama_modelle(client, url) or []
        if modell_installiert(args.embed_modell, installiert):
            try:
                embed = embedding_test(client, url, args.embed_modell)
                print(f"  Suchanfrage: {embed['abfrage_s']:.2f} s")
            except EmbeddingFehler as exc:
                print(f"  Fehler: {exc}")
        else:
            print(f"  übersprungen, fehlt: ollama pull {args.embed_modell}")

        laeufe = {}
        for modell in args.modelle:
            if not modell_installiert(modell, installiert):
                if args.pull and ollama_pull(client, url, modell):
                    installiert = ollama_modelle(client, url) or []
                else:
                    print(f"{modell}: übersprungen, fehlt (ollama pull {modell} oder --pull)")
                    continue
            print(f"{modell} …", flush=True)
            laeufe[modell] = strukturierung_test(OllamaStrukturierer(url, modell, client=client))

    if args.claude:
        if settings.anthropic_api_key:
            print(f"Claude ({settings.claude_model}) …", flush=True)
            claude = create_strukturierer(settings.anthropic_api_key, settings.claude_model, settings.claude_effort)
            laeufe[f"Claude {settings.claude_model}"] = strukturierung_test(claude, metriken=False)
        else:
            print("Claude übersprungen: kein ANTHROPIC_API_KEY in .env")

    ziel = Path(args.ausgabe) if args.ausgabe else ROOT / f"benchmark-ergebnis-{datetime.now():%Y-%m-%d-%H%M}.md"
    ziel.write_text(bericht(info, embed, laeufe), encoding="utf-8")
    print(f"\nBericht: {ziel}")
    return ziel


if __name__ == "__main__":
    run()
