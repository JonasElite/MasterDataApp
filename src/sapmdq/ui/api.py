"""Fachliche Schnittstelle der Oberfläche.

Die Funktionen hier kennen kein HTTP. Sie nehmen den Zustand und die
Aufrufparameter, liefern Datenstrukturen zurück und werfen ``ApiFehler``,
wenn etwas nicht stimmt. Das macht sie ohne laufenden Server prüfbar.

Befunde werden nicht in den Speicher geladen, sondern bei jeder Anfrage aus
der Parquet-Datei gelesen und dort gefiltert und geblättert. Eine Oberfläche,
die eine Million Befunde vorhält, wäre weder schnell noch sparsam.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import date, datetime
from pathlib import Path
from typing import Any, Mapping

import duckdb

from sapmdq.findings.model import FindingStatus
from sapmdq.findings.status import load_status, save_status
from sapmdq.findings.whitelist import (
    WhitelistEntry,
    load_whitelist,
    save_whitelist,
)
from sapmdq.logging_setup import get_logger
from sapmdq.report.laufbericht import SUMMARY_FILENAME, read_summary
from sapmdq.sap.sql_conversion import quote_literal
from sapmdq.ui.state import UiState
from sapmdq.util.timeutil import parse_date

logger = get_logger("ui.api")

#: Höchstzahl Befunde je Seite. Verhindert, dass ein Aufruf die Oberfläche
#: mit hunderttausend Zeilen belädt.
MAX_PAGE_SIZE = 200


@dataclass
class ApiFehler(Exception):
    """Ein Aufruf war nicht ausführbar.

    ``vorlage`` und ``werte`` sind gesetzt, wenn die Meldung in der
    Oberfläche übersetzt werden soll: die Vorlage ist der Schlüssel im
    Wörterbuch, die Werte werden erst dort eingesetzt. Ohne sie zeigt die
    Oberfläche ``meldung`` unverändert an.
    """

    meldung: str
    status: int = 400
    vorlage: str = ""
    werte: dict[str, Any] = field(default_factory=dict)

    def __str__(self) -> str:  # pragma: no cover - Anzeige
        return self.meldung


def uebersetzbar(vorlage: str, status: int = 400, **werte: Any) -> ApiFehler:
    """Baut einen Fehler, dessen Wortlaut die Oberfläche übersetzen kann."""
    return ApiFehler(vorlage.format(**werte), status, vorlage, dict(werte))


def _erste(werte: Mapping[str, list[str]], name: str, vorgabe: str = "") -> str:
    eintraege = werte.get(name) or []
    return eintraege[0] if eintraege else vorgabe


def _liste(werte: Mapping[str, list[str]], name: str) -> list[str]:
    """Mehrfach angegebene oder mit Komma getrennte Werte."""
    ergebnis: list[str] = []
    for eintrag in werte.get(name) or []:
        ergebnis.extend(teil for teil in eintrag.split(",") if teil.strip())
    return ergebnis


# --------------------------------------------------------------------- Projekt
def projekt(state: UiState) -> dict[str, Any]:
    """Angaben zum Projekt und zu den Pfaden."""
    config = state.neu_laden()
    return {
        "name": config.project.name,
        "kunde": config.project.customer,
        "quellsystem": config.project.source_system,
        "analyst": config.project.analyst,
        "konfiguration": str(config.source_path) if config.source_path else "",
        "eingangsverzeichnis": str(config.paths.input_dir),
        "ausgabeverzeichnis": str(config.paths.output_dir),
        "ausnahmeliste": str(config.findings.whitelist_file)
        if config.findings.whitelist_file
        else "",
        "statusdatei": str(config.findings.status_file) if config.findings.status_file else "",
        "eingangsdateien": sorted(
            pfad.name for pfad in config.paths.input_dir.glob("*") if pfad.is_file()
        )
        if config.paths.input_dir.is_dir()
        else [],
        "externe_validierung": config.rules.allow_external_validation,
    }


# ----------------------------------------------------------------------- Läufe
def laeufe(state: UiState) -> dict[str, Any]:
    """Liste aller Läufe, neueste zuerst."""
    eintraege: list[dict[str, Any]] = []
    if state.runs_dir.is_dir():
        for verzeichnis in sorted(state.runs_dir.iterdir(), reverse=True):
            if not verzeichnis.is_dir():
                continue
            zusammenfassung = read_summary(verzeichnis)
            if zusammenfassung is None:
                # Lauf ohne Zusammenfassung - etwa abgebrochen. Er soll
                # trotzdem sichtbar sein, damit er nicht unbemerkt verschwindet.
                eintraege.append(
                    {
                        "lauf_id": verzeichnis.name,
                        "unvollstaendig": True,
                        # Ohne Zusammenfassung lässt sich der Lauf nicht
                        # anzeigen, aber sehr wohl vergleichen - dafür reicht
                        # die Befunddatei.
                        "vergleichbar": (verzeichnis / "befunde.parquet").is_file(),
                        "verzeichnis": str(verzeichnis),
                    }
                )
                continue
            befunde = zusammenfassung.get("befunde", {})
            coverage = zusammenfassung.get("coverage", {})
            bewertung = zusammenfassung.get("bewertung", {})
            eintraege.append(
                {
                    "lauf_id": zusammenfassung.get("lauf_id", verzeichnis.name),
                    "erstellt_am": zusammenfassung.get("erstellt_am", ""),
                    "laufzeit_sekunden": zusammenfassung.get("laufzeit_sekunden", 0),
                    "saetze": zusammenfassung.get("saetze_verarbeitet", 0),
                    "befunde": befunde.get("effektiv", 0),
                    "ausnahmen": befunde.get("ausnahmen", 0),
                    "je_schweregrad": befunde.get("je_schweregrad", {}),
                    "coverage": coverage.get("anteil", 0),
                    "regeln_ausfuehrbar": coverage.get("ausfuehrbar", 0),
                    "regeln_gesamt": coverage.get("regeln_gesamt", 0),
                    "regelfehler": zusammenfassung.get("regelfehler", 0),
                    "score": bewertung.get("gesamt"),
                    "katalog": zusammenfassung.get("regelkatalog", {}).get("version", ""),
                    "verzeichnis": str(verzeichnis),
                    "unvollstaendig": False,
                    "vergleichbar": (verzeichnis / "befunde.parquet").is_file(),
                }
            )
    return {"laeufe": eintraege}


def lauf(state: UiState, lauf_id: str) -> dict[str, Any]:
    """Vollständige Zusammenfassung eines Laufs."""
    verzeichnis = state.lauf_verzeichnis(lauf_id)
    if verzeichnis is None:
        raise ApiFehler(f"Lauf {lauf_id} nicht gefunden.", 404)
    zusammenfassung = read_summary(verzeichnis)
    if zusammenfassung is None:
        raise ApiFehler(
            f"Zu Lauf {lauf_id} gibt es keine Zusammenfassung ({SUMMARY_FILENAME} fehlt). "
            "Der Lauf wurde vermutlich abgebrochen.",
            404,
        )
    zusammenfassung["verzeichnis"] = str(verzeichnis)
    return zusammenfassung


# ---------------------------------------------------------------------- Befunde
def _befunddatei(state: UiState, lauf_id: str) -> Path:
    verzeichnis = state.lauf_verzeichnis(lauf_id)
    if verzeichnis is None:
        raise ApiFehler(f"Lauf {lauf_id} nicht gefunden.", 404)
    pfad = verzeichnis / "befunde.parquet"
    if not pfad.is_file():
        raise ApiFehler(f"Zu Lauf {lauf_id} liegen keine Befunde vor.", 404)
    return pfad


def _bedingungen(werte: Mapping[str, list[str]]) -> tuple[list[str], list[Any]]:
    """Übersetzt die Filter der Oberfläche in SQL-Bedingungen.

    Die Werte werden als Parameter übergeben und nicht in den Text
    eingesetzt - eine Suchanfrage aus der Oberfläche darf die Abfrage nicht
    verändern können.
    """
    bedingungen: list[str] = []
    parameter: list[Any] = []

    if _erste(werte, "ausnahmen", "aus") != "ein":
        bedingungen.append("NOT whitelisted")

    for feld, spalte in (
        ("schweregrad", "severity"),
        ("kategorie", "category"),
        ("bereich", "object_area"),
        ("regel", "rule_id"),
        ("status", "status"),
        ("vergleich", "delta_state"),
    ):
        auswahl = _liste(werte, feld)
        if auswahl:
            platzhalter = ", ".join("?" for _ in auswahl)
            bedingungen.append(f"{spalte} IN ({platzhalter})")
            parameter.extend(auswahl)

    suche = _erste(werte, "suche").strip()
    if suche:
        bedingungen.append(
            "(object_key ILIKE ? OR rule_name ILIKE ? OR detail ILIKE ?)"
        )
        muster = f"%{suche}%"
        parameter.extend([muster, muster, muster])

    return bedingungen, parameter


def _pflegestand(state: UiState) -> tuple[Any, Any]:
    """Liest Statusdatei und Ausnahmeliste in ihrem heutigen Stand.

    Die Befunddatei eines Laufs hält den Stand von damals fest und wird nicht
    nachträglich verändert - der Bericht muss zu ihr passen. Wer aber gerade
    in der Oberfläche einen Stand gesetzt hat, will ihn auch sehen. Deshalb
    wird die gespeicherte Pflege über die Anzeige gelegt und als
    ``noch_nicht_im_bericht`` gekennzeichnet.
    """
    config = state.neu_laden()
    return (
        load_status(config.findings.status_file),
        load_whitelist(config.findings.whitelist_file),
    )


def _ueberlagern(zeile: dict[str, Any], speicher: Any, liste: Any) -> dict[str, Any]:
    """Legt den heutigen Pflegestand über einen Befund aus der Laufdatei."""
    offen = False

    eintrag = speicher.get(zeile["finding_id"])
    if eintrag is not None and eintrag.status.value != zeile.get("status"):
        zeile["status_im_bericht"] = zeile.get("status")
        zeile["status"] = eintrag.status.value
        if "status_bemerkung" in zeile:
            zeile["status_bemerkung"] = eintrag.note
        offen = True

    if not zeile.get("ausnahme"):
        treffer = liste.match(
            zeile["finding_id"], zeile.get("rule_id", ""), zeile.get("schluessel", "")
        )
        if treffer is not None:
            zeile["ausnahme_vorgemerkt"] = True
            zeile["ausnahme_grund"] = treffer.reason
            offen = True

    zeile["noch_nicht_im_bericht"] = offen
    return zeile


def befunde(state: UiState, lauf_id: str, werte: Mapping[str, list[str]]) -> dict[str, Any]:
    """Befunde eines Laufs, gefiltert und seitenweise."""
    pfad = _befunddatei(state, lauf_id)
    quelle = f"read_parquet({quote_literal(str(pfad))})"

    bedingungen, parameter = _bedingungen(werte)
    where = (" WHERE " + " AND ".join(bedingungen)) if bedingungen else ""

    try:
        seite = max(int(_erste(werte, "seite", "1")), 1)
        groesse = min(max(int(_erste(werte, "groesse", "50")), 1), MAX_PAGE_SIZE)
    except ValueError:
        raise ApiFehler("Seitenangaben müssen Zahlen sein.") from None

    with duckdb.connect() as con:
        gesamt = con.execute(f"SELECT count(*) FROM {quelle}{where}", parameter).fetchone()[0]
        zeilen = con.execute(
            f"SELECT finding_id, rule_id, rule_name, category_label, severity, severity_rank,"
            f" object_area, object_type, object_key, mandt, bukrs, status, whitelisted,"
            f" whitelist_reason, data_owner, delta_state"
            f" FROM {quelle}{where}"
            " ORDER BY severity_rank, rule_id, object_key"
            f" LIMIT {groesse} OFFSET {(seite - 1) * groesse}",
            parameter,
        ).fetchall()
        spalten = [
            "finding_id", "rule_id", "rule_name", "kategorie", "schweregrad",
            "rang", "bereich", "objektart", "schluessel", "mandant", "buchungskreis",
            "status", "ausnahme", "ausnahme_grund", "data_owner", "vergleich",
        ]

    speicher, liste = _pflegestand(state)
    return {
        "gesamt": gesamt,
        "seite": seite,
        "groesse": groesse,
        "seiten": max((gesamt + groesse - 1) // groesse, 1),
        "befunde": [
            _ueberlagern(dict(zip(spalten, zeile)), speicher, liste) for zeile in zeilen
        ],
    }


def befund(state: UiState, lauf_id: str, finding_id: str) -> dict[str, Any]:
    """Ein einzelner Befund mit Details und der zugehörigen Regel."""
    pfad = _befunddatei(state, lauf_id)
    quelle = f"read_parquet({quote_literal(str(pfad))})"

    with duckdb.connect() as con:
        zeile = con.execute(
            f"SELECT finding_id, rule_id, rule_version, rule_name, category_label,"
            f" requirement, severity, object_area, object_type, object_key, mandt,"
            f" bukrs, detail, status, status_note, whitelisted, whitelist_reason,"
            f" data_owner, delta_state FROM {quelle} WHERE finding_id = ?",
            [finding_id],
        ).fetchone()

    if zeile is None:
        raise ApiFehler("Befund nicht gefunden.", 404)

    spalten = [
        "finding_id", "rule_id", "rule_version", "rule_name", "kategorie",
        "anforderung", "schweregrad", "bereich", "objektart", "schluessel",
        "mandant", "buchungskreis", "detail", "status", "status_bemerkung",
        "ausnahme", "ausnahme_grund", "data_owner", "vergleich",
    ]
    ergebnis = dict(zip(spalten, zeile))
    speicher, liste = _pflegestand(state)
    _ueberlagern(ergebnis, speicher, liste)
    try:
        ergebnis["detail"] = json.loads(ergebnis["detail"] or "{}")
    except json.JSONDecodeError:
        ergebnis["detail"] = {}

    # Regelbeschreibung und Handlungsempfehlung aus der Laufzusammenfassung -
    # sie gilt für diesen Lauf und nicht für den heutigen Katalogstand.
    zusammenfassung = read_summary(state.lauf_verzeichnis(lauf_id) or Path())
    if zusammenfassung:
        for regel in zusammenfassung.get("coverage", {}).get("regeln", []):
            if regel.get("id") == ergebnis["rule_id"]:
                ergebnis["regel"] = regel
                break
    return ergebnis


# -------------------------------------------------------------------- Dubletten
def dubletten(state: UiState, lauf_id: str) -> dict[str, Any]:
    """Alle Dublettencluster eines Laufs, groß zuerst.

    Eigener Aufruf und nicht ein Filter auf die Befundliste: ein Cluster wird
    mit seinen Mitgliedern und deren verglichenen Feldern gebraucht, damit die
    Oberfläche sie nebeneinanderstellen kann. Das aus der Liste heraus je
    Cluster einzeln nachzuladen wäre eine Abfrage je Zeile.
    """
    pfad = _befunddatei(state, lauf_id)
    quelle = f"read_parquet({quote_literal(str(pfad))})"

    with duckdb.connect() as con:
        zeilen = con.execute(
            f"SELECT finding_id, rule_id, rule_name, severity, object_area,"
            f" object_key, detail, status, whitelisted, whitelist_reason"
            f" FROM {quelle} WHERE category = 'duplicate'"
            " ORDER BY severity_rank, rule_id, object_key"
        ).fetchall()

    speicher, liste = _pflegestand(state)
    cluster: list[dict[str, Any]] = []
    for zeile in zeilen:
        try:
            detail = json.loads(zeile[6] or "{}")
        except json.JSONDecodeError:
            detail = {}
        eintrag = {
            "finding_id": zeile[0],
            "rule_id": zeile[1],
            "rule_name": zeile[2],
            "schweregrad": zeile[3],
            "bereich": zeile[4],
            "schluessel": zeile[5],
            "status": zeile[7],
            "ausnahme": zeile[8],
            "ausnahme_grund": zeile[9],
            "anzahl_saetze": detail.get("anzahl_saetze", 0),
            "score": detail.get("aehnlichkeitsscore"),
            "art": detail.get("art_des_treffers", ""),
            "begruendung": detail.get("begruendung", []),
            "namensfeld": detail.get("namensfeld", ""),
            "verglichene_felder": detail.get("verglichene_felder", []),
            "exakte_schluessel": detail.get("exakte_schluessel", []),
            "mitglieder": detail.get("mitglieder", []),
        }
        _ueberlagern(eintrag, speicher, liste)
        cluster.append(eintrag)

    # Große Cluster zuerst: sie binden die meiste Bereinigungsarbeit und
    # eignen sich am besten, um das Verfahren zu zeigen.
    cluster.sort(key=lambda e: (-e["anzahl_saetze"], e["rule_id"], e["schluessel"]))

    betroffene = sum(eintrag["anzahl_saetze"] for eintrag in cluster)
    return {
        "cluster": cluster,
        "anzahl_cluster": len(cluster),
        "betroffene_saetze": betroffene,
        # Was eine Bereinigung an Stammsätzen einspart: je Cluster bleibt
        # einer stehen, die übrigen entfallen.
        "einsparung": betroffene - len(cluster),
        "je_regel": _je_regel(cluster),
    }


def _je_regel(cluster: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Fasst die Cluster je Regel zusammen."""
    gruppen: dict[str, dict[str, Any]] = {}
    for eintrag in cluster:
        gruppe = gruppen.setdefault(
            eintrag["rule_id"],
            {
                "id": eintrag["rule_id"],
                "name": eintrag["rule_name"],
                "schweregrad": eintrag["schweregrad"],
                "bereich": eintrag["bereich"],
                "art": eintrag["art"],
                "cluster": 0,
                "saetze": 0,
            },
        )
        gruppe["cluster"] += 1
        gruppe["saetze"] += eintrag["anzahl_saetze"]
    return sorted(gruppen.values(), key=lambda g: -g["saetze"])


