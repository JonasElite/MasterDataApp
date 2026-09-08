"""Lasttest fuer NFA-01: Durchsatz auf einer Lieferung in Zielgroesse.

NFA-01 verlangt 5 Millionen Saetze ueber den vollen Regelkatalog in unter
15 Minuten auf einem Standard-Notebook. Diese Zahl laesst sich nur auf der
Zielhardware belegen. Das Skript erzeugt eine Lieferung in waehlbarer Groesse
und misst den vollstaendigen Lauf.

Aufruf:
    python tools/lasttest.py --vendors 1000000 --materials 500000

Die Daten werden zeilenweise geschrieben und nicht im Speicher gehalten -
sonst maesse man den Generator und nicht das Werkzeug.
"""

from __future__ import annotations

import argparse
import random
import shutil
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

SEED = 20260908
ORTE = [("Berlin", "DE"), ("Hamburg", "DE"), ("Wien", "AT"), ("Zuerich", "CH"),
        ("Amsterdam", "NL"), ("Paris", "FR"), ("Mailand", "IT")]
FORMEN = ["GmbH", "AG", "KG", "OHG", "SE"]
STAEMME = [
    "Baumann", "Kessler", "Lindner", "Hoffmann", "Wagner", "Brandt", "Ziegler",
    "Kaufmann", "Roth", "Sommer", "Winkler", "Faber", "Gerber", "Hartmann",
]


def mod97(text: str) -> int:
    rest = 0
    for char in text:
        rest = (rest * 10 + int(char)) % 97 if char.isdigit() else (rest * 100 + ord(char) - 55) % 97
    return rest


def schreibe_kreditoren(
    ziel: Path, anzahl: int, rng: random.Random, dublettenanteil: float = 0.0
) -> None:
    """Schreibt LFA1, LFB1, LFM1 und LFBK zeilenweise.

    ``dublettenanteil`` bestimmt, welcher Anteil der Saetze einen Namen aus
    einem bewusst kleinen Vorrat erhaelt. Der Aufwand der Dublettenerkennung
    haengt an der Zahl der Treffer, nicht an der Satzanzahl - mit diesem
    Schalter laesst sich beides getrennt messen.
    """
    with (ziel / "LFA1.csv").open("w", encoding="utf-8", newline="") as lfa1, \
         (ziel / "LFB1.csv").open("w", encoding="utf-8", newline="") as lfb1, \
         (ziel / "LFM1.csv").open("w", encoding="utf-8", newline="") as lfm1, \
         (ziel / "LFBK.csv").open("w", encoding="utf-8", newline="") as lfbk:

        lfa1.write("MANDT;LIFNR;NAME1;LAND1;ORT01;PSTLZ;STRAS;PFACH;KTOKK;ERDAT;ERNAM;"
                   "STCEG;STCD1;LOEVM;SPERR;SPERM;XCPDK;STKZN;ADRNR;NAME2;STCD2;KUNNR;TELF1\n")
        lfb1.write("MANDT;LIFNR;BUKRS;AKONT;ZTERM;ZWELS;ZAHLS;LOEVM;SPERR;ERDAT\n")
        lfm1.write("MANDT;LIFNR;EKORG;WAERS;ZTERM;LOEVM\n")
        lfbk.write("MANDT;LIFNR;BANKS;BANKL;BANKN;BKONT;KOINH;IBAN\n")

        for index in range(1, anzahl + 1):
            lifnr = f"{100000 + index}"
            ort, land = ORTE[index % len(ORTE)]
            plz = f"{10000 + (index * 7) % 89999}"
            # Der Name ist nahezu eindeutig. Zieht man aus einem kleinen
            # Vorrat, entsteht ein Bestand mit einem Dublettenanteil, den kein
            # gewachsener Stamm hat - gemessen wuerde dann die Bewaeltigung
            # eines Sonderfalls und nicht der Regelbetrieb. Wie sich das
            # Werkzeug bei hoher Dublettendichte verhaelt, zeigt --dubletten.
            if dublettenanteil and (index % 1000) < dublettenanteil * 1000:
                name = f"{STAEMME[index % len(STAEMME)]} Handel {FORMEN[index % 5]}"[:35]
            else:
                name = f"{STAEMME[index % len(STAEMME)]}{index} {FORMEN[index % 5]}"[:35]
            erdat = f"20{18 + index % 8:02d}{1 + index % 12:02d}{1 + index % 28:02d}"
            ustid = f"DE{100000000 + (index * 37) % 899999999}" if land == "DE" else ""
            blz = f"{10000000 + (index * 13) % 89999999}"
            body = (blz + f"{index:010d}")[:18]
            iban = f"DE{98 - mod97(body + 'DE00'):02d}{body}"

            lfa1.write(f"100;{lifnr};{name};{land};{ort};{plz};Hauptstrasse {index % 199 + 1};;"
                       f"KRED;{erdat};USER{index % 12:02d};{ustid};;;;;;;;;;;\n")
            lfb1.write(f"100;{lifnr};1000;0000160000;ZB0{index % 3 + 1};U;;;;{erdat}\n")
            lfm1.write(f"100;{lifnr};1000;EUR;ZB0{index % 3 + 1};\n")
            lfbk.write(f"100;{lifnr};DE;{blz};{index:010d};;;{iban}\n")


