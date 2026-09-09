/* Sprachen der Oberflaeche.
 *
 * Der deutsche Text ist die Quelle und zugleich der Schluessel. Das hat einen
 * praktischen Grund: fehlt eine Uebersetzung, erscheint der deutsche Satz -
 * unschoen, aber lesbar. Ein Schluesselwort wie "befunde.leer" erschiene
 * stattdessen als solches, und niemand koennte damit etwas anfangen.
 *
 * Damit daraus keine stille Nachlaessigkeit wird, prueft
 * ``tests/test_ui_sprachen.py``, dass jeder in der Oberflaeche verwendete Text
 * eine englische Fassung hat.
 *
 * Platzhalter stehen in geschweiften Klammern: t("{n} Befunde", {n: 5}).
 */
"use strict";

const SPRACHEN = { de: "Deutsch", en: "English" };
const SPRACHE_SPEICHER = "sapmdq.sprache";

/** Woerterbuch Deutsch -> Englisch. */
const EN = {
  // ------------------------------------------------------------ Grundgeruest
  "SAP-Stammdatenpruefung": "SAP Master Data Check",
  "Stammdaten­pruefung": "Master Data Check",
  "Sitzungsmerkmal fehlt": "Session token missing",
  "Die Oberflaeche wird ueber die Adresse aus der Startmeldung geoeffnet. Sie enthaelt das Merkmal dieser Sitzung. Ohne es antwortet der Server nicht.":
    "Open the interface using the address printed at startup. It carries this session's token. Without it the server does not respond.",
  "Beispiel:": "Example:",
  "Bereiche": "Sections",
  "Sprache": "Language",
  "Angezeigter Lauf": "Selected run",
  "Angezeigten Lauf waehlen": "Select the run to display",
  "Praesentation": "Presentation",
  "Pruefung starten": "Start check",

  // ---------------------------------------------------------------- Ansichten
  "Lagebild": "Overview",
  "Befunde": "Findings",
  "Dubletten": "Duplicates",
  "Pruefumfang": "Scope",
  "Lieferung": "Delivery",
  "Ausnahmen": "Exceptions",
  "Laeufe": "Runs",

  // ----------------------------------------------------------------- Lagebild
  "Datenqualitaet": "Data quality",
  "Auf einen Blick": "At a glance",
  "Befunde nach Schweregrad": "Findings by severity",
  "Befunde nach Objektbereich": "Findings by object area",
  "Zum Filtern auf eine Zeile klicken.": "Click a row to filter.",
  "Woran es am haeufigsten liegt": "Most frequent causes",
  "Was eine Nachlieferung braechte": "What a follow-up delivery would unlock",
  "Nach Wirkung geordnet: wieviele zusaetzliche Pruefungen die Tabelle freischaltet.":
    "Ordered by effect: how many additional checks each table unlocks.",
  "Bewertung je Bereich": "Score by area",
  "Der Wert ist unter dem Vorbehalt des jeweils erreichten Pruefumfangs zu lesen. Was nicht geprueft werden konnte, geht nicht ein.":
    "Read the score subject to the scope actually achieved. What could not be checked is not reflected in it.",
  "Befunde offen": "Open findings",
  "kritisch": "critical",
  "hoch": "high",
  "mittel": "medium",
  "Regelfehler": "Rule failures",
  "gegen den Vorlauf": "vs. previous run",
  "Ohne die als Ausnahme anerkannten Befunde.": "Excluding findings accepted as exceptions.",
  "Befunde, die mit Begruendung anerkannt wurden.": "Findings accepted with a documented reason.",
  "Das Ergebnis ist unvollstaendig.": "The result is incomplete.",
  "Alle Regeln liefen durch.": "All rules completed.",
  "Kein Lauf ausgewaehlt.": "No run selected.",
  "Keine Befunde.": "No findings.",
  "Nichts vorhanden.": "Nothing to show.",
  "Die Lieferung ist vollstaendig - es fehlt nichts.":
    "The delivery is complete - nothing is missing.",
  "unveraendert": "unchanged",
  "von 100 Punkten": "out of 100 points",

  // ---------------------------------------------------------------- Lieferung
  "Dateien": "Files",
  "Tabellen": "Tables",
  "Pruefungen der Lieferung": "Delivery checks",
  "Die Lieferung ist verwertbar.": "The delivery is usable.",
  "Die Lieferung ist nicht verwertbar. Der Lauf wurde nur mit ausdruecklicher Freigabe fortgesetzt; die Ergebnisse sind entsprechend eingeschraenkt.":
    "The delivery is not usable. The run continued only after explicit approval; the results are limited accordingly.",
  "Datei": "File",
  "Tabelle": "Table",
  "Zuordnung": "Assignment",
  "Format": "Format",
  "Zeilen": "Rows",
  "Abgewiesen": "Rejected",
  "Stichtag": "Extraction date",
  "Groesse": "Size",
  "SHA-256": "SHA-256",
  "Bereich": "Area",
  "Saetze": "Records",
  "Vor Filter": "Before filter",
  "Spalten": "Columns",
  "Mandanten": "Clients",
  "Quelldateien": "Source files",
  "Pruefung": "Check",
  "Gewicht": "Weight",
  "Gegenstand": "Subject",
  "Anforderung": "Requirement",
  "Meldung": "Message",

  // -------------------------------------------------------------- Pruefumfang
  "Nachforderung": "Follow-up request",
  "Was zusaetzlich geliefert werden muesste, damit die entfallenen Regeln laufen koennen - nach Wirkung geordnet.":
    "What would need to be delivered so the skipped rules can run - ordered by effect.",
  "Regeln": "Rules",
  "Regel suchen": "Search rules",
  "nur entfallene": "skipped only",
  "Einstufung": "Tier",
  "Bedeutung": "Meaning",
  "Status": "Status",
  "geliefert": "delivered",
  "fehlt": "missing",
  "Fehlende Felder": "Missing fields",
  "Kumuliert": "Cumulative",
  "Regel": "Rule",
  "Bezeichnung": "Name",
  "Kategorie": "Category",
  "Grad": "Severity",
  "Ausfuehrbar": "Executable",
  "Grund": "Reason",
  "ja": "yes",
  "nein": "no",
  "unverzichtbar": "essential",
  "Was geprueft wird": "What is checked",
  "Handlungsempfehlung": "Recommended action",
  "Schweregrad": "Severity",
  "Regelversion": "Rule version",
  "Keine Angaben zum Pruefumfang.": "No scope information available.",

  // ----------------------------------------------------------------- Befunde
  "Schluessel, Regel oder Detail": "Key, rule or detail",
  "Befunde durchsuchen": "Search findings",
  "Schweregrad: alle": "Severity: all",
  "Bereich: alle": "Area: all",
  "Kategorie: alle": "Category: all",
  "Bearbeitungsstand": "Processing state",
  "Stand: alle": "State: all",
  "Vergleich zum Vorlauf": "Comparison with previous run",
  "Vergleich: alle": "Comparison: all",
  "Ausnahmen zeigen": "Show exceptions",
  "Filter loeschen": "Clear filters",
  "Zurueck": "Back",
  "Weiter": "Next",
  "Objekt": "Object",
  "Mandant": "Client",
  "Stand": "State",
  "Vergleich": "Comparison",
  "Ausnahme": "Exception",
  "Zustaendig": "Owner",
  "Buchungskreis": "Company code",
  "Befund": "Finding",
  "Befundangaben": "Finding details",
  "Merkmal": "Attribute",
  "Wert": "Value",
  "Befundkennung": "Finding ID",
  "nicht hinterlegt": "not assigned",
  "Als Ausnahme anerkannt": "Accepted as an exception",
  "Als Ausnahme vorgemerkt": "Exception pending",
  "Als Ausnahme anerkennen": "Accept as an exception",
  "ohne Begruendung": "no reason given",
  "Ausnahme zuruecknehmen": "Withdraw exception",
  "vorgemerkt": "pending",
  "Die Ausnahme steht in der Ausnahmeliste, ist aber in diesem Bericht noch nicht beruecksichtigt. Sie wirkt ab dem naechsten Lauf.":
    "The exception is on the list but is not yet reflected in this report. It takes effect from the next run.",
  "Der Stand wird in der Statusdatei des Projekts gefuehrt und beim naechsten Lauf uebernommen (FA-603).":
    "The state is kept in the project's status file and applied on the next run (FA-603).",
  "Bemerkung (freiwillig)": "Note (optional)",
  "Bearbeiter": "Handled by",
  "Stand speichern": "Save state",
  "Die Ausnahme wird in der Ausnahmeliste des Projekts gefuehrt. Sie wirkt ab dem naechsten Lauf; der bereits geschriebene Bericht bleibt unveraendert (FA-602).":
    "The exception is kept in the project's exception list. It takes effect from the next run; the report already written stays unchanged (FA-602).",
  "Begruendung - warum ist der Befund vertretbar?": "Reason - why is this finding acceptable?",
  "Freigegeben von": "Approved by",
  "Verweis (Ticket, Protokoll)": "Reference (ticket, minutes)",
  "Laeuft ab": "Expires",
  "Geltungsbereich": "Scope",
  "nur dieser Befund": "this finding only",
  "dieses Objekt in dieser Regel": "this object within this rule",
  "alle Befunde dieser Regel": "all findings of this rule",
  "laeuft ab am": "expires on",
  "Ausnahme aufnehmen": "Add exception",
  "Gepflegt, aber noch nicht in den Bericht uebernommen - das geschieht beim naechsten Lauf.":
    "Maintained but not yet reflected in the report - that happens on the next run.",
  "Stand im Bericht": "State in the report",

  // --------------------------------------------------------------- Dubletten
  "Cluster": "Clusters",
  "Nach Regel": "By rule",
  "Name oder Schluessel": "Name or key",
  "Cluster durchsuchen": "Search clusters",
  "Art des Treffers": "Type of match",
  "Nachweis: alle": "Evidence: all",
  "exakt - harter Schluessel": "exact - hard key",
  "unscharf - Namensaehnlichkeit": "fuzzy - name similarity",
  "Alle aufklappen": "Expand all",
  "Alle zuklappen": "Collapse all",
  "aufklappen": "expand",
  "zuklappen": "collapse",
  "Betroffene Saetze": "Records affected",
  "mutmasslich mehrfach angelegt": "presumed created more than once",
  "in allen Clustern zusammen": "across all clusters",
  "Bereinigungspotenzial": "Cleanup potential",
  "Saetze entfallen, wenn je Cluster einer fuehrend wird":
    "records removed once one record per cluster becomes the leading one",
  "harter Schluessel": "hard key",
  "Keine Dubletten gefunden.": "No duplicates found.",
  "Kein Cluster passt zu diesem Filter.": "No cluster matches this filter.",
  "Befund oeffnen": "Open finding",
  "exakt": "exact",
  "unscharf": "fuzzy",
  "weicht von den uebrigen Saetzen ab": "differs from the other records",
  "in allen Saetzen gleich": "identical in all records",
  "Name": "Name",

  // --------------------------------------------------------------- Ausnahmen
  "Hinterlegte Ausnahmen": "Recorded exceptions",
  "In der Projektkonfiguration ist keine Ausnahmeliste hinterlegt.":
    "No exception list is configured in the project.",
  "Begruendung": "Reason",
  "Am": "On",
  "Verweis": "Reference",
  "Wirksam": "In effect",
  "abgelaufen": "expired",
  "entfernen": "remove",

  // ------------------------------------------------------------------ Laeufe
  "Zwei Laeufe vergleichen": "Compare two runs",
  "Frueherer Lauf": "Earlier run",
  "Spaeterer Lauf": "Later run",
  "gegen": "vs.",
  "Vergleichen": "Compare",
  "Lauf": "Run",
  "Zeitpunkt": "Time",
  "Dauer": "Duration",
  "Umfang": "Scope",
  "Punkte": "Points",
  "Katalog": "Catalogue",
  "Zustand": "State",
  "unvollstaendig": "incomplete",
  "vollstaendig": "complete",
  "Wird berechnet ...": "Calculating ...",
  "Behoben": "Resolved",
  "Neu": "New",
  "Unveraendert": "Unchanged",
  "Anerkannte Ausnahmen": "Accepted exceptions",
  "nicht behoben, nur anerkannt": "not resolved, only accepted",
  "Vorher": "Before",
  "Jetzt": "Now",
  "Zu diesem Lauf gibt es keine Zusammenfassung. Er wurde vermutlich abgebrochen.":
    "There is no summary for this run. It was probably aborted.",

  // ------------------------------------------------------------ Lauf starten
  "Pruefungslauf": "Check run",
  "Schliessen": "Close",
  "Kein Lauf gestartet.": "No run started.",
  "Beenden": "Quit",
  "Als PDF": "As PDF",
  "Vorige Folie": "Previous slide",
  "Naechste Folie": "Next slide",

  // ------------------------------------------------------- Praesentationsfolien
  "Titel": "Title",
  "Analyse der Stammdatenqualitaet": "Master data quality analysis",
  "Stammdatenpruefung": "Master data check",
  "Was geprueft wurde": "What was checked",
  "Worueber eine Aussage moeglich ist": "What can be stated at all",
  "Ergebnis": "Result",
  "Datenqualitaet insgesamt": "Overall data quality",
  "Wo die Befunde liegen": "Where the findings are",
  "Nach Kategorie": "By category",
  "Mehrfach angelegte Stammsaetze": "Master records created more than once",
  "Naechste Schritte": "Next steps",
  "Ohne Lauf laesst sich nichts zeigen.": "There is nothing to show without a run.",
  "Berechtigte Faelle als Ausnahme mit Begruendung vermerken, damit sie im Folgelauf nicht erneut als Befund erscheinen.":
    "Record legitimate cases as exceptions with a reason so they do not reappear as findings in the next run.",
  "Nach der Bereinigung erneut messen - die Aussage liegt im Verlauf, nicht im einzelnen Wert.":
    "Measure again after cleanup - the meaning lies in the trend, not in a single value.",

  // ------------------------------------------------------- Zusammengesetztes
  "{n} Befunde": "{n} findings",
  "{n} Saetze": "{n} records",
  "{n} Cluster": "{n} clusters",
  "{n} von {gesamt} Clustern": "{n} of {gesamt} clusters",
  "{n} Regelfehler": "{n} rule failures",
  "{a} von {b}": "{a} of {b}",
  "{a} von {b} Regeln": "{a} of {b} rules",
  "Seite {a} von {b}": "Page {a} of {b}",
  " - eingeschraenkt auf Regel {regel}": " - limited to rule {regel}",
  "von 100 Punkten, aus {n} geprueften Saetzen.":
    "out of 100 points, from {n} records checked.",
  "{n} Befunde mit Schweregrad {grad} - klicken, um die Liste darauf einzuschraenken":
    "{n} findings with severity {grad} - click to limit the list to them",
  "{n} Befunde in {bereich} - klicken, um die Liste darauf einzuschraenken":
    "{n} findings in {bereich} - click to limit the list to them",
  "schaltet {n} weitere Pruefungen frei": "unlocks {n} further checks",
  "{behoben} behoben, {neu} neu hinzugekommen": "{behoben} resolved, {neu} newly added",
  "{n} netto": "{n} net",
  "{n} weniger": "{n} fewer",
  "{n} mehr": "{n} more",
  "Aehnlichkeit {n}": "Similarity {n}",
  "{c} Cluster mit zusammen {s} Saetzen, Nachweis {art}, Schweregrad {grad}":
    "{c} clusters totalling {s} records, evidence {art}, severity {grad}",
  "{n} Ausnahme(n) entfernt.": "{n} exception(s) removed.",
  "{n} Ausnahme(n) entfernt. Wirksam ab dem naechsten Lauf.":
    "{n} exception(s) removed. Effective from the next run.",
  "Ausnahme aufgenommen ({bereich}).": "Exception added ({bereich}).",
  "Gefuehrt in {datei}": "Kept in {datei}",
  "der gepflegte Stand ist neuer und wird beim naechsten Lauf uebernommen.":
    "the maintained state is newer and will be applied on the next run.",
  "seit {lauf}": "since {lauf}",
  "in {lauf}": "in {lauf}",
  "Lauf {lauf} vom {stand} - Katalog {katalog} - Werkzeug {version}":
    "Run {lauf} of {stand} - catalogue {katalog} - tool {version}",
  "Quellsystem {system} - {n} Datei(en) im Eingang":
    "Source system {system} - {n} file(s) in the inbox",
  "Es liegt noch kein Lauf vor. Die Pruefung laesst sich links starten.":
    "There is no run yet. You can start the check on the left.",
  "Es liegt noch kein Lauf vor. Mit 'Pruefung starten' wird die Lieferung aus {pfad} geprueft.":
    "There is no run yet. 'Start check' will check the delivery in {pfad}.",
  "Aufruf fehlgeschlagen ({status}).": "Request failed ({status}).",
  "Der Lauf arbeitet seit {beginn} ...": "The run has been working since {beginn} ...",
  "Fertig:": "Finished:",
  "Abgebrochen:": "Aborted:",
  "Lauf arbeitet ...": "Run in progress ...",
  "Lauf {lauf} abgeschlossen:": "Run {lauf} completed:",
  "unbekannt": "unknown",

  // ------------------------------------------------------- Praesentationstexte
  "Quellsystem {system} \u2013 {n} Stammsaetze \u2013 Stand {stand}":
    "Source system {system} \u2013 {n} master records \u2013 as of {stand}",
  "{dateien} Dateien mit zusammen {saetze} Saetzen aus {tabellen} Tabellen. Jede Datei ist ueber ihre Pruefsumme im Bericht nachweisbar.":
    "{dateien} files totalling {saetze} records from {tabellen} tables. Every file is traceable through its checksum in the report.",
  "{cluster} Cluster mit zusammen {saetze} Stammsaetzen. Bleibt je Cluster ein fuehrender Satz stehen, entfallen {einsparung} Saetze.":
    "{cluster} clusters totalling {saetze} master records. Keeping one leading record per cluster removes {einsparung} records.",
  "Beispiel": "Example",
  "ueber einen harten Schluessel nachgewiesen": "proven by a hard key",
  "Namensaehnlichkeit {n} von 100": "name similarity {n} out of 100",
  "{n} kritische Befunde zuerst klaeren - sie betreffen Zahlungsverkehr, Steuer oder Bilanz.":
    "Address the {n} critical findings first - they affect payments, tax or the balance sheet.",
  "{n} Dublettencluster sichten und je Cluster den fuehrenden Stammsatz bestimmen.":
    "Review the {n} duplicate clusters and determine the leading master record for each.",
  "Fehlende Tabellen nachfordern ({tabellen}), um den Pruefumfang von {anteil} anzuheben.":
    "Request the missing tables ({tabellen}) to raise the scope of {anteil}.",

  // ---------------------------------------------------------------- Prosa
  // Wortgleich mit dem Bericht - wer die Management-Summary daneben liegen
  // hat, soll denselben Satz lesen.
  "Es waren keine Regeln aktiv. Die Lieferung wurde nicht fachlich geprueft.":
    "No rules were active. The delivery was not checked against any business rule.",
  "Alle {n} aktiven Regeln waren ausfuehrbar. Die Aussage stuetzt sich auf den vollstaendigen Regelkatalog.":
    "All {n} active rules were executable. The statement rests on the complete rule catalogue.",
  "Von {gesamt} aktiven Regeln waren {ausfuehrbar} ausfuehrbar ({anteil}). {entfallen} Regeln konnten nicht laufen, weil Tabellen oder Felder fehlen (vor allem {tabellen}). Die Aussage dieses Berichts gilt ausschliesslich fuer die ausgefuehrten Pruefungen; zu den entfallenen Pruefungen ist keine Aussage moeglich - weder positiv noch negativ.":
    "Of {gesamt} active rules, {ausfuehrbar} were executable ({anteil}). {entfallen} rules could not run because tables or fields are missing (chiefly {tabellen}). This report speaks only for the checks that were carried out; about the checks that were skipped no statement is possible - neither positive nor negative.",
  "Fuer {bereich} war keine Regel ausfuehrbar. Es liegt keine Aussage zur Datenqualitaet vor - weder eine gute noch eine schlechte.":
    "No rule was executable for {bereich}. There is no statement about data quality - neither good nor bad.",
  "Der Wert stuetzt sich auf {a} von {b} Regeln ({anteil}). Er ist nur mit Laeufen vergleichbar, die denselben Umfang hatten.":
    "The value rests on {a} of {b} rules ({anteil}). It is comparable only with runs of the same scope.",
  "Alle Regeln dieses Bereichs waren ausfuehrbar.": "All rules of this area were executable.",
  "gleiche {feld}: {wert}": "identical {feld}: {wert}",
  "uebereinstimmender harter Schluessel": "matching hard key",
  "Name sehr aehnlich ({n} von 100)": "names very similar ({n} out of 100)",
  "{behoben} Befunde behoben, {neu} neu hinzugekommen, {unveraendert} unveraendert.":
    "{behoben} findings resolved, {neu} newly added, {unveraendert} unchanged.",
  "In Summe unveraendert.": "No net change.",
  "In Summe {n} Befunde weniger.": "{n} findings fewer in total.",
  "In Summe {n} Befunde mehr.": "{n} findings more in total.",

  "Ein unscharfer Treffer ist ein begruendeter Verdacht, kein Nachweis. Berechtigte Mehrfachanlagen - etwa je Werk - gehoeren als Ausnahme vermerkt.":
    "A fuzzy match is a reasoned suspicion, not proof. Legitimate multiple records - one per plant, say - belong on the exception list.",
  "Ein harter Schluessel ist ein Nachweis: dieselbe Nummer kann nicht zwei Partnern gehoeren.":
    "A hard key is proof: the same number cannot belong to two partners.",

  // ------------------------------------------------ Lieferungsvalidierung
  // Die Vorlagen stammen aus validate/delivery.py und kommen mit ihren
  // Werten getrennt in lauf.json an.
  "Fuer {tabelle} ist keine Satzanzahl gemeldet. Es wurden {gelesen} Saetze gelesen; ob die Lieferung vollstaendig ist, laesst sich nicht pruefen.":
    "No record count was reported for {tabelle}. {gelesen} records were read; whether the delivery is complete cannot be checked.",
  "{tabelle}: {gelesen} Saetze wie gemeldet.": "{tabelle}: {gelesen} records as reported.",
  "{tabelle}: {gelesen} Saetze gelesen, aber {gemeldet} gemeldet (Abweichung {abweichung}). Die Lieferung ist unvollstaendig oder die Meldung falsch.":
    "{tabelle}: {gelesen} records read, but {gemeldet} reported (difference {abweichung}). Either the delivery is incomplete or the report is wrong.",
  "{datei}: {abgewiesen} von {gesamt} Zeilen ({anteil}) sind strukturell defekt und wurden nicht gelesen. Haeufigste Ursache: ein nicht maskiertes Trennzeichen in einem Freitextfeld. {beispiele}":
    "{datei}: {abgewiesen} of {gesamt} lines ({anteil}) are structurally broken and were not read. Most common cause: an unescaped separator in a free-text field. {beispiele}",
  "{datei} endet ohne Zeilenumbruch. Der Export koennte an der letzten Zeile abgebrochen worden sein.":
    "{datei} ends without a line break. The export may have been cut off at the last line.",
  "{tabelle} enthaelt genau {saetze} Saetze. Das ist eine typische Exportgrenze - bitte pruefen, ob der Export abgeschnitten wurde.":
    "{tabelle} contains exactly {saetze} records. That is a typical export limit - please check whether the export was truncated.",
  "{tabelle}.{spalte}: laengster Wert hat {laenge} Zeichen, das Feld ist laut DDIC {ddic} Zeichen lang. Die Spalte wurde vermutlich falsch zugeordnet oder enthaelt Fremdinhalte.":
    "{tabelle}.{spalte}: the longest value has {laenge} characters, the field is {ddic} characters long according to the DDIC. The column was probably mapped wrongly or holds foreign content.",
  "{tabelle}.{spalte}: {treffer} von {gesamt} Werten ({anteil}) sind genau {laenge} Zeichen lang, waehrend auf den {breite} Laengen darunter zusammen nur {darunter} Werte liegen. Dieser Aufstau auf der Grenze deutet auf beim Export abgeschnittene Feldinhalte hin.":
    "{tabelle}.{spalte}: {treffer} of {gesamt} values ({anteil}) are exactly {laenge} characters long, while the {breite} lengths below hold only {darunter} values in total. This pile-up at the limit points to field content truncated during export.",
  "{tabelle} wurde in {anzahl} Dateien mit unterschiedlichen Spalten geliefert ({luecken}). Die fehlenden Spalten werden mit NULL aufgefuellt; Vollstaendigkeitsregeln melden fuer diese Saetze deshalb moeglicherweise Luecken, die im Quellsystem gepflegt sind.":
    "{tabelle} was delivered in {anzahl} files with differing columns ({luecken}). The missing columns are filled with NULL; completeness rules may therefore report gaps for these records that are in fact maintained in the source system.",
  "{tabelle}: {betroffen} Schluesselwert(e) kommen mehrfach vor ({ueberzaehlig} ueberzaehlige Saetze). Der Schluessel {schluessel} ist im Quellsystem eindeutig - die Lieferung enthaelt Ueberschneidungen. Beispiele: {beispiele}.":
    "{tabelle}: {betroffen} key value(s) occur more than once ({ueberzaehlig} surplus records). The key {schluessel} is unique in the source system - the delivery contains overlaps. Examples: {beispiele}.",
  "{tabelle} enthaelt kein Mandantenfeld. Ob die Lieferung genau einen Mandanten umfasst, laesst sich nicht pruefen.":
    "{tabelle} contains no client field. Whether the delivery covers exactly one client cannot be checked.",
  "{tabelle} enthaelt mehrere Mandanten ({mandanten}), ohne dass ein Mandantenfilter konfiguriert ist. Auswertungen ueber vermischte Mandanten sind nicht belastbar. Bitte delivery.expected_clients setzen.":
    "{tabelle} contains several clients ({mandanten}) without a client filter being configured. Analyses across mixed clients do not hold up. Please set delivery.expected_clients.",
  "{tabelle} enthaelt die Mandanten {mandanten}, erwartet wurde {erwartet}. Nach der Filterung bliebe die Tabelle leer.":
    "{tabelle} contains clients {mandanten}, but {erwartet} was expected. After filtering the table would be empty.",
  "Die Lieferung enthielt die Mandanten {geliefert}; verarbeitet wurde {verarbeitet}.":
    "The delivery contained clients {geliefert}; {verarbeitet} was processed.",
  "Fuer {anzahl} Datei(en) ist kein Extraktionsstichtag dokumentiert ({dateien}). Ersatzweise wird der Zeitstempel der Datei verwendet; er sagt nichts ueber den fachlichen Stichtag aus (A-04).":
    "No extraction date is documented for {anzahl} file(s) ({dateien}). The file timestamp is used instead; it says nothing about the business cut-off date (A-04).",
  "Die Dateien wurden zu unterschiedlichen Stichtagen extrahiert ({stichtage}). Konsistenzpruefungen ueber Tabellen hinweg koennen dadurch Scheinbefunde erzeugen.":
    "The files were extracted on different dates ({stichtage}). Consistency checks across tables can therefore produce spurious findings.",
  "{datei} ist inhaltsgleich mit {andere} (identischer SHA-256). Die Saetze wurden doppelt eingelesen.":
    "{datei} is identical in content to {andere} (same SHA-256). The records were read in twice.",
  "{datei} ist leer.": "{datei} is empty.",
  "{datei} wurde keiner Tabelle zugeordnet und bleibt unberuecksichtigt. {hinweis}":
    "{datei} was not assigned to any table and is disregarded. {hinweis}",
  "{tabelle} fehlen die Schluesselfelder {felder}. Ohne Schluessel laesst sich kein Befund einem Stammsatz zuordnen.":
    "{tabelle} is missing the key fields {felder}. Without a key no finding can be assigned to a master record.",
  "{tabelle} enthaelt keine Saetze. {grund}": "{tabelle} contains no records. {grund}",
  "Alle Saetze wurden vom Mandanten- bzw. Buchungskreisfilter entfernt.":
    "All records were removed by the client or company code filter.",
  "Die Tabelle wurde leer geliefert.": "The table was delivered empty.",
  "{tabelle} ist in den Tabellenmetadaten nicht beschrieben. Die Spalten werden als Text uebernommen; typabhaengige Pruefungen entfallen.":
    "{tabelle} is not described in the table metadata. The columns are taken over as text; type-dependent checks are skipped.",
  "{tabelle}: {anzahl} Spalte(n) ohne bekannten Feldnamen ({spalten}). Sie werden unveraendert uebernommen.":
    "{tabelle}: {anzahl} column(s) without a known field name ({spalten}). They are taken over unchanged.",
  "Es fehlen als Pflicht vereinbarte Tabellen: {tabellen}":
    "Tables agreed as mandatory are missing: {tabellen}",

  // Regelkategorien (Category.label in rules/model.py)
  "Vollstaendigkeit": "Completeness",
  "Format / Syntax": "Format / syntax",
  "Konsistenz ueber Sichten": "Consistency across views",
  "Referenzintegritaet": "Referential integrity",
  "Aktualitaet / Lifecycle": "Currency / lifecycle",
  "Risiko- / Compliance-Indikatoren": "Risk / compliance indicators",
  "Externe Validierung": "External validation",

  // Anforderungen der Lieferungsvalidierung
  "Satzanzahlabgleich": "Record count reconciliation",
  "Truncation-Erkennung": "Truncation detection",
  "Mandantenpruefung": "Client check",
  "Extraktionsstichtag": "Extraction date",
  "Nachvollziehbarkeit": "Traceability",
  "Verwertbarkeit": "Usability",
  "Datei-zu-Tabelle-Zuordnung": "File-to-table assignment",
  "Header-Mapping": "Header mapping",

  "Einordnung": "Assessment",
  "Vorbehalt": "Qualification",

  // -------------------------------------------------------------- Wortschatz
  "Kreditoren": "Vendors",
  "Debitoren": "Customers",
  "Material": "Materials",
  "Geschaeftspartner": "Business partners",
  "Bankdaten": "Bank data",
  "Uebergreifend": "Cross-area",
  "offen": "open",
  "in Klaerung": "in clarification",
  "akzeptiert": "accepted",
  "korrigiert": "corrected",
  "neu": "new",
  "behoben": "resolved",
  "kein Vergleich": "no comparison",
  "nicht bewertbar": "not assessable",
  "sehr gut": "very good",
  "gut": "good",
  "befriedigend": "satisfactory",
  "unzureichend": "inadequate",
  "bereit": "ready",
  "laeuft": "running",
  "fertig": "finished",
  "fehler": "failed",
};

