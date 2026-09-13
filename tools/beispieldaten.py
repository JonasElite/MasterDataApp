"""Erzeugt eine Beispiellieferung mit absichtlich eingebauten Mängeln.

Zweck ist zweierlei: eine Lieferung zum Ausprobieren des Werkzeugs ohne
Kundendaten, und eine belastbare Grundlage für die Tests. Jeder eingebaute
Mangel ist unten benannt, damit sich prüfen lässt, ob die zugehörige Regel
ihn tatsächlich findet.

Aufruf:
    python tools/beispieldaten.py ziel/verzeichnis [--vendors 500]

Die Daten sind frei erfunden. Firmennamen, Anschriften und Bankverbindungen
sind konstruiert; die IBANs sind rechnerisch gültig, gehören aber zu keinem
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
# Werkzeug später prüft. Andernfalls entstehen Befunde, die nur von der
# Nachlässigkeit des Generators zeugen und nicht von einem eingebauten Mangel.
from sapmdq.rules.validators import IBAN_LENGTHS, iban_valid, vat_id_valid

# Der Zufallsgenerator wird fest angesät: dieselbe Beispiellieferung soll bei
# jedem Aufruf entstehen, sonst wären die Tests nicht reproduzierbar.
SEED = 20260908

ORTE = [
    ("Berlin", "10115", "DE"), ("Hamburg", "20095", "DE"), ("München", "80331", "DE"),
    ("Köln", "50667", "DE"), ("Frankfurt", "60311", "DE"), ("Stuttgart", "70173", "DE"),
    ("Wien", "1010", "AT"), ("Salzburg", "5020", "AT"), ("Zürich", "8001", "CH"),
    ("Amsterdam", "1012 AB", "NL"), ("Paris", "75001", "FR"), ("Mailand", "20121", "IT"),
]
BRANCHEN = ["Handel", "Technik", "Logistik", "Bau", "Pharma", "Textil", "Metall", "Chemie"]

#: Namensbestandteile. Firmennamen werden aus zwei verschiedenen Stammwörtern
#: gebildet und ohne Zurücklegen gezogen. Zwei Namen, die sich nur in einer
#: laufenden Nummer unterscheiden, wären für den unscharfen Abgleich zu
#: ähnlich - die Dublettenerkennung meldete sie zu Recht, und die absichtlich
#: eingebauten Cluster gingen darin unter.
STAMMWOERTER = [
    "Baumann", "Kessler", "Lindner", "Hoffmann", "Wagner", "Brandt", "Ziegler",
    "Kaufmann", "Roth", "Sommer", "Winkler", "Faber", "Gerber", "Hartmann",
    "Krüger", "Lehmann", "Mayer", "Neumann", "Ostermann", "Pfeiffer", "Quandt",
    "Reinhardt", "Schuster", "Thiel", "Ulrich", "Vogel", "Wendt", "Zimmer",
    "Ahrens", "Bergmann", "Clausen", "Dietrich", "Engel", "Fischer", "Grabowski",
    "Huber", "Ingwer", "Jansen", "Köhler", "Lorenz", "Moser", "Nolte",
    "Petersen", "Richter", "Stein", "Voigt", "Werner", "Adler", "Busch",
    "Cordes", "Dohme", "Ehlers",
]
FORMEN = ["GmbH", "AG", "KG", "GmbH & Co. KG", "OHG", "e.K."]
STRASSEN = ["Hauptstrasse", "Bahnhofstrasse", "Industrieweg", "Am Markt", "Lindenallee"]

#: Positionstexte der Fakturen. Sie muessen nichts bedeuten - geprueft wird,
#: ob ueberhaupt einer da ist.
TEXTE = [
    "Vierkantrohr 40x40", "Dichtungssatz Typ B", "Montage vor Ort",
    "Kugellager 6203", "Frachtpauschale", "Wartung Jahrespauschale",
    "Kabeltrommel 50 m", "Schraubensortiment", "Beratungsleistung",
]

#: Stellenzahl der Bankleitzahl je Land, passend zum Aufbau der IBAN.
BANK_KEY_LENGTHS = {"DE": 8, "AT": 5, "CH": 5, "NL": 4, "FR": 5, "IT": 5}


def mod97(text: str) -> int:
    rest = 0
    for char in text:
        rest = (rest * 10 + int(char)) % 97 if char.isdigit() else (rest * 100 + ord(char) - 55) % 97
    return rest


def make_iban(country: str, rng: random.Random, bank_key: str = "") -> str:
    """Baut eine rechnerisch gültige IBAN in der Länge des Landes.

    Wo bekannt, wird die Bankleitzahl des Stammsatzes übernommen - sonst
    meldet die Regel VEN-FMT-005 zu Recht, dass IBAN und Bankschlüssel nicht
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
    """Erzeugt eine syntaktisch gültige USt-IdNr. des Landes.

    Erzeugt und geprüft wird gegen dieselbe Funktion, die später beurteilt -
    für Länder mit Prüfziffernverfahren durch Ausprobieren, was bei
    einstelligen Prüfziffern in wenigen Versuchen gelingt.
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
    """Deutsche USt-IdNr. mit gültiger Prüfziffer."""
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
    """Zieht paarweise verschiedene Firmennamen ohne Zurücklegen.

    Jeder Name trägt einen vierstelligen Zusatz, wie er in gewachsenen
    Stammdaten häufig vorkommt. Er ist hier kein Schmuck: ohne ihn
    unterscheiden sich zwei Namen aus dem Wortvorrat schnell nur in einem von
    drei Bestandteilen, was der unscharfe Abgleich zu Recht als mögliche
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
    """Zieht paarweise verschiedene Materialkurztexte ohne Zurücklegen.

    Die Bestandteile unterscheiden sich in ganzen Wörtern, nicht nur in einer
    Ziffer. Sonst lägen die Texte so nah beieinander, dass MAT-DUP-001 sie zu
    Recht als mögliche Dubletten meldet - was die absichtlich eingebaute
    Dublette unkenntlich machte.
    """
    gegenstaende = [
        "Schraube", "Blech", "Rohr", "Kabel", "Ventil", "Flansch", "Dichtung",
        "Lager", "Welle", "Zahnrad", "Feder", "Buchse", "Mutter", "Scheibe",
        "Winkel", "Träger", "Profil", "Platte", "Stange", "Kupplung",
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
    # Der Sachnummernzusatz ist in technischen Materialstämmen üblich und
    # sorgt zugleich dafür, dass sich zwei Kurztexte in mehr als einem von
    # drei Bestandteilen unterscheiden.
    return [
        f"{text} {rng.choice('ABCDEFGH')}{rng.randint(100, 999)}"
        for text in rng.sample(kombinationen, anzahl)
    ]


#: Feldlänge von NAME1 laut DDIC.
NAME1_LAENGE = 35


def kuerzbarer_name(basis: str, rechtsform: str) -> str:
    """Setzt Namen und Rechtsform zusammen, ohne die Feldlänge zu sprengen.

    Passt beides nicht, entfällt die Rechtsform. Ein hart abgeschnittener
    Name würde die Truncation-Prüfung der Vorstufe auslösen - völlig zu
    Recht, aber es wäre ein Mangel des Generators und keiner der Daten.
    """
    voll = f"{basis} {rechtsform}"
    if len(voll) <= NAME1_LAENGE:
        return voll
    return basis[:NAME1_LAENGE].rstrip()


def write_csv(path: Path, rows: list[dict], columns: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=columns, delimiter=";", extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow(row)



def fakturen(rng, mandant: str, kna1: list[dict], heute, defekte: list[str],
             schwergewichte: list[str] | None = None):
    """Erzeugt Fakturen zu den Debitoren - mit gezielt eingebauten Mängeln.

    Der Betrachtungszeitraum ist bewusst ein halbes Jahr: damit greift die
    Hochrechnung auf ein Jahr, und man sieht im Bericht, dass sie greift.

    Wichtiger als die Zahl der Belege ist ihre Verteilung. Ein Zehntel der
    Kunden bekommt das Zwölffache an Umsatz, und die in ``schwergewichte``
    genannten noch einmal deutlich mehr. Sie tragen zugleich einen
    Stammdatenmangel - erst dadurch weicht der Volumenanteil von der
    Partnerquote ab, und genau diese Abweichung ist der Grund, warum es die
    Belegsicht überhaupt gibt.
    """
    beginn = heute - timedelta(days=182)
    vbrk: list[dict] = []
    vbrp: list[dict] = []
    nummer = 90000000

    # Nur aktive Debitoren mit Anschrift bekommen Fakturen; ein zur Löschung
    # vorgemerkter Satz hat keine laufenden Umsaetze.
    kunden = [
        satz for satz in kna1
        if satz.get("LOEVM") != "X" and satz.get("XCPDK") != "X"
    ]
    grosskunden = {satz["KUNNR"] for satz in kunden[::10]}
    schwer = set(schwergewichte or [])

    def beleg(kunde: dict, positionen: list[dict], **kopf) -> dict:
        nonlocal nummer
        nummer += 1
        vbeln = f"{nummer}"
        netto = round(sum(p["NETWR"] for p in positionen), 2)
        steuer = round(sum(p["MWSBP"] for p in positionen), 2)
        satz = {
            "MANDT": mandant, "VBELN": vbeln, "FKART": "F2", "FKTYP": "L",
            "FKDAT": (beginn + timedelta(days=rng.randint(0, 182))).strftime("%Y%m%d"),
            "BUKRS": "1000", "VKORG": "1000",
            "KUNRG": kunde["KUNNR"], "KUNAG": kunde["KUNNR"],
            "WAERK": "EUR", "NETWR": netto, "MWSBK": steuer,
            "ZTERM": "ZB01", "SFAKN": "", "FKSTO": "",
            "LAND1": kunde.get("LAND1", "DE"), "STCEG": kunde.get("STCEG", ""),
        }
        satz.update(kopf)
        vbrk.append(satz)
        for lauf, position in enumerate(positionen, start=1):
            vbrp.append({
                "MANDT": mandant, "VBELN": vbeln, "POSNR": f"{lauf * 10:06d}",
                "MATNR": position.get("MATNR", f"{rng.randint(100000, 199999)}"),
                "ARKTX": position["ARKTX"],
                "FKIMG": position["FKIMG"], "VRKME": position.get("VRKME", "ST"),
                "NETWR": position["NETWR"], "MWSBP": position["MWSBP"],
                "MWSKZ": position.get("MWSKZ", "A1"),
                "WAERK": "EUR", "MATKL": "001", "WERKS": "1000",
            })
        return satz

    def position(wert: float, **felder) -> dict:
        kennzeichen = felder.get("MWSKZ", "A1")
        steuer = round(wert * 0.19, 2) if kennzeichen in ("A1", "XX") else 0.0
        satz = {
            "ARKTX": rng.choice(TEXTE), "FKIMG": rng.randint(1, 40),
            "NETWR": round(wert, 2), "MWSBP": steuer,
        }
        satz.update(felder)
        return satz

    # ------------------------------------------------- der normale Bestand
    for kunde in kunden:
        if kunde["KUNNR"] in schwer:
            anzahl, hebel = 7, 22
        elif kunde["KUNNR"] in grosskunden:
            anzahl, hebel = rng.randint(2, 5), 12
        else:
            anzahl, hebel = rng.randint(0, 3), 1
        for _ in range(anzahl):
            steuerkennzeichen = "A1" if kunde.get("LAND1") == "DE" else "A0"
            beleg(kunde, [
                position(rng.uniform(300, 4000) * hebel, MWSKZ=steuerkennzeichen)
                for _ in range(rng.randint(1, 3))
            ])

    if not vbrk:  # pragma: no cover - nur bei leerem Debitorenstamm
        return vbrk, vbrp

    def maengelkunden(anzahl: int) -> list[dict]:
        return rng.sample(kunden, min(anzahl, len(kunden)))

    # ------------------------------------------------- eingebaute Mängel
    ohne_datum = [beleg(k, [position(1200)], FKDAT=None) for k in maengelkunden(2)]
    defekte.append(
        "ERE-COMP-008: 2 Fakturen ohne Rechnungsdatum | betroffen: "
        + ", ".join(b["VBELN"] for b in ohne_datum)
    )

    fremdwaehrung = [beleg(k, [position(2500)], WAERK="DEM") for k in maengelkunden(3)]
    for satz in vbrp:
        if satz["VBELN"] in {b["VBELN"] for b in fremdwaehrung}:
            satz["WAERK"] = "DEM"
    defekte.append(
        "ERE-REF-006: 1 Belegwährung ohne ISO-Code (DEM) in 3 Fakturen | "
        "betroffen: " + ", ".join(b["VBELN"] for b in fremdwaehrung)
    )

    # Summenkonsistenz: der Kopf wird nach dem Schreiben verbogen.
    schief = [beleg(k, [position(900), position(1100)]) for k in maengelkunden(3)]
    for satz in schief:
        satz["NETWR"] = round(satz["NETWR"] + 25.5, 2)
    defekte.append(
        "ERE-CONS-003: 3 Fakturen, deren Positionssummen nicht den Kopfbetrag "
        "ergeben | betroffen: " + ", ".join(b["VBELN"] for b in schief)
    )

    gutschriften = [beleg(k, [position(-450)], FKART="G2") for k in maengelkunden(2)]
    defekte.append(
        "ERE-CONS-004: 2 Gutschriften ohne Bezug zum Ursprungsbeleg | "
        "betroffen: " + ", ".join(b["VBELN"] for b in gutschriften)
    )

    ohne_text = [beleg(k, [position(700, ARKTX=""), position(800)])
                 for k in maengelkunden(3)]
    defekte.append(
        "ERE-COMP-009: 3 Fakturen mit einer Position ohne Bezeichnung | "
        "betroffen: " + ", ".join(b["VBELN"] for b in ohne_text)
    )

    palette = [beleg(k, [position(1500, VRKME="PAL")]) for k in maengelkunden(4)]
    defekte.append(
        "ERE-REF-005: 1 Mengeneinheit ohne ISO-Code (PAL) in 4 Fakturen | "
        "betroffen: " + ", ".join(b["VBELN"] for b in palette)
    )

    nullposition = [beleg(k, [position(600), position(0, FKIMG=0, ARKTX="Naturalrabatt")])
                    for k in maengelkunden(3)]
    defekte.append(
        "ERE-CONS-005: 3 Fakturen mit einer Position ohne Menge und Wert | "
        "betroffen: " + ", ".join(b["VBELN"] for b in nullposition)
    )

    unzugeordnet = [beleg(k, [position(1800, MWSKZ="AX")]) for k in maengelkunden(2)]
    defekte.append(
        "ERE-REF-003: Kennzeichen AX in 2 Fakturen | betroffen: "
        + ", ".join(b["VBELN"] for b in unzugeordnet)
    )

    altkennzeichen = [beleg(k, [position(1400, MWSKZ="XX")]) for k in maengelkunden(2)]
    defekte.append(
        "ERE-REF-004: Kennzeichen XX in 2 Fakturen | betroffen: "
        + ", ".join(b["VBELN"] for b in altkennzeichen)
    )

    # Zwei Mengen, die nicht unter die Pflicht fallen. Sie sind kein Mangel,
    # sondern der Beleg dafuer, dass die Abgrenzung greift.
    klein = [beleg(k, [position(rng.uniform(40, 180))]) for k in maengelkunden(5)]
    defekte.append(
        "Abgrenzung: 5 Kleinbetragsrechnungen unter 250 Euro - kein Befund, "
        "sondern eine Ausschlussmenge | betroffen: "
        + ", ".join(b["VBELN"] for b in klein)
    )
    steuerfrei = [beleg(k, [position(3200, MWSKZ="AZ")]) for k in maengelkunden(4)]
    defekte.append(
        "Abgrenzung: 4 steuerfreie Umsätze (Kennzeichen AZ, Kategorie E) - "
        "kein Befund, sondern eine Ausschlussmenge | betroffen: "
        + ", ".join(b["VBELN"] for b in steuerfrei)
    )

    # Steuerbetrag trotz Nullsatz: die Position traegt A0, aber Steuer.
    widerspruch = [beleg(k, [position(2200, MWSKZ="A0")]) for k in maengelkunden(3)]
    fuer_widerspruch = {b["VBELN"] for b in widerspruch}
    for satz in vbrp:
        if satz["VBELN"] in fuer_widerspruch:
            satz["MWSBP"] = round(satz["NETWR"] * 0.19, 2)
    defekte.append(
        "ERE-CONS-002: 3 Fakturen mit Steuerbetrag trotz Nullsatz-Kennzeichen | "
        "betroffen: " + ", ".join(b["VBELN"] for b in widerspruch)
    )

    return vbrk, vbrp


def build(target: Path, vendor_count: int = 400) -> dict[str, int]:
    rng = random.Random(SEED)
    heute = date(2026, 1, 31)
    mandant = "100"

    lfa1: list[dict] = []
    lfb1: list[dict] = []
    lfm1: list[dict] = []
    lfbk: list[dict] = []

    # Ein einziger Namensvorrat für reguläre Kreditoren und Mangelfälle.
    # Zwei getrennte Ziehungen könnten dieselbe Namenskombination liefern -
    # und zwei Kreditoren mit gleichem Namensstamm sind für den unscharfen
    # Abgleich zu Recht eine mögliche Dublette.
    MANGELNAMEN_ANZAHL = 90
    namen = eindeutige_namen(rng, vendor_count + MANGELNAMEN_ANZAHL)

    def anschrift(vorgabe: str | None = None) -> tuple[str, str, str, str]:
        """Erzeugt eine Anschrift mit landesüblicher Postleitzahl.

        Die Postleitzahl wird gestreut und nicht aus einer kurzen Liste
        gezogen: sie ist der Blockschlüssel der Dublettenerkennung. Trägen
        hunderte Kreditoren dieselbe Postleitzahl, landen sie alle im selben
        Block, und ähnliche Namen an vermeintlich gleicher Anschrift werden
        zu Recht als mögliche Dubletten gemeldet.

        Mit ``vorgabe`` lässt sich das Land festlegen. Das ist nötig, wenn
        ein Mangelfall ein bestimmtes Land braucht: sonst trägt der Satz eine
        österreichische Postleitzahl bei deutschem Länderschlüssel und
        löst einen Formatbefund aus, der gar nicht eingebaut war.
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

    # ------------------------------------------------ reguläre Kreditoren
    for index in range(1, vendor_count + 1):
        lifnr = f"{100000 + index}"
        strasse, plz, ort, land = anschrift()
        # Der Name muss in NAME1 passen (35 Zeichen laut DDIC). Statt zu
        # kürzen entfällt die Rechtsform, wenn es sonst nicht reicht -
        # abgeschnittene Namen würden die Truncation-Prüfung auslösen, und
        # zwar zu Recht.
        name = kuerzbarer_name(namen[index - 1], rng.choice(FORMEN))
        angelegt = heute - timedelta(days=rng.randint(30, 2600))

        # Zahlungsbedingung gilt für beide Sichten gleich - abweichende Werte
        # sind ein eigener Mangel (VEN-CONS-006) und kein Grundrauschen.
        zahlungsbedingung = rng.choice(["ZB01", "ZB02", "ZB03"])
        bankland = land if land in IBAN_LENGTHS else "DE"
        # Die Bankleitzahl muss die Länge haben, die das Land in der IBAN
        # vorsieht - sonst meldet VEN-FMT-005 für jeden ausländischen
        # Kreditor eine Abweichung, die nur der Generator verursacht hat.
        stellen = BANK_KEY_LENGTHS.get(bankland, 8)
        bankleitzahl = "".join(str(rng.randint(0, 9)) for _ in range(stellen))

        lfa1.append({
            "MANDT": mandant, "LIFNR": lifnr, "NAME1": name, "LAND1": land,
            "ORT01": ort, "PSTLZ": plz, "STRAS": strasse, "PFACH": "",
            "KTOKK": "KRED", "ERDAT": angelegt.strftime("%Y%m%d"),
            "ERNAM": f"USER{rng.randint(1, 12):02d}",
            "STCEG": make_vat(land, rng),
            # Länder ohne USt-IdNr. tragen wenigstens eine Steuernummer,
            # sonst meldet VEN-COMP-004 für jeden Schweizer Kreditor.
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
    # Namen für die Mangelfälle aus dem hinteren Teil desselben Vorrats. Ein
    # sprechender Name wie "Adresslos GmbH" wäre bequem zu lesen, aber
    # unbrauchbar: alle Sätze einer Mangelgruppe trägen dann einen langen
    # gemeinsamen Namensbestandteil, und die Dublettenerkennung meldete sie
    # völlig zu Recht als Cluster. Welcher Satz welchen Mangel trägt, steht
    # stattdessen in EINGEBAUTE_MAENGEL.md.
    mangelnamen = namen[vendor_count:][::-1]

    def gruppe(beschreibung: str, saetze: list[dict]) -> None:
        """Vermerkt eine Mangelgruppe samt der betroffenen Kreditorennummern."""
        schluessel = ", ".join(satz["LIFNR"] for satz in saetze[:8])
        weiter = " ..." if len(saetze) > 8 else ""
        defekte.append(f"{beschreibung} | betroffen: {schluessel}{weiter}")

    def neuer_kreditor(eindeutig: bool = True, **felder) -> dict:
        """Legt einen Kreditor mit einem gezielt eingebauten Mangel an.

        ``eindeutig`` hängt an den Namen einen unterscheidungskräftigen
        Zusatz. Ohne ihn trägen alle Sätze einer Mangelgruppe denselben
        Namen und die Dublettenerkennung meldet sie völlig zu Recht als
        Cluster - was den einen absichtlich eingebauten Dublettenfall
        unkenntlich machte.
        """
        nonlocal naechste
        naechste += 1
        lifnr = f"{100000 + naechste}"
        strasse, plz, ort, land = anschrift(felder.get("LAND1"))
        if eindeutig:
            felder = dict(felder)
            felder["NAME1"] = kuerzbarer_name(mangelnamen.pop(), rng.choice(FORMEN))
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

    # ------------------------------------------------ eingebaute Mängel
    # VEN-COMP-001: EU-Kreditor ohne USt-IdNr.
    gruppe(
        "VEN-COMP-001 und VEN-COMP-004: 6 EU-Kreditoren ohne USt-IdNr. und ohne Steuernummer",
        [neuer_kreditor(LAND1="DE", STCEG="", STCD1="") for _ in range(6)],
    )

    # VEN-FMT-001: USt-IdNr. mit falscher Prüfziffer.
    #
    # Jeder Satz bekommt eine andere falsche Nummer. Trägen alle vier dieselbe,
    # meldet VEN-DUP-001 sie nebenher als Dublettencluster - völlig zu Recht,
    # aber es steht dann ein unbenanntes Cluster im Bericht, das die
    # absichtlich eingebauten Dubletten verwässert.
    falsche_ustid = [f"DE1111111{ziffer}1" for ziffer in range(4)]
    gruppe(
        "VEN-FMT-001: 4 Kreditoren mit falscher USt-IdNr.-Prüfziffer",
        [neuer_kreditor(LAND1="DE", STCEG=nummer) for nummer in falsche_ustid],
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

    # VEN-CONS-007: natürliche Person mit Rechtsform im Namen
    gruppe(
        "VEN-CONS-007: 3 Kreditoren als natürliche Person mit Rechtsform im Namen",
        [neuer_kreditor(STKZN="X") for _ in range(3)],
    )

    # VEN-DUP-003: Namensdubletten mit Schreibvarianten
    dubletten = [
        ("Mueller & Sohn GmbH", "Hauptstrasse 12", "10115", "Berlin"),
        ("Müller und Sohn G.m.b.H.", "Hauptstr. 12", "10115", "Berlin"),
        ("MUELLER U SOHN GMBH", "Haupt-Straße 12", "10115", "Berlin"),
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

    # VEN-LC-001: Löschvormerkung ohne Archivierung
    gruppe(
        "VEN-LC-001: 7 Kreditoren mit alter Löschvormerkung ohne Archivierung",
        [
            neuer_kreditor(
                LOEVM="X", ERDAT=(heute - timedelta(days=1500)).strftime("%Y%m%d")
            )
            for _ in range(7)
        ],
    )

    # Kreditoren, denen anschließend die Buchungskreissicht entzogen wird.
    ohne_buchungskreis = [neuer_kreditor() for _ in range(4)]

    # Buchungskreis-, Einkaufs- und Bankdaten für die Mangelfälle ergänzen.
    # Ohne sie meldeten Regeln wie VEN-COMP-005 oder VEN-COMP-008 für jeden
    # eingebauten Mangelfall zusätzlich eine fehlende Sicht.
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
    defekte.append("VEN-COMP-006: 5 Buchungskreissätze ohne Abstimmkonto")

    # VEN-COMP-007: ohne Zahlungsbedingung
    for satz in lfb1[5:11]:
        satz["ZTERM"] = ""
    defekte.append("VEN-COMP-007: 6 Buchungskreissätze ohne Zahlungsbedingung")

    # VEN-REF-003: Zahlungsbedingung, die es im Customizing nicht gibt
    for satz in lfb1[11:15]:
        satz["ZTERM"] = "ZZ99"
    defekte.append("VEN-REF-003: 4 Verweise auf unbekannte Zahlungsbedingung")

    # VEN-COMP-005: Kreditoren ganz ohne Buchungskreissicht. Die Sätze werden
    # ausdrücklich dafür angelegt: nähme man die zuletzt entstandenen, wären
    # es die zur Löschung vorgemerkten, und die Regel schließt diese zu Recht
    # aus - der Mangel entstünde gar nicht.
    ohne_bukrs = {satz["LIFNR"] for satz in ohne_buchungskreis}
    lfb1 = [satz for satz in lfb1 if satz["LIFNR"] not in ohne_bukrs]
    gruppe(
        "VEN-COMP-005: 4 Kreditoren ohne Buchungskreisdaten", ohne_buchungskreis
    )

    # VEN-FMT-003: ungültige IBAN
    for satz in lfbk[:5]:
        satz["IBAN"] = satz["IBAN"][:-1] + ("0" if satz["IBAN"][-1] != "0" else "1")
    defekte.append("VEN-FMT-003: 5 ungültige IBAN")

    # VEN-FMT-004: IBAN-Land weicht vom Bankland ab. Das Bankland wird
    # ausdrücklich auf ein anderes Land als das der IBAN gesetzt - ein fest
    # gewählter Wert träfe sonst gelegentlich das Land der IBAN und der
    # Mangel entstünde gar nicht.
    for satz in lfbk[5:8]:
        satz["BANKS"] = "IT" if satz["IBAN"][:2] != "IT" else "PL"
    defekte.append("VEN-FMT-004: 3 Bankverbindungen mit abweichendem Bankland")

    # VEN-DUP-002: gleiche Bankverbindung bei zwei Kreditoren. Übernommen wird
    # die vollständige Verbindung: kopierte man nur die IBAN, passten Bankland
    # und Bankschlüssel nicht mehr dazu und es entstünden nebenher zwei
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

    # MAT-FMT-001: EAN mit falscher Prüfziffer
    for satz in mara[13:17]:
        satz["EAN11"] = "4006381333930"
    defekte.append("MAT-FMT-001: 4 Materialien mit falscher EAN-Prüfziffer")

    # MAT-COMP-001: Material ohne Kurztext
    ohne_text = {satz["MATNR"] for satz in mara[17:21]}
    makt = [satz for satz in makt if satz["MATNR"] not in ohne_text]
    defekte.append("MAT-COMP-001: 4 Materialien ohne Kurztext")

    # MAT-DUP-001: doppelte Kurzbezeichnung
    if len(makt) > 30:
        makt[30]["MAKTX"] = makt[29]["MAKTX"]
        defekte.append("MAT-DUP-001: 1 Cluster mit doppelter Materialkurzbezeichnung")

    # ======================================================== Debitoren
    #
    # Der Debitorenstamm trägt dieselben Mangelarten wie der Kreditorenstamm,
    # dazu die Dublettenfälle als Schaustück: derselbe Kunde mehrfach
    # angelegt, einmal über Schreibvarianten erkennbar und einmal nur über
    # die USt-IdNr. Dazu ein Gegenbeispiel, das nicht gemeldet werden darf.
    kna1: list[dict] = []
    knb1: list[dict] = []
    knbk: list[dict] = []
    knvv: list[dict] = []
    #: Zentrale Adressverwaltung: E-Mail-Adressen (ADR6) und Anschriften
    #: (ADRC). Beide braucht die E-Rechnungsprüfung.
    adr6: list[dict] = []
    adrc: list[dict] = []

    customer_count = max(120, vendor_count // 3)
    KUNDEN_MANGELNAMEN = 70
    kundennamen = eindeutige_namen(rng, customer_count + KUNDEN_MANGELNAMEN)

    def debitor_saetze(kunnr: str, felder: dict, mit_buchungskreis: bool = True,
                       mit_bank: bool = True, mit_vertrieb: bool = True) -> dict:
        """Legt einen Debitor in allen vier Sichten an."""
        land = felder.get("LAND1", "DE")
        angelegt = felder.pop("_erdat", None) or (
            heute - timedelta(days=rng.randint(30, 2600))
        )
        allgemein = {
            "MANDT": mandant, "KUNNR": kunnr, "NAME1": "", "NAME2": "",
            "LAND1": land, "ORT01": "", "PSTLZ": "", "STRAS": "", "PFACH": "",
            "KTOKD": "KUNA", "ERDAT": angelegt.strftime("%Y%m%d"),
            "ERNAM": f"USER{rng.randint(1, 12):02d}",
            "STCEG": make_vat(land, rng),
            "STCD1": "" if land in ("DE", "AT", "NL", "FR", "IT") else f"{rng.randint(100000000, 999999999)}",
            "LOEVM": "", "SPERR": "", "AUFSD": "", "LIFSD": "", "FAKSD": "",
            "XCPDK": "", "STKZN": "", "ADRNR": f"{500000 + int(kunnr)}", "TELF1": "",
        }
        ohne_email = allgemein.pop("_ohne_email", False) or felder.pop("_ohne_email", False)
        allgemein.update(felder)
        kna1.append(allgemein)

        # Die E-Mail-Adresse steht in SAP nicht am Stammsatz, sondern in der
        # zentralen Adressverwaltung. Ohne sie gibt es keinen Weg, eine
        # E-Rechnung zuzustellen - deshalb ist sie hier die Vorgabe und ihr
        # Fehlen der gezielt eingebaute Mangel.
        if not ohne_email and allgemein["ADRNR"]:
            adr6.append({
                "CLIENT": mandant, "ADDRNUMBER": allgemein["ADRNR"],
                "PERSNUMBER": "", "CONSNUMBER": "001",
                "SMTP_ADDR": f"rechnung{kunnr}@example.invalid", "FLGDEFAULT": "X",
            })

        if mit_buchungskreis:
            knb1.append({
                "MANDT": mandant, "KUNNR": kunnr, "BUKRS": "1000",
                "AKONT": "0000140000", "ZTERM": rng.choice(["ZB01", "ZB02", "ZB03"]),
                "ZWELS": "U", "ZAHLS": "",
                "LOEVM": allgemein["LOEVM"], "SPERR": "",
                "ERDAT": angelegt.strftime("%Y%m%d"),
            })
        if mit_bank:
            bankland = land if land in IBAN_LENGTHS else "DE"
            bankleitzahl = "".join(
                str(rng.randint(0, 9)) for _ in range(BANK_KEY_LENGTHS.get(bankland, 8))
            )
            knbk.append({
                "MANDT": mandant, "KUNNR": kunnr, "BANKS": bankland,
                "BANKL": bankleitzahl,
                "BANKN": f"{rng.randint(1000000000, 9999999999)}",
                "IBAN": make_iban(bankland, rng, bankleitzahl),
                "BKONT": "", "KOINH": "",
            })
        if mit_vertrieb:
            knvv.append({
                "MANDT": mandant, "KUNNR": kunnr, "VKORG": "1000",
                "VTWEG": "10", "SPART": "00", "LOEVM": "",
            })
        return allgemein

    # ------------------------------------------------- reguläre Debitoren
    for index in range(1, customer_count + 1):
        strasse, plz, ort, land = anschrift()
        debitor_saetze(
            f"{200000 + index}",
            {
                "NAME1": kuerzbarer_name(kundennamen[index - 1], rng.choice(FORMEN)),
                "LAND1": land, "ORT01": ort, "PSTLZ": plz, "STRAS": strasse,
            },
        )

    kundenmangelnamen = kundennamen[customer_count:][::-1]
    naechster_kunde = customer_count

    def neuer_debitor(eindeutig: bool = True, **felder) -> dict:
        """Legt einen Debitor mit einem gezielt eingebauten Mangel an.

        Wie bei den Kreditoren trägt der Name einen unterscheidungskräftigen
        Zusatz, damit die Sätze einer Mangelgruppe nicht selbst als Cluster
        gemeldet werden und die eingebauten Dubletten darin untergehen.
        """
        nonlocal naechster_kunde
        naechster_kunde += 1
        kunnr = f"{200000 + naechster_kunde}"
        strasse, plz, ort, land = anschrift(felder.get("LAND1"))
        vorgabe = {
            "NAME1": kuerzbarer_name(
                kundenmangelnamen[naechster_kunde % len(kundenmangelnamen)],
                rng.choice(FORMEN),
            ) if eindeutig else "",
            "LAND1": land, "ORT01": ort, "PSTLZ": plz, "STRAS": strasse,
        }
        vorgabe.update(felder)
        return debitor_saetze(
            kunnr, vorgabe,
            mit_buchungskreis=felder.pop("_mit_buchungskreis", True),
            mit_bank=felder.pop("_mit_bank", True),
            mit_vertrieb=felder.pop("_mit_vertrieb", True),
        )

    def kundengruppe(beschreibung: str, saetze: list[dict]) -> None:
        schluessel = ", ".join(satz["KUNNR"] for satz in saetze[:8])
        weiter = " ..." if len(saetze) > 8 else ""
        defekte.append(f"{beschreibung} | betroffen: {schluessel}{weiter}")

    # ------------------------------------------- Dubletten als Schaustück
    #
    # Fall 1: derselbe Kunde dreimal, erkennbar allein am Namen. Umlaut,
    # ausgeschriebene und abgekürzte Rechtsform, Bindestrich - für den
    # Menschen offensichtlich, für einen Gleichheitsvergleich unsichtbar.
    schreibvarianten = [
        ("Nordwind Handels GmbH", "Seeweg 8"),
        ("NORDWIND HANDELS G.M.B.H.", "Seeweg 8"),
        ("Nordwind Handels-Ges. mbH", "See-Weg 8"),
    ]
    kundengruppe(
        "CUS-DUP-002: 1 Cluster aus 3 Schreibvarianten desselben Kunden",
        [
            neuer_debitor(eindeutig=False, NAME1=name, STRAS=strasse,
                          PSTLZ="24103", ORT01="Kiel", LAND1="DE")
            for name, strasse in schreibvarianten
        ],
    )

    # Vierte Variante desselben Kunden, an derselben Anschrift - und dennoch
    # nicht gefunden: "Handelsgesellschaft" in einem Wort erreicht gegen
    # "Handels GmbH" nur 73 von 100, und auch die gleiche Adresse hebt den
    # zusammengesetzten Wert nur auf 82 - unter der Schwelle von 85.
    #
    # Der Fall steht hier absichtlich. Ein unscharfer Abgleich, der zusammen-
    # gesetzte Wörter zerlegte, fände ihn - und meldete dafür jede
    # "Handelsgesellschaft" als mögliche Dublette jeder anderen. Wer das
    # Werkzeug vorführt, sollte diese Grenze kennen und nennen können.
    nicht_gefunden = neuer_debitor(
        eindeutig=False, NAME1="Nordwind Handelsgesellschaft mbH",
        STRAS="Seeweg 8", PSTLZ="24103", ORT01="Kiel", LAND1="DE",
    )
    defekte.append(
        "GRENZFALL (wird bewusst NICHT gefunden): 4. Schreibvariante desselben "
        "Kunden, Rechtsform mit dem Namen zu einem Wort verschmolzen "
        f"(\"Handelsgesellschaft\") | betroffen: {nicht_gefunden['KUNNR']}"
    )

    # Fall 2: ein Paar mit Umlautvariante und abweichender Rechtsformschreibung.
    kundengruppe(
        "CUS-DUP-002: 1 Cluster aus 2 Schreibvarianten (Umlaut, Rechtsform)",
        [
            neuer_debitor(eindeutig=False, NAME1=name, STRAS="Lindenallee 44",
                          PSTLZ="04109", ORT01="Leipzig", LAND1="DE")
            for name in ("Baeckerei Kruse e.K.", "Bäckerei Kruse eK")
        ],
    )

    # Fall 3: derselbe Kunde unter völlig verschiedenem Namen an einer anderen
    # Anschrift. Der unscharfe Abgleich hat hier keine Chance - nur die
    # gemeinsame USt-IdNr. beweist die Dublette. Genau dafür gibt es zwei
    # getrennte Regeln.
    geteilte_kunden_ustid = make_vat("DE", rng)
    kundengruppe(
        "CUS-DUP-001: 2 Debitoren mit gleicher USt-IdNr., ohne Namensähnlichkeit",
        [
            neuer_debitor(eindeutig=False, NAME1="Alpenland Vertrieb GmbH",
                          STRAS="Bergweg 3", PSTLZ="83022", ORT01="Rosenheim",
                          LAND1="DE", STCEG=geteilte_kunden_ustid),
            neuer_debitor(eindeutig=False, NAME1="Südstern Distribution AG",
                          STRAS="Hafenstrasse 19", PSTLZ="18055", ORT01="Rostock",
                          LAND1="DE", STCEG=geteilte_kunden_ustid),
        ],
    )

    # Gegenbeispiel: zwei verschiedene Unternehmen mit gleichem Namensstamm in
    # derselben Straße. Verschiedene Hausnummer, verschiedene USt-IdNr.,
    # verschiedenes Geschäft. Diese beiden dürfen nicht gemeldet werden -
    # sonst wäre die Dublettenerkennung im Kundentermin nicht vorzeigbar.
    gegenbeispiel = [
        neuer_debitor(eindeutig=False, NAME1="Weber Metallbau GmbH",
                      STRAS="Industriering 7", PSTLZ="70565", ORT01="Stuttgart",
                      LAND1="DE"),
        neuer_debitor(eindeutig=False, NAME1="Weber Kunststoff GmbH",
                      STRAS="Industriering 9", PSTLZ="70565", ORT01="Stuttgart",
                      LAND1="DE"),
    ]
    defekte.append(
        "GEGENBEISPIEL (darf NICHT gemeldet werden): 2 verschiedene Unternehmen "
        "mit gleichem Namensstamm in derselben Straße | betroffen: "
        + ", ".join(satz["KUNNR"] for satz in gegenbeispiel)
    )

    # --------------------------------------------- übrige Debitorenmängel
    kundengruppe(
        "CUS-COMP-001: 5 Debitoren ohne USt-IdNr.",
        [neuer_debitor(LAND1="DE", STCEG="") for _ in range(5)],
    )
    kundengruppe(
        "CUS-COMP-002: 3 Debitoren ohne Ort oder Postleitzahl (im Inland, "
        "damit sie auch in der E-Rechnungsprüfung erscheinen)",
        [neuer_debitor(LAND1="DE", PSTLZ="") for _ in range(2)]
        + [neuer_debitor(LAND1="DE", ORT01="")],
    )
    kundengruppe(
        "CUS-FMT-001: 4 Debitoren mit ungültiger USt-IdNr.",
        [neuer_debitor(LAND1="DE", STCEG=f"DE{rng.randint(100000000, 999999999)}")
         for _ in range(4)],
    )
    kundengruppe(
        "CUS-FMT-002: 3 Debitoren mit Postleitzahl, die nicht zum Land passt",
        [neuer_debitor(LAND1="DE", PSTLZ="123") for _ in range(3)],
    )
    kundengruppe(
        "CUS-CONS-004: 2 Debitoren mit USt-IdNr. eines anderen Landes",
        [neuer_debitor(LAND1="DE", STCEG=make_vat("AT", rng)) for _ in range(2)],
    )
    kundengruppe(
        "CUS-CONS-005: 3 Debitoren mit Vertriebssperre, Buchungskreis offen",
        [neuer_debitor(AUFSD="01") for _ in range(3)],
    )
    kundengruppe(
        "CUS-RISK-001: 3 Debitoren mit reiner Postfachanschrift",
        [neuer_debitor(LAND1="DE", STRAS="", PFACH=f"{rng.randint(1000, 9999)}")
         for _ in range(3)],
    )
    kundengruppe(
        "CUS-LC-001: 4 Debitoren mit alter Löschvormerkung ohne Archivierung",
        [neuer_debitor(LOEVM="X", _erdat=heute - timedelta(days=1500))
         for _ in range(4)],
    )
    kundengruppe(
        "CUS-CONS-003: 3 Debitoren zentral zur Löschung vorgemerkt, im "
        "Buchungskreis aber nicht",
        # Das Anlagedatum ist festgelegt: die drei Sätze zählen auch für
        # CUS-LC-001 mit, und diese Zahl soll nicht davon abhängen, welches
        # Datum der Zufallsgenerator gerade zieht.
        [neuer_debitor(LOEVM="X", _erdat=heute - timedelta(days=1200))
         for _ in range(3)],
    )
    # Der Buchungskreis der drei Sätze muss offen bleiben, sonst ist es kein
    # Widerspruch mehr. debitor_saetze übernimmt LOEVM - hier zurücksetzen.
    for satz in knb1[-3:]:
        satz["LOEVM"] = ""

    # Buchungskreis- und Vertriebsdaten ohne allgemeine Daten: die Sätze
    # entstehen ohne KNA1-Eintrag und müssen deshalb von Hand angelegt werden.
    for lauf in range(2):
        naechster_kunde += 1
        verwaist = f"{200000 + naechster_kunde}"
        knb1.append({
            "MANDT": mandant, "KUNNR": verwaist, "BUKRS": "1000",
            "AKONT": "0000140000", "ZTERM": "ZB01", "ZWELS": "U", "ZAHLS": "",
            "LOEVM": "", "SPERR": "", "ERDAT": heute.strftime("%Y%m%d"),
        })
    defekte.append(
        "CUS-CONS-001: 2 Buchungskreisdatensätze ohne allgemeine Daten | betroffen: "
        f"{knb1[-2]['KUNNR']}, {knb1[-1]['KUNNR']}"
    )

    naechster_kunde += 1
    verwaister_vertrieb = f"{200000 + naechster_kunde}"
    knvv.append({"MANDT": mandant, "KUNNR": verwaister_vertrieb, "VKORG": "1000",
                 "VTWEG": "10", "SPART": "00", "LOEVM": ""})
    defekte.append(
        "CUS-CONS-002: 1 Vertriebsbereichsdatensatz ohne allgemeine Daten | "
        f"betroffen: {verwaister_vertrieb}"
    )

    # CUS-COMP-004 und CUS-COMP-005: Buchungskreisdaten ohne Abstimmkonto
    # beziehungsweise ohne Zahlungsbedingung.
    for satz in knb1[3:6]:
        satz["AKONT"] = ""
    defekte.append(
        "CUS-COMP-004: 3 Buchungskreisdatensätze ohne Abstimmkonto | betroffen: "
        + ", ".join(satz["KUNNR"] for satz in knb1[3:6])
    )
    ohne_zahlungsbedingung = [neuer_debitor(LAND1="DE") for _ in range(3)]
    for satz in knb1[-3:]:
        satz["ZTERM"] = ""
    defekte.append(
        "CUS-COMP-005: 3 Buchungskreisdatensätze ohne Zahlungsbedingung | betroffen: "
        + ", ".join(satz["KUNNR"] for satz in ohne_zahlungsbedingung)
    )

    # CUS-REF-001: Abstimmkonto, das es im Buchungskreis nicht gibt.
    knb1[12]["AKONT"] = "0000149999"
    defekte.append(
        f"CUS-REF-001: 1 Buchungskreisdatensatz mit unbekanntem Abstimmkonto | "
        f"betroffen: {knb1[12]['KUNNR']}"
    )

    # CUS-FMT-003: ungültige IBAN in den Bankdaten des Debitors.
    for satz in knbk[2:5]:
        satz["IBAN"] = satz["IBAN"][:-1] + ("0" if satz["IBAN"][-1] != "0" else "1")
    defekte.append(
        "CUS-FMT-003: 3 Debitoren mit ungültiger IBAN | betroffen: "
        + ", ".join(satz["KUNNR"] for satz in knbk[2:5])
    )

    # CUS-COMP-003: Debitor ohne Buchungskreisdaten.
    kundengruppe(
        "CUS-COMP-003: 3 Debitoren ohne Buchungskreisdaten",
        [neuer_debitor(_mit_buchungskreis=False) for _ in range(3)],
    )

    # CUS-REF-005: Vertriebsbereichsdaten mit unbekannter Verkaufsorganisation.
    knvv[5]["VKORG"] = "9999"
    defekte.append(
        f"CUS-REF-005: 1 Vertriebsbereich mit unbekannter Verkaufsorganisation | "
        f"betroffen: {knvv[5]['KUNNR']}"
    )

    # ------------------------------------- Mängel der E-Rechnungs-Readiness
    #
    # Sie hängen nicht am Stammsatz an sich, sondern daran, ob aus ihm eine
    # Rechnung nach EN 16931 erzeugt werden kann. Die Beispiellieferung
    # enthält für jede Regel einen Fall - und dazu die Mengen, die
    # ausgeschlossen gehören.

    ohne_email = [neuer_debitor(LAND1="DE", _ohne_email=True) for _ in range(4)]
    kundengruppe(
        "ERE-COMP-005: 4 Debitoren ohne E-Mail-Adresse in der Adressverwaltung",
        ohne_email,
    )
    kundengruppe(
        "ERE-COMP-004: 3 Debitoren ohne Straße - für die E-Rechnung eine "
        "Pflichtangabe, im Papierprozess bisher unauffällig",
        [neuer_debitor(LAND1="DE", STRAS="") for _ in range(3)],
    )
    # Steuernummer statt USt-IdNr.: die allgemeine Stammdatenregel meldet das,
    # die E-Rechnungsregel nicht - die Norm lässt die Steuernummer zu. Der
    # Fall zeigt den Unterschied zwischen beiden Sichten.
    kundengruppe(
        "CUS-COMP-001 ohne ERE-COMP-003: 2 Debitoren ohne USt-IdNr., aber mit "
        "Steuernummer",
        [neuer_debitor(LAND1="DE", STCEG="", STCD1=f"151/815/{nummer:05d}")
         for nummer in (30001, 30002)],
    )
    # Privatkunden: sie fallen nicht unter die B2B-Pflicht und werden über die
    # Kontengruppe ausgeschlossen. Ohne diese Abgrenzung stünden sie als
    # Befund in der Liste und die Quote wäre unbrauchbar.
    kundengruppe(
        "Abgrenzung: 6 Privatkunden (Kontengruppe PRIV) - kein Befund, sondern "
        "eine Ausschlussmenge",
        [neuer_debitor(LAND1="DE", KTOKD="PRIV", STKZN="X", STCEG="", STCD1="")
         for _ in range(6)],
    )
    # Einmalkunden: Stammdaten naturgemäß leer, prüfbar erst am Beleg.
    kundengruppe(
        "Abgrenzung: 2 Einmalkunden (CpD) - kein Befund, sondern eine "
        "Ausschlussmenge",
        [neuer_debitor(LAND1="DE", KTOKD="CPD", XCPDK="X", STCEG="") for _ in range(2)],
    )
    # Ein Länderschlüssel ohne ISO-Code: ein Customizing-Mangel, der jede
    # Rechnung an diese Kunden an einer Pflichtangabe scheitern lässt.
    kundengruppe(
        "ERE-REF-001: 2 Debitoren mit Länderschlüssel 'EN' ohne ISO-Code",
        [neuer_debitor(LAND1="EN", STCEG="", STCD1=f"GB12345678{ziffer}",
                       ORT01="London", PSTLZ="EC1A 1BB",
                       STRAS=f"Fleet Street {ziffer}")
         for ziffer in (1, 2)],
    )

    # Zahlungsbedingungen: eine ohne ableitbares Datum, eine mit zweistufiger
    # Skontostaffel. Beide werden über eigene Debitoren in Umlauf gebracht.
    ere_zahlung = [neuer_debitor(LAND1="DE") for _ in range(2)]
    knb1[-2]["ZTERM"] = "ZB99"
    knb1[-1]["ZTERM"] = "ZB04"
    defekte.append(
        "ERE-REF-002: 1 Zahlungsbedingung ohne ableitbares Fälligkeitsdatum "
        f"(ZB99) | betroffen: {ere_zahlung[0]['KUNNR']}"
    )
    defekte.append(
        "ERE-CONS-001: 1 Zahlungsbedingung mit zweistufiger Skontostaffel "
        f"(ZB04) | betroffen: {ere_zahlung[1]['KUNNR']}"
    )

    # ------------------------------------------------------ Customizing
    #
    # Der eigene Buchungskreis ist bewusst nicht in Ordnung: ohne USt-IdNr.
    # und ohne Straße in der zugeordneten Adresse lässt sich keine einzige
    # normkonforme Rechnung erzeugen, wie gut die Debitoren auch gepflegt
    # sind. Im Kundentermin ist das erfahrungsgemäß der erste Befund.
    t001 = [{"MANDT": mandant, "BUKRS": "1000", "BUTXT": "Musterwerk AG",
             "LAND1": "DE", "WAERS": "EUR", "KTOPL": "INT",
             "STCEG": "", "ADRNR": "0000009000"}]
    defekte.append(
        "ERE-COMP-001: 1 Buchungskreis ohne USt-IdNr. | betroffen: 1000"
    )
    adrc.append({
        "CLIENT": mandant, "ADDRNUMBER": "0000009000", "DATE_FROM": "19000101",
        "NATION": "", "NAME1": "Musterwerk AG", "STREET": "", "HOUSE_NUM1": "",
        "POST_CODE1": "12345", "CITY1": "Musterstadt", "COUNTRY": "DE",
    })
    defekte.append(
        "ERE-COMP-002: 1 Buchungskreis mit unvollständiger Anschrift "
        "(Straße fehlt) | betroffen: 1000"
    )
    def zahlungsbedingung(zterm, tag1=0, prz1=0, tag2=0, prz2=0, tag3=0, faell=0):
        """Ein T052-Satz mit allen Spalten.

        Alle Sätze brauchen dieselben Schlüssel: write_csv bildet die
        Kopfzeile aus der ersten Zeile, und ein später ergänztes Feld fiele
        sonst still unter den Tisch.
        """
        return {"MANDT": mandant, "ZTERM": zterm, "ZTAGG": "00",
                "ZTAG1": tag1, "ZPRZ1": prz1, "ZTAG2": tag2, "ZPRZ2": prz2,
                "ZTAG3": tag3, "ZFAEL": faell, "ZMONA": 0}

    t052 = [zahlungsbedingung(z, tag1=t) for z, t in
            (("ZB01", 30), ("ZB02", 14), ("ZB03", 60))]
    # ZB99 löst sich in kein Datum auf, ZB04 trägt eine zweistufige Staffel.
    t052.append(zahlungsbedingung("ZB99"))
    t052.append(zahlungsbedingung("ZB04", tag1=14, prz1=2.0, tag2=30, prz2=1.0, tag3=60))
    # Zahlwege für jedes vorkommende Land - sonst meldet VEN-REF-004 für
    # jeden ausländischen Kreditor eine Lücke im Customizing.
    t042z = [
        {"MANDT": mandant, "LAND1": land, "ZLSCH": z, "TEXT1": t}
        for land in ("DE", "AT", "CH", "NL", "FR", "IT")
        for z, t in (("U", "Überweisung"), ("S", "Scheck"))
    ]
    t005 = [{"MANDT": mandant, "LAND1": land, "INTCA": land,
             "XEGLD": "X" if land in ("DE", "AT", "NL", "FR", "IT") else ""}
            for land in ("DE", "AT", "CH", "NL", "FR", "IT")]
    # Altschlüssel ohne gepflegten ISO-Code - in gewachsenen Systemen ein
    # häufiger Fund, für die E-Rechnung ein Ausfall.
    t005.append({"MANDT": mandant, "LAND1": "EN", "INTCA": "", "XEGLD": ""})
    defekte.append(
        "ERE-REF-001: 1 Länderschlüssel ohne ISO-Code | betroffen: EN"
    )
    t077k = [{"MANDT": mandant, "KTOKK": "KRED", "NUMKR": "01"}]
    t077d = [{"MANDT": mandant, "KTOKD": k, "NUMKR": n}
             for k, n in (("KUNA", "02"), ("PRIV", "03"), ("CPD", "04"))]
    tvko = [{"MANDT": mandant, "VKORG": "1000", "VTEXT": "Vertrieb Inland",
             "BUKRS": "1000", "WAERS": "EUR"}]
    t134 = [{"MANDT": mandant, "MTART": a, "KKREF": k} for a, k in
            (("ROH", "0001"), ("HALB", "0002"), ("FERT", "0002"), ("HAWA", "0001"))]
    t025 = [{"MANDT": mandant, "BKLAS": b, "KKREF": k} for b, k in
            (("3000", "0001"), ("3100", "0001"), ("7900", "0002"), ("7920", "0002"))]
    t023 = [{"MANDT": mandant, "MATKL": m} for m in ("001", "002", "003", "004")]
    # Mengeneinheiten mit ISO-Code nach UN/ECE Rec 20 - und eine hauseigene
    # Einheit ohne, wie sie in gewachsenen Systemen aus der Fertigung kommt.
    t006 = [{"MANDT": mandant, "MSEHI": m, "ISOCODE": iso} for m, iso in
            (("ST", "H87"), ("KG", "KGM"), ("M", "MTR"), ("PAL", ""))]
    t001w = [{"MANDT": mandant, "WERKS": "1000", "NAME1": "Werk Musterstadt", "LAND1": "DE"}]
    skb1 = [{"MANDT": mandant, "BUKRS": "1000", "SAKNR": "0000160000", "MITKZ": "K"},
            {"MANDT": mandant, "BUKRS": "1000", "SAKNR": "0000140000", "MITKZ": "D"}]
    tcurc = [{"MANDT": mandant, "WAERS": w, "ISOCD": iso} for w, iso in
             (("EUR", "EUR"), ("CHF", "CHF"), ("USD", "USD"))]
    t024e = [{"MANDT": mandant, "EKORG": "1000", "EKOTX": "Einkauf zentral", "BUKRS": "1000"}]

    # ----------------------------------------------- Steuerkennzeichen
    #
    # T007A ist Customizing, STEUERZUORDNUNG ist eine Projektleistung: die
    # Zuordnung zu den Kategorie-Codes der Norm laesst sich nicht ableiten.
    # Die Beispiellieferung enthaelt beides, damit die Gruppe Steuerlogik
    # vorfuehrbar ist - und je einen Fall, der auffaellt.
    t007a = [{"MANDT": mandant, "KALSM": "TAXD", "MWSKZ": k, "MWART": "A"}
             for k in ("A1", "A0", "AZ", "AX")]
    steuerzuordnung = [
        {"MWSKZ": "A1", "KATEGORIE": "S", "SATZ": 19.0,
         "BEFREIUNGSGRUND": "", "BEZEICHNUNG": "Regelsatz Inland"},
        {"MWSKZ": "A0", "KATEGORIE": "K", "SATZ": 0.0,
         "BEFREIUNGSGRUND": "Innergemeinschaftliche Lieferung nach § 4 Nr. 1b UStG",
         "BEZEICHNUNG": "Steuerfrei innergemeinschaftlich"},
        # Befreit, aber ohne hinterlegten Grund - der Befund zu ERE-COMP-007.
        {"MWSKZ": "AZ", "KATEGORIE": "E", "SATZ": 0.0,
         "BEFREIUNGSGRUND": "", "BEZEICHNUNG": "Steuerfrei ohne Vorsteuerabzug"},
        # In der Zuordnung, aber im Customizing nicht mehr gepflegt.
        {"MWSKZ": "XX", "KATEGORIE": "S", "SATZ": 19.0,
         "BEFREIUNGSGRUND": "", "BEZEICHNUNG": "Altkennzeichen"},
    ]
    defekte.append(
        "ERE-COMP-007: 1 Steuerkennzeichen ohne Befreiungsgrund | betroffen: AZ"
    )
    defekte.append(
        "ERE-REF-003: 1 Steuerkennzeichen ohne Zuordnung zu einem "
        "Kategorie-Code | betroffen: AX"
    )
    defekte.append(
        "ERE-REF-004: 1 Steuerkennzeichen aus den Belegen fehlt im "
        "Customizing | betroffen: XX"
    )

    # Zwei der Debitoren ohne E-Mail-Adresse sind Grosskunden. Das ist der
    # Fall, fuer den es die Belegsicht gibt: nach Koepfen sind es vier von
    # hundert, nach Umsatz ein Viertel.
    vbrk, vbrp = fakturen(
        rng, mandant, kna1, heute, defekte,
        schwergewichte=[satz["KUNNR"] for satz in ohne_email[:2]],
    )

    # ------------------------------------------------------ schreiben
    write_csv(target / "LFA1.csv", lfa1, list(lfa1[0]))
    write_csv(target / "LFB1.csv", lfb1, list(lfb1[0]))
    write_csv(target / "LFM1.csv", lfm1, list(lfm1[0]))
    write_csv(target / "LFBK.csv", lfbk, list(lfbk[0]))
    write_csv(target / "KNA1.csv", kna1, list(kna1[0]))
    write_csv(target / "KNB1.csv", knb1, list(knb1[0]))
    write_csv(target / "KNBK.csv", knbk, list(knbk[0]))
    write_csv(target / "KNVV.csv", knvv, list(knvv[0]))
    write_csv(target / "ADR6.csv", adr6, list(adr6[0]))
    write_csv(target / "ADRC.csv", adrc, list(adrc[0]))
    write_csv(target / "VBRK.csv", vbrk, list(vbrk[0]))
    write_csv(target / "VBRP.csv", vbrp, list(vbrp[0]))
    write_csv(target / "STEUERZUORDNUNG.csv", steuerzuordnung, list(steuerzuordnung[0]))
    write_csv(target / "MARA.csv", mara, list(mara[0]))
    write_csv(target / "MAKT.csv", makt, list(makt[0]))
    write_csv(target / "MARC.csv", marc, list(marc[0]))
    write_csv(target / "MBEW.csv", mbew, list(mbew[0]))
    for name, rows in (
        ("T001", t001), ("T052", t052), ("T042Z", t042z), ("T005", t005),
        ("T077K", t077k), ("T134", t134), ("T025", t025), ("T023", t023),
        ("T006", t006), ("T001W", t001w), ("SKB1", skb1), ("TCURC", tcurc),
        ("T024E", t024e), ("T077D", t077d), ("TVKO", tvko), ("T007A", t007a),
    ):
        write_csv(target / f"{name}.csv", rows, list(rows[0]))

    zaehlung = {
        "LFA1": len(lfa1), "LFB1": len(lfb1), "LFM1": len(lfm1), "LFBK": len(lfbk),
        "KNA1": len(kna1), "KNB1": len(knb1), "KNBK": len(knbk), "KNVV": len(knvv),
        "ADR6": len(adr6), "ADRC": len(adrc),
        "VBRK": len(vbrk), "VBRP": len(vbrp), "T007A": len(t007a),
        "STEUERZUORDNUNG": len(steuerzuordnung),
        "MARA": len(mara), "MAKT": len(makt), "MARC": len(marc), "MBEW": len(mbew),
        "T001": len(t001), "T052": len(t052), "T042Z": len(t042z), "T005": len(t005),
        "T077K": len(t077k), "T134": len(t134), "T025": len(t025), "T023": len(t023),
        "T006": len(t006), "T001W": len(t001w), "SKB1": len(skb1), "TCURC": len(tcurc),
        "T024E": len(t024e), "T077D": len(t077d), "TVKO": len(tvko),
    }

    manifest = ["# Begleitzettel der Beispiellieferung", "delivery:",
                f"  extraction_date: {heute.isoformat()}", '  client: "100"',
                "  source_system: ECC", "", "tables:"]
    for name, anzahl in zaehlung.items():
        manifest.append(f"  {name}: {{rows: {anzahl}, file: {name}.csv}}")
    (target / "manifest.yaml").write_text("\n".join(manifest) + "\n", encoding="utf-8")

    (target.parent / "EINGEBAUTE_MAENGEL.md").write_text(
        "# Absichtlich eingebaute Mängel der Beispiellieferung\n\n"
        "Diese Liste dient dem Abgleich: jede Zeile nennt eine Regel, was sie "
        "finden soll und welche Stammsätze betroffen sind.\n\n"
        + "\n".join(f"- {eintrag}" for eintrag in defekte)
        + "\n\n## Folgebefunde\n\n"
        "Über die aufgeführten Mängel hinaus melden weitere Regeln Befunde, "
        "die aus denselben Sätzen folgen - eine Löschvormerkung ohne Zahlsperre "
        "(VEN-RISK-006) etwa ergibt sich aus den vorgemerkten Kreditoren. Solche "
        "Folgebefunde sind erwünscht und zeigen, dass die Regeln ineinandergreifen.\n",
        encoding="utf-8",
    )
    return zaehlung


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("target", help="Zielverzeichnis für die Eingangsdateien")
    parser.add_argument("--vendors", type=int, default=400, help="Anzahl regulärer Kreditoren")
    args = parser.parse_args()

    target = Path(args.target).resolve()
    counts = build(target, args.vendors)
    print(f"Beispiellieferung erzeugt in {target}")
    for name, count in counts.items():
        print(f"  {name:8s} {count:6d} Sätze")


if __name__ == "__main__":
    main()
