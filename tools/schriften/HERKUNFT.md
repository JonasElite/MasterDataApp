# Schriften des One-Pagers

Die drei Familien liegen hier als `woff2` im Subset `latin` (es trägt die
deutschen Umlaute und das Eszett). `tools/onepager.py` bettet sie als
Data-URI in das erzeugte Blatt ein. Das hat zwei Gründe: das Blatt bleibt
eine einzelne Datei, die sich weiterreichen lässt, und es sieht auch dort
richtig aus, wo kein Netz ist - das Werkzeug selbst wirbt schließlich damit,
lokal und offline zu laufen.

| Datei | Familie | Schnitt | Herkunft |
|---|---|---|---|
| `Archivo-500/600/700.woff2` | Archivo | Medium, SemiBold, Bold | Omnibus-Type |
| `SourceSans3-400/600.woff2` | Source Sans 3 | Regular, SemiBold | Adobe |
| `IBMPlexMono-500.woff2` | IBM Plex Mono | Medium | IBM |

Alle drei stehen unter der **SIL Open Font License 1.1** und dürfen
eingebettet und weitergegeben werden. Die Dateien stammen unverändert von
Google Fonts (`fonts.gstatic.com`).

Erneuern lassen sie sich mit `python tools/schriften_holen.py`.