# -------------------------------------------------------------------- Ausnahmen
def ausnahmen(state: UiState) -> dict[str, Any]:
    """Alle hinterlegten Ausnahmen."""
    config = state.neu_laden()
    liste = load_whitelist(config.findings.whitelist_file)
    return {
        "datei": str(config.findings.whitelist_file)
        if config.findings.whitelist_file
        else "",
        "eintraege": [
            {
                "finding_id": eintrag.finding_id or "",
                "regel": eintrag.rule_id or "",
                "schluessel": eintrag.object_key or "",
                "muster": eintrag.object_key_pattern or "",
                "begruendung": eintrag.reason,
                "freigegeben_von": eintrag.approved_by,
                "freigegeben_am": eintrag.approved_on.isoformat() if eintrag.approved_on else "",
                "laeuft_ab": eintrag.expires_on.isoformat() if eintrag.expires_on else "",
                "verweis": eintrag.reference,
                "wirksam": not eintrag.expired(),
                "geltungsbereich": eintrag.scope_description,
            }
            for eintrag in liste.entries
        ],
    }


def ausnahme_setzen(state: UiState, daten: Mapping[str, Any]) -> dict[str, Any]:
    """Nimmt eine Ausnahme auf (FA-602)."""
    config = state.neu_laden()
    pfad = config.findings.whitelist_file
    if pfad is None:
        raise ApiFehler(
            "In der Projektkonfiguration ist keine Ausnahmeliste hinterlegt "
            "(findings.whitelist_file)."
        )

    begruendung = str(daten.get("begruendung", "")).strip()
    if not begruendung:
        raise ApiFehler(
            "Eine Ausnahme braucht eine Begründung. Ohne sie ist sie in einer "
            "prüffesten Auswertung nicht vertretbar."
        )
    if not any(daten.get(feld) for feld in ("finding_id", "regel", "schluessel", "muster")):
        raise ApiFehler("Die Ausnahme muss benennen, wofür sie gilt.")

    ablauf = str(daten.get("laeuft_ab", "")).strip()
    ablaufdatum = parse_date(ablauf) if ablauf else None
    if ablauf and ablaufdatum is None:
        raise ApiFehler(f"'{ablauf}' ist kein gültiges Datum.")

    liste = load_whitelist(pfad)
    eintrag = WhitelistEntry(
        reason=begruendung,
        approved_by=str(daten.get("freigegeben_von", "")).strip(),
        approved_on=date.today(),
        expires_on=ablaufdatum,
        finding_id=str(daten["finding_id"]).strip() if daten.get("finding_id") else None,
        rule_id=str(daten["regel"]).strip().upper() if daten.get("regel") else None,
        object_key=str(daten["schluessel"]).strip() if daten.get("schluessel") else None,
        object_key_pattern=str(daten["muster"]).strip() if daten.get("muster") else None,
        reference=str(daten.get("verweis", "")).strip(),
    )
    liste.entries.append(eintrag)
    save_whitelist(liste, pfad)
    logger.info("Ausnahme aufgenommen: %s", eintrag.scope_description)
    return {
        "aufgenommen": True,
        "geltungsbereich": eintrag.scope_description,
        "hinweis": (
            "Die Ausnahme wirkt ab dem nächsten Lauf. Der aktuelle Bericht "
            "bleibt unverändert - er ist bereits geschrieben."
        ),
    }