def schreibe_material(ziel: Path, anzahl: int) -> None:
    """Schreibt MARA, MAKT, MARC und MBEW zeilenweise."""
    with (ziel / "MARA.csv").open("w", encoding="utf-8", newline="") as mara, \
         (ziel / "MAKT.csv").open("w", encoding="utf-8", newline="") as makt, \
         (ziel / "MARC.csv").open("w", encoding="utf-8", newline="") as marc, \
         (ziel / "MBEW.csv").open("w", encoding="utf-8", newline="") as mbew:

        mara.write("MANDT;MATNR;MTART;MATKL;MEINS;ERSDA;LAEDA;ERNAM;LVORM;EAN11\n")
        makt.write("MANDT;MATNR;SPRAS;MAKTX\n")
        marc.write("MANDT;MATNR;WERKS;DISMM;LVORM\n")
        mbew.write("MANDT;MATNR;BWKEY;BWTAR;VPRSV;STPRS;VERPR;PEINH;BKLAS;LBKUM;SALK3;LVORM\n")

        arten = ["ROH", "HALB", "FERT", "HAWA"]
        klassen = {"ROH": "3000", "HALB": "7900", "FERT": "7920", "HAWA": "3100"}
        for index in range(1, anzahl + 1):
            matnr = f"{2000000 + index}"
            art = arten[index % 4]
            preis = round(1.5 + (index % 8000) / 10, 2)
            menge = (index * 3) % 500
            mara.write(f"100;{matnr};{art};00{index % 4 + 1};ST;2019{1 + index % 12:02d}"
                       f"{1 + index % 28:02d};20250101;USER01;;\n")
            makt.write(f"100;{matnr};D;Bauteil {index % 9973} Serie {index % 97}\n")
            marc.write(f"100;{matnr};1000;PD;\n")
            mbew.write(f"100;{matnr};1000;;S;{preis:.2f};0.00;1;{klassen[art]};"
                       f"{menge};{menge * preis:.2f};\n")


