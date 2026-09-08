"""Erzeugt eine Beispiellieferung mit absichtlich eingebauten Maengeln.

Zweck ist zweierlei: eine Lieferung zum Ausprobieren des Werkzeugs ohne
Kundendaten, und eine belastbare Grundlage fuer die Tests. Jeder eingebaute
Mangel ist unten benannt, damit sich pruefen laesst, ob die zugehoerige Regel
ihn tatsaechlich findet.

Aufruf:
    python tools/beispieldaten.py ziel/verzeichnis [--vendors 500]

Die Daten sind frei erfunden. Firmennamen, Anschriften und Bankverbindungen
sind konstruiert; die IBANs sind rechnerisch gueltig, gehoeren aber zu keinem
realen Konto.
"""

from __future__ import annotations

import argparse
import csv
import random
import sys
from datetime import date, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

# Die Beispieldaten werden gegen dieselben Verfahren erzeugt, gegen die das
# Werkzeug spaeter prueft. Andernfalls entstehen Befunde, die nur von der
# Nachlaessigkeit des Generators zeugen und nicht von einem eingebauten Mangel.
from sapmdq.rules.validators import IBAN_LENGTHS, iban_valid, vat_id_valid

# Der Zufallsgenerator wird fest angesaet: dieselbe Beispiellieferung soll bei
# jedem Aufruf entstehen, sonst waeren die Tests nicht reproduzierbar.
SEED = 20260908

ORTE = [
    ("Berlin", "10115", "DE"), ("Hamburg", "20095", "DE"), ("Muenchen", "80331", "DE"),
    ("Koeln", "50667", "DE"), ("Frankfurt", "60311", "DE"), ("Stuttgart", "70173", "DE"),
    ("Wien", "1010", "AT"), ("Salzburg", "5020", "AT"), ("Zuerich", "8001", "CH"),
    ("Amsterdam", "1012 AB", "NL"), ("Paris", "75001", "FR"), ("Mailand", "20121", "IT"),
]
BRANCHEN = ["Handel", "Technik", "Logistik", "Bau", "Pharma", "Textil", "Metall", "Chemie"]

#: Namensbestandteile. Firmennamen werden aus zwei verschiedenen Stammwoertern
#: gebildet und ohne Zuruecklegen gezogen. Zwei Namen, die sich nur in einer
#: laufenden Nummer unterscheiden, waeren fuer den unscharfen Abgleich zu
#: aehnlich - die Dublettenerkennung meldete sie zu Recht, und die absichtlich
#: eingebauten Cluster gingen darin unter.
STAMMWOERTER = [
    "Baumann", "Kessler", "Lindner", "Hoffmann", "Wagner", "Brandt", "Ziegler",
    "Kaufmann", "Roth", "Sommer", "Winkler", "Faber", "Gerber", "Hartmann",
    "Krueger", "Lehmann", "Mayer", "Neumann", "Ostermann", "Pfeiffer", "Quandt",
    "Reinhardt", "Schuster", "Thiel", "Ulrich", "Vogel", "Wendt", "Zimmer",
    "Ahrens", "Bergmann", "Clausen", "Dietrich", "Engel", "Fischer", "Grabowski",
    "Huber", "Ingwer", "Jansen", "Koehler", "Lorenz", "Moser", "Nolte",
]
FORMEN = ["GmbH", "AG", "KG", "GmbH & Co. KG", "OHG", "e.K."]
STRASSEN = ["Hauptstrasse", "Bahnhofstrasse", "Industrieweg", "Am Markt", "Lindenallee"]

#: Stellenzahl der Bankleitzahl je Land, passend zum Aufbau der IBAN.
BANK_KEY_LENGTHS = {"DE": 8, "AT": 5, "CH": 5, "NL": 4, "FR": 5, "IT": 5}


def mod97(text: str) -> int:
    rest = 0
    for char in text:
        rest = (rest * 10 + int(char)) % 97 if char.isdigit() else (rest * 100 + ord(char) - 55) % 97
    return rest


def make_iban(country: str, rng: random.Random, bank_key: str = "") -> str:
    """Baut eine rechnerisch gueltige IBAN in der Laenge des Landes.

    Wo bekannt, wird die Bankleitzahl des Stammsatzes uebernommen - sonst
    meldet die Regel VEN-FMT-005 zu Recht, dass IBAN und Bankschluessel nicht
    zusammenpassen.
    """
    length = IBAN_LENGTHS.get(country, 22)
    prefix_lengths = {"DE": 8, "AT": 5, "CH": 5, "NL": 4, "FR": 5, "IT": 5}
    prefix = ""
    if bank_key and country in prefix_lengths:
        prefix = "".join(char for char in bank_key if char.isdigit())[: prefix_lengths[country]]
        prefix = prefix.ljust(prefix_lengths[country], "0")
    rest = length - 4 - len(prefix)
    body = prefix + "".join(str(rng.randint(0, 9)) for _ in range(rest))
    check = 98 - mod97(body + country + "00")
    return f"{country}{check:02d}{body}"