def ausnahme_entfernen(state: UiState, daten: Mapping[str, Any]) -> dict[str, Any]:
    """Nimmt eine Ausnahme zurück."""
    config = state.neu_laden()
    pfad = config.findings.whitelist_file
    if pfad is None or not pfad.is_file():
        raise ApiFehler("Es ist keine Ausnahmeliste vorhanden.", 404)

    finding_id = str(daten.get("finding_id", "")).strip()
    regel = str(daten.get("regel", "")).strip().upper()
    schluessel = str(daten.get("schluessel", "")).strip()
    if not any((finding_id, regel, schluessel)):
        raise ApiFehler("Es wurde nicht benannt, welche Ausnahme entfallen soll.")

    liste = load_whitelist(pfad)
    vorher = len(liste.entries)
    liste.entries = [
        eintrag
        for eintrag in liste.entries
        if not (
            (not finding_id or eintrag.finding_id == finding_id)
            and (not regel or eintrag.rule_id == regel)
            and (not schluessel or eintrag.object_key == schluessel)
        )
    ]
    entfernt = vorher - len(liste.entries)
    if entfernt:
        save_whitelist(liste, pfad)
    return {"entfernt": entfernt}


# ----------------------------------------------------------------------- Status
def status_setzen(state: UiState, daten: Mapping[str, Any]) -> dict[str, Any]:
    """Setzt den Bearbeitungsstand eines Befundes (FA-603)."""
    config = state.neu_laden()
    pfad = config.findings.status_file
    if pfad is None:
        raise ApiFehler(
            "In der Projektkonfiguration ist keine Statusdatei hinterlegt "
            "(findings.status_file)."
        )
    finding_id = str(daten.get("finding_id", "")).strip()
    if not finding_id:
        raise ApiFehler("Es wurde kein Befund benannt.")

    speicher = load_status(pfad)
    stand = FindingStatus.parse(str(daten.get("status", "")))
    speicher.set_status(
        finding_id,
        stand,
        note=str(daten.get("bemerkung", "")).strip(),
        updated_by=str(daten.get("bearbeiter", "")).strip(),
        rule_id=str(daten.get("regel", "")).strip().upper(),
        object_key=str(daten.get("schluessel", "")).strip(),
    )
    save_status(speicher, pfad)
    return {
        "gesetzt": stand.value,
        "hinweis": "Der Stand wird beim nächsten Lauf in den Bericht übernommen.",
    }


