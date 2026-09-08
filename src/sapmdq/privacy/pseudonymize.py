"""Pseudonymisierung personenbezogener Felder (DS-05).

Zweck ist ausschliesslich, aus einer echten Lieferung eine Fassung fuer
Demonstrationen, Tests und Schulungen abzuleiten. Sie ersetzt keine
Anonymisierung im Rechtssinn: die Zuordnung bleibt ueber das Salt
wiederherstellbar, und aus Struktur und Verteilung der Daten kann sich ein
Personenbezug ergeben.

Zwei Eigenschaften sind fuer die Brauchbarkeit entscheidend:

Gleiche Eingabe ergibt gleiches Pseudonym.
    Sonst zerfielen alle Beziehungen: derselbe Kreditor haette in LFA1 einen
    anderen Namen als in ADRC, und die Dublettenerkennung liesse sich an der
    Demofassung nicht mehr zeigen.

Die Form bleibt erhalten.
    Aus einer IBAN wird eine andere gueltige IBAN, aus einer Postleitzahl eine
    Postleitzahl. Sonst wuerden die Formatregeln auf der Demofassung lauter
    Befunde erzeugen, die es im Original nicht gibt.

Das Salt gehoert getrennt von den pseudonymisierten Daten aufbewahrt. Wer
beides hat, kann die Zuordnung durch Ausprobieren wiederherstellen.

Was nicht erhalten bleibt
-------------------------
Maengel, die gerade im Wert selbst liegen, verschwinden zwangslaeufig: eine
IBAN mit falscher Pruefziffer wird durch eine gueltige ersetzt, eine
fehlerhafte USt-IdNr. durch eine formgerechte, ein Platzhaltername wie
"unbekannt" durch einen erfundenen Firmennamen. Auf der pseudonymisierten
Fassung finden die Formatregeln diese Faelle deshalb nicht mehr.

Das ist kein Fehler, sondern die Folge der Aufgabenstellung - es gehoert aber
gewusst: eine Demofassung eignet sich zum Zeigen des Verfahrens, nicht zum
Nachvollziehen eines konkreten Befundes. Vollstaendigkeits-, Konsistenz-,
Referenz- und Dublettenbefunde bleiben dagegen erhalten.
"""

from __future__ import annotations

import hashlib
import hmac
import secrets
from dataclasses import dataclass
from pathlib import Path

from sapmdq.logging_setup import get_logger
from sapmdq.rules.validators import _mod97

logger = get_logger("privacy.pseudonymize")

#: Vorsilben je Feldart - halten die Demodaten lesbar.
_NAME_PARTS = (
    "Alpha", "Beta", "Gamma", "Delta", "Omega", "Nord", "Sued", "West", "Ost",
    "Berg", "Tal", "Stein", "Feld", "Wald", "See", "Bach", "Rhein", "Main",
)
_LEGAL_FORMS = ("GmbH", "AG", "KG", "OHG", "GmbH & Co. KG", "SE", "e.K.")
_STREETS = ("Musterweg", "Beispielstrasse", "Probeallee", "Testplatz", "Demoring")
_CITIES = ("Musterstadt", "Beispielheim", "Probdorf", "Testberg", "Demoburg")


def generate_salt() -> str:
    """Erzeugt ein neues Salt."""
    return secrets.token_hex(32)


def load_or_create_salt(path: Path | None) -> tuple[str, bool]:
    """Laedt das Salt oder erzeugt es.

    Rueckgabe ist das Salt und ob es neu erzeugt wurde. Ohne Datei entsteht
    ein neues Salt je Aufruf - dann sind zwei Laeufe nicht mehr miteinander
    vergleichbar. Darauf wird hingewiesen.
    """
    if path is None:
        return generate_salt(), True
    if path.is_file():
        return path.read_text(encoding="utf-8").strip(), False
    salt = generate_salt()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(salt, encoding="utf-8")
    try:
        path.chmod(0o600)
    except OSError:  # pragma: no cover - Dateisystem ohne Rechteverwaltung
        pass
    logger.info("Neues Salt erzeugt und in %s abgelegt", path)
    return salt, True