def make_vat(country: str, rng: random.Random) -> str:
    """Erzeugt eine syntaktisch gueltige USt-IdNr. des Landes.

    Erzeugt und geprueft wird gegen dieselbe Funktion, die spaeter beurteilt -
    fuer Laender mit Pruefziffernverfahren durch Ausprobieren, was bei
    einstelligen Pruefziffern in wenigen Versuchen gelingt.
    """
    if country not in ("DE", "AT", "NL", "FR", "IT"):
        return ""
    for _ in range(400):
        digits = "".join(str(rng.randint(0, 9)) for _ in range(11))
        candidate = {
            "DE": "DE" + digits[:9],
            "AT": "ATU" + digits[:8],
            "NL": "NL" + digits[:9] + "B" + digits[9:11],
            "FR": "FR" + digits[:2] + digits[:9],
            "IT": "IT" + digits[:11],
        }[country]
        if vat_id_valid(country, candidate):
            return candidate
    return ""


def vat_de(rng: random.Random) -> str:
    """Deutsche USt-IdNr. mit gueltiger Pruefziffer."""
    while True:
        digits = [rng.randint(0, 9) for _ in range(8)]
        product = 10
        for digit in digits:
            total = (digit + product) % 10 or 10
            product = (2 * total) % 11
        check = (11 - product) % 10
        candidate = "".join(map(str, digits)) + str(check)
        if candidate[0] != "0":
            return "DE" + candidate


def eindeutige_namen(rng: random.Random, anzahl: int) -> list[str]:
    """Zieht paarweise verschiedene Firmennamen ohne Zuruecklegen.

    Jeder Name traegt einen vierstelligen Zusatz, wie er in gewachsenen
    Stammdaten haeufig vorkommt. Er ist hier kein Schmuck: ohne ihn
    unterscheiden sich zwei Namen aus dem Wortvorrat schnell nur in einem von
    drei Bestandteilen, was der unscharfe Abgleich zu Recht als moegliche
    Dublette meldet. Die absichtlich eingebauten Cluster gingen darin unter.
    """
    paare = [
        (erst, zweit)
        for index, erst in enumerate(STAMMWOERTER)
        for zweit in STAMMWOERTER[index + 1 :]
    ]
    if anzahl > len(paare):
        raise ValueError(
            f"Es lassen sich nur {len(paare)} verschiedene Namen bilden, "
            f"angefordert waren {anzahl}."
        )
    buchstaben = "ABCDEFGHJKLMNPQRSTUVWXYZ"
    namen = []
    for lauf, (erst, zweit) in enumerate(rng.sample(paare, anzahl), start=1):
        zusatz = "".join(rng.choice(buchstaben) for _ in range(3)) + str(lauf % 10)
        namen.append(f"{erst} {zweit} {zusatz}")
    return namen


def eindeutige_kurztexte(rng: random.Random, anzahl: int) -> list[str]:
    """Zieht paarweise verschiedene Materialkurztexte ohne Zuruecklegen.

    Die Bestandteile unterscheiden sich in ganzen Woertern, nicht nur in einer
    Ziffer. Sonst laegen die Texte so nah beieinander, dass MAT-DUP-001 sie zu
    Recht als moegliche Dubletten meldet - was die absichtlich eingebaute
    Dublette unkenntlich machte.
    """
    gegenstaende = [
        "Schraube", "Blech", "Rohr", "Kabel", "Ventil", "Flansch", "Dichtung",
        "Lager", "Welle", "Zahnrad", "Feder", "Buchse", "Mutter", "Scheibe",
        "Winkel", "Traeger", "Profil", "Platte", "Stange", "Kupplung",
    ]
    werkstoffe = ["Stahl", "Edelstahl", "Messing", "Alu", "Kunststoff", "Kupfer", "Guss"]
    ausfuehrungen = ["verzinkt", "poliert", "lackiert", "gehaertet", "roh", "beschichtet"]
    kombinationen = [
        f"{gegenstand} {werkstoff} {ausfuehrung}"
        for gegenstand in gegenstaende
        for werkstoff in werkstoffe
        for ausfuehrung in ausfuehrungen
    ]
    if anzahl > len(kombinationen):
        raise ValueError(
            f"Es lassen sich nur {len(kombinationen)} verschiedene Kurztexte bilden."
        )
    # Der Sachnummernzusatz ist in technischen Materialstaemmen ueblich und
    # sorgt zugleich dafuer, dass sich zwei Kurztexte in mehr als einem von
    # drei Bestandteilen unterscheiden.
    return [
        f"{text} {rng.choice('ABCDEFGH')}{rng.randint(100, 999)}"
        for text in rng.sample(kombinationen, anzahl)
    ]