def schreibe_customizing(ziel: Path) -> None:
    dateien = {
        "T001.csv": "MANDT;BUKRS;BUTXT;LAND1;WAERS;KTOPL\n100;1000;Musterwerk;DE;EUR;INT\n",
        "T052.csv": "MANDT;ZTERM;ZTAGG;ZTAG1\n" + "".join(
            f"100;ZB0{i};00;{i * 14}\n" for i in (1, 2, 3)
        ),
        "T042Z.csv": "MANDT;LAND1;ZLSCH;TEXT1\n" + "".join(
            f"100;{land};{weg};Text\n" for land in ("DE", "AT", "CH", "NL", "FR", "IT")
            for weg in ("U", "S")
        ),
        "T005.csv": "MANDT;LAND1;INTCA;XEGLD\n" + "".join(
            f"100;{land};{land};{'X' if land != 'CH' else ''}\n"
            for land in ("DE", "AT", "CH", "NL", "FR", "IT")
        ),
        "T077K.csv": "MANDT;KTOKK;NUMKR\n100;KRED;01\n",
        "T134.csv": "MANDT;MTART;KKREF\n100;ROH;0001\n100;HALB;0002\n100;FERT;0002\n100;HAWA;0001\n",
        "T025.csv": "MANDT;BKLAS;KKREF\n100;3000;0001\n100;3100;0001\n100;7900;0002\n100;7920;0002\n",
        "T023.csv": "MANDT;MATKL\n100;001\n100;002\n100;003\n100;004\n",
        "T006.csv": "MANDT;MSEHI\n100;ST\n100;KG\n100;M\n",
        "T001W.csv": "MANDT;WERKS;NAME1;LAND1\n100;1000;Werk;DE\n",
        "SKB1.csv": "MANDT;BUKRS;SAKNR;MITKZ\n100;1000;0000160000;K\n",
        "TCURC.csv": "MANDT;WAERS\n100;EUR\n100;CHF\n",
        "T024E.csv": "MANDT;EKORG;EKOTX;BUKRS\n100;1000;Einkauf;1000\n",
    }
    for name, inhalt in dateien.items():
        (ziel / name).write_text(inhalt, encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--vendors", type=int, default=1_000_000)
    parser.add_argument("--materials", type=int, default=500_000)
    parser.add_argument("--workdir", default=None, help="Arbeitsverzeichnis des Lasttests")
    parser.add_argument("--keep", action="store_true", help="Daten nach dem Lauf behalten")
    parser.add_argument(
        "--dubletten", type=float, default=0.0,
        help="Anteil der Kreditoren mit absichtlich aehnlichem Namen (0.0 bis 1.0)",
    )
    args = parser.parse_args()

    import tempfile

    basis = Path(args.workdir) if args.workdir else Path(tempfile.mkdtemp(prefix="sapmdq_last_"))
    eingang = basis / "input"
    eingang.mkdir(parents=True, exist_ok=True)

    rng = random.Random(SEED)
    print(f"Erzeuge Lieferung in {basis} ...")
    begonnen = time.perf_counter()
    schreibe_kreditoren(eingang, args.vendors, rng, args.dubletten)
    schreibe_material(eingang, args.materials)
    schreibe_customizing(eingang)
    erzeugung = time.perf_counter() - begonnen

    saetze = args.vendors * 4 + args.materials * 4
    groesse = sum(p.stat().st_size for p in eingang.iterdir()) / 1_048_576
    print(f"  {saetze:,} Saetze in {groesse:,.0f} MB, erzeugt in {erzeugung:.0f}s".replace(",", "."))

    konfiguration = basis / "projekt.yaml"
    konfiguration.write_text(
        f"""
project:
  name: Lasttest
paths:
  input_dir: {eingang}
  work_dir: {basis / 'work'}
  output_dir: {basis / 'out'}
delivery:
  expected_clients: ["100"]
rules:
  catalog_dirs: ["{Path(__file__).resolve().parents[1] / 'rules'}"]
report:
  formats: [md, csv]
""",
        encoding="utf-8",
    )

    from sapmdq.config import load_config
    from sapmdq.run import execute_run

    print("Starte Lauf ...")
    begonnen = time.perf_counter()
    ergebnis = execute_run(load_config(konfiguration), quiet=True)
    dauer = time.perf_counter() - begonnen

    print()
    print(f"Saetze verarbeitet   : {ergebnis.rows_ingested:,}".replace(",", "."))
    print(f"Regeln ausgefuehrt   : "
          f"{len([e for e in ergebnis.all_executions if e.status.value == 'ausgefuehrt'])}"
          f" von {ergebnis.coverage.total}")
    print(f"Befunde              : {ergebnis.total_findings:,}".replace(",", "."))
    print(f"Laufzeit             : {dauer / 60:.1f} Minuten ({dauer:.0f}s)")
    print(f"Durchsatz            : {ergebnis.rows_ingested / dauer:,.0f} Saetze/s".replace(",", "."))
    print()
    grenze = 15 * 60
    hochrechnung = dauer / max(ergebnis.rows_ingested, 1) * 5_000_000
    print(f"Hochrechnung auf 5 Mio. Saetze: {hochrechnung / 60:.1f} Minuten "
          f"({'unter' if hochrechnung < grenze else 'ueber'} der Vorgabe von 15 Minuten)")

    langsamste = sorted(ergebnis.all_executions, key=lambda e: -e.duration_seconds)[:5]
    print("\nLangsamste Regeln:")
    for eintrag in langsamste:
        print(f"  {eintrag.rule.id:14s} {eintrag.duration_seconds:6.1f}s "
              f"{eintrag.finding_count:>9,} Befunde".replace(",", "."))

    if not args.keep:
        shutil.rmtree(basis, ignore_errors=True)
        print(f"\nTestdaten geloescht. Mit --keep bleiben sie in {basis}.")


if __name__ == "__main__":
    main()