# -------------------------------------------------------------------- Lauf
def lauf_starten(state: UiState, daten: Mapping[str, Any]) -> dict[str, Any]:
    """Startet einen Prüfungslauf im Hintergrund."""
    gestartet, meldung = state.lauf_starten(force=bool(daten.get("force")))
    if not gestartet:
        raise ApiFehler(meldung, 409)
    return {"gestartet": True, "meldung": meldung}


def fortschritt(state: UiState) -> dict[str, Any]:
    """Stand des laufenden oder zuletzt gelaufenen Auftrags."""
    return state.auftrag.als_dict()


# ------------------------------------------------------------------ Vergleich
def vergleich(state: UiState, werte: Mapping[str, list[str]]) -> dict[str, Any]:
    """Vergleicht zwei Läufe (FA-605)."""
    from sapmdq.findings.delta import compare_runs

    vorher_id = _erste(werte, "vorher")
    jetzt_id = _erste(werte, "jetzt")
    if not vorher_id or not jetzt_id:
        raise ApiFehler("Es müssen zwei Läufe benannt werden.")
    if vorher_id == jetzt_id:
        raise ApiFehler("Ein Lauf lässt sich nicht mit sich selbst vergleichen.")

    vorher = _befunddatei(state, vorher_id)
    jetzt = _befunddatei(state, jetzt_id)

    with duckdb.connect() as con:
        bericht = compare_runs(con, vorher, jetzt)

    a = read_summary(state.lauf_verzeichnis(vorher_id) or Path()) or {}
    b = read_summary(state.lauf_verzeichnis(jetzt_id) or Path()) or {}
    katalog_a = a.get("regelkatalog", {}).get("version", "")
    katalog_b = b.get("regelkatalog", {}).get("version", "")

    warnungen = []
    if katalog_a and katalog_b and katalog_a != katalog_b:
        warnungen.append(
            f"Die Läufe haben unterschiedliche Regelkataloge benutzt ({katalog_a} "
            f"gegen {katalog_b}). Die Differenz zeigt dann auch die Änderung des "
            "Maßstabs und nicht allein den Fortschritt der Daten."
        )
    anteil_a = a.get("coverage", {}).get("anteil")
    anteil_b = b.get("coverage", {}).get("anteil")
    if anteil_a is not None and anteil_b is not None and anteil_a != anteil_b:
        warnungen.append(
            f"Der Coverage-Grad hat sich geändert ({anteil_a:.0%} gegen "
            f"{anteil_b:.0%}). Es wurde nicht dasselbe geprüft."
        )

    return {
        "vorher": vorher_id,
        "jetzt": jetzt_id,
        "zusammenfassung": bericht.summary_line(),
        "neu": bericht.new_findings,
        "behoben": bericht.resolved_findings,
        "unveraendert": bericht.unchanged_findings,
        "anerkannte_ausnahmen": bericht.newly_whitelisted,
        "warnungen": warnungen,
        "je_regel": [
            {
                "id": eintrag.rule_id,
                "name": eintrag.rule_name,
                "schweregrad": eintrag.severity,
                "vorher": eintrag.baseline,
                "jetzt": eintrag.current,
                "neu": eintrag.new,
                "behoben": eintrag.resolved,
            }
            for eintrag in bericht.by_rule
            if eintrag.change != 0
        ],
    }