def write_csv(path: Path, rows: list[dict], columns: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=columns, delimiter=";", extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow(row)


def build(target: Path, vendor_count: int = 400) -> dict[str, int]:
    rng = random.Random(SEED)
    heute = date(2026, 1, 31)
    mandant = "100"

    lfa1: list[dict] = []
    lfb1: list[dict] = []
    lfm1: list[dict] = []
    lfbk: list[dict] = []

    # Ein einziger Namensvorrat fuer regulaere Kreditoren und Mangelfaelle.
    # Zwei getrennte Ziehungen koennten dieselbe Namenskombination liefern -
    # und zwei Kreditoren mit gleichem Namensstamm sind fuer den unscharfen
    # Abgleich zu Recht eine moegliche Dublette.
    MANGELNAMEN_ANZAHL = 90
    namen = eindeutige_namen(rng, vendor_count + MANGELNAMEN_ANZAHL)

    def anschrift(vorgabe: str | None = None) -> tuple[str, str, str, str]:
        """Erzeugt eine Anschrift mit landesueblicher Postleitzahl.

        Die Postleitzahl wird gestreut und nicht aus einer kurzen Liste
        gezogen: sie ist der Blockschluessel der Dublettenerkennung. Traegen
        hunderte Kreditoren dieselbe Postleitzahl, landen sie alle im selben
        Block, und aehnliche Namen an vermeintlich gleicher Anschrift werden
        zu Recht als moegliche Dubletten gemeldet.

        Mit ``vorgabe`` laesst sich das Land festlegen. Das ist noetig, wenn
        ein Mangelfall ein bestimmtes Land braucht: sonst traegt der Satz eine
        oesterreichische Postleitzahl bei deutschem Laenderschluessel und
        loest einen Formatbefund aus, der gar nicht eingebaut war.
        """
        moeglich = [eintrag for eintrag in ORTE if vorgabe is None or eintrag[2] == vorgabe]
        ort, _, land = rng.choice(moeglich or ORTE)
        plz = {
            "DE": lambda: f"{rng.randint(10000, 99999)}",
            "AT": lambda: f"{rng.randint(1000, 9999)}",
            "CH": lambda: f"{rng.randint(1000, 9999)}",
            "NL": lambda: f"{rng.randint(1000, 9999)} "
                          f"{rng.choice('ABCDEFGHJKLMNPRSTUVWXYZ')}"
                          f"{rng.choice('ABCDEFGHJKLMNPRSTUVWXYZ')}",
            "FR": lambda: f"{rng.randint(10000, 99999)}",
            "IT": lambda: f"{rng.randint(10000, 99999)}",
        }[land]()
        strasse = f"{rng.choice(STRASSEN)} {rng.randint(1, 199)}"
        return strasse, plz, ort, land

    # ------------------------------------------------ regulaere Kreditoren
    for index in range(1, vendor_count + 1):
        lifnr = f"{100000 + index}"
        strasse, plz, ort, land = anschrift()
        # Der Name muss in NAME1 passen (35 Zeichen laut DDIC).
        name = f"{namen[index - 1]} {rng.choice(FORMEN)}"[:35]
        angelegt = heute - timedelta(days=rng.randint(30, 2600))

        # Zahlungsbedingung gilt fuer beide Sichten gleich - abweichende Werte
        # sind ein eigener Mangel (VEN-CONS-006) und kein Grundrauschen.
        zahlungsbedingung = rng.choice(["ZB01", "ZB02", "ZB03"])
        bankland = land if land in IBAN_LENGTHS else "DE"
        # Die Bankleitzahl muss die Laenge haben, die das Land in der IBAN
        # vorsieht - sonst meldet VEN-FMT-005 fuer jeden auslaendischen
        # Kreditor eine Abweichung, die nur der Generator verursacht hat.
        stellen = BANK_KEY_LENGTHS.get(bankland, 8)
        bankleitzahl = "".join(str(rng.randint(0, 9)) for _ in range(stellen))

        lfa1.append({
            "MANDT": mandant, "LIFNR": lifnr, "NAME1": name, "LAND1": land,
            "ORT01": ort, "PSTLZ": plz, "STRAS": strasse, "PFACH": "",
            "KTOKK": "KRED", "ERDAT": angelegt.strftime("%Y%m%d"),
            "ERNAM": f"USER{rng.randint(1, 12):02d}",
            "STCEG": make_vat(land, rng),
            # Laender ohne USt-IdNr. tragen wenigstens eine Steuernummer,
            # sonst meldet VEN-COMP-004 fuer jeden Schweizer Kreditor.
            "STCD1": "" if land in ("DE", "AT", "NL", "FR", "IT") else f"{rng.randint(100000000, 999999999)}",
            "LOEVM": "", "SPERR": "", "SPERM": "", "XCPDK": "", "STKZN": "",
            "ADRNR": "", "NAME2": "", "STCD2": "", "KUNNR": "", "TELF1": "",
        })
        lfb1.append({
            "MANDT": mandant, "LIFNR": lifnr, "BUKRS": "1000",
            "AKONT": "0000160000", "ZTERM": zahlungsbedingung,
            "ZWELS": "U", "ZAHLS": "", "LOEVM": "", "SPERR": "",
            "ERDAT": angelegt.strftime("%Y%m%d"),
        })
        lfm1.append({
            "MANDT": mandant, "LIFNR": lifnr, "EKORG": "1000",
            "WAERS": "EUR" if land != "CH" else "CHF",
            "ZTERM": zahlungsbedingung, "LOEVM": "",
        })
        lfbk.append({
            "MANDT": mandant, "LIFNR": lifnr, "BANKS": bankland,
            "BANKL": bankleitzahl,
            "BANKN": f"{rng.randint(1000000000, 9999999999)}",
            "IBAN": make_iban(bankland, rng, bankleitzahl),
            "BKONT": "", "KOINH": "",
        })

    defekte: list[str] = []
    naechste = vendor_count
    # Namen fuer die Mangelfaelle aus dem hinteren Teil desselben Vorrats. Ein
    # sprechender Name wie "Adresslos GmbH" waere bequem zu lesen, aber
    # unbrauchbar: alle Saetze einer Mangelgruppe traegen dann einen langen
    # gemeinsamen Namensbestandteil, und die Dublettenerkennung meldete sie
    # voellig zu Recht als Cluster. Welcher Satz welchen Mangel traegt, steht
    # stattdessen in EINGEBAUTE_MAENGEL.md.
    mangelnamen = namen[vendor_count:][::-1]

    def gruppe(beschreibung: str, saetze: list[dict]) -> None:
        """Vermerkt eine Mangelgruppe samt der betroffenen Kreditorennummern."""
        schluessel = ", ".join(satz["LIFNR"] for satz in saetze[:8])
        weiter = " ..." if len(saetze) > 8 else ""
        defekte.append(f"{beschreibung} | betroffen: {schluessel}{weiter}")

    def neuer_kreditor(eindeutig: bool = True, **felder) -> dict:
        """Legt einen Kreditor mit einem gezielt eingebauten Mangel an.

        ``eindeutig`` haengt an den Namen einen unterscheidungskraeftigen
        Zusatz. Ohne ihn traegen alle Saetze einer Mangelgruppe denselben
        Namen und die Dublettenerkennung meldet sie voellig zu Recht als
        Cluster - was den einen absichtlich eingebauten Dublettenfall
        unkenntlich machte.
        """
        nonlocal naechste
        naechste += 1
        lifnr = f"{100000 + naechste}"
        strasse, plz, ort, land = anschrift(felder.get("LAND1"))
        if eindeutig:
            felder = dict(felder)
            felder["NAME1"] = f"{mangelnamen.pop()} {rng.choice(FORMEN)}"[:35]
        satz = {
            "MANDT": mandant, "LIFNR": lifnr, "NAME1": "Beispiel GmbH", "LAND1": land,
            "ORT01": ort, "PSTLZ": plz, "STRAS": strasse, "PFACH": "", "KTOKK": "KRED",
            "ERDAT": (heute - timedelta(days=400)).strftime("%Y%m%d"), "ERNAM": "USER01",
            "STCEG": make_vat(land, rng), "STCD1": f"{rng.randint(100000000, 999999999)}",
            "LOEVM": "", "SPERR": "", "SPERM": "", "XCPDK": "",
            "STKZN": "", "ADRNR": "", "NAME2": "", "STCD2": "", "KUNNR": "", "TELF1": "",
        }
        satz.update(felder)
        lfa1.append(satz)
        return satz

    # ------------------------------------------------ eingebaute Maengel
    # VEN-COMP-001: EU-Kreditor ohne USt-IdNr.
    gruppe(
        "VEN-COMP-001 und VEN-COMP-004: 6 EU-Kreditoren ohne USt-IdNr. und ohne Steuernummer",
        [neuer_kreditor(LAND1="DE", STCEG="", STCD1="") for _ in range(6)],
    )

    # VEN-FMT-001: USt-IdNr. mit falscher Pruefziffer
    gruppe(
        "VEN-FMT-001: 4 Kreditoren mit falscher USt-IdNr.-Pruefziffer",
        [neuer_kreditor(LAND1="DE", STCEG="DE111111111") for _ in range(4)],
    )

    # VEN-FMT-002: Postleitzahl passt nicht zum Land
    gruppe(
        "VEN-FMT-002: 3 Kreditoren mit unpassender Postleitzahl",
        [neuer_kreditor(LAND1="DE", PSTLZ="123", ORT01="Berlin") for _ in range(3)],
    )

    # VEN-COMP-002: ohne Ort und Postleitzahl
    gruppe(
        "VEN-COMP-002: 5 Kreditoren ohne Ort oder Postleitzahl",
        [neuer_kreditor(ORT01="", PSTLZ="") for _ in range(5)],
    )

    # VEN-FMT-006: Platzhaltername
    gruppe(
        "VEN-FMT-006: 3 Kreditoren mit Platzhalternamen",
        [neuer_kreditor(eindeutig=False, NAME1=name) for name in ("xxxx", "unbekannt", "TEST")],
    )

    # VEN-RISK-002: reine Postfachanschrift
    gruppe(
        "VEN-RISK-002: 4 Kreditoren mit reiner Postfachanschrift",
        [neuer_kreditor(STRAS="", PFACH="10 20 30") for _ in range(4)],
    )

    # VEN-CONS-007: natuerliche Person mit Rechtsform im Namen
    gruppe(
        "VEN-CONS-007: 3 Kreditoren als natuerliche Person mit Rechtsform im Namen",
        [neuer_kreditor(STKZN="X") for _ in range(3)],
    )

    # VEN-DUP-003: Namensdubletten mit Schreibvarianten
    dubletten = [
        ("Mueller & Sohn GmbH", "Hauptstrasse 12", "10115", "Berlin"),
        ("Müller und Sohn G.m.b.H.", "Hauptstr. 12", "10115", "Berlin"),
        ("MUELLER U SOHN GMBH", "Haupt-Strasse 12", "10115", "Berlin"),
    ]
    gruppe(
        "VEN-DUP-003: 1 Cluster aus 3 Namensdubletten mit Schreibvarianten",
        [
            neuer_kreditor(
                eindeutig=False, NAME1=name, STRAS=strasse, PSTLZ=plz, ORT01=ort, LAND1="DE"
            )
            for name, strasse, plz, ort in dubletten
        ],
    )

    # VEN-DUP-001: gleiche USt-IdNr. bei zwei Kreditoren
    geteilte_ustid = make_vat("DE", rng)
    gruppe(
        "VEN-DUP-001: 2 Kreditoren mit gleicher USt-IdNr.",
        [neuer_kreditor(LAND1="DE", STCEG=geteilte_ustid) for _ in range(2)],
    )

    # VEN-LC-001: Loeschvormerkung ohne Archivierung
    gruppe(
        "VEN-LC-001: 7 Kreditoren mit alter Loeschvormerkung ohne Archivierung",
        [
            neuer_kreditor(
                LOEVM="X", ERDAT=(heute - timedelta(days=1500)).strftime("%Y%m%d")
            )
            for _ in range(7)
        ],
    )

    # Kreditoren, denen anschliessend die Buchungskreissicht entzogen wird.
    ohne_buchungskreis = [neuer_kreditor() for _ in range(4)]

    # Buchungskreis-, Einkaufs- und Bankdaten fuer die Mangelfaelle ergaenzen.
    # Ohne sie meldeten Regeln wie VEN-COMP-005 oder VEN-COMP-008 fuer jeden
    # eingebauten Mangelfall zusaetzlich eine fehlende Sicht.
    vorhanden_bukrs = {satz["LIFNR"] for satz in lfb1}
    vorhanden_bank = {satz["LIFNR"] for satz in lfbk}
    for satz in lfa1:
        if satz["LIFNR"] not in vorhanden_bukrs:
            lfb1.append({
                "MANDT": mandant, "LIFNR": satz["LIFNR"], "BUKRS": "1000",
                "AKONT": "0000160000", "ZTERM": "ZB01", "ZWELS": "U", "ZAHLS": "",
                "LOEVM": "", "SPERR": "", "ERDAT": satz["ERDAT"],
            })
        if satz["LIFNR"] not in vorhanden_bank:
            land = satz["LAND1"]
            bankland = land if land in IBAN_LENGTHS else "DE"
            stellen = BANK_KEY_LENGTHS.get(bankland, 8)
            bankleitzahl = "".join(str(rng.randint(0, 9)) for _ in range(stellen))
            lfbk.append({
                "MANDT": mandant, "LIFNR": satz["LIFNR"], "BANKS": bankland,
                "BANKL": bankleitzahl,
                "BANKN": f"{rng.randint(1000000000, 9999999999)}",
                "IBAN": make_iban(bankland, rng, bankleitzahl),
                "BKONT": "", "KOINH": "",
            })

    # VEN-COMP-006: Buchungskreisdaten ohne Abstimmkonto
    for satz in lfb1[:5]:
        satz["AKONT"] = ""
    defekte.append("VEN-COMP-006: 5 Buchungskreissaetze ohne Abstimmkonto")

    # VEN-COMP-007: ohne Zahlungsbedingung
    for satz in lfb1[5:11]:
        satz["ZTERM"] = ""
    defekte.append("VEN-COMP-007: 6 Buchungskreissaetze ohne Zahlungsbedingung")

    # VEN-REF-003: Zahlungsbedingung, die es im Customizing nicht gibt
    for satz in lfb1[11:15]:
        satz["ZTERM"] = "ZZ99"
    defekte.append("VEN-REF-003: 4 Verweise auf unbekannte Zahlungsbedingung")

    # VEN-COMP-005: Kreditoren ganz ohne Buchungskreissicht. Die Saetze werden
    # ausdruecklich dafuer angelegt: naehme man die zuletzt entstandenen, waeren
    # es die zur Loeschung vorgemerkten, und die Regel schliesst diese zu Recht
    # aus - der Mangel entstuende gar nicht.
    ohne_bukrs = {satz["LIFNR"] for satz in ohne_buchungskreis}
    lfb1 = [satz for satz in lfb1 if satz["LIFNR"] not in ohne_bukrs]
    gruppe(
        "VEN-COMP-005: 4 Kreditoren ohne Buchungskreisdaten", ohne_buchungskreis
    )

    # VEN-FMT-003: ungueltige IBAN
    for satz in lfbk[:5]:
        satz["IBAN"] = satz["IBAN"][:-1] + ("0" if satz["IBAN"][-1] != "0" else "1")
    defekte.append("VEN-FMT-003: 5 ungueltige IBAN")

    # VEN-FMT-004: IBAN-Land weicht vom Bankland ab. Das Bankland wird
    # ausdruecklich auf ein anderes Land als das der IBAN gesetzt - ein fest
    # gewaehlter Wert traefe sonst gelegentlich das Land der IBAN und der
    # Mangel entstuende gar nicht.
    for satz in lfbk[5:8]:
        satz["BANKS"] = "IT" if satz["IBAN"][:2] != "IT" else "PL"
    defekte.append("VEN-FMT-004: 3 Bankverbindungen mit abweichendem Bankland")

    # VEN-DUP-002: gleiche Bankverbindung bei zwei Kreditoren. Uebernommen wird
    # die vollstaendige Verbindung: kopierte man nur die IBAN, passten Bankland
    # und Bankschluessel nicht mehr dazu und es entstuenden nebenher zwei
    # Formatbefunde, die gar nicht eingebaut waren.
    if len(lfbk) > 20:
        for feld in ("BANKS", "BANKL", "BANKN", "IBAN"):
            lfbk[20][feld] = lfbk[19][feld]
        defekte.append(
            "VEN-DUP-002: 2 Kreditoren mit gleicher Bankverbindung | betroffen: "
            f"{lfbk[19]['LIFNR']}, {lfbk[20]['LIFNR']}"
        )

    # ------------------------------------------------------- Material
    mara: list[dict] = []
    makt: list[dict] = []
    marc: list[dict] = []
    mbew: list[dict] = []
    material_count = max(120, vendor_count // 3)
    kurztexte = eindeutige_kurztexte(rng, material_count)
    for index in range(1, material_count + 1):
        matnr = f"{2000000 + index}"
        art = rng.choice(["ROH", "HALB", "FERT", "HAWA"])
        mara.append({
            "MANDT": mandant, "MATNR": matnr, "MTART": art,
            "MATKL": rng.choice(["001", "002", "003", "004"]),
            "MEINS": rng.choice(["ST", "KG", "M"]),
            "ERSDA": (heute - timedelta(days=rng.randint(60, 2400))).strftime("%Y%m%d"),
            "LAEDA": (heute - timedelta(days=rng.randint(1, 500))).strftime("%Y%m%d"),
            "ERNAM": f"USER{rng.randint(1, 12):02d}", "LVORM": "", "EAN11": "",
        })
        makt.append({
            "MANDT": mandant, "MATNR": matnr, "SPRAS": "D",
            "MAKTX": kurztexte[index - 1],
        })
        marc.append({
            "MANDT": mandant, "MATNR": matnr, "WERKS": "1000",
            "DISMM": rng.choice(["PD", "VB", "ND"]), "LVORM": "",
        })
        preis = round(rng.uniform(1.5, 900.0), 2)
        menge = rng.choice([0, 0, 10, 55, 320, 1200])
        mbew.append({
            "MANDT": mandant, "MATNR": matnr, "BWKEY": "1000", "BWTAR": "",
            "VPRSV": "S", "STPRS": f"{preis:.2f}", "VERPR": "0.00", "PEINH": "1",
            "BKLAS": {"ROH": "3000", "HALB": "7900", "FERT": "7920", "HAWA": "3100"}[art],
            "LBKUM": str(menge), "SALK3": f"{menge * preis:.2f}", "LVORM": "",
        })

    # MAT-COMP-002: ohne Warengruppe
    for satz in mara[:4]:
        satz["MATKL"] = ""
    defekte.append("MAT-COMP-002: 4 Materialien ohne Warengruppe")

    # MAT-CONS-003: Standardpreissteuerung ohne Standardpreis
    for satz in mbew[4:9]:
        satz["STPRS"] = "0.00"
        satz["SALK3"] = "0.00"
    defekte.append("MAT-CONS-003: 5 Materialien mit Preissteuerung S ohne Standardpreis")

    # MAT-CONS-005: Bestandswert passt nicht zu Menge und Preis
    for satz in mbew[9:13]:
        satz["LBKUM"] = "100"
        satz["STPRS"] = "10.00"
        satz["SALK3"] = "5000.00"
    defekte.append("MAT-CONS-005: 4 Materialien mit falschem Bestandswert")

    # MAT-FMT-001: EAN mit falscher Pruefziffer
    for satz in mara[13:17]:
        satz["EAN11"] = "4006381333930"
    defekte.append("MAT-FMT-001: 4 Materialien mit falscher EAN-Pruefziffer")

    # MAT-COMP-001: Material ohne Kurztext
    ohne_text = {satz["MATNR"] for satz in mara[17:21]}
    makt = [satz for satz in makt if satz["MATNR"] not in ohne_text]
    defekte.append("MAT-COMP-001: 4 Materialien ohne Kurztext")

    # MAT-DUP-001: doppelte Kurzbezeichnung
    if len(makt) > 30:
        makt[30]["MAKTX"] = makt[29]["MAKTX"]
        defekte.append("MAT-DUP-001: 1 Cluster mit doppelter Materialkurzbezeichnung")

    # ------------------------------------------------------ Customizing
    t001 = [{"MANDT": mandant, "BUKRS": "1000", "BUTXT": "Musterwerk AG",
             "LAND1": "DE", "WAERS": "EUR", "KTOPL": "INT"}]
    t052 = [{"MANDT": mandant, "ZTERM": z, "ZTAGG": "00", "ZTAG1": t}
            for z, t in (("ZB01", 30), ("ZB02", 14), ("ZB03", 60))]
    # Zahlwege fuer jedes vorkommende Land - sonst meldet VEN-REF-004 fuer
    # jeden auslaendischen Kreditor eine Luecke im Customizing.
    t042z = [
        {"MANDT": mandant, "LAND1": land, "ZLSCH": z, "TEXT1": t}
        for land in ("DE", "AT", "CH", "NL", "FR", "IT")
        for z, t in (("U", "Ueberweisung"), ("S", "Scheck"))
    ]
    t005 = [{"MANDT": mandant, "LAND1": land, "INTCA": land,
             "XEGLD": "X" if land in ("DE", "AT", "NL", "FR", "IT") else ""}
            for land in ("DE", "AT", "CH", "NL", "FR", "IT")]
    t077k = [{"MANDT": mandant, "KTOKK": "KRED", "NUMKR": "01"}]
    t134 = [{"MANDT": mandant, "MTART": a, "KKREF": k} for a, k in
            (("ROH", "0001"), ("HALB", "0002"), ("FERT", "0002"), ("HAWA", "0001"))]
    t025 = [{"MANDT": mandant, "BKLAS": b, "KKREF": k} for b, k in
            (("3000", "0001"), ("3100", "0001"), ("7900", "0002"), ("7920", "0002"))]
    t023 = [{"MANDT": mandant, "MATKL": m} for m in ("001", "002", "003", "004")]
    t006 = [{"MANDT": mandant, "MSEHI": m} for m in ("ST", "KG", "M")]
    t001w = [{"MANDT": mandant, "WERKS": "1000", "NAME1": "Werk Musterstadt", "LAND1": "DE"}]
    skb1 = [{"MANDT": mandant, "BUKRS": "1000", "SAKNR": "0000160000", "MITKZ": "K"},
            {"MANDT": mandant, "BUKRS": "1000", "SAKNR": "0000140000", "MITKZ": "D"}]
    tcurc = [{"MANDT": mandant, "WAERS": w} for w in ("EUR", "CHF", "USD")]
    t024e = [{"MANDT": mandant, "EKORG": "1000", "EKOTX": "Einkauf zentral", "BUKRS": "1000"}]

    # ------------------------------------------------------ schreiben
    write_csv(target / "LFA1.csv", lfa1, list(lfa1[0]))
    write_csv(target / "LFB1.csv", lfb1, list(lfb1[0]))
    write_csv(target / "LFM1.csv", lfm1, list(lfm1[0]))
    write_csv(target / "LFBK.csv", lfbk, list(lfbk[0]))
    write_csv(target / "MARA.csv", mara, list(mara[0]))
    write_csv(target / "MAKT.csv", makt, list(makt[0]))
    write_csv(target / "MARC.csv", marc, list(marc[0]))
    write_csv(target / "MBEW.csv", mbew, list(mbew[0]))
    for name, rows in (
        ("T001", t001), ("T052", t052), ("T042Z", t042z), ("T005", t005),
        ("T077K", t077k), ("T134", t134), ("T025", t025), ("T023", t023),
        ("T006", t006), ("T001W", t001w), ("SKB1", skb1), ("TCURC", tcurc),
        ("T024E", t024e),
    ):
        write_csv(target / f"{name}.csv", rows, list(rows[0]))

    zaehlung = {
        "LFA1": len(lfa1), "LFB1": len(lfb1), "LFM1": len(lfm1), "LFBK": len(lfbk),
        "MARA": len(mara), "MAKT": len(makt), "MARC": len(marc), "MBEW": len(mbew),
        "T001": len(t001), "T052": len(t052), "T042Z": len(t042z), "T005": len(t005),
        "T077K": len(t077k), "T134": len(t134), "T025": len(t025), "T023": len(t023),
        "T006": len(t006), "T001W": len(t001w), "SKB1": len(skb1), "TCURC": len(tcurc),
        "T024E": len(t024e),
    }

    manifest = ["# Begleitzettel der Beispiellieferung", "delivery:",
                f"  extraction_date: {heute.isoformat()}", '  client: "100"',
                "  source_system: ECC", "", "tables:"]
    for name, anzahl in zaehlung.items():
        manifest.append(f"  {name}: {{rows: {anzahl}, file: {name}.csv}}")
    (target / "manifest.yaml").write_text("\n".join(manifest) + "\n", encoding="utf-8")

    (target.parent / "EINGEBAUTE_MAENGEL.md").write_text(
        "# Absichtlich eingebaute Maengel der Beispiellieferung\n\n"
        "Diese Liste dient dem Abgleich: jede Zeile nennt eine Regel, was sie "
        "finden soll und welche Stammsaetze betroffen sind.\n\n"
        + "\n".join(f"- {eintrag}" for eintrag in defekte)
        + "\n\n## Folgebefunde\n\n"
        "Ueber die aufgefuehrten Maengel hinaus melden weitere Regeln Befunde, "
        "die aus denselben Saetzen folgen - eine Loeschvormerkung ohne Zahlsperre "
        "(VEN-RISK-006) etwa ergibt sich aus den vorgemerkten Kreditoren. Solche "
        "Folgebefunde sind erwuenscht und zeigen, dass die Regeln ineinandergreifen.\n",
        encoding="utf-8",
    )
    return zaehlung


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("target", help="Zielverzeichnis fuer die Eingangsdateien")
    parser.add_argument("--vendors", type=int, default=400, help="Anzahl regulaerer Kreditoren")
    args = parser.parse_args()

    target = Path(args.target).resolve()
    counts = build(target, args.vendors)
    print(f"Beispiellieferung erzeugt in {target}")
    for name, count in counts.items():
        print(f"  {name:8s} {count:6d} Saetze")


if __name__ == "__main__":
    main()