@dataclass
class Pseudonymizer:
    """Bildet Werte deterministisch auf Pseudonyme ab."""

    salt: str

    def _digest(self, kind: str, value: str) -> bytes:
        return hmac.new(
            self.salt.encode("utf-8"), f"{kind}\x1f{value}".encode("utf-8"), hashlib.sha256
        ).digest()

    def _number(self, kind: str, value: str, modulus: int) -> int:
        return int.from_bytes(self._digest(kind, value)[:8], "big") % modulus

    def _pick(self, kind: str, value: str, options: tuple[str, ...]) -> str:
        return options[self._number(kind, value, len(options))]

    # ------------------------------------------------------------ Verfahren
    def company_name(self, value: str) -> str:
        """Firmenname aus festen Bausteinen und einem eindeutigen Zusatz.

        Der vierstellige Zusatz ist nicht schmueckend. Ohne ihn stammten alle
        Namen aus einem Vorrat von wenigen hundert Kombinationen; bei
        tausenden Kreditoren traefen zwangslaeufig mehrere auf denselben Namen,
        und die Dublettenerkennung meldete auf der Demofassung hunderte
        Cluster, die es im Original nicht gibt.
        """
        first = self._pick("name1", value, _NAME_PARTS)
        second = self._pick("name2", value, _NAME_PARTS)
        form = self._pick("form", value, _LEGAL_FORMS)
        digest = self._digest("namenszusatz", value)
        buchstaben = "ABCDEFGHJKLMNPQRSTUVWXYZ"
        zusatz = "".join(buchstaben[digest[index] % len(buchstaben)] for index in range(4))
        return f"{first}{second.lower()} {zusatz} {form}"

    def person_name(self, value: str) -> str:
        """Personenname."""
        return f"{self._pick('vorname', value, _NAME_PARTS)} {self._pick('nachname', value, _NAME_PARTS)}"

    def street(self, value: str) -> str:
        """Strasse mit Hausnummer."""
        return f"{self._pick('strasse', value, _STREETS)} {self._number('hausnr', value, 199) + 1}"

    def city(self, value: str) -> str:
        return self._pick("ort", value, _CITIES)

    def postal_code(self, value: str) -> str:
        """Postleitzahl gleicher Laenge und gleichen Aufbaus.

        Ziffern werden durch Ziffern ersetzt, Buchstaben durch Buchstaben.
        Damit bleibt eine niederlaendische PLZ wie "1012 AB" formgerecht und
        die Formatregeln melden auf der Demofassung nichts Falsches.
        """
        return self._preserve_shape("plz", value)

    def _preserve_shape(self, kind: str, value: str) -> str:
        digest = self._digest(kind, value)
        result: list[str] = []
        for position, char in enumerate(value):
            byte = digest[position % len(digest)]
            if char.isdigit():
                result.append(str(byte % 10))
            elif char.isalpha():
                letter = chr(ord("A") + byte % 26)
                result.append(letter if char.isupper() else letter.lower())
            else:
                result.append(char)
        return "".join(result)

    def phone(self, value: str) -> str:
        return self._preserve_shape("telefon", value)

    def email(self, value: str) -> str:
        local = self._digest("email", value)[:4].hex()
        return f"kontakt.{local}@example.invalid"

    def tax_number(self, value: str) -> str:
        return self._preserve_shape("steuernr", value)

    def vat_id(self, value: str) -> str:
        """Erzeugt eine syntaktisch gueltige USt-IdNr. desselben Landes.

        Ein blosses Ersetzen der Ziffern wuerde die Pruefziffer zerstoeren:
        die Demofassung erzeugte dann bei jedem Kreditor einen Formatbefund,
        den es im Original nicht gibt. Deshalb wird so lange erzeugt, bis die
        Nummer der Pruefung standhaelt - deterministisch, weil der
        Ausgangswert die Folge bestimmt.
        """
        from sapmdq.rules.validators import VAT_PATTERNS, vat_id_valid

        cleaned = "".join(char for char in str(value).upper() if char.isalnum())
        if len(cleaned) < 3:
            return self._preserve_shape("ustid", value)
        country = cleaned[:2]
        if country not in VAT_PATTERNS:
            return self._preserve_shape("ustid", value)

        digest = self._digest("ustid", cleaned)
        for versuch in range(256):
            byte_offset = versuch % len(digest)
            ziffern = "".join(
                str(digest[(byte_offset + position) % len(digest)] % 10)
                for position in range(12)
            )
            kandidat = {
                "DE": lambda: country + ziffern[:9],
                "AT": lambda: country + "U" + ziffern[:8],
                "NL": lambda: country + ziffern[:9] + "B" + ziffern[9:11],
                "FR": lambda: country + ziffern[:2] + ziffern[:9],
                "IT": lambda: country + ziffern[:11],
            }.get(country, lambda: country + ziffern[: len(cleaned) - 2])()
            if vat_id_valid(country, kandidat):
                return kandidat
            digest = hashlib.sha256(digest).digest()
        return self._preserve_shape("ustid", value)

    def account_number(self, value: str) -> str:
        return self._preserve_shape("konto", value)

    def iban(self, value: str) -> str:
        """Erzeugt eine formal gueltige IBAN gleicher Laenge und gleichen Landes.

        Die Pruefziffer wird neu berechnet, damit die Formatregeln auf der
        Demofassung greifen - sonst waere jede pseudonymisierte Bankverbindung
        ein Befund.
        """
        cleaned = "".join(char for char in str(value).upper() if char.isalnum())
        if len(cleaned) < 5 or not cleaned[:2].isalpha():
            return self._preserve_shape("iban", value)

        country, body_length = cleaned[:2], len(cleaned) - 4
        digest = self._digest("iban", cleaned)
        body = "".join(str(digest[index % len(digest)] % 10) for index in range(body_length))

        # Die Bankkennung wird aus der urspruenglichen IBAN uebernommen und
        # mit demselben Verfahren ersetzt wie das Feld BANKL. Nur so tragen
        # Bankverbindung und IBAN nach der Pseudonymisierung noch dieselbe
        # Bank - andernfalls meldete die Demofassung fuer jede Bankverbindung
        # eine Abweichung zwischen IBAN und Bankschluessel (VEN-FMT-005).
        bank_key_lengths = {"DE": 8, "AT": 5, "CH": 5, "NL": 4, "FR": 5, "ES": 4, "IT": 5, "BE": 3}
        laenge = bank_key_lengths.get(country)
        if laenge and body_length >= laenge:
            original_bank = cleaned[4 : 4 + laenge]
            body = self.account_number(original_bank) + body[laenge:]

        remainder = _mod97(body + country + "00")
        check = f"{98 - remainder:02d}"
        return f"{country}{check}{body}"

    def generic(self, value: str) -> str:
        return f"X{self._digest('generic', value)[:4].hex()}"