# ------------------------------------------------------------------- Eingang
#: Namen, die Windows für Geräte reserviert. Eine Datei "con.csv" liesse sich
#: dort nicht anlegen; abgelehnt wird sie hier trotzdem auf jedem System,
#: damit dieselbe Lieferung überall gleich behandelt wird.
_GERAETENAMEN = {
    "con", "prn", "aux", "nul",
    *(f"com{n}" for n in range(1, 10)),
    *(f"lpt{n}" for n in range(1, 10)),
}

#: Höchstgröße einer hochgeladenen Datei. Eine Extraktion aus MARA kann
#: mehrere hundert Megabyte haben; darüber ist der Weg über das Dateisystem
#: der ehrlichere.
MAX_UPLOAD = 512 * 1024 * 1024


def erlaubte_endungen() -> list[str]:
    """Was hochgeladen werden darf.

    Die Lesbarkeit entscheidet: Lieferdateien plus der Begleitzettel. Alles
    andere wäre eine Datei, die im Eingang liegt und nichts bewirkt.
    """
    from sapmdq.ingest.mapping import KNOWN_SUFFIXES

    return sorted(KNOWN_SUFFIXES | {".yaml", ".yml"})


def sicherer_dateiname(name: str) -> str:
    """Prüft einen vom Browser gemeldeten Dateinamen.

    Der Name kommt vom Benutzer und bestimmt, wohin geschrieben wird - das
    ist die einzige Stelle der Oberfläche, an der das so ist. Deshalb wird
    nicht bereinigt, sondern abgelehnt: ein Name, der nicht durchgeht, wird
    gemeldet und nicht stillschweigend zu etwas anderem gemacht.
    """
    name = (name or "").strip()
    if not name:
        raise uebersetzbar("Es wurde kein Dateiname übergeben.")
    if len(name) > 120:
        raise uebersetzbar("Der Dateiname ist zu lang (höchstens 120 Zeichen).")
    if name != Path(name).name or name in (".", ".."):
        raise uebersetzbar("Der Dateiname enthält einen Pfad: {name}", name=name)
    if any(zeichen in name for zeichen in '/\\:*?"<>|') or any(ord(z) < 32 for z in name):
        raise uebersetzbar("Der Dateiname enthält unzulässige Zeichen: {name}", name=name)
    if name.startswith("."):
        raise uebersetzbar("Ein Dateiname darf nicht mit einem Punkt beginnen.")
    if Path(name).stem.lower() in _GERAETENAMEN:
        raise uebersetzbar("Der Dateiname ist ein reservierter Name: {name}", name=name)

    erlaubt = erlaubte_endungen()
    if Path(name).suffix.lower() not in erlaubt:
        raise uebersetzbar(
            "Diese Dateiendung wird nicht gelesen: {name}. Möglich sind {endungen}.",
            name=name,
            endungen=", ".join(erlaubt),
        )
    return name