/** Aktuelle Sprache. */
let SPRACHE = (function () {
  try {
    const gemerkt = localStorage.getItem(SPRACHE_SPEICHER);
    if (gemerkt && SPRACHEN[gemerkt]) return gemerkt;
  } catch (fehler) {
    // Ein privates Fenster kann den Zugriff verweigern - dann gilt die Vorgabe.
  }
  const vom_browser = (navigator.language || "de").slice(0, 2).toLowerCase();
  return SPRACHEN[vom_browser] ? vom_browser : "de";
})();

function spracheSetzen(sprache) {
  if (!SPRACHEN[sprache]) return;
  SPRACHE = sprache;
  try {
    localStorage.setItem(SPRACHE_SPEICHER, sprache);
  } catch (fehler) {
    // Bleibt fuer diese Sitzung gesetzt, mehr nicht.
  }
  document.documentElement.lang = sprache;
}

/** Uebersetzt einen Text und setzt Platzhalter ein.
 *
 * Unbekannte Texte gehen unveraendert durch. Das ist beabsichtigt: Regelnamen,
 * Objektschluessel und Feldinhalte laufen durch dieselbe Funktion und duerfen
 * nicht angetastet werden.
 */
function t(text, werte) {
  let ergebnis = text === null || text === undefined ? "" : String(text);
  if (SPRACHE !== "de") {
    const uebersetzt = EN[ergebnis];
    if (uebersetzt !== undefined) ergebnis = uebersetzt;
  }
  if (werte) {
    ergebnis = ergebnis.replace(/\{(\w+)\}/g, (treffer, name) =>
      Object.prototype.hasOwnProperty.call(werte, name) ? String(werte[name]) : treffer);
  }
  return ergebnis;
}

/** Die Sprachkennung fuer Zahlen- und Datumsformate. */
function gebietsschema() {
  return SPRACHE === "de" ? "de-DE" : "en-GB";
}