#: Zuordnung Feldname zu Verfahren. Was hier nicht steht, aber als
#: personenbezogen gekennzeichnet ist, wird ueber ``generic`` ersetzt.
FIELD_METHODS: dict[str, str] = {
    "NAME1": "company_name", "NAME2": "company_name", "NAME3": "company_name",
    "NAME4": "company_name", "NAME_ORG1": "company_name", "NAME_ORG2": "company_name",
    "NAME_ORG3": "company_name", "NAME_ORG4": "company_name", "BANKA": "company_name",
    "MCOD1": "company_name", "KOINH": "company_name", "ACCNAME": "company_name",
    "EMFTX": "person_name", "NAME_LAST": "person_name", "NAME_FIRST": "person_name",
    "ERNAM": "person_name", "AENAM": "person_name", "USERNAME": "person_name",
    "CREATED_BY": "person_name", "VERKF": "person_name",
    "STRAS": "street", "STREET": "street", "PFACH": "street", "PO_BOX": "street",
    "HOUSE_NUM1": "street", "HOUSE_NUM2": "street",
    "ORT01": "city", "ORT02": "city", "CITY1": "city", "CITY2": "city",
    "PSTLZ": "postal_code", "PSTL2": "postal_code", "POST_CODE1": "postal_code",
    "POST_CODE2": "postal_code",
    "TELF1": "phone", "TELF2": "phone", "TELFX": "phone", "TEL_NUMBER": "phone",
    "FAX_NUMBER": "phone",
    "EMAIL": "email", "SMTP_ADDR": "email",
    "STCD1": "tax_number", "STCD2": "tax_number", "STCD3": "tax_number",
    "STCD4": "tax_number", "PERNR": "tax_number",
    "STCEG": "vat_id",
    "BANKN": "account_number", "BANKL": "account_number",
    "IBAN": "iban",
    "VALUE_NEW": "generic", "VALUE_OLD": "generic",
}