def eingangsziel(state: UiState, name: str) -> Path:
    """Liefert den Zielpfad einer Eingangsdatei.

    Der Name ist zu diesem Zeitpunkt schon geprüft. Die zweite Prüfung gegen
    das aufgelöste Verzeichnis kostet nichts und hält, falls die erste je
    eine Lücke bekommt.
    """
    verzeichnis = state.neu_laden().paths.input_dir
    verzeichnis.mkdir(parents=True, exist_ok=True)
    ziel = (verzeichnis / sicherer_dateiname(name)).resolve()
    try:
        ziel.relative_to(verzeichnis.resolve())
    except ValueError:
        raise uebersetzbar(
            "Der Dateiname führt aus dem Eingangsverzeichnis: {name}", name=name
        ) from None
    return ziel


def _dateiangabe(pfad: Path, gelesen: bool) -> dict[str, Any]:
    daten = pfad.stat()
    return {
        "name": pfad.name,
        "groesse": daten.st_size,
        "geaendert": datetime.fromtimestamp(daten.st_mtime).isoformat(timespec="seconds"),
        "wird_gelesen": gelesen,
    }


def eingang(state: UiState) -> dict[str, Any]:
    """Inhalt des Eingangsverzeichnisses.

    Aufgeführt wird alles, was dort liegt - auch eine Datei, die kein Lauf
    anfassen wird. Sie stillschweigend zu verschweigen wäre die schlechtere
    Auskunft: wer eine Datei hochgeladen hat, will sie wiederfinden.
    """
    from sapmdq.ingest.mapping import collect_input_files

    config = state.neu_laden()
    verzeichnis = config.paths.input_dir
    if not verzeichnis.is_dir():
        return {
            "verzeichnis": str(verzeichnis),
            "dateien": [],
            "hoechstgroesse": MAX_UPLOAD,
            "endungen": erlaubte_endungen(),
        }

    gelesen = {pfad.name for pfad in collect_input_files(verzeichnis, config.ingestion.ignore_patterns)}
    dateien = [
        _dateiangabe(pfad, pfad.name in gelesen)
        for pfad in sorted(verzeichnis.iterdir())
        if pfad.is_file()
    ]
    return {
        "verzeichnis": str(verzeichnis),
        "dateien": dateien,
        "hoechstgroesse": MAX_UPLOAD,
        "endungen": erlaubte_endungen(),
    }


