"""Zuordnung eines Data Owners je Befund (FA-604).

Ein Befund ohne benannte Verantwortung bleibt liegen. Die Zuordnung erfolgt
ueber die Projektkonfiguration und wird von der genauesten zur allgemeinsten
Angabe aufgeloest: erst die einzelne Regel, dann die Kategorie, dann der
Objektbereich, zuletzt eine allgemeine Vorgabe.
"""

from __future__ import annotations

from typing import Mapping

#: Schluessel fuer die allgemeine Vorgabe.
DEFAULT_KEY = "default"


def resolve_owner(
    owners: Mapping[str, str], rule_id: str, category: str, object_area: str
) -> str:
    """Bestimmt den zustaendigen Data Owner eines Befundes.

    Die Aufloesung geht von der genauesten zur allgemeinsten Angabe. Damit
    laesst sich eine einzelne heikle Regel abweichend zuordnen, ohne die
    Zuordnung des ganzen Objektbereichs aufzugeben.
    """
    if not owners:
        return ""
    for key in (rule_id.lower(), category.lower(), object_area.lower(), DEFAULT_KEY):
        owner = owners.get(key)
        if owner:
            return owner
    return ""