def method_for_field(field_name: str) -> str:
    """Verfahren fuer ein Feld; unbekannte personenbezogene Felder generisch."""
    return FIELD_METHODS.get(field_name.upper(), "generic")


def pseudonymize_tables(
    con,
    ingestion,
    target_dir: Path,
    pseudonymizer: Pseudonymizer,
    file_format: str = "csv",
) -> dict[str, Path]:
    """Schreibt eine pseudonymisierte Fassung der eingelesenen Tabellen.

    Ausgegeben wird standardmaessig CSV: die Fassung soll sich unmittelbar als
    Eingangsverzeichnis eines Demonstrationslaufs verwenden lassen. Die
    Spaltenueberschriften bleiben technische Feldnamen, das Trennzeichen ist
    das Semikolon - also genau das Lieferformat, das Kapitel 8.4 empfiehlt.
    """
    from sapmdq.sap.sql_conversion import quote_identifier, quote_literal

    registry = ingestion.registry
    target_dir.mkdir(parents=True, exist_ok=True)
    written: dict[str, Path] = {}

    # Je Verfahren eine SQL-Funktion, damit die Ersetzung in der Datenbank
    # laeuft und die Daten nicht durch Python-Speicher wandern muessen.
    methods = {
        "company_name": pseudonymizer.company_name,
        "person_name": pseudonymizer.person_name,
        "street": pseudonymizer.street,
        "city": pseudonymizer.city,
        "postal_code": pseudonymizer.postal_code,
        "phone": pseudonymizer.phone,
        "email": pseudonymizer.email,
        "tax_number": pseudonymizer.tax_number,
        "account_number": pseudonymizer.account_number,
        "iban": pseudonymizer.iban,
        "vat_id": pseudonymizer.vat_id,
        "generic": pseudonymizer.generic,
    }
    def als_udf(verfahren):
        """Bindet ein Verfahren als einstellige Funktion.

        Ein Vorgabewert im Lambda waere hier untauglich: DuckDB liest die
        Signatur aus und zaehlte ihn als zweiten Parameter.
        """

        def anwenden(wert):
            return verfahren(str(wert)) if wert is not None else None

        return anwenden

    for name, function in methods.items():
        udf_name = f"pseudo_{name}"
        try:
            con.remove_function(udf_name)
        except Exception:
            pass
        con.create_function(
            udf_name, als_udf(function), ["VARCHAR"], "VARCHAR",
            null_handling="special", side_effects=False,
        )

    for table_name in sorted(ingestion.tables):
        entry = ingestion.tables[table_name]
        spec = registry.get(table_name) if registry else None
        projections: list[str] = []
        replaced: list[str] = []
        for column in entry.columns:
            identifier = quote_identifier(column)
            field_spec = spec.field_spec(column) if spec else None
            if field_spec is not None and field_spec.pii:
                method = method_for_field(column)
                projections.append(
                    f"pseudo_{method}(CAST({identifier} AS VARCHAR)) AS {identifier}"
                )
                replaced.append(column)
            else:
                projections.append(identifier)

        source = f"read_parquet({quote_literal(str(entry.parquet_path))})"
        if file_format == "parquet":
            target = target_dir / f"{table_name}.parquet"
            options = "(FORMAT PARQUET, COMPRESSION ZSTD)"
        else:
            target = target_dir / f"{table_name}.csv"
            options = "(FORMAT CSV, DELIMITER ';', HEADER true)"
        con.execute(
            f"COPY (SELECT {', '.join(projections)} FROM {source}) "
            f"TO {quote_literal(str(target))} {options}"
        )
        written[table_name] = target
        logger.info(
            "%s pseudonymisiert (%d Felder ersetzt): %s",
            table_name, len(replaced), target.name,
        )

    return written