def eingang_entfernen(state: UiState, daten: Mapping[str, Any]) -> dict[str, Any]:
    """Löscht eine Datei aus dem Eingangsverzeichnis.

    Gelöscht wird nur im Eingang. Ein Lauf, der die Datei schon gelesen hat,
    bleibt davon unberührt - seine Ergebnisse liegen im Ausgabeverzeichnis.
    """
    name = str(daten.get("name", ""))
    ziel = eingangsziel(state, name)
    if not ziel.is_file():
        raise uebersetzbar("Diese Datei liegt nicht im Eingang: {name}", 404, name=name)
    ziel.unlink()
    logger.info("Eingangsdatei entfernt: %s", ziel.name)
    return {"entfernt": ziel.name}


# ------------------------------------------------------------------ Projekte
def _projektangabe(pfad: Path, aktuell: Path | None) -> dict[str, Any]:
    """Beschreibt ein Projekt für die Liste.

    Name und Kunde werden aus der Konfiguration gelesen, nicht aus der Liste:
    wer sie in der Datei ändert, sieht die Änderung sofort. Lässt sich die
    Konfiguration nicht laden - verschobenes Verzeichnis, kaputtes YAML -,
    bleibt der Eintrag trotzdem stehen und sagt, was los ist. Ein Projekt,
    das stillschweigend aus der Liste verschwindet, ist schwerer zu finden
    als eines mit einer roten Zeile.
    """
    from sapmdq.config import load_config
    from sapmdq.errors import SapMdqError

    angabe: dict[str, Any] = {
        "pfad": str(pfad),
        "verzeichnis": str(pfad.parent),
        "aktuell": aktuell is not None and pfad == aktuell,
        "lesbar": False,
        "name": pfad.parent.name,
    }
    try:
        config = load_config(pfad)
    except (SapMdqError, OSError) as fehler:
        angabe["fehler"] = str(fehler)
        return angabe

    laufverzeichnis = config.paths.output_dir / "runs"
    laeufe = (
        sorted(p.name for p in laufverzeichnis.iterdir() if p.is_dir())
        if laufverzeichnis.is_dir()
        else []
    )
    eingang = config.paths.input_dir
    angabe.update(
        {
            "lesbar": True,
            "name": config.project.name,
            "kunde": config.project.customer,
            "quellsystem": config.project.source_system,
            "analyst": config.project.analyst,
            "laeufe": len(laeufe),
            "letzter_lauf": laeufe[-1] if laeufe else "",
            "eingangsdateien": (
                len([p for p in eingang.iterdir() if p.is_file()]) if eingang.is_dir() else 0
            ),
        }
    )
    return angabe


