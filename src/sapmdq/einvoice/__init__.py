"""E-Rechnungs-Readiness nach EN 16931.

Beantwortet die Frage, ob aus dem heutigen Debitorenstamm heraus
normkonforme Rechnungen erzeugt werden können - und woran es scheitert.

**Was hier geprüft wird und was nicht.** Geprüft wird ausschließlich die
Datengrundlage vor der Rechnung: Stammdaten des Rechnungsstellers, des
Empfängers und die Zahlungsbedingungen. Nicht geprüft werden Belege
(VBRK/VBRP, BKPF/BSEG), Steuerkennzeichen und fertige XML-Dateien. Damit
fehlt die Belegsicht - also die Gewichtung der Mängel mit dem tatsächlichen
Rechnungsvolumen. Der Bericht sagt, wieviele Geschäftspartner betroffen
sind, nicht wieviel Umsatz. Beides steht in der Oberfläche nebeneinander,
damit niemand das eine für das andere hält.

Das ist keine Rechtsberatung. Die Abgrenzung bildet gesetzliche Tatbestände
ab und ersetzt keine Einzelfallwürdigung.
"""

from sapmdq.einvoice.abgrenzung import (
    BEREICH,
    Abgrenzung,
    Ausschluss,
    Gruppe,
    bewerten,
    bezugsgroessen,
    ermittle_abgrenzung,
    parameter_setzen,
)

__all__ = [
    "BEREICH",
    "Abgrenzung",
    "Ausschluss",
    "Gruppe",
    "bewerten",
    "bezugsgroessen",
    "ermittle_abgrenzung",
    "parameter_setzen",
]
