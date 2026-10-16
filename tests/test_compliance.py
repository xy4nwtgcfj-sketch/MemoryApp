from lessons_vault.compliance import pruefen


def test_firmenname():
    assert any("Firmenname" in h for h in pruefen("Bei Kunde Müller GmbH lief der Cutover schief", "Beruf"))


def test_kunde_mit_name():
    assert any("Eigenname" in h for h in pruefen("Kunde Brenntag wollte keine Testphase", "Beruf"))


def test_person():
    assert any("Personenname" in h for h in pruefen("Herr Schmidt hat die Abnahme verweigert", "Immobilien"))


def test_sperrliste_unabhaengig_vom_bereich():
    hinweise = pruefen("Wieder Probleme mit acme beim Go-live", "Projekte", ["ACME"])
    assert any("Sperrliste" in h for h in hinweise)


def test_sperrliste_nur_ganzes_wort():
    assert pruefen("Acmewerk ist ein Wort", "Projekte", ["Acme"]) == []


def test_betrag_und_zahlen_nur_beruf():
    assert pruefen("Die Sanierung kostete 12.000 €", "Immobilien") == []
    hinweise = pruefen("Die Welle umfasste 4500 Lagerplätze und 1,2 Mio. € Budget", "Beruf")
    assert any("Geldbetrag" in h for h in hinweise)
    assert any("4500" in h for h in hinweise)


def test_jahreszahl_ok():
    assert pruefen("Seit 2024 machen wir Rollouts in Wellen", "Beruf") == []


def test_kontaktdaten():
    hinweise = pruefen("Ansprechpartner: max@example.com, 0171 1234567", "Immobilien")
    assert any("E-Mail" in h for h in hinweise)
    assert any("Telefon" in h for h in hinweise)


def test_abstrahierte_formulierungen_sind_ok():
    texte = [
        "Bei großen EWM-Rollouts muss der Cutover-Plan zwei Wochen vor Go-live mit dem Kunden abgestimmt sein.",
        "Der Kunde hat die Abnahme verschoben, weil das Lager zu spät informiert wurde.",
        "Vor jedem Steering Committee die Eskalationen mit der Projektleitung vorbesprechen.",
        "In der SAP EWM Welle 3 fehlten Stammdaten im Lager.",
    ]
    for text in texte:
        assert pruefen(text, "Beruf") == [], text
