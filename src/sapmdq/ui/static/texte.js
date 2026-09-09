/* Sprachen der Oberfläche.
 *
 * Der deutsche Text ist die Quelle und zugleich der Schlüssel. Das hat einen
 * praktischen Grund: fehlt eine Übersetzung, erscheint der deutsche Satz -
 * unschön, aber lesbar. Ein Schlüsselwort wie "befunde.leer" erschiene
 * stattdessen als solches, und niemand könnte damit etwas anfangen.
 *
 * Damit daraus keine stille Nachlässigkeit wird, prüft
 * ``tests/test_ui_sprachen.py``, dass jeder in der Oberfläche verwendete Text
 * eine englische Fassung hat.
 *
 * Platzhalter stehen in geschweiften Klammern: t("{n} Befunde", {n: 5}).
 */
"use strict";

const SPRACHEN = { de: "Deutsch", en: "English" };
const SPRACHE_SPEICHER = "sapmdq.sprache";

/** Wörterbuch Deutsch -> Englisch. */
const EN = {
  // ------------------------------------------------------------ Grundgeruest
  "SAP-Stammdatenprüfung": "SAP Master Data Check",
  "Stammdaten­prüfung": "Master Data Check",
  "Sitzungsmerkmal fehlt": "Session token missing",
  "Die Oberfläche wird über die Adresse aus der Startmeldung geöffnet. Sie enthält das Merkmal dieser Sitzung. Ohne es antwortet der Server nicht.":
    "Open the interface using the address printed at startup. It carries this session's token. Without it the server does not respond.",
  "Beispiel:": "Example:",
  "Bereiche": "Sections",
  "Sprache": "Language",
  "Angezeigter Lauf": "Selected run",
  "Angezeigten Lauf wählen": "Select the run to display",
  "Präsentation": "Presentation",
  "Prüfung starten": "Start check",

  // ---------------------------------------------------------------- Ansichten
  "Lagebild": "Overview",
  "Befunde": "Findings",
  "Dubletten": "Duplicates",
  "Prüfumfang": "Scope",
  "Eingang": "Inbox",
  "Lieferung": "Delivery",
  "Ausnahmen": "Exceptions",
  "Läufe": "Runs",

  // ----------------------------------------------------------------- Lagebild
  "Datenqualität": "Data quality",
  "Auf einen Blick": "At a glance",
  "Befunde nach Schweregrad": "Findings by severity",
  "Befunde nach Objektbereich": "Findings by object area",
  "Zum Filtern auf eine Zeile klicken.": "Click a row to filter.",
  "Woran es am häufigsten liegt": "Most frequent causes",
  "Was eine Nachlieferung brächte": "What a follow-up delivery would unlock",
  "Nach Wirkung geordnet: wieviele zusätzliche Prüfungen die Tabelle freischaltet.":
    "Ordered by effect: how many additional checks each table unlocks.",
  "Bewertung je Bereich": "Score by area",
  "Der Wert ist unter dem Vorbehalt des jeweils erreichten Prüfumfangs zu lesen. Was nicht geprüft werden konnte, geht nicht ein.":
    "Read the score subject to the scope actually achieved. What could not be checked is not reflected in it.",
  "Befunde offen": "Open findings",
  "kritisch": "critical",
  "hoch": "high",
  "mittel": "medium",
  "Regelfehler": "Rule failures",
  "gegen den Vorlauf": "vs. previous run",
  "Ohne die als Ausnahme anerkannten Befunde.": "Excluding findings accepted as exceptions.",
  "Befunde, die mit Begründung anerkannt wurden.": "Findings accepted with a documented reason.",
  "Das Ergebnis ist unvollständig.": "The result is incomplete.",
  "Alle Regeln liefen durch.": "All rules completed.",
  "Kein Lauf ausgewählt.": "No run selected.",
  "Keine Befunde.": "No findings.",
  "Nichts vorhanden.": "Nothing to show.",
  "Die Lieferung ist vollständig - es fehlt nichts.":
    "The delivery is complete - nothing is missing.",
  "unverändert": "unchanged",
  "von 100 Punkten": "out of 100 points",

  // ---------------------------------------------------------------- Lieferung
  "Dateien": "Files",
  "Tabellen": "Tables",
  "Prüfungen der Lieferung": "Delivery checks",
  "Die Lieferung ist verwertbar.": "The delivery is usable.",
  "Die Lieferung ist nicht verwertbar. Der Lauf wurde nur mit ausdrücklicher Freigabe fortgesetzt; die Ergebnisse sind entsprechend eingeschränkt.":
    "The delivery is not usable. The run continued only after explicit approval; the results are limited accordingly.",
  "Datei": "File",
  "Tabelle": "Table",
  "Zuordnung": "Assignment",
  "Format": "Format",
  "Zeilen": "Rows",
  "Abgewiesen": "Rejected",
  "Stichtag": "Extraction date",
  "Größe": "Size",
  "SHA-256": "SHA-256",
  "Bereich": "Area",
  "Sätze": "Records",
  "Vor Filter": "Before filter",
  "Spalten": "Columns",
  "Mandanten": "Clients",
  "Quelldateien": "Source files",
  "Prüfung": "Check",
  "Gewicht": "Weight",
  "Gegenstand": "Subject",
  "Anforderung": "Requirement",
  "Meldung": "Message",

  // -------------------------------------------------------------- Pruefumfang
  "Nachforderung": "Follow-up request",
  "Was zusätzlich geliefert werden müsste, damit die entfallenen Regeln laufen können - nach Wirkung geordnet.":
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
  "Ausführbar": "Executable",
  "Grund": "Reason",
  "ja": "yes",
  "nein": "no",
  "unverzichtbar": "essential",
  "Was geprüft wird": "What is checked",
  "Handlungsempfehlung": "Recommended action",
  "Schweregrad": "Severity",
  "Regelversion": "Rule version",
  "Keine Angaben zum Prüfumfang.": "No scope information available.",

  // ----------------------------------------------------------------- Befunde
  "Schlüssel, Regel oder Detail": "Key, rule or detail",
  "Befunde durchsuchen": "Search findings",
  "Schweregrad: alle": "Severity: all",
  "Bereich: alle": "Area: all",
  "Kategorie: alle": "Category: all",
  "Bearbeitungsstand": "Processing state",
  "Stand: alle": "State: all",
  "Vergleich zum Vorlauf": "Comparison with previous run",
  "Vergleich: alle": "Comparison: all",
  "Ausnahmen zeigen": "Show exceptions",
  "Filter löschen": "Clear filters",
  "Zurück": "Back",
  "Weiter": "Next",
  "Objekt": "Object",
  "Mandant": "Client",
  "Stand": "State",
  "Vergleich": "Comparison",
  "Ausnahme": "Exception",
  "Zuständig": "Owner",
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
  "ohne Begründung": "no reason given",
  "Ausnahme zurücknehmen": "Withdraw exception",
  "vorgemerkt": "pending",
  "Die Ausnahme steht in der Ausnahmeliste, ist aber in diesem Bericht noch nicht berücksichtigt. Sie wirkt ab dem nächsten Lauf.":
    "The exception is on the list but is not yet reflected in this report. It takes effect from the next run.",
  "Der Stand wird in der Statusdatei des Projekts geführt und beim nächsten Lauf übernommen (FA-603).":
    "The state is kept in the project's status file and applied on the next run (FA-603).",
  "Bemerkung (freiwillig)": "Note (optional)",
  "Bearbeiter": "Handled by",
  "Stand speichern": "Save state",
  "Die Ausnahme wird in der Ausnahmeliste des Projekts geführt. Sie wirkt ab dem nächsten Lauf; der bereits geschriebene Bericht bleibt unverändert (FA-602).":
    "The exception is kept in the project's exception list. It takes effect from the next run; the report already written stays unchanged (FA-602).",
  "Begründung - warum ist der Befund vertretbar?": "Reason - why is this finding acceptable?",
  "Freigegeben von": "Approved by",
  "Verweis (Ticket, Protokoll)": "Reference (ticket, minutes)",
  "Läuft ab": "Expires",
  "Geltungsbereich": "Scope",
  "nur dieser Befund": "this finding only",
  "dieses Objekt in dieser Regel": "this object within this rule",
  "alle Befunde dieser Regel": "all findings of this rule",
  "läuft ab am": "expires on",
  "Ausnahme aufnehmen": "Add exception",
  "Gepflegt, aber noch nicht in den Bericht übernommen - das geschieht beim nächsten Lauf.":
    "Maintained but not yet reflected in the report - that happens on the next run.",
  "Stand im Bericht": "State in the report",

  // --------------------------------------------------------------- Dubletten
  "Cluster": "Clusters",
  "Nach Regel": "By rule",
  "Name oder Schlüssel": "Name or key",
  "Cluster durchsuchen": "Search clusters",
  "Art des Treffers": "Type of match",
  "Nachweis: alle": "Evidence: all",
  "exakt - harter Schlüssel": "exact - hard key",
  "unscharf - Namensähnlichkeit": "fuzzy - name similarity",
  "Alle aufklappen": "Expand all",
  "Alle zuklappen": "Collapse all",
  "aufklappen": "expand",
  "zuklappen": "collapse",
  "Betroffene Sätze": "Records affected",
  "mutmaßlich mehrfach angelegt": "presumed created more than once",
  "in allen Clustern zusammen": "across all clusters",
  "Bereinigungspotenzial": "Cleanup potential",
  "Sätze entfallen, wenn je Cluster einer führend wird":
    "records removed once one record per cluster becomes the leading one",
  "harter Schlüssel": "hard key",
  "Keine Dubletten gefunden.": "No duplicates found.",
  "Kein Cluster passt zu diesem Filter.": "No cluster matches this filter.",
  "Befund öffnen": "Open finding",
  "exakt": "exact",
  "unscharf": "fuzzy",
  "weicht von den übrigen Sätzen ab": "differs from the other records",
  "in allen Sätzen gleich": "identical in all records",
  "Name": "Name",

  // --------------------------------------------------------------- Ausnahmen
  "Hinterlegte Ausnahmen": "Recorded exceptions",
  "In der Projektkonfiguration ist keine Ausnahmeliste hinterlegt.":
    "No exception list is configured in the project.",
  "Begründung": "Reason",
  "Am": "On",
  "Verweis": "Reference",
  "Wirksam": "In effect",
  "abgelaufen": "expired",
  "entfernen": "remove",

  // ------------------------------------------------------------------ Laeufe
  "Zwei Läufe vergleichen": "Compare two runs",
  "Früherer Lauf": "Earlier run",
  "Späterer Lauf": "Later run",
  "gegen": "vs.",
  "Vergleichen": "Compare",
  "Lauf": "Run",
  "Zeitpunkt": "Time",
  "Dauer": "Duration",
  "Umfang": "Scope",
  "Punkte": "Points",
  "Katalog": "Catalogue",
  "Zustand": "State",
  "unvollständig": "incomplete",
  "vollständig": "complete",
  "Wird berechnet ...": "Calculating ...",
  "Behoben": "Resolved",
  "Neu": "New",
  "Unverändert": "Unchanged",
  "Anerkannte Ausnahmen": "Accepted exceptions",
  "nicht behoben, nur anerkannt": "not resolved, only accepted",
  "Vorher": "Before",
  "Jetzt": "Now",
  "Zu diesem Lauf gibt es keine Zusammenfassung. Er wurde vermutlich abgebrochen.":
    "There is no summary for this run. It was probably aborted.",

  // ------------------------------------------------------------ Lauf starten
  "Prüfungslauf": "Check run",
  "Schließen": "Close",
  "Kein Lauf gestartet.": "No run started.",
  "Beenden": "Quit",
  "Als PDF": "As PDF",
  "Vorige Folie": "Previous slide",
  "Nächste Folie": "Next slide",

  // ------------------------------------------------------- Praesentationsfolien
  "Titel": "Title",
  "Analyse der Stammdatenqualität": "Master data quality analysis",
  "Stammdatenprüfung": "Master data check",
  "Was geprüft wurde": "What was checked",
  "Worüber eine Aussage möglich ist": "What can be stated at all",
  "Ergebnis": "Result",
  "Datenqualität insgesamt": "Overall data quality",
  "Wo die Befunde liegen": "Where the findings are",
  "Nach Kategorie": "By category",
  "Mehrfach angelegte Stammsätze": "Master records created more than once",
  "Nächste Schritte": "Next steps",
  "Ohne Lauf lässt sich nichts zeigen.": "There is nothing to show without a run.",
  "Berechtigte Fälle als Ausnahme mit Begründung vermerken, damit sie im Folgelauf nicht erneut als Befund erscheinen.":
    "Record legitimate cases as exceptions with a reason so they do not reappear as findings in the next run.",
  "Nach der Bereinigung erneut messen - die Aussage liegt im Verlauf, nicht im einzelnen Wert.":
    "Measure again after cleanup - the meaning lies in the trend, not in a single value.",

  // ------------------------------------------------------- Zusammengesetztes
  "{n} Befunde": "{n} findings",
  "{n} Sätze": "{n} records",
  "{n} Cluster": "{n} clusters",
  "{n} von {gesamt} Clustern": "{n} of {gesamt} clusters",
  "{n} Regelfehler": "{n} rule failures",
  "{a} von {b}": "{a} of {b}",
  "{a} von {b} Regeln": "{a} of {b} rules",
  "Seite {a} von {b}": "Page {a} of {b}",
  " - eingeschränkt auf Regel {regel}": " - limited to rule {regel}",
  "von 100 Punkten, aus {n} geprüften Sätzen.":
    "out of 100 points, from {n} records checked.",
  "{n} Befunde mit Schweregrad {grad} - klicken, um die Liste darauf einzuschränken":
    "{n} findings with severity {grad} - click to limit the list to them",
  "{n} Befunde in {bereich} - klicken, um die Liste darauf einzuschränken":
    "{n} findings in {bereich} - click to limit the list to them",
  "schaltet {n} weitere Prüfungen frei": "unlocks {n} further checks",
  "{behoben} behoben, {neu} neu hinzugekommen": "{behoben} resolved, {neu} newly added",
  "{n} netto": "{n} net",
  "{n} weniger": "{n} fewer",
  "{n} mehr": "{n} more",
  "Ähnlichkeit {n}": "Similarity {n}",
  "{c} Cluster mit zusammen {s} Sätzen, Nachweis {art}, Schweregrad {grad}":
    "{c} clusters totalling {s} records, evidence {art}, severity {grad}",
  "{n} Ausnahme(n) entfernt.": "{n} exception(s) removed.",
  "{n} Ausnahme(n) entfernt. Wirksam ab dem nächsten Lauf.":
    "{n} exception(s) removed. Effective from the next run.",
  "Ausnahme aufgenommen ({bereich}).": "Exception added ({bereich}).",
  "Geführt in {datei}": "Kept in {datei}",
  "der gepflegte Stand ist neuer und wird beim nächsten Lauf übernommen.":
    "the maintained state is newer and will be applied on the next run.",
  "seit {lauf}": "since {lauf}",
  "in {lauf}": "in {lauf}",
  "Lauf {lauf} vom {stand} - Katalog {katalog} - Werkzeug {version}":
    "Run {lauf} of {stand} - catalogue {katalog} - tool {version}",
  "Quellsystem {system} - {n} Datei(en) im Eingang":
    "Source system {system} - {n} file(s) in the inbox",
  "Es liegt noch kein Lauf vor. Die Prüfung lässt sich links starten.":
    "There is no run yet. You can start the check on the left.",
  "Es liegt noch kein Lauf vor. Mit 'Prüfung starten' wird die Lieferung aus {pfad} geprüft.":
    "There is no run yet. 'Start check' will check the delivery in {pfad}.",
  "Aufruf fehlgeschlagen ({status}).": "Request failed ({status}).",
  "Der Lauf arbeitet seit {beginn} ...": "The run has been working since {beginn} ...",
  "Fertig:": "Finished:",
  "Abgebrochen:": "Aborted:",
  "Lauf arbeitet ...": "Run in progress ...",
  "Lauf {lauf} abgeschlossen:": "Run {lauf} completed:",
  "unbekannt": "unknown",

  // ------------------------------------------------------- Praesentationstexte
  "Quellsystem {system} \u2013 {n} Stammsätze \u2013 Stand {stand}":
    "Source system {system} \u2013 {n} master records \u2013 as of {stand}",
  "{dateien} Dateien mit zusammen {saetze} Sätzen aus {tabellen} Tabellen. Jede Datei ist über ihre Prüfsumme im Bericht nachweisbar.":
    "{dateien} files totalling {saetze} records from {tabellen} tables. Every file is traceable through its checksum in the report.",
  "{cluster} Cluster mit zusammen {saetze} Stammsätzen. Bleibt je Cluster ein führender Satz stehen, entfallen {einsparung} Sätze.":
    "{cluster} clusters totalling {saetze} master records. Keeping one leading record per cluster removes {einsparung} records.",
  "Beispiel": "Example",
  "über einen harten Schlüssel nachgewiesen": "proven by a hard key",
  "Namensähnlichkeit {n} von 100": "name similarity {n} out of 100",
  "{n} kritische Befunde zuerst klären - sie betreffen Zahlungsverkehr, Steuer oder Bilanz.":
    "Address the {n} critical findings first - they affect payments, tax or the balance sheet.",
  "{n} Dublettencluster sichten und je Cluster den führenden Stammsatz bestimmen.":
    "Review the {n} duplicate clusters and determine the leading master record for each.",
  "Fehlende Tabellen nachfordern ({tabellen}), um den Prüfumfang von {anteil} anzuheben.":
    "Request the missing tables ({tabellen}) to raise the scope of {anteil}.",

  // ---------------------------------------------------------------- Prosa
  // Wortgleich mit dem Bericht - wer die Management-Summary daneben liegen
  // hat, soll denselben Satz lesen.
  "Es waren keine Regeln aktiv. Die Lieferung wurde nicht fachlich geprüft.":
    "No rules were active. The delivery was not checked against any business rule.",
  "Alle {n} aktiven Regeln waren ausführbar. Die Aussage stützt sich auf den vollständigen Regelkatalog.":
    "All {n} active rules were executable. The statement rests on the complete rule catalogue.",
  "Von {gesamt} aktiven Regeln waren {ausfuehrbar} ausführbar ({anteil}). {entfallen} Regeln konnten nicht laufen, weil Tabellen oder Felder fehlen (vor allem {tabellen}). Die Aussage dieses Berichts gilt ausschließlich für die ausgeführten Prüfungen; zu den entfallenen Prüfungen ist keine Aussage möglich - weder positiv noch negativ.":
    "Of {gesamt} active rules, {ausfuehrbar} were executable ({anteil}). {entfallen} rules could not run because tables or fields are missing (chiefly {tabellen}). This report speaks only for the checks that were carried out; about the checks that were skipped no statement is possible - neither positive nor negative.",
  "Für {bereich} war keine Regel ausführbar. Es liegt keine Aussage zur Datenqualität vor - weder eine gute noch eine schlechte.":
    "No rule was executable for {bereich}. There is no statement about data quality - neither good nor bad.",
  "Der Wert stützt sich auf {a} von {b} Regeln ({anteil}). Er ist nur mit Läufen vergleichbar, die denselben Umfang hatten.":
    "The value rests on {a} of {b} rules ({anteil}). It is comparable only with runs of the same scope.",
  "Alle Regeln dieses Bereichs waren ausführbar.": "All rules of this area were executable.",
  "gleiche {feld}: {wert}": "identical {feld}: {wert}",
  "übereinstimmender harter Schlüssel": "matching hard key",
  "Name sehr ähnlich ({n} von 100)": "names very similar ({n} out of 100)",
  "{behoben} Befunde behoben, {neu} neu hinzugekommen, {unveraendert} unverändert.":
    "{behoben} findings resolved, {neu} newly added, {unveraendert} unchanged.",
  "In Summe unverändert.": "No net change.",
  "In Summe {n} Befunde weniger.": "{n} findings fewer in total.",
  "In Summe {n} Befunde mehr.": "{n} findings more in total.",

  "Ein unscharfer Treffer ist ein begründeter Verdacht, kein Nachweis. Berechtigte Mehrfachanlagen - etwa je Werk - gehören als Ausnahme vermerkt.":
    "A fuzzy match is a reasoned suspicion, not proof. Legitimate multiple records - one per plant, say - belong on the exception list.",
  "Ein harter Schlüssel ist ein Nachweis: dieselbe Nummer kann nicht zwei Partnern gehören.":
    "A hard key is proof: the same number cannot belong to two partners.",

  // ------------------------------------------------ Lieferungsvalidierung
  // Die Vorlagen stammen aus validate/delivery.py und kommen mit ihren
  // Werten getrennt in lauf.json an.
  "Für {tabelle} ist keine Satzanzahl gemeldet. Es wurden {gelesen} Sätze gelesen; ob die Lieferung vollständig ist, lässt sich nicht prüfen.":
    "No record count was reported for {tabelle}. {gelesen} records were read; whether the delivery is complete cannot be checked.",
  "{tabelle}: {gelesen} Sätze wie gemeldet.": "{tabelle}: {gelesen} records as reported.",
  "{tabelle}: {gelesen} Sätze gelesen, aber {gemeldet} gemeldet (Abweichung {abweichung}). Die Lieferung ist unvollständig oder die Meldung falsch.":
    "{tabelle}: {gelesen} records read, but {gemeldet} reported (difference {abweichung}). Either the delivery is incomplete or the report is wrong.",
  "{datei}: {abgewiesen} von {gesamt} Zeilen ({anteil}) sind strukturell defekt und wurden nicht gelesen. Häufigste Ursache: ein nicht maskiertes Trennzeichen in einem Freitextfeld. {beispiele}":
    "{datei}: {abgewiesen} of {gesamt} lines ({anteil}) are structurally broken and were not read. Most common cause: an unescaped separator in a free-text field. {beispiele}",
  "{datei} endet ohne Zeilenumbruch. Der Export könnte an der letzten Zeile abgebrochen worden sein.":
    "{datei} ends without a line break. The export may have been cut off at the last line.",
  "{tabelle} enthält genau {saetze} Sätze. Das ist eine typische Exportgrenze - bitte prüfen, ob der Export abgeschnitten wurde.":
    "{tabelle} contains exactly {saetze} records. That is a typical export limit - please check whether the export was truncated.",
  "{tabelle}.{spalte}: längster Wert hat {laenge} Zeichen, das Feld ist laut DDIC {ddic} Zeichen lang. Die Spalte wurde vermutlich falsch zugeordnet oder enthält Fremdinhalte.":
    "{tabelle}.{spalte}: the longest value has {laenge} characters, the field is {ddic} characters long according to the DDIC. The column was probably mapped wrongly or holds foreign content.",
  "{tabelle}.{spalte}: {treffer} von {gesamt} Werten ({anteil}) sind genau {laenge} Zeichen lang, während auf den {breite} Längen darunter zusammen nur {darunter} Werte liegen. Dieser Aufstau auf der Grenze deutet auf beim Export abgeschnittene Feldinhalte hin.":
    "{tabelle}.{spalte}: {treffer} of {gesamt} values ({anteil}) are exactly {laenge} characters long, while the {breite} lengths below hold only {darunter} values in total. This pile-up at the limit points to field content truncated during export.",
  "{tabelle} wurde in {anzahl} Dateien mit unterschiedlichen Spalten geliefert ({luecken}). Die fehlenden Spalten werden mit NULL aufgefüllt; Vollständigkeitsregeln melden für diese Sätze deshalb möglicherweise Lücken, die im Quellsystem gepflegt sind.":
    "{tabelle} was delivered in {anzahl} files with differing columns ({luecken}). The missing columns are filled with NULL; completeness rules may therefore report gaps for these records that are in fact maintained in the source system.",
  "{tabelle}: {betroffen} Schlüsselwert(e) kommen mehrfach vor ({ueberzaehlig} überzählige Sätze). Der Schlüssel {schluessel} ist im Quellsystem eindeutig - die Lieferung enthält Überschneidungen. Beispiele: {beispiele}.":
    "{tabelle}: {betroffen} key value(s) occur more than once ({ueberzaehlig} surplus records). The key {schluessel} is unique in the source system - the delivery contains overlaps. Examples: {beispiele}.",
  "{tabelle} enthält kein Mandantenfeld. Ob die Lieferung genau einen Mandanten umfasst, lässt sich nicht prüfen.":
    "{tabelle} contains no client field. Whether the delivery covers exactly one client cannot be checked.",
  "{tabelle} enthält mehrere Mandanten ({mandanten}), ohne dass ein Mandantenfilter konfiguriert ist. Auswertungen über vermischte Mandanten sind nicht belastbar. Bitte delivery.expected_clients setzen.":
    "{tabelle} contains several clients ({mandanten}) without a client filter being configured. Analyses across mixed clients do not hold up. Please set delivery.expected_clients.",
  "{tabelle} enthält die Mandanten {mandanten}, erwartet wurde {erwartet}. Nach der Filterung bliebe die Tabelle leer.":
    "{tabelle} contains clients {mandanten}, but {erwartet} was expected. After filtering the table would be empty.",
  "Die Lieferung enthielt die Mandanten {geliefert}; verarbeitet wurde {verarbeitet}.":
    "The delivery contained clients {geliefert}; {verarbeitet} was processed.",
  "Für {anzahl} Datei(en) ist kein Extraktionsstichtag dokumentiert ({dateien}). Ersatzweise wird der Zeitstempel der Datei verwendet; er sagt nichts über den fachlichen Stichtag aus (A-04).":
    "No extraction date is documented for {anzahl} file(s) ({dateien}). The file timestamp is used instead; it says nothing about the business cut-off date (A-04).",
  "Die Dateien wurden zu unterschiedlichen Stichtagen extrahiert ({stichtage}). Konsistenzprüfungen über Tabellen hinweg können dadurch Scheinbefunde erzeugen.":
    "The files were extracted on different dates ({stichtage}). Consistency checks across tables can therefore produce spurious findings.",
  "{datei} ist inhaltsgleich mit {andere} (identischer SHA-256). Die Sätze wurden doppelt eingelesen.":
    "{datei} is identical in content to {andere} (same SHA-256). The records were read in twice.",
  "{datei} ist leer.": "{datei} is empty.",
  "{datei} wurde keiner Tabelle zugeordnet und bleibt unberücksichtigt. {hinweis}":
    "{datei} was not assigned to any table and is disregarded. {hinweis}",
  "{tabelle} fehlen die Schlüsselfelder {felder}. Ohne Schlüssel lässt sich kein Befund einem Stammsatz zuordnen.":
    "{tabelle} is missing the key fields {felder}. Without a key no finding can be assigned to a master record.",
  "{tabelle} enthält keine Sätze. {grund}": "{tabelle} contains no records. {grund}",
  "Alle Sätze wurden vom Mandanten- bzw. Buchungskreisfilter entfernt.":
    "All records were removed by the client or company code filter.",
  "Die Tabelle wurde leer geliefert.": "The table was delivered empty.",
  "{tabelle} ist in den Tabellenmetadaten nicht beschrieben. Die Spalten werden als Text übernommen; typabhängige Prüfungen entfallen.":
    "{tabelle} is not described in the table metadata. The columns are taken over as text; type-dependent checks are skipped.",
  "{tabelle}: {anzahl} Spalte(n) ohne bekannten Feldnamen ({spalten}). Sie werden unverändert übernommen.":
    "{tabelle}: {anzahl} column(s) without a known field name ({spalten}). They are taken over unchanged.",
  "Es fehlen als Pflicht vereinbarte Tabellen: {tabellen}":
    "Tables agreed as mandatory are missing: {tabellen}",

  // Regelkategorien (Category.label in rules/model.py)
  "Vollständigkeit": "Completeness",
  "Format / Syntax": "Format / syntax",
  "Konsistenz über Sichten": "Consistency across views",
  "Referenzintegrität": "Referential integrity",
  "Aktualität / Lifecycle": "Currency / lifecycle",
  "Risiko- / Compliance-Indikatoren": "Risk / compliance indicators",
  "Externe Validierung": "External validation",

  // Anforderungen der Lieferungsvalidierung
  "Satzanzahlabgleich": "Record count reconciliation",
  "Truncation-Erkennung": "Truncation detection",
  "Mandantenprüfung": "Client check",
  "Extraktionsstichtag": "Extraction date",
  "Nachvollziehbarkeit": "Traceability",
  "Verwertbarkeit": "Usability",
  "Datei-zu-Tabelle-Zuordnung": "File-to-table assignment",
  "Header-Mapping": "Header mapping",

  "Einordnung": "Assessment",
  "Vorbehalt": "Qualification",

  // ---------------------------------------------------------------- Abdeckung
  "Abdeckung": "Coverage",
  "Was das Werkzeug überhaupt prüft - unabhängig von dieser Lieferung. Je Prozess steht daneben, wieviel davon sich mit den gelieferten Tabellen tatsächlich prüfen ließ.":
    "What the tool checks at all - independently of this delivery. For each process it also shows how much of that could actually be checked with the tables delivered.",
  "Kernprozesse": "Core processes",
  "Querschnittsthemen": "Cross-cutting topics",
  "Alle Tabellen": "All tables",
  "Welche Tabelle wofür gebraucht wird und an wievielen Regeln sie hängt.":
    "What each table is needed for and how many rules depend on it.",
  "Tabelle suchen": "Search tables",
  "nur fehlende": "missing only",
  "Prozesse": "Processes",
  "{n} davon Kernprozesse": "{n} of them core processes",
  "im aktiven Katalog": "in the active catalogue",
  "{n} in dieser Lieferung vorhanden": "{n} present in this delivery",
  "Vollständig prüfbar": "Fully checkable",
  "von {n} Prozessen in dieser Lieferung": "of {n} processes in this delivery",
  "Nicht im Umfang:": "Out of scope:",
  "Benötigte Tabellen": "Tables required",
  "in dieser Lieferung": "in this delivery",
  "in dieser Lieferung nicht enthalten": "not contained in this delivery",
  "Geliefert": "Delivered",
  "wichtig": "important",
  "hilfreich": "helpful",

  // Folien zur Abdeckung
  "Was das Werkzeug prüft": "What the tool checks",
  "{regeln} Regeln über {prozesse} Geschäftsprozesse, gestützt auf {tabellen} SAP-Tabellen. Geprüft werden die Stammdaten, auf denen die Prozesse aufsetzen - nicht die Prozessausführung selbst.":
    "{regeln} rules across {prozesse} business processes, resting on {tabellen} SAP tables. What is checked is the master data the processes build on - not the execution of the processes themselves.",
  "Was davon hier prüfbar war": "How much of that was checkable here",
  "Je Prozess: wieviele der Regeln mit den gelieferten Tabellen laufen konnten. Fehlende Tabellen stehen daneben.":
    "Per process: how many rules could run with the tables delivered. Missing tables are named alongside.",
  "Prozess": "Process",
  "Anteil": "Share",
  "Fehlende Tabellen": "Missing tables",

  // ------------------------------------------------- Prozesse (prozesse.yaml)
  "Plan-to-Produce und Bestandsführung": "Plan-to-Produce and inventory",
  "Steuer und Compliance": "Tax and compliance",
  "Internes Kontrollsystem": "Internal control system",
  "Dublettenmanagement": "Duplicate management",
  "Stammdatenlebenszyklus": "Master data lifecycle",

  // Prozessschritte
  "Lieferantenanlage": "Vendor creation",
  "Bestellung": "Purchase order",
  "Wareneingang": "Goods receipt",
  "Rechnungsprüfung": "Invoice verification",
  "Zahllauf": "Payment run",
  "Kundenanlage": "Customer creation",
  "Auftrag": "Sales order",
  "Faktura": "Billing",
  "Zahlungseingang": "Incoming payment",
  "Mahnwesen": "Dunning",
  "Materialanlage": "Material creation",
  "Disposition": "Requirements planning",
  "Beschaffung oder Fertigung": "Procurement or production",
  "Bestandsführung": "Inventory management",
  "Bewertung": "Valuation",
  "Nebenbuch": "Sub-ledger",
  "Kontenfindung": "Account determination",
  "Hauptbuch": "General ledger",
  "Abschluss": "Closing",

  // Beschreibungen
  "Von der Lieferantenanlage bis zur Zahlung. Geprüft werden die Stammdaten, ohne die eine Bestellung nicht buchbar und ein Zahllauf nicht ausführbar ist.":
    "From vendor creation to payment. What is checked is the master data without which a purchase order cannot be posted and a payment run cannot be executed.",
  "Vom Kundenstammsatz bis zum Zahlungseingang. Im Mittelpunkt stehen die Angaben, an denen Steuerfreiheit, Fakturierbarkeit und Mahnwesen hängen.":
    "From the customer master record to the incoming payment. The focus is on the entries that tax exemption, billing and dunning depend on.",
  "Vom Materialstammsatz über die Disposition bis zur Bestandsbewertung. Geprüft wird, ob ein Material überhaupt disponierbar, bewegbar und bewertbar ist.":
    "From the material master record through requirements planning to inventory valuation. What is checked is whether a material can be planned, moved and valued at all.",
  "Die Stellen, an denen Stammdaten unmittelbar in den Abschluss wirken. Ein falsch zugeordnetes Bestandskonto fällt nicht beim Buchen auf, sondern erst in der Bilanzanalyse.":
    "The points where master data feed straight into the financial statements. A wrongly assigned stock account does not surface when posting, but only in the balance sheet analysis.",
  "Angaben, an denen steuerliche Pflichten und aufsichtsrechtliche Sorgfaltspflichten hängen - quer über Kreditoren und Debitoren.":
    "Entries that tax obligations and regulatory due diligence depend on - across vendors and customers alike.",
  "Konstellationen, die in der Abschlussprüfung regelmäßig zur Feststellung werden. Keine davon ist für sich genommen ein Nachweis - jede verlangt eine Klärung und deren Dokumentation.":
    "Constellations that regularly become audit findings. None of them is proof in itself - each calls for clarification and its documentation.",
  "Mehrfach angelegte Stammsätze über alle Bereiche. Unterschieden wird zwischen hartem Nachweis (gleiche USt-IdNr., gleiche Bankverbindung, gleiche EAN) und begründetem Verdacht aus dem unscharfen Namens- und Adressabgleich.":
    "Master records created more than once, across all areas. A distinction is made between hard proof (same VAT registration number, same bank details, same EAN) and a reasoned suspicion from the fuzzy name and address match.",
  "Anlage, Sperre, Löschvormerkung, Archivierung. Der häufigste Befund ist die nie abgeschlossene Archivierung - sie belastet jede Auswertung und jede Dublettensuche.":
    "Creation, blocking, deletion flag, archiving. The most frequent finding is archiving that was never completed - it burdens every analysis and every duplicate search.",
  "Der zentrale Geschäftspartner, der in S/4HANA an die Stelle getrennter Kreditoren- und Debitorenstämme tritt. Geprüft wird die Konsistenz seiner Grunddaten und Rollen.":
    "The central business partner that replaces separate vendor and customer masters in S/4HANA. What is checked is the consistency of its basic data and roles.",

  // Pruefschwerpunkte
  "Voraussetzungen des Zahllaufs - IBAN nach ISO 13616, BIC, Zahlweg je Land, Bankland gegen IBAN":
    "Prerequisites of the payment run - IBAN to ISO 13616, BIC, payment method per country, bank country against IBAN",
  "Buchbarkeit - Abstimmkonto vorhanden, im Buchungskreis angelegt und als Kreditorenkonto gekennzeichnet":
    "Postability - reconciliation account present, created in the company code and marked as a vendor account",
  "Fälligkeit und Skonto - Zahlungsbedingung in Buchungskreis und Einkauf, widerspruchsfrei":
    "Due date and cash discount - payment terms in company code and purchasing, free of contradiction",
  "Mehrfach angelegte Lieferanten über USt-IdNr., Bankverbindung und Namensähnlichkeit":
    "Vendors created more than once, via VAT registration number, bank details and name similarity",
  "Zahlungsumleitungsrisiken - kürzlich geänderte Bankdaten, fehlende Funktionstrennung, CpD mit fester Bankverbindung":
    "Payment diversion risks - recently changed bank details, missing segregation of duties, one-time account with fixed bank details",
  "Steuerfreiheit innergemeinschaftlicher Lieferungen - USt-IdNr. vorhanden, formal richtig, über VIES bestätigt":
    "Exemption of intra-Community supplies - VAT registration number present, formally correct, confirmed through VIES",
  "Fakturierbarkeit - Buchungskreis- und Vertriebsbereichsdaten vollständig, Verkaufsorganisation vorhanden":
    "Billability - company code and sales area data complete, sales organization present",
  "Fälligkeit und Altersstruktur - Zahlungsbedingung im Buchungskreis":
    "Due date and ageing - payment terms in the company code",
  "Wirksamkeit von Sperren - Vertriebssperre gegen offenen Buchungskreis":
    "Effectiveness of blocks - sales block against an open company code",
  "Kundendubletten, die Zahlungshistorie und Kreditlimit auf mehrere Konten verteilen":
    "Customer duplicates that split payment history and credit limit across several accounts",
  "Disponierbarkeit - Dispomerkmal, Werkssicht, Basismengeneinheit":
    "Planability - MRP type, plant view, base unit of measure",
  "Bewertbarkeit - Bewertungsklasse vorhanden und zur Materialart passend":
    "Valuability - valuation class present and matching the material type",
  "Bestandswert - Standardpreissteuerung ohne Preis, Bestand ohne Preis, Wert gegen Menge mal Preis":
    "Stock value - standard price control without a price, stock without a price, value against quantity times price",
  "Identifikation - Kurztext, EAN mit gültiger Prüfziffer":
    "Identification - short text, EAN with a valid check digit",
  "Doppelt angelegte Materialien, die Bestand und Bedarf zersplittern":
    "Materials created twice that fragment stock and requirements",
  "Abstimmkonten - vorhanden, im Buchungskreis angelegt, richtige Kontoart":
    "Reconciliation accounts - present, created in the company code, correct account type",
  "Kontenfindung im Materialstamm - Bewertungsklasse gegen Materialart über die Kontenkategorie-Referenz":
    "Account determination in the material master - valuation class against material type via the account category reference",
  "Bestandsbewertung - Wert, Menge und Preis müssen zueinander passen":
    "Inventory valuation - value, quantity and price must match",
  "Verwaiste Nebenbuchsätze ohne allgemeine Daten":
    "Orphaned sub-ledger records without general data",
  "USt-IdNr. - Vorhandensein, länderspezifischer Aufbau, Prüfziffer für DE, NL und IT":
    "VAT registration number - presence, country-specific structure, check digit for DE, NL and IT",
  "Qualifizierte Bestätigung über das VIES-Verfahren der Europäischen Kommission":
    "Qualified confirmation through the European Commission's VIES procedure",
  "Länderkennzeichen der USt-IdNr. gegen das Land des Partners":
    "Country code of the VAT registration number against the partner's country",
  "Kennzeichen \"natürliche Person\" - es steuert Quellensteuer und Meldepflichten":
    "The \"natural person\" indicator - it drives withholding tax and reporting obligations",
  "Ladungsfähige Anschrift statt reiner Postfachanschrift":
    "A physical address rather than a PO box only",
  "Zahlungsumleitung - kürzlich geänderte Bankdaten, Bankverbindung eines Mitarbeiters":
    "Payment diversion - recently changed bank details, an employee's bank details",
  "Funktionstrennung - derselbe Benutzer legt an und ändert Bankdaten":
    "Segregation of duties - the same user creates the record and changes the bank details",
  "CpD-Konto mit fest hinterlegter Bankverbindung":
    "One-time account with fixed bank details",
  "Dieselbe Bankverbindung bei mehreren Partnern oder über Kreditor und Debitor hinweg":
    "The same bank details with several partners, or across vendor and customer",
  "Zur Löschung vorgemerkte Kreditoren ohne Zahlsperre":
    "Vendors flagged for deletion without a payment block",
  "Harter Nachweis über USt-IdNr., Steuernummer, Bankverbindung und EAN":
    "Hard proof via VAT registration number, tax number, bank details and EAN",
  "Unscharfer Abgleich nach Normalisierung von Umlauten, Rechtsformen und Straßenabkürzungen":
    "Fuzzy matching after normalising umlauts, legal forms and street abbreviations",
  "Cluster statt Paarlisten - ein Befund je Gruppe, in einem Zug bereinigbar":
    "Clusters instead of pair lists - one finding per group, cleanable in one go",
  "Bereinigungspotenzial in Stammsätzen, wenn je Cluster einer führend wird":
    "Cleanup potential in master records once one per cluster becomes the leading one",
  "Löschvormerkung gesetzt, Archivierungslauf nie ausgeführt":
    "Deletion flag set, archiving run never executed",
  "Vormerkung zentral gesetzt, im Buchungskreis oder Werk aber nicht - sie wirkt dann nicht":
    "Flag set centrally but not in the company code or plant - it then has no effect",
  "Dauerhafte Sperren als Zeichen beendeter Geschäftsbeziehungen":
    "Permanent blocks as a sign of ended business relationships",
  "Fehlanlagen - kurz nach der Anlage wieder vorgemerkt":
    "Mistaken entries - flagged again shortly after creation",
  "Material mit Löschvormerkung, aber weiterhin mit Bestand":
    "Material with a deletion flag but still carrying stock",
  "Identifizierbarkeit - Name je nach Partnertyp in den richtigen Feldern":
    "Identifiability - the name in the right fields for the partner category",
  "Rollen - ohne Rolle ist der Partner in keinem Prozess verwendbar":
    "Roles - without a role the partner is usable in no process",
  "Adresszuordnung über die zentrale Adressverwaltung":
    "Address assignment through central address management",
  "Gültigkeitszeiträume und Löschkennzeichen gegen aktive Rollen":
    "Validity periods and deletion marks against active roles",

  // Grenzen
  "Bestellungen, Wareneingänge, Rechnungen und Zahlungen sind nicht im Umfang. Doppelte Rechnungen, Abweichungen im Drei-Wege-Abgleich und Bestellungen am Rahmenvertrag vorbei lassen sich damit nicht finden.":
    "Purchase orders, goods receipts, invoices and payments are out of scope. Duplicate invoices, three-way-match discrepancies and orders placed around the framework agreement cannot be found with this.",
  "Aufträge, Lieferungen und Fakturen sind nicht im Umfang. Die Kreditausschöpfung gegen das Limit, die Umsatzverteilung und offene Posten lassen sich damit nicht bewerten - wohl aber der Umstand, dass ein Limit durch eine Dublette auf zwei Konten zerfällt.":
    "Sales orders, deliveries and billing documents are out of scope. Credit utilisation against the limit, revenue distribution and open items cannot be assessed with this - but the fact that a limit falls apart across two accounts through a duplicate can.",
  "Warenbewegungen, Bestellungen und Fertigungsaufträge sind nicht im Umfang. \"Seit langem unbewegt\" stützt sich auf das Änderungsdatum im Stammsatz, nicht auf die letzte Bewegung - ein Material mit regem Umschlag, aber unverändertem Stammsatz erscheint darin als Kandidat für die Stilllegung.":
    "Goods movements, purchase orders and production orders are out of scope. \"Unmoved for a long time\" rests on the change date in the master record, not on the last movement - a material with brisk turnover but an unchanged master record appears there as a candidate for retirement.",
  "Buchungen, Belege und Salden sind nicht im Umfang. Das Werkzeug zeigt, wo die Kontenfindung falsch aufgesetzt ist - nicht, welcher Betrag dadurch auf dem falschen Konto gelandet ist.":
    "Postings, documents and balances are out of scope. The tool shows where account determination is set up wrongly - not which amount ended up in the wrong account as a result.",
  "Steuerkennzeichen, Steuerfindung und Quellensteuerarten sind noch nicht belegt, obwohl die Tabellen T007A, T059P und T059Z in den Metadaten bereits beschrieben sind. Der Abgleich \"natürliche Person ohne Quellensteuerkennzeichen\" wäre als reine Regeldatei nachzuziehen.":
    "Tax codes, tax determination and withholding tax types are not covered yet, although tables T007A, T059P and T059Z are already described in the metadata. The check \"natural person without a withholding tax code\" could be added as a pure rule file.",
  "Die Auswertung stützt sich auf Stammdaten und Änderungsbelege. Ohne Zahllaufdaten lässt sich nicht sagen, ob eine auffällige Konstellation auch tatsächlich zu einer Zahlung geführt hat.":
    "The analysis rests on master data and change documents. Without payment run data it cannot be said whether a conspicuous constellation actually led to a payment.",
  "Ein unscharfer Treffer ist ein Verdacht mit Score, kein Nachweis. Geblockt wird nach Land und Postleitzahl sowie nach Namensanfang; ein Partner, der unter völlig anderem Namen an anderer Anschrift in einem anderen Land angelegt wurde, wird nur über einen harten Schlüssel gefunden.":
    "A fuzzy hit is a suspicion with a score, not proof. Blocking is by country and postal code as well as by name prefix; a partner created under a completely different name, at a different address, in a different country is found only through a hard key.",
  "\"Seit langem unverändert\" stützt sich auf die Änderungshistorie (CDHDR/CDPOS) und auf das Änderungsdatum im Stammsatz. Eine Buchung ohne Stammdatenänderung bleibt unsichtbar; die Aussage ist ein Ersatzmaß, kein Bewegungsnachweis.":
    "\"Unchanged for a long time\" rests on the change history (CDHDR/CDPOS) and on the change date in the master record. A posting without a master data change stays invisible; the statement is a proxy, not evidence of movement.",
  "Der Abgleich zwischen Geschäftspartner und den abgeleiteten Kreditoren- und Debitorensichten (Customer/Vendor Integration) ist noch nicht belegt. Eine eigene Dublettenregel auf Geschäftspartnern gibt es ebenfalls noch nicht - Dubletten werden über die Rollensichten gefunden.":
    "The reconciliation between the business partner and the derived vendor and customer views (Customer/Vendor Integration) is not covered yet. There is no dedicated duplicate rule on business partners either - duplicates are found through the role views.",

  // -------------------------------------------------------------- Wortschatz
  "Kreditoren": "Vendors",
  "Debitoren": "Customers",
  "Material": "Materials",
  "Geschäftspartner": "Business partners",
  "Bankdaten": "Bank data",
  "Übergreifend": "Cross-area",
  "offen": "open",
  "in Klärung": "in clarification",
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

  // ------------------------------------------------------------------ Eingang
  "Die Dateien, aus denen der nächste Lauf liest. Sie bleiben auf diesem Rechner: der Browser schickt sie an das Werkzeug, das hier läuft, und dieses legt sie in das Eingangsverzeichnis.":
    "The files the next run reads from. They stay on this machine: the browser hands them to the tool running here, and it places them in the input directory.",
  "Dateien hierher ziehen oder auswählen": "Drop files here or choose them",
  "Dateien auswählen oder hierher ziehen": "Choose files or drop them here",
  "Dateien auswählen": "Choose files",
  "Im Eingangsverzeichnis": "In the input directory",
  "{endungen} - bis {groesse} je Datei": "{endungen} - up to {groesse} per file",
  "Noch keine Datei im Eingang.": "No file in the inbox yet.",
  "Abgelegt": "Added",
  "Wird gelesen": "Read by the run",
  "Diese Datei wird beim Lauf übergangen - die Endung gehört nicht zu den gelesenen oder ein Ausschlussmuster greift.":
    "This file is skipped by the run - its extension is not among those read, or an ignore pattern applies.",
  "{name} aus dem Eingangsverzeichnis löschen?": "Delete {name} from the input directory?",
  "{name} entfernt.": "{name} removed.",
  "Fehler": "Error",
  "{n} Datei(en) übernommen. Mit 'Prüfung starten' wird die Lieferung geprüft.":
    "{n} file(s) accepted. Use 'Start check' to run the analysis.",
  "Diese Dateiendung wird nicht gelesen. Möglich sind {endungen}.":
    "This file extension is not read. Possible are {endungen}.",
  "Die Datei ist größer als {groesse}.": "The file is larger than {groesse}.",
  "Die Datei ist leer.": "The file is empty.",
  "Die Übertragung wurde abgebrochen.": "The transfer was interrupted.",

  // Meldungen des Servers beim Hochladen. Sie kommen als Vorlage mit Werten
  // zurück, damit sie hier übersetzbar bleiben.
  "Es wurde kein Dateiname übergeben.": "No file name was supplied.",
  "Der Dateiname ist zu lang (höchstens 120 Zeichen).":
    "The file name is too long (120 characters at most).",
  "Der Dateiname enthält einen Pfad: {name}": "The file name contains a path: {name}",
  "Der Dateiname enthält unzulässige Zeichen: {name}":
    "The file name contains characters that are not allowed: {name}",
  "Ein Dateiname darf nicht mit einem Punkt beginnen.":
    "A file name must not start with a dot.",
  "Der Dateiname ist ein reservierter Name: {name}":
    "The file name is a reserved name: {name}",
  "Diese Dateiendung wird nicht gelesen: {name}. Möglich sind {endungen}.":
    "This file extension is not read: {name}. Possible are {endungen}.",
  "Der Dateiname führt aus dem Eingangsverzeichnis: {name}":
    "The file name leads out of the input directory: {name}",
  "Diese Datei liegt nicht im Eingang: {name}": "This file is not in the inbox: {name}",
  "Die Datei ist größer als {n} MB. Bitte legen Sie sie direkt in das Eingangsverzeichnis.":
    "The file is larger than {n} MB. Please place it in the input directory directly.",
  "Die Datei ließ sich nicht schreiben: {fehler}": "The file could not be written: {fehler}",

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

/** Übersetzt einen Text und setzt Platzhalter ein.
 *
 * Unbekannte Texte gehen unverändert durch. Das ist beabsichtigt: Regelnamen,
 * Objektschlüssel und Feldinhalte laufen durch dieselbe Funktion und dürfen
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

/** Die Sprachkennung für Zahlen- und Datumsformate. */
function gebietsschema() {
  return SPRACHE === "de" ? "de-DE" : "en-GB";
}