def projekte(state: UiState) -> dict[str, Any]:
    """Alle bekannten Projekte, zuletzt geöffnetes zuerst."""
    from sapmdq import projekte as liste

    aktuell = Path(state.config.source_path).resolve() if state.config.source_path else None
    eintraege = liste.laden()
    bekannt = {eintrag.pfad for eintrag in eintraege}

    angaben = []
    for eintrag in eintraege:
        angabe = _projektangabe(eintrag.pfad, aktuell)
        angabe["zuletzt_geoeffnet"] = eintrag.zuletzt_geoeffnet
        angaben.append(angabe)

    # Das laufende Projekt gehört in die Liste, auch wenn es noch nie
    # aufgenommen wurde - etwa weil die Liste gerade gelöscht wurde.
    if aktuell is not None and aktuell not in bekannt:
        angaben.insert(0, {**_projektangabe(aktuell, aktuell), "zuletzt_geoeffnet": ""})

    return {
        "aktuell": str(aktuell) if aktuell else "",
        "liste": str(liste.listenpfad()),
        "projekte": angaben,
        "quellsysteme": ["ECC", "S4"],
    }


def _pfadangabe(daten: Mapping[str, Any], feld: str = "pfad") -> str:
    pfad = str(daten.get(feld, "")).strip()
    if not pfad:
        raise uebersetzbar("Es wurde kein Pfad angegeben.")
    return pfad


def projekt_oeffnen(state: UiState, daten: Mapping[str, Any]) -> dict[str, Any]:
    """Bindet die Sitzung an ein anderes Projekt."""
    from sapmdq import projekte as liste
    from sapmdq.errors import SapMdqError

    pfad = _pfadangabe(daten)
    try:
        ziel = liste.pruefen(pfad)
    except (SapMdqError, OSError) as fehler:
        raise uebersetzbar(
            "Dieses Projekt lässt sich nicht öffnen: {grund}", 400, grund=str(fehler)
        ) from None

    try:
        config = state.wechseln(ziel)
    except RuntimeError:
        raise uebersetzbar(
            "Während eines Prüfungslaufs lässt sich das Projekt nicht wechseln.", 409
        ) from None

    liste.geoeffnet(ziel)
    return {"geoeffnet": str(ziel), "name": config.project.name}


def projekt_aufnehmen(state: UiState, daten: Mapping[str, Any]) -> dict[str, Any]:
    """Nimmt ein bestehendes Projekt in die Liste auf."""
    from sapmdq import projekte as liste
    from sapmdq.errors import SapMdqError

    pfad = _pfadangabe(daten)
    try:
        ziel = liste.aufnehmen(pfad)
    except (SapMdqError, OSError) as fehler:
        raise uebersetzbar(
            "Dort liegt kein lesbares Projekt: {grund}", 400, grund=str(fehler)
        ) from None
    return {"aufgenommen": str(ziel)}


def projekt_entfernen(state: UiState, daten: Mapping[str, Any]) -> dict[str, Any]:
    """Nimmt ein Projekt aus der Liste - die Dateien bleiben liegen."""
    from sapmdq import projekte as liste

    pfad = _pfadangabe(daten)
    if state.config.source_path and Path(pfad).expanduser().resolve() == Path(
        state.config.source_path
    ).resolve():
        raise uebersetzbar(
            "Das gerade geöffnete Projekt lässt sich nicht aus der Liste nehmen.", 409
        )
    if not liste.entfernen(pfad):
        raise uebersetzbar("Dieses Projekt steht nicht in der Liste: {pfad}", 404, pfad=pfad)
    return {"entfernt": pfad}


def projekt_anlegen(state: UiState, daten: Mapping[str, Any]) -> dict[str, Any]:
    """Legt ein neues Projektverzeichnis an, nimmt es auf und öffnet es."""
    from sapmdq import projekte as liste
    from sapmdq.errors import SapMdqError

    verzeichnis = _pfadangabe(daten, "verzeichnis")
    try:
        ziel = liste.anlegen(
            verzeichnis,
            name=str(daten.get("name", "")),
            kunde=str(daten.get("kunde", "")),
            quellsystem=str(daten.get("quellsystem", "ECC")).upper() or "ECC",
            analyst=str(daten.get("analyst", "")),
        )
    except (SapMdqError, OSError) as fehler:
        raise uebersetzbar(
            "Das Projekt ließ sich nicht anlegen: {grund}", 400, grund=str(fehler)
        ) from None

    liste.aufnehmen(ziel, geoeffnet=True)
    config = state.wechseln(ziel)
    return {"angelegt": str(ziel), "name": config.project.name}
