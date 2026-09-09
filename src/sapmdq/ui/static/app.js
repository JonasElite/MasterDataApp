/* Oberflaeche der SAP-Stammdatenpruefung.
 *
 * Kein Rahmenwerk, keine Abhaengigkeit, keine Nachladung aus dem Netz. Die
 * Datei baut die Anzeige aus den Antworten der lokalen Schnittstelle auf.
 *
 * Werte aus den Daten werden ausschliesslich als Textknoten gesetzt und nie
 * als HTML eingefuegt. Ein Materialkurztext, der wie ein Auszeichnungsbefehl
 * aussieht, bleibt damit Text - er stammt aus dem Kundensystem und ist fuer
 * uns nicht vertrauenswuerdig.
 */
"use strict";

const TOKEN = new URLSearchParams(location.search).get("token") || "";

/* ------------------------------------------------------------- Bausteine */

function el(tag, attrs, kinder) {
  const knoten = document.createElement(tag);
  for (const [name, wert] of Object.entries(attrs || {})) {
    if (wert === null || wert === undefined || wert === false) continue;
    if (name === "text") knoten.textContent = String(wert);
    else if (name === "class") knoten.className = wert;
    else if (name.startsWith("on")) knoten.addEventListener(name.slice(2), wert);
    else knoten.setAttribute(name, wert === true ? "" : String(wert));
  }
  for (const kind of [].concat(kinder || [])) {
    if (kind === null || kind === undefined || kind === false) continue;
    knoten.append(typeof kind === "object" ? kind : document.createTextNode(String(kind)));
  }
  return knoten;
}

function leeren(ziel) {
  while (ziel.firstChild) ziel.removeChild(ziel.firstChild);
  return ziel;
}

function setzen(ziel, inhalt) {
  leeren(ziel);
  for (const kind of [].concat(inhalt || [])) if (kind) ziel.append(kind);
  return ziel;
}

const $ = (auswahl) => document.querySelector(auswahl);

/* --------------------------------------------------------- Formatierungen */

const zahl = (wert) =>
  wert === null || wert === undefined || Number.isNaN(Number(wert))
    ? "-"
    : Number(wert).toLocaleString("de-DE");

const prozent = (anteil, stellen) =>
  anteil === null || anteil === undefined
    ? "-"
    : (Number(anteil) * 100).toFixed(stellen === undefined ? 0 : stellen).replace(".", ",") + " %";

function zeitpunkt(iso) {
  if (!iso) return "-";
  const wert = new Date(iso);
  if (Number.isNaN(wert.getTime())) return iso;
  return wert.toLocaleString("de-DE", {
    year: "numeric", month: "2-digit", day: "2-digit",
    hour: "2-digit", minute: "2-digit",
  });
}

function dauer(sekunden) {
  const s = Number(sekunden || 0);
  if (s < 60) return s.toFixed(1).replace(".", ",") + " s";
  if (s < 3600) return Math.floor(s / 60) + " min " + Math.round(s % 60) + " s";
  return Math.floor(s / 3600) + " h " + Math.round((s % 3600) / 60) + " min";
}

const BEREICHE = {
  vendor: "Kreditoren",
  customer: "Debitoren",
  material: "Material",
  business_partner: "Geschaeftspartner",
  bank: "Bankdaten",
  cross: "Uebergreifend",
  delivery: "Lieferung",
};
const bereichName = (schluessel) => BEREICHE[schluessel] || schluessel || "-";

const SCHWEREGRADE = ["critical", "high", "medium", "low", "info"];

function merkmal(wert, klasse) {
  return el("span", { class: "merkmal " + (klasse || "leise"), text: wert });
}

function schweregradMerkmal(grad) {
  return merkmal(grad || "-", SCHWEREGRADE.includes(grad) ? grad : "leise");
}

/* --------------------------------------------------------------- Aufrufe */

async function hole(pfad, werte) {
  const url = new URL(pfad, location.origin);
  for (const [name, wert] of Object.entries(werte || {})) {
    if (wert === "" || wert === null || wert === undefined) continue;
    url.searchParams.set(name, wert);
  }
  const antwort = await fetch(url, { headers: { "X-Sapmdq-Token": TOKEN } });
  const daten = await antwort.json().catch(() => ({ fehler: "Antwort nicht lesbar." }));
  if (!antwort.ok) throw new Error(daten.fehler || "Aufruf fehlgeschlagen (" + antwort.status + ").");
  return daten;
}

async function sende(pfad, daten) {
  const antwort = await fetch(pfad, {
    method: "POST",
    headers: { "X-Sapmdq-Token": TOKEN, "Content-Type": "application/json" },
    body: JSON.stringify(daten || {}),
  });
  const ergebnis = await antwort.json().catch(() => ({ fehler: "Antwort nicht lesbar." }));
  if (!antwort.ok) throw new Error(ergebnis.fehler || "Aufruf fehlgeschlagen (" + antwort.status + ").");
  return ergebnis;
}

/* ------------------------------------------------------------- Meldungen */

function melden(text, art) {
  const kasten = el("div", { class: "meldung " + (art || "hinweis") }, [
    el("span", { text: text }),
  ]);
  $("#meldungen").append(kasten);
  if (art !== "fehler") setTimeout(() => kasten.remove(), 8000);
}

function meldungenLeeren() {
  leeren($("#meldungen"));
}

/* ---------------------------------------------------------------- Zustand */

const Z = {
  projekt: null,
  laeufe: [],
  laufId: "",
  lauf: null,
  ansicht: "lagebild",
  befunde: { seite: 1, gesamt: 0, seiten: 1 },
  fortschrittUhr: null,
};

/* ------------------------------------------------------------- Tabellen */

function tabelle(spalten, zeilen, aufZeile) {
  if (!zeilen.length) return el("p", { class: "nichts", text: "Nichts vorhanden." });
  const kopf = el("tr", {}, spalten.map((spalte) =>
    el("th", { class: spalte.zahl ? "zahl" : null, text: spalte.titel })));
  const koerper = el("tbody", {}, zeilen.map((zeile, index) => {
    const tr = el("tr", {
      class: aufZeile ? "klickbar" : null,
      tabindex: aufZeile ? "0" : null,
      onclick: aufZeile ? () => aufZeile(zeile) : null,
      onkeydown: aufZeile
        ? (ereignis) => {
            if (ereignis.key === "Enter" || ereignis.key === " ") {
              ereignis.preventDefault();
              aufZeile(zeile);
            }
          }
        : null,
    });
    for (const spalte of spalten) {
      const inhalt = spalte.zelle(zeile, index);
      tr.append(el("td", {
        class: [spalte.zahl ? "zahl" : "", spalte.fest ? "fest" : ""].join(" ").trim() || null,
      }, typeof inhalt === "object" && inhalt !== null ? [inhalt] : [inhalt === "" || inhalt === null || inhalt === undefined ? "-" : inhalt]));
    }
    return tr;
  }));
  return el("div", { class: "tabellenrahmen" }, [
    el("table", {}, [el("thead", {}, [kopf]), koerper]),
  ]);
}

function balken(eintraege, farbeFuer) {
  if (!eintraege.length) return el("p", { class: "nichts", text: "Keine Befunde." });
  const groesster = Math.max(...eintraege.map((e) => e.wert), 1);
  return el("div", { class: "balken" }, eintraege.map((eintrag) => {
    const fuellung = el("div", { class: "balken-fuellung" });
    fuellung.style.width = Math.max((eintrag.wert / groesster) * 100, 2) + "%";
    if (farbeFuer) fuellung.style.background = farbeFuer(eintrag);
    return el("div", { class: "balken-zeile" }, [
      el("div", { class: "balken-name", title: eintrag.name, text: eintrag.name }),
      el("div", { class: "balken-spur" }, [fuellung]),
      el("div", { class: "balken-wert", text: zahl(eintrag.wert) }),
    ]);
  }));
}

/* ------------------------------------------------------------ Diagramme
 *
 * Alles aus HTML und CSS. Zwei Formen genuegen fuer das, was hier gezeigt
 * wird: liegende Saeulen fuer einen Groessenvergleich und ein Ring fuer einen
 * Anteil. Jeder Wert steht als Zahl daneben - niemand soll eine Laenge
 * schaetzen oder erst mit der Maus danach suchen muessen.
 */

/** Liegende Saeulen mit Beschriftung am Ende.
 *
 * ``eintraege``: {name, wert, farbe?, titel?, aufKlick?, anteilVon?}
 */
function saeulen(eintraege, einstellungen) {
  const opt = einstellungen || {};
  if (!eintraege.length) {
    return el("p", { class: "nichts", text: opt.leer || "Nichts vorhanden." });
  }
  const groesster = Math.max(...eintraege.map((e) => e.wert), 1);
  const summe = eintraege.reduce((a, e) => a + e.wert, 0);

  return el("div", { class: "saeulen" + (opt.langeNamen ? " lange-namen" : "") },
      eintraege.map((eintrag) => {
    const balken = el("div", { class: "saeule-balken" });
    balken.style.width = Math.max((eintrag.wert / groesster) * 100, 1.5) + "%";
    if (eintrag.farbe) balken.style.background = eintrag.farbe;

    const anteil = opt.anteile && summe
      ? el("span", { class: "saeule-anteil", text: " " + Math.round((eintrag.wert / summe) * 100) + " %" })
      : null;

    return el("div", {
      class: "saeule" + (eintrag.aufKlick ? " klickbar" : ""),
      title: eintrag.titel || (eintrag.name + ": " + zahl(eintrag.wert)),
      tabindex: eintrag.aufKlick ? "0" : null,
      role: eintrag.aufKlick ? "button" : null,
      onclick: eintrag.aufKlick || null,
      onkeydown: eintrag.aufKlick
        ? (ereignis) => {
            if (ereignis.key === "Enter" || ereignis.key === " ") {
              ereignis.preventDefault();
              eintrag.aufKlick();
            }
          }
        : null,
    }, [
      el("div", { class: "saeule-name", text: eintrag.name }),
      el("div", { class: "saeule-spur" }, [balken]),
      el("div", { class: "saeule-wert" }, [zahl(eintrag.wert), anteil]),
    ]);
  }));
}

/** Anteilsring - ein Wert gegen sein Ganzes. */
function ring(anteil, wert, unter, ton) {
  const koerper = el("div", { class: "ring" }, [
    el("div", { class: "ring-text" }, [
      el("div", { class: "ring-wert", text: wert }),
      el("div", { class: "ring-unter", text: unter || "" }),
    ]),
  ]);
  koerper.style.setProperty("--anteil", Math.max(0, Math.min(100, anteil * 100)));
  if (ton) koerper.style.setProperty("--ton", ton);
  return koerper;
}

function ampelfeld(titel, wert, klasse, hinweis) {
  return el("div", { class: "ampel-feld " + (klasse || ""), title: hinweis || null }, [
    el("div", { class: "ampel-wert", text: wert }),
    el("div", { class: "ampel-titel", text: titel }),
  ]);
}

/** Veraenderung gegen den Vorlauf. Weniger Befunde ist besser. */
function trend(neu, behoben) {
  const netto = (neu || 0) - (behoben || 0);
  if (!neu && !behoben) return el("span", { class: "trend gleich", text: "unveraendert" });
  const klasse = netto < 0 ? "besser" : netto > 0 ? "schlechter" : "gleich";
  const zeichen = netto < 0 ? "\u2193 " : netto > 0 ? "\u2191 " : "";
  return el("span", { class: "trend " + klasse, title:
      zahl(behoben) + " behoben, " + zahl(neu) + " neu hinzugekommen" }, [
    zeichen + zahl(Math.abs(netto)) + (netto === 0 ? " netto" : netto < 0 ? " weniger" : " mehr"),
  ]);
}

/** Einordnung eines Punktwertes in Worten.
 *
 * Wortlaut und Schwellen sind dieselben wie in ``report/score.py``. Sonst
 * stuende in der Management-Summary ein anderes Wort als auf dem Bildschirm,
 * und beides waere im selben Termin zu sehen.
 */
function einordnung(score) {
  if (score === null || score === undefined) return { text: "nicht bewertbar", klasse: "leise" };
  if (score >= 95) return { text: "sehr gut", klasse: "gut" };
  if (score >= 85) return { text: "gut", klasse: "gut" };
  if (score >= 70) return { text: "befriedigend", klasse: "medium" };
  if (score >= 50) return { text: "kritisch", klasse: "high" };
  return { text: "unzureichend", klasse: "critical" };
}

function kachel(titel, wert, zusatz, klasse) {
  return el("div", { class: "kachel " + (klasse || "") }, [
    el("div", { class: "titel", text: titel }),
    el("div", { class: "wert", text: wert }),
    zusatz ? el("div", { class: "zusatz", text: zusatz }) : null,
  ]);
}

const farbeSchweregrad = (grad) =>
  "var(--" + (SCHWEREGRADE.includes(grad) ? grad : "low") + ")";

/* ------------------------------------------------------------- Lagebild */

function zeigeLagebild() {
  const lauf = Z.lauf;
  const leer = (id) => setzen($(id), [el("p", { class: "nichts", text: "Kein Lauf ausgewaehlt." })]);
  if (!lauf) {
    for (const id of ["#lb-ampel", "#lb-schweregrade", "#lb-bereiche", "#lb-regeln",
                      "#lb-nachforderung", "#lb-bewertung", "#lb-ring"]) leer(id);
    $("#lb-score").textContent = "-";
    return;
  }

  const befunde = lauf.befunde || {};
  const coverage = lauf.coverage || {};
  const bewertung = lauf.bewertung || {};
  const vergleich = lauf.vergleich;
  const jeGrad = befunde.je_schweregrad || {};

  // ------------------------------------------------------------ Kennzahl
  const score = bewertung.gesamt;
  $("#lb-score").textContent = score === null || score === undefined
    ? "-" : String(score).replace(".", ",");
  const note = einordnung(score);
  setzen($("#lb-einordnung"), [
    el("span", { class: "merkmal hero-einordnung " + note.klasse, text: note.text }),
  ]);
  $("#lb-score-zusatz").textContent =
    "von 100 Punkten, aus " + zahl(lauf.saetze_verarbeitet) + " geprueften Saetzen.";

  // ------------------------------------------------------- Pruefumfang
  setzen($("#lb-ring"), [ring(
    coverage.anteil || 0,
    prozent(coverage.anteil),
    (coverage.ausfuehrbar || 0) + " von " + (coverage.regeln_gesamt || 0),
  )]);
  $("#lb-ring-text").textContent = coverage.vorbehalt || "";

  // ---------------------------------------------------------- Ampelzeile
  const felder = [
    ampelfeld("Befunde offen", zahl(befunde.effektiv),
      (befunde.effektiv || 0) ? "" : "gut",
      "Ohne die als Ausnahme anerkannten Befunde."),
    ampelfeld("kritisch", zahl(jeGrad.critical || 0),
      (jeGrad.critical || 0) ? "critical" : "gut"),
    ampelfeld("hoch", zahl(jeGrad.high || 0), (jeGrad.high || 0) ? "high" : "gut"),
    ampelfeld("Ausnahmen", zahl(befunde.ausnahmen || 0), "",
      "Befunde, die mit Begruendung anerkannt wurden."),
    ampelfeld("Regelfehler", zahl(lauf.regelfehler),
      lauf.regelfehler ? "critical" : "gut",
      lauf.regelfehler ? "Das Ergebnis ist unvollstaendig." : "Alle Regeln liefen durch."),
  ];
  if (vergleich) {
    felder.push(el("div", { class: "ampel-feld" }, [
      el("div", { class: "ampel-wert" }, [trend(vergleich.neu, vergleich.behoben)]),
      el("div", { class: "ampel-titel", text: "gegen den Vorlauf" }),
    ]));
  }
  setzen($("#lb-ampel"), felder);

  // ------------------------------------------------------- Schweregrade
  setzen($("#lb-schweregrade"), [saeulen(
    SCHWEREGRADE.filter((grad) => jeGrad[grad]).map((grad) => ({
      name: grad,
      wert: jeGrad[grad],
      farbe: "var(--" + grad + ")",
      titel: zahl(jeGrad[grad]) + " Befunde mit Schweregrad " + grad
             + " - klicken, um die Liste darauf einzuschraenken",
      aufKlick: () => {
        zuAnsicht("befunde");
        $("#b-schweregrad").value = grad;
        Z.befunde.seite = 1;
        zeigeBefunde();
      },
    })),
    { anteile: true, leer: "Keine Befunde." },
  )]);

  // ------------------------------------------------------------ Bereiche
  setzen($("#lb-bereiche"), [saeulen(
    Object.entries(befunde.je_bereich || {})
      .map(([schluessel, wert]) => ({
        name: bereichName(schluessel),
        wert: wert,
        titel: zahl(wert) + " Befunde in " + bereichName(schluessel)
               + " - klicken, um die Liste darauf einzuschraenken",
        aufKlick: () => {
          zuAnsicht("befunde");
          $("#b-bereich").value = schluessel;
          Z.befunde.seite = 1;
          zeigeBefunde();
        },
      }))
      .sort((a, b) => b.wert - a.wert),
    { anteile: true, leer: "Keine Befunde." },
  )]);

  // -------------------------------------------------------------- Regeln
  const haeufigste = (lauf.regellauf || [])
    .filter((eintrag) => eintrag.befunde > 0)
    .sort((a, b) => b.befunde - a.befunde)
    .slice(0, 8);
  setzen($("#lb-regeln"), [saeulen(
    haeufigste.map((eintrag) => ({
      name: eintrag.name,
      wert: eintrag.befunde,
      titel: eintrag.id + ": " + eintrag.name + " - " + zahl(eintrag.befunde) + " Befunde",
      aufKlick: () => zuAnsicht("befunde", { regel: eintrag.id }),
    })),
    { leer: "Keine Befunde.", langeNamen: true },
  )]);

  // ------------------------------------------------------- Nachforderung
  const offen = (coverage.nachforderung || [])
    .filter((k) => !k.geliefert)
    .slice()
    .sort((a, b) => (b.kumuliert || 0) - (a.kumuliert || 0))
    .slice(0, 8);
  setzen($("#lb-nachforderung"), [saeulen(
    offen.map((kandidat) => ({
      name: kandidat.tabelle,
      wert: kandidat.kumuliert || kandidat.zusaetzliche_pruefungen || 0,
      titel: kandidat.tabelle + " (" + kandidat.bedeutung + "): schaltet "
             + zahl(kandidat.kumuliert) + " weitere Pruefungen frei",
    })),
    { leer: "Die Lieferung ist vollstaendig - es fehlt nichts." },
  )]);

  // ----------------------------------------------------------- Bewertung
  setzen($("#lb-bewertung"), [tabelle([
    { titel: "Bereich", zelle: (z) => bereichName(z.bereich) },
    { titel: "Punkte", zahl: true, zelle: (z) => z.score === null ? "-" : String(z.score).replace(".", ",") },
    { titel: "Einordnung", zelle: (z) => {
        const n = einordnung(z.score);
        return merkmal(z.einordnung || n.text, n.klasse);
      } },
    { titel: "Befunde", zahl: true, zelle: (z) => zahl(z.befunde) },
    { titel: "Saetze", zahl: true, zelle: (z) => zahl(z.gepruefte_saetze) },
    { titel: "Regeln", zahl: true, zelle: (z) => z.regeln_ausfuehrbar + " / " + z.regeln_gesamt },
    { titel: "Vorbehalt", zelle: (z) => z.vorbehalt || "" },
  ], bewertung.bereiche || [])]);
}

/* -------------------------------------------------------------- Lieferung */

function zeigeLieferung() {
  const lieferung = (Z.lauf || {}).lieferung || {};

  setzen($("#l-urteil"), [
    el("div", { class: "meldung " + (lieferung.verwertbar === false ? "fehler" : "erfolg") }, [
      lieferung.verwertbar === false
        ? "Die Lieferung ist nicht verwertbar. Der Lauf wurde nur mit ausdruecklicher Freigabe fortgesetzt; die Ergebnisse sind entsprechend eingeschraenkt."
        : "Die Lieferung ist verwertbar.",
    ]),
  ]);

  setzen($("#l-dateien"), [tabelle([
    { titel: "Datei", zelle: (z) => z.name },
    { titel: "Tabelle", fest: true, zelle: (z) => z.tabelle },
    { titel: "Zuordnung", zelle: (z) => z.zuordnung },
    { titel: "Format", zelle: (z) => z.format + " / " + z.encoding },
    { titel: "Zeilen", zahl: true, zelle: (z) => zahl(z.zeilen) },
    { titel: "Abgewiesen", zahl: true, zelle: (z) =>
        z.abgewiesene_zeilen
          ? el("span", { class: "merkmal critical", text: zahl(z.abgewiesene_zeilen) })
          : "0" },
    { titel: "Stichtag", zelle: (z) => z.stichtag ? z.stichtag + " (" + z.stichtag_quelle + ")" : "" },
    { titel: "Groesse", zahl: true, zelle: (z) => zahl(Math.round((z.groesse_bytes || 0) / 1024)) + " kB" },
    { titel: "SHA-256", fest: true, zelle: (z) => (z.sha256 || "").slice(0, 12) },
  ], lieferung.dateien || [])]);

  setzen($("#l-tabellen"), [tabelle([
    { titel: "Tabelle", fest: true, zelle: (z) => z.name },
    { titel: "Bereich", zelle: (z) => bereichName(z.bereich) },
    { titel: "Saetze", zahl: true, zelle: (z) => zahl(z.saetze) },
    { titel: "Vor Filter", zahl: true, zelle: (z) => zahl(z.saetze_vor_filter) },
    { titel: "Spalten", zahl: true, zelle: (z) => zahl(z.spalten) },
    { titel: "Mandanten", zelle: (z) => (z.mandanten || []).join(", ") },
    { titel: "Quelldateien", zelle: (z) => (z.quelldateien || []).join(", ") },
  ], lieferung.tabellen || [])]);

  setzen($("#l-pruefungen"), [tabelle([
    { titel: "Pruefung", fest: true, zelle: (z) => z.id },
    { titel: "Gewicht", zelle: (z) => schweregradMerkmal(z.gewicht) },
    { titel: "Gegenstand", zelle: (z) => z.gegenstand },
    { titel: "Anforderung", zelle: (z) => z.anforderung },
    { titel: "Meldung", zelle: (z) => z.meldung },
  ], lieferung.pruefungen || [])]);
}

/* --------------------------------------------------------------- Coverage */

function zeigeCoverage() {
  const coverage = (Z.lauf || {}).coverage || {};

  $("#c-vorbehalt").textContent = coverage.vorbehalt || "Keine Angaben zum Pruefumfang.";
  $("#c-anteil").firstElementChild.style.width = Math.round((coverage.anteil || 0) * 100) + "%";

  setzen($("#c-bereiche"), Object.entries(coverage.je_bereich || {}).map(([bereich, werte]) =>
    kachel(bereichName(bereich),
      prozent(werte.gesamt ? werte.ausfuehrbar / werte.gesamt : 0),
      werte.ausfuehrbar + " von " + werte.gesamt + " Regeln")));

  setzen($("#c-nachforderung"), [tabelle([
    { titel: "Tabelle", fest: true, zelle: (z) => z.tabelle },
    { titel: "Einstufung", zelle: (z) =>
        merkmal(z.einstufung, z.einstufung === "unverzichtbar" ? "critical" : "leise") },
    { titel: "Bedeutung", zelle: (z) => z.bedeutung },
    { titel: "Status", zelle: (z) => z.geliefert
        ? merkmal("geliefert", "gut")
        : merkmal("fehlt", "high") },
    { titel: "Fehlende Felder", fest: true, zelle: (z) => (z.fehlende_felder || []).join(", ") },
    { titel: "Regeln", zahl: true, zelle: (z) => zahl(z.zusaetzliche_pruefungen) },
    { titel: "Kumuliert", zahl: true, zelle: (z) => zahl(z.kumuliert) },
  ], coverage.nachforderung || [])]);

  zeichneRegeln();
}

function zeichneRegeln() {
  const coverage = (Z.lauf || {}).coverage || {};
  const suche = $("#c-suche").value.trim().toLowerCase();
  const nurEntfallen = $("#c-nur-entfallen").checked;

  const regeln = (coverage.regeln || []).filter((regel) => {
    if (nurEntfallen && regel.ausfuehrbar) return false;
    if (!suche) return true;
    return (regel.id + " " + regel.name + " " + regel.beschreibung).toLowerCase().includes(suche);
  });

  setzen($("#c-regeln"), [tabelle([
    { titel: "Regel", fest: true, zelle: (z) => z.id },
    { titel: "Bezeichnung", zelle: (z) => z.name },
    { titel: "Bereich", zelle: (z) => bereichName(z.bereich) },
    { titel: "Kategorie", zelle: (z) => z.kategorie_text },
    { titel: "Grad", zelle: (z) => schweregradMerkmal(z.schweregrad) },
    { titel: "Anforderung", fest: true, zelle: (z) => z.anforderung },
    { titel: "Ausfuehrbar", zelle: (z) => z.ausfuehrbar
        ? merkmal("ja", "gut")
        : merkmal("nein", "high") },
    { titel: "Grund", zelle: (z) => z.ausfuehrbar ? "" : z.grund },
  ], regeln, (regel) => zeigeRegel(regel))]);
}

function zeigeRegel(regel) {
  $("#d-titel").textContent = regel.id;
  setzen($("#d-inhalt"), [
    el("h3", { text: regel.name }),
    el("dl", { class: "paar" }, [
      el("dt", { text: "Bereich" }), el("dd", { text: bereichName(regel.bereich) }),
      el("dt", { text: "Kategorie" }), el("dd", { text: regel.kategorie_text }),
      el("dt", { text: "Schweregrad" }), el("dd", {}, [schweregradMerkmal(regel.schweregrad)]),
      el("dt", { text: "Anforderung" }), el("dd", { text: regel.anforderung }),
      el("dt", { text: "Regelversion" }), el("dd", { class: "fest", text: regel.version }),
      el("dt", { text: "Ausfuehrbar" }), el("dd", { text: regel.ausfuehrbar ? "ja" : "nein - " + regel.grund }),
    ]),
    el("div", { class: "abschnitt" }, [
      el("h3", { text: "Was geprueft wird" }),
      el("p", { text: regel.beschreibung }),
    ]),
    regel.empfehlung
      ? el("div", { class: "abschnitt" }, [
          el("h3", { text: "Handlungsempfehlung" }),
          el("p", { text: regel.empfehlung }),
        ])
      : null,
  ]);
  $("#blende").hidden = false;
}

/* ---------------------------------------------------------------- Befunde */

function befundFilter() {
  return {
    suche: $("#b-suche").value.trim(),
    schweregrad: $("#b-schweregrad").value,
    bereich: $("#b-bereich").value,
    kategorie: $("#b-kategorie").value,
    status: $("#b-status").value,
    vergleich: $("#b-vergleich").value,
    ausnahmen: $("#b-ausnahmen").checked ? "ein" : "aus",
  };
}

function fuelleBefundfilter() {
  const lauf = Z.lauf || {};
  const bereiche = Object.keys((lauf.befunde || {}).je_bereich || {});
  const auswahlBereich = $("#b-bereich");
  const vorherBereich = auswahlBereich.value;
  setzen(auswahlBereich, [el("option", { value: "", text: "Bereich: alle" })].concat(
    bereiche.map((bereich) => el("option", { value: bereich, text: bereichName(bereich) }))));
  auswahlBereich.value = bereiche.includes(vorherBereich) ? vorherBereich : "";

  const kategorien = new Map();
  for (const regel of (lauf.coverage || {}).regeln || []) {
    kategorien.set(regel.kategorie, regel.kategorie_text);
  }
  const auswahlKategorie = $("#b-kategorie");
  const vorherKategorie = auswahlKategorie.value;
  setzen(auswahlKategorie, [el("option", { value: "", text: "Kategorie: alle" })].concat(
    [...kategorien].map(([wert, text]) => el("option", { value: wert, text: text }))));
  auswahlKategorie.value = kategorien.has(vorherKategorie) ? vorherKategorie : "";
}

let befundeAnfrage = 0;

async function zeigeBefunde() {
  if (!Z.laufId) {
    setzen($("#b-tabelle"), [el("p", { class: "nichts", text: "Kein Lauf ausgewaehlt." })]);
    return;
  }
  const laufend = ++befundeAnfrage;
  const werte = Object.assign(befundFilter(), {
    seite: Z.befunde.seite,
    groesse: 50,
    regel: Z.befunde.regel || "",
  });

  try {
    const daten = await hole("/api/laeufe/" + encodeURIComponent(Z.laufId) + "/befunde", werte);
    if (laufend !== befundeAnfrage) return; // eine neuere Anfrage ist unterwegs
    Z.befunde.gesamt = daten.gesamt;
    Z.befunde.seiten = daten.seiten;
    Z.befunde.seite = daten.seite;

    $("#b-anzahl").textContent = zahl(daten.gesamt) + " Befunde"
      + (Z.befunde.regel ? " - eingeschraenkt auf Regel " + Z.befunde.regel : "");
    $("#b-seite").textContent = "Seite " + daten.seite + " von " + daten.seiten;
    $("#b-zurueck").disabled = daten.seite <= 1;
    $("#b-weiter").disabled = daten.seite >= daten.seiten;

    setzen($("#b-tabelle"), [tabelle([
      { titel: "Grad", zelle: (z) => schweregradMerkmal(z.schweregrad) },
      { titel: "Regel", fest: true, zelle: (z) => z.rule_id },
      { titel: "Bezeichnung", zelle: (z) => z.rule_name },
      { titel: "Bereich", zelle: (z) => bereichName(z.bereich) },
      { titel: "Objekt", fest: true, zelle: (z) => z.schluessel },
      { titel: "Mandant", fest: true, zelle: (z) => z.mandant },
      { titel: "Stand", zelle: (z) => el("span", {
          title: z.noch_nicht_im_bericht
            ? "Gepflegt, aber noch nicht in den Bericht uebernommen - das geschieht beim naechsten Lauf."
            : null,
        }, [
          merkmal(z.status, z.status === "offen" ? "leise" : "gut"),
          z.noch_nicht_im_bericht ? " *" : null,
        ]) },
      { titel: "Vergleich", zelle: (z) =>
          z.vergleich === "neu" ? merkmal("neu", "high") : el("span", { class: "leise", text: z.vergleich || "" }) },
      { titel: "Ausnahme", zelle: (z) => z.ausnahme
          ? merkmal("ja", "leise")
          : (z.ausnahme_vorgemerkt ? merkmal("vorgemerkt", "leise") : "") },
      { titel: "Zustaendig", zelle: (z) => z.data_owner },
    ], daten.befunde, (zeile) => oeffneBefund(zeile.finding_id))]);
  } catch (fehler) {
    setzen($("#b-tabelle"), [el("p", { class: "nichts", text: fehler.message })]);
  }
}

async function oeffneBefund(findingId) {
  let befund;
  try {
    befund = await hole("/api/laeufe/" + encodeURIComponent(Z.laufId)
      + "/befunde/" + encodeURIComponent(findingId));
  } catch (fehler) {
    melden(fehler.message, "fehler");
    return;
  }

  $("#d-titel").textContent = befund.rule_id + " - " + befund.schluessel;

  const detailZeilen = Object.entries(befund.detail || {});
  const regel = befund.regel || {};

  setzen($("#d-inhalt"), [
    el("h3", { text: befund.rule_name }),
    el("dl", { class: "paar" }, [
      el("dt", { text: "Schweregrad" }), el("dd", {}, [schweregradMerkmal(befund.schweregrad)]),
      el("dt", { text: "Kategorie" }), el("dd", { text: befund.kategorie }),
      el("dt", { text: "Anforderung" }), el("dd", { text: befund.anforderung }),
      el("dt", { text: "Bereich" }), el("dd", { text: bereichName(befund.bereich) + " / " + befund.objektart }),
      el("dt", { text: "Objekt" }), el("dd", { class: "fest", text: befund.schluessel }),
      el("dt", { text: "Mandant" }), el("dd", { class: "fest", text: befund.mandant || "-" }),
      befund.buchungskreis ? el("dt", { text: "Buchungskreis" }) : null,
      befund.buchungskreis ? el("dd", { class: "fest", text: befund.buchungskreis }) : null,
      el("dt", { text: "Zustaendig" }), el("dd", { text: befund.data_owner || "nicht hinterlegt" }),
      el("dt", { text: "Vergleich" }), el("dd", { text: befund.vergleich || "-" }),
      befund.status_im_bericht ? el("dt", { text: "Stand im Bericht" }) : null,
      befund.status_im_bericht
        ? el("dd", { text: befund.status_im_bericht + " - der gepflegte Stand ist neuer und "
            + "wird beim naechsten Lauf uebernommen." })
        : null,
      el("dt", { text: "Regelversion" }), el("dd", { class: "fest", text: befund.rule_version }),
      el("dt", { text: "Befundkennung" }), el("dd", { class: "fest", text: befund.finding_id }),
    ]),

    detailZeilen.length
      ? el("div", { class: "abschnitt" }, [
          el("h3", { text: "Befundangaben" }),
          tabelle([
            { titel: "Merkmal", zelle: (z) => z[0] },
            { titel: "Wert", fest: true, zelle: (z) => z[1] === null ? "-" : String(z[1]) },
          ], detailZeilen),
        ])
      : null,

    regel.beschreibung
      ? el("div", { class: "abschnitt" }, [
          el("h3", { text: "Was geprueft wird" }),
          el("p", { text: regel.beschreibung }),
          regel.empfehlung ? el("h3", { text: "Handlungsempfehlung" }) : null,
          regel.empfehlung ? el("p", { text: regel.empfehlung }) : null,
        ])
      : null,

    (befund.ausnahme || befund.ausnahme_vorgemerkt)
      ? el("div", { class: "abschnitt" }, [
          el("h3", { text: befund.ausnahme ? "Als Ausnahme anerkannt" : "Als Ausnahme vorgemerkt" }),
          el("p", { text: befund.ausnahme_grund || "ohne Begruendung" }),
          befund.ausnahme_vorgemerkt
            ? el("p", { class: "leise", text: "Die Ausnahme steht in der Ausnahmeliste, ist aber "
                + "in diesem Bericht noch nicht beruecksichtigt. Sie wirkt ab dem naechsten Lauf." })
            : null,
          el("button", {
            class: "knopf knopf-leise",
            text: "Ausnahme zuruecknehmen",
            onclick: async () => {
              try {
                const ergebnis = await sende("/api/ausnahmen/entfernen", { finding_id: befund.finding_id });
                melden(ergebnis.entfernt + " Ausnahme(n) entfernt. Wirksam ab dem naechsten Lauf.", "erfolg");
                oeffneBefund(findingId);
              } catch (fehler) { melden(fehler.message, "fehler"); }
            },
          }),
        ])
      : ausnahmeFormular(befund, findingId),

    statusFormular(befund, findingId),
  ]);

  $("#blende").hidden = false;
}

function statusFormular(befund, findingId) {
  const auswahl = el("select", { "aria-label": "Bearbeitungsstand" },
    ["offen", "in Klaerung", "akzeptiert", "korrigiert"].map((wert) =>
      el("option", { value: wert, text: wert, selected: wert === befund.status })));
  const bemerkung = el("textarea", { placeholder: "Bemerkung (freiwillig)" });
  bemerkung.value = befund.status_bemerkung || "";
  const bearbeiter = el("input", { type: "text", placeholder: "Bearbeiter" });

  return el("div", { class: "abschnitt" }, [
    el("h3", { text: "Bearbeitungsstand" }),
    el("p", { class: "leise", text: "Der Stand wird in der Statusdatei des Projekts gefuehrt und beim naechsten Lauf uebernommen (FA-603)." }),
    el("div", { class: "formular" }, [
      el("div", { class: "formular-reihe" }, [auswahl, bearbeiter]),
      bemerkung,
      el("div", { class: "formular-reihe" }, [
        el("button", {
          class: "knopf knopf-haupt",
          text: "Stand speichern",
          onclick: async (ereignis) => {
            ereignis.target.disabled = true;
            try {
              await sende("/api/status", {
                finding_id: findingId,
                status: auswahl.value,
                bemerkung: bemerkung.value,
                bearbeiter: bearbeiter.value,
                regel: befund.rule_id,
                schluessel: befund.schluessel,
              });
              melden("Bearbeitungsstand gespeichert.", "erfolg");
              zeigeBefunde();
            } catch (fehler) {
              melden(fehler.message, "fehler");
            } finally {
              ereignis.target.disabled = false;
            }
          },
        }),
      ]),
    ]),
  ]);
}

function ausnahmeFormular(befund, findingId) {
  const begruendung = el("textarea", { placeholder: "Begruendung - warum ist der Befund vertretbar?" });
  const freigabe = el("input", { type: "text", placeholder: "Freigegeben von" });
  const verweis = el("input", { type: "text", placeholder: "Verweis (Ticket, Protokoll)" });
  const ablauf = el("input", { type: "date", "aria-label": "Laeuft ab" });
  const umfang = el("select", { "aria-label": "Geltungsbereich" }, [
    el("option", { value: "befund", text: "nur dieser Befund" }),
    el("option", { value: "objekt", text: "dieses Objekt in dieser Regel" }),
    el("option", { value: "regel", text: "alle Befunde dieser Regel" }),
  ]);

  return el("div", { class: "abschnitt" }, [
    el("h3", { text: "Als Ausnahme anerkennen" }),
    el("p", { class: "leise", text: "Die Ausnahme wird in der Ausnahmeliste des Projekts gefuehrt. Sie wirkt ab dem naechsten Lauf; der bereits geschriebene Bericht bleibt unveraendert (FA-602)." }),
    el("div", { class: "formular" }, [
      begruendung,
      el("div", { class: "formular-reihe" }, [umfang, freigabe]),
      el("div", { class: "formular-reihe" }, [verweis, el("span", { class: "leise", text: "laeuft ab am" }), ablauf]),
      el("div", { class: "formular-reihe" }, [
        el("button", {
          class: "knopf knopf-haupt",
          text: "Ausnahme aufnehmen",
          onclick: async (ereignis) => {
            const daten = { begruendung: begruendung.value, freigegeben_von: freigabe.value,
                            verweis: verweis.value, laeuft_ab: ablauf.value };
            if (umfang.value === "befund") daten.finding_id = findingId;
            else if (umfang.value === "objekt") {
              daten.regel = befund.rule_id;
              daten.schluessel = befund.schluessel;
            } else daten.regel = befund.rule_id;

            ereignis.target.disabled = true;
            try {
              const ergebnis = await sende("/api/ausnahmen", daten);
              melden("Ausnahme aufgenommen (" + ergebnis.geltungsbereich + "). " + ergebnis.hinweis, "erfolg");
              schliesseBlende();
            } catch (fehler) {
              melden(fehler.message, "fehler");
            } finally {
              ereignis.target.disabled = false;
            }
          },
        }),
      ]),
    ]),
  ]);
}

/* -------------------------------------------------------------- Dubletten */

let dublettenDaten = null;

async function zeigeDubletten() {
  if (!Z.laufId) {
    setzen($("#d-cluster"), [el("p", { class: "nichts", text: "Kein Lauf ausgewaehlt." })]);
    return;
  }
  try {
    dublettenDaten = await hole("/api/laeufe/" + encodeURIComponent(Z.laufId) + "/dubletten");
  } catch (fehler) {
    setzen($("#d-cluster"), [el("p", { class: "nichts", text: fehler.message })]);
    return;
  }

  const daten = dublettenDaten;
  setzen($("#d-kennzahlen"), [
    kachel("Cluster", zahl(daten.anzahl_cluster), "mutmasslich mehrfach angelegt"),
    kachel("Betroffene Saetze", zahl(daten.betroffene_saetze), "in allen Clustern zusammen"),
    kachel("Bereinigungspotenzial", zahl(daten.einsparung),
      "Saetze entfallen, wenn je Cluster einer fuehrend wird",
      daten.einsparung ? "warnung" : "gut"),
  ]);

  setzen($("#d-je-regel"), [saeulen(
    // Ein Farbton: verglichen werden Mengen, nicht Zugehoerigkeiten. Der
    // Schweregrad steht als Wort in der Beschriftung und an jedem Cluster.
    (daten.je_regel || []).map((gruppe) => ({
      name: gruppe.id + " \u2013 " + gruppe.name,
      wert: gruppe.saetze,
      titel: gruppe.id + ": " + gruppe.cluster + " Cluster mit zusammen "
             + zahl(gruppe.saetze) + " Saetzen, Nachweis " + gruppe.art
             + ", Schweregrad " + gruppe.schweregrad,
    })),
    { leer: "Keine Dubletten gefunden.", langeNamen: true },
  )]);

  zeichneCluster();
}

function zeichneCluster() {
  const daten = dublettenDaten;
  if (!daten) return;
  const suche = $("#d-suche").value.trim().toLowerCase();
  const art = $("#d-art").value;

  const gefiltert = (daten.cluster || []).filter((cluster) => {
    if (art && cluster.art !== art) return false;
    if (!suche) return true;
    const text = [cluster.schluessel, cluster.rule_id]
      .concat((cluster.mitglieder || []).map((m) => m.schluessel + " " + m.name))
      .join(" ").toLowerCase();
    return text.includes(suche);
  });

  $("#d-anzahl").textContent = gefiltert.length === (daten.cluster || []).length
    ? zahl(gefiltert.length) + " Cluster"
    : zahl(gefiltert.length) + " von " + zahl((daten.cluster || []).length) + " Clustern";

  setzen($("#d-cluster"), gefiltert.length
    ? gefiltert.map((cluster) => clusterKarte(cluster))
    : [el("p", { class: "nichts", text: "Kein Cluster passt zu diesem Filter." })]);
}

function clusterKarte(cluster) {
  const inhalt = el("div", { hidden: true });
  const pfeil = el("span", { class: "leise", text: "aufklappen" });

  const kopf = el("div", {
    class: "cluster-kopf",
    role: "button",
    tabindex: "0",
    "aria-expanded": "false",
    onclick: () => umschalten(),
    onkeydown: (ereignis) => {
      if (ereignis.key === "Enter" || ereignis.key === " ") {
        ereignis.preventDefault();
        umschalten();
      }
    },
  }, [
    schweregradMerkmal(cluster.schweregrad),
    el("span", { class: "fest leise", text: cluster.rule_id }),
    el("span", { class: "cluster-titel", text: kurzname(cluster) }),
    merkmal(cluster.anzahl_saetze + " Saetze", "leise"),
    // Der Nachweis ist die wichtigste Angabe: ein harter Schluessel ist ein
    // Beweis, eine Namensaehnlichkeit ein begruendeter Verdacht.
    cluster.art === "exakt"
      ? merkmal("harter Schluessel", "critical")
      : merkmal("Aehnlichkeit " + Math.round(cluster.score || 0), "medium"),
    cluster.ausnahme || cluster.ausnahme_vorgemerkt
      ? merkmal(cluster.ausnahme ? "Ausnahme" : "Ausnahme vorgemerkt", "leise")
      : null,
    el("span", { class: "fuellung" }, [pfeil]),
  ]);

  let offen = false;
  function umschalten(erzwinge) {
    offen = erzwinge === undefined ? !offen : erzwinge;
    inhalt.hidden = !offen;
    kopf.setAttribute("aria-expanded", String(offen));
    pfeil.textContent = offen ? "zuklappen" : "aufklappen";
    if (offen && !inhalt.firstChild) setzen(inhalt, clusterInhalt(cluster));
  }

  const karte = el("div", { class: "cluster-karte" }, [kopf, inhalt]);
  karte.aufklappen = umschalten;
  return karte;
}

/** Kurze Bezeichnung eines Clusters: die ersten beiden Namen. */
function kurzname(cluster) {
  const namen = (cluster.mitglieder || [])
    .map((m) => m.name || m.schluessel)
    .filter(Boolean);
  if (!namen.length) return cluster.schluessel;
  const gezeigt = namen.slice(0, 2).join("  /  ");
  return namen.length > 2 ? gezeigt + "  / +" + (namen.length - 2) : gezeigt;
}

/** Die Saetze eines Clusters nebeneinander, abweichende Werte hervorgehoben.
 *
 * Je Stammsatz eine Spalte, je Feld eine Zeile. Wer zwei Kreditoren
 * zusammenfuehren soll, muss sehen, worin sie sich unterscheiden - und das
 * ist genau das, was eine Liste untereinander nicht zeigt.
 */
function clusterInhalt(cluster) {
  const mitglieder = cluster.mitglieder || [];
  const felder = cluster.verglichene_felder || [];

  // Die erste Zeile traegt den Namen der Spalte, die verglichen wurde. Bei
  // MAT-DUP-002 ist das die EAN und nicht ein Name - "Name" darueberzuschreiben
  // waere schlicht falsch.
  const zeilen = [{
    feld: cluster.namensfeld || "Name",
    werte: mitglieder.map((m) => m.name || ""),
  }].concat(
    felder.map((feld) => ({
      feld: feld,
      werte: mitglieder.map((m) => (m.felder || {})[feld] || ""),
    })),
  );

  const kopfzeile = el("tr", {}, [el("th", { class: "feld", text: "" })].concat(
    mitglieder.map((m) => el("th", { class: "satzkopf", text: m.schluessel })),
  ));

  const koerper = el("tbody", {}, zeilen.map((zeile) => {
    // Hervorgehoben wird, was aus der Reihe faellt - nicht die ganze Zeile.
    // Tragen zwei von drei Saetzen "Seeweg 8" und einer "See-Weg 8", ist der
    // dritte der Ausreisser; die beiden anderen mitzufaerben verwischte genau
    // die Stelle, auf die es ankommt.
    const haeufigkeit = new Map();
    for (const wert of zeile.werte) haeufigkeit.set(wert, (haeufigkeit.get(wert) || 0) + 1);
    const haeufigster = [...haeufigkeit.entries()]
      .sort((a, b) => b[1] - a[1])[0];
    // Nur wenn ein Wert wirklich ueberwiegt, gibt es einen Ausreisser. Bei
    // lauter verschiedenen Werten weicht jeder ab.
    const eindeutig = haeufigkeit.size > 1;
    const mehrheitswert = haeufigster && haeufigster[1] > 1 ? haeufigster[0] : null;

    return el("tr", {}, [el("th", { class: "feld", text: zeile.feld })].concat(
      zeile.werte.map((wert) => {
        const abweichend = eindeutig && wert !== mehrheitswert;
        return el("td", {}, [
          el("span", {
            class: abweichend ? "abweichend" : "gleich",
            text: wert || "-",
            title: abweichend
              ? "weicht von den uebrigen Saetzen ab"
              : (eindeutig ? "" : "in allen Saetzen gleich"),
          }),
        ]);
      }),
    ));
  }));

  return [
    el("div", { class: "gegenueber" }, [
      el("table", {}, [el("thead", {}, [kopfzeile]), koerper]),
    ]),
    el("p", { class: "hinweis-zeile" }, [
      (cluster.begruendung || []).join("; ") || "",
      cluster.art === "unscharf"
        ? "  \u2013  Ein unscharfer Treffer ist ein begruendeter Verdacht, kein Nachweis. "
          + "Berechtigte Mehrfachanlagen - etwa je Werk - gehoeren als Ausnahme vermerkt."
        : "  \u2013  Ein harter Schluessel ist ein Nachweis: dieselbe Nummer kann nicht "
          + "zwei Partnern gehoeren.",
    ]),
    el("div", { class: "fuss-knopf" }, [
      el("button", {
        class: "knopf knopf-leise",
        text: "Befund oeffnen",
        onclick: () => oeffneBefund(cluster.finding_id),
      }),
    ]),
  ];
}

/* -------------------------------------------------------------- Ausnahmen */

async function zeigeAusnahmen() {
  let daten;
  try {
    daten = await hole("/api/ausnahmen");
  } catch (fehler) {
    setzen($("#a-liste"), [el("p", { class: "nichts", text: fehler.message })]);
    return;
  }
  $("#a-datei").textContent = daten.datei
    ? "Gefuehrt in " + daten.datei
    : "In der Projektkonfiguration ist keine Ausnahmeliste hinterlegt.";

  setzen($("#a-liste"), [tabelle([
    { titel: "Geltungsbereich", zelle: (z) => z.geltungsbereich },
    { titel: "Begruendung", zelle: (z) => z.begruendung },
    { titel: "Freigegeben von", zelle: (z) => z.freigegeben_von },
    { titel: "Am", zelle: (z) => z.freigegeben_am },
    { titel: "Laeuft ab", zelle: (z) => z.laeuft_ab },
    { titel: "Verweis", zelle: (z) => z.verweis },
    { titel: "Wirksam", zelle: (z) => z.wirksam ? merkmal("ja", "gut") : merkmal("abgelaufen", "high") },
    { titel: "", zelle: (z) => el("button", {
        class: "knopf knopf-leise knopf-gefahr",
        text: "entfernen",
        onclick: async (ereignis) => {
          ereignis.stopPropagation();
          try {
            const ergebnis = await sende("/api/ausnahmen/entfernen", {
              finding_id: z.finding_id, regel: z.regel, schluessel: z.schluessel,
            });
            melden(ergebnis.entfernt + " Ausnahme(n) entfernt.", "erfolg");
            zeigeAusnahmen();
          } catch (fehler) { melden(fehler.message, "fehler"); }
        },
      }) },
  ], daten.eintraege)]);
}

/* ----------------------------------------------------------------- Laeufe */

function zeigeLaeufe() {
  setzen($("#r-liste"), [tabelle([
    { titel: "Lauf", fest: true, zelle: (z) => z.lauf_id },
    { titel: "Zeitpunkt", zelle: (z) => zeitpunkt(z.erstellt_am) },
    { titel: "Dauer", zahl: true, zelle: (z) => z.unvollstaendig ? "-" : dauer(z.laufzeit_sekunden) },
    { titel: "Saetze", zahl: true, zelle: (z) => z.unvollstaendig ? "-" : zahl(z.saetze) },
    { titel: "Befunde", zahl: true, zelle: (z) => z.unvollstaendig ? "-" : zahl(z.befunde) },
    { titel: "Kritisch", zahl: true, zelle: (z) => zahl(((z.je_schweregrad || {}).critical) || 0) },
    { titel: "Umfang", zahl: true, zelle: (z) => z.unvollstaendig ? "-" : prozent(z.coverage) },
    { titel: "Punkte", zahl: true, zelle: (z) =>
        z.score === null || z.score === undefined ? "-" : String(z.score).replace(".", ",") },
    { titel: "Katalog", fest: true, zelle: (z) => (z.katalog || "").split("+")[0] },
    { titel: "Zustand", zelle: (z) => z.unvollstaendig
        ? merkmal("unvollstaendig", "high")
        : (z.regelfehler ? merkmal(z.regelfehler + " Regelfehler", "critical") : merkmal("vollstaendig", "gut")) },
  ], Z.laeufe, (zeile) => {
    if (zeile.unvollstaendig) {
      melden("Zu diesem Lauf gibt es keine Zusammenfassung. Er wurde vermutlich abgebrochen.", "warnung");
      return;
    }
    $("#lauf-auswahl").value = zeile.lauf_id;
    waehleLauf(zeile.lauf_id).then(() => zuAnsicht("lagebild"));
  })]);

  // Verglichen werden kann jeder Lauf mit einer Befunddatei, auch einer ohne
  // Zusammenfassung - fuer die Differenz werden nur die Befunde gebraucht.
  const vergleichbar = Z.laeufe.filter((lauf) => lauf.vergleichbar);
  for (const auswahl of [$("#v-vorher"), $("#v-jetzt")]) {
    const vorher = auswahl.value;
    setzen(auswahl, vergleichbar.map((lauf) => el("option", {
      value: lauf.lauf_id,
      text: lauf.lauf_id + (lauf.unvollstaendig ? "" : " (" + zahl(lauf.befunde) + " Befunde)"),
    })));
    if (vorher && vergleichbar.some((lauf) => lauf.lauf_id === vorher)) auswahl.value = vorher;
  }
  $("#v-starten").disabled = vergleichbar.length < 2;
  if (vergleichbar.length > 1 && $("#v-vorher").value === $("#v-jetzt").value) {
    $("#v-jetzt").value = vergleichbar[0].lauf_id;
    $("#v-vorher").value = vergleichbar[1].lauf_id;
  }
}

async function vergleichen() {
  const vorher = $("#v-vorher").value;
  const jetzt = $("#v-jetzt").value;
  setzen($("#v-ergebnis"), [el("p", { class: "leise", text: "Wird berechnet ..." })]);
  let daten;
  try {
    daten = await hole("/api/vergleich", { vorher: vorher, jetzt: jetzt });
  } catch (fehler) {
    setzen($("#v-ergebnis"), [el("p", { class: "nichts", text: fehler.message })]);
    return;
  }

  setzen($("#v-ergebnis"), [
    el("div", { class: "kacheln" }, [
      kachel("Behoben", zahl(daten.behoben), "seit " + daten.vorher, "gut"),
      kachel("Neu", zahl(daten.neu), "in " + daten.jetzt, daten.neu ? "warnung" : "gut"),
      kachel("Unveraendert", zahl(daten.unveraendert), ""),
      kachel("Anerkannte Ausnahmen", zahl(daten.anerkannte_ausnahmen), "nicht behoben, nur anerkannt"),
    ]),
    el("p", { text: daten.zusammenfassung }),
    el("div", {}, (daten.warnungen || []).map((warnung) =>
      el("div", { class: "meldung warnung", text: warnung }))),
    tabelle([
      { titel: "Regel", fest: true, zelle: (z) => z.id },
      { titel: "Bezeichnung", zelle: (z) => z.name },
      { titel: "Grad", zelle: (z) => schweregradMerkmal(z.schweregrad) },
      { titel: "Vorher", zahl: true, zelle: (z) => zahl(z.vorher) },
      { titel: "Jetzt", zahl: true, zelle: (z) => zahl(z.jetzt) },
      { titel: "Neu", zahl: true, zelle: (z) => zahl(z.neu) },
      { titel: "Behoben", zahl: true, zelle: (z) => zahl(z.behoben) },
    ], daten.je_regel || []),
  ]);
}

/* ---------------------------------------------------------- Praesentation
 *
 * Eine Abfolge von Folien, die sich aus dem Lauf ergibt. Sie soll den Bogen
 * schlagen, den ein Termin braucht: was geliefert wurde, worueber das Werkzeug
 * ueberhaupt eine Aussage macht, wie es steht, woran es liegt, und was als
 * naechstes zu tun ist.
 *
 * Der Vorbehalt zum Pruefumfang steht bewusst vor dem Ergebnis. Eine Zahl, die
 * ohne ihn gezeigt wird, wird als vollstaendiges Urteil verstanden - und das
 * waere sie nicht.
 */

const P = { folien: [], index: 0 };

function folie(titel, aufbau) {
  return { titel: titel, aufbau: aufbau };
}

function baueFolien() {
  const lauf = Z.lauf;
  if (!lauf) return [];

  const befunde = lauf.befunde || {};
  const coverage = lauf.coverage || {};
  const bewertung = lauf.bewertung || {};
  const lieferung = lauf.lieferung || {};
  const jeGrad = befunde.je_schweregrad || {};
  const projekt = lauf.projekt || {};
  const folien = [];

  // ------------------------------------------------------------ Titelseite
  folien.push(folie("Titel", () => el("div", { class: "folie-titelseite" }, [
    el("p", { class: "unterzeile", text: "Analyse der Stammdatenqualitaet" }),
    el("h2", { text: projekt.kunde || projekt.name || "Stammdatenpruefung" }),
    el("p", { class: "aussage", text:
      "Quellsystem " + (projekt.quellsystem || "unbekannt")
      + " \u2013 " + zahl(lauf.saetze_verarbeitet) + " Stammsaetze"
      + " \u2013 Stand " + zeitpunkt(lauf.erstellt_am) }),
    projekt.analyst ? el("p", { class: "unterzeile", text: projekt.analyst }) : null,
  ])));

  // ------------------------------------------------------------- Lieferung
  folien.push(folie("Was geprueft wurde", () => el("div", {}, [
    el("h2", { text: "Was geprueft wurde" }),
    el("p", { class: "aussage", text:
      (lieferung.dateien || []).length + " Dateien mit zusammen "
      + zahl(lauf.saetze_verarbeitet) + " Saetzen aus "
      + (lieferung.tabellen || []).length + " Tabellen. Jede Datei ist ueber "
      + "ihre Pruefsumme im Bericht nachweisbar." }),
    saeulen(
      (lieferung.tabellen || [])
        .slice().sort((a, b) => b.saetze - a.saetze).slice(0, 9)
        .map((tabelle) => ({
          name: tabelle.name + " \u2013 " + bereichName(tabelle.bereich),
          wert: tabelle.saetze,
        })),
      { leer: "Keine Tabellen." },
    ),
    lieferung.verwertbar === false
      ? el("p", { class: "meldung fehler", text:
          "Die Lieferung wurde als nicht verwertbar bewertet. Die Ergebnisse "
          + "sind entsprechend eingeschraenkt." })
      : null,
  ])));

  // ----------------------------------------------------------- Pruefumfang
  folien.push(folie("Worueber eine Aussage moeglich ist", () => el("div", {}, [
    el("h2", { text: "Worueber eine Aussage moeglich ist" }),
    el("div", { class: "nebeneinander" }, [
      ring(coverage.anteil || 0, prozent(coverage.anteil),
        (coverage.ausfuehrbar || 0) + " von " + (coverage.regeln_gesamt || 0)),
      el("p", { class: "aussage", text: coverage.vorbehalt || "" }),
    ]),
  ])));

  // -------------------------------------------------------------- Ergebnis
  const note = einordnung(bewertung.gesamt);
  folien.push(folie("Ergebnis", () => el("div", {}, [
    el("p", { class: "unterzeile", text: "Datenqualitaet insgesamt" }),
    el("div", { class: "gross", text:
      bewertung.gesamt === null || bewertung.gesamt === undefined
        ? "-" : String(bewertung.gesamt).replace(".", ",") }),
    el("p", { class: "unterzeile" }, [
      "von 100 Punkten \u2013 ",
      el("span", { class: "merkmal " + note.klasse, text: note.text }),
    ]),
    el("div", { class: "ampel abstand-oben ampel-breit" }, [
      ampelfeld("Befunde offen", zahl(befunde.effektiv), ""),
      ampelfeld("kritisch", zahl(jeGrad.critical || 0), (jeGrad.critical || 0) ? "critical" : "gut"),
      ampelfeld("hoch", zahl(jeGrad.high || 0), (jeGrad.high || 0) ? "high" : "gut"),
      ampelfeld("mittel", zahl(jeGrad.medium || 0), "medium"),
    ]),
  ])));

  // ----------------------------------------------------------- Wo es liegt
  folien.push(folie("Wo die Befunde liegen", () => el("div", {}, [
    el("h2", { text: "Wo die Befunde liegen" }),
    saeulen(
      Object.entries(befunde.je_bereich || {})
        .map(([schluessel, wert]) => ({ name: bereichName(schluessel), wert: wert }))
        .sort((a, b) => b.wert - a.wert),
      { anteile: true, leer: "Keine Befunde." },
    ),
    el("p", { class: "unterzeile abstand-oben-weit", text: "Nach Kategorie" }),
    saeulen(
      Object.entries(befunde.je_kategorie || {})
        .map(([schluessel, wert]) => ({ name: schluessel, wert: wert }))
        .sort((a, b) => b.wert - a.wert).slice(0, 7),
      { leer: "" },
    ),
  ])));

  // ------------------------------------------------------- Haeufigste Regeln
  folien.push(folie("Woran es am haeufigsten liegt", () => el("div", {}, [
    el("h2", { text: "Woran es am haeufigsten liegt" }),
    saeulen(
      (lauf.regellauf || [])
        .filter((eintrag) => eintrag.befunde > 0)
        .sort((a, b) => b.befunde - a.befunde).slice(0, 8)
        .map((eintrag) => ({ name: eintrag.name, wert: eintrag.befunde })),
      { leer: "Keine Befunde." },
    ),
  ])));

  // -------------------------------------------------------------- Dubletten
  if (dublettenDaten && dublettenDaten.anzahl_cluster) {
    const beispiel = (dublettenDaten.cluster || [])
      .filter((c) => c.art === "unscharf" && (c.mitglieder || []).length > 1)[0]
      || dublettenDaten.cluster[0];
    folien.push(folie("Mehrfach angelegte Stammsaetze", () => el("div", {}, [
      el("h2", { text: "Mehrfach angelegte Stammsaetze" }),
      el("p", { class: "aussage", text:
        zahl(dublettenDaten.anzahl_cluster) + " Cluster mit zusammen "
        + zahl(dublettenDaten.betroffene_saetze) + " Stammsaetzen. Bleibt je "
        + "Cluster ein fuehrender Satz stehen, entfallen "
        + zahl(dublettenDaten.einsparung) + " Saetze." }),
      beispiel ? el("div", { class: "karte ohne-abstand" }, [
        el("p", { class: "unterzeile abstand-unten", text:
          "Beispiel \u2013 " + beispiel.rule_id + ", "
          + (beispiel.art === "exakt"
              ? "ueber einen harten Schluessel nachgewiesen"
              : "Namensaehnlichkeit " + Math.round(beispiel.score || 0) + " von 100") }),
      ].concat(clusterInhalt(beispiel).slice(0, 2))) : null,
    ])));
  }

  // ---------------------------------------------------------- Nachforderung
  const offen = (coverage.nachforderung || [])
    .filter((k) => !k.geliefert)
    .slice()
    .sort((a, b) => (b.kumuliert || 0) - (a.kumuliert || 0));
  if (offen.length) {
    folien.push(folie("Was eine Nachlieferung braechte", () => el("div", {}, [
      el("h2", { text: "Was eine Nachlieferung braechte" }),
      el("p", { class: "aussage", text:
        "Nach Wirkung geordnet: wieviele zusaetzliche Pruefungen jede Tabelle "
        + "freischaltet." }),
      saeulen(
        offen.slice(0, 8).map((kandidat) => ({
          name: kandidat.tabelle + " \u2013 " + kandidat.bedeutung,
          wert: kandidat.kumuliert || kandidat.zusaetzliche_pruefungen || 0,
        })),
        { leer: "" },
      ),
    ])));
  }

  // ------------------------------------------------------------- Empfehlung
  folien.push(folie("Naechste Schritte", () => {
    const schritte = [];
    if (jeGrad.critical) {
      schritte.push(zahl(jeGrad.critical) + " kritische Befunde zuerst klaeren - "
        + "sie betreffen Zahlungsverkehr, Steuer oder Bilanz.");
    }
    if (dublettenDaten && dublettenDaten.anzahl_cluster) {
      schritte.push(zahl(dublettenDaten.anzahl_cluster) + " Dublettencluster sichten "
        + "und je Cluster den fuehrenden Stammsatz bestimmen.");
    }
    if (offen.length) {
      schritte.push("Fehlende Tabellen nachfordern (" + offen.slice(0, 3)
        .map((k) => k.tabelle).join(", ") + "), um den Pruefumfang von "
        + prozent(coverage.anteil) + " anzuheben.");
    }
    schritte.push("Berechtigte Faelle als Ausnahme mit Begruendung vermerken, "
      + "damit sie im Folgelauf nicht erneut als Befund erscheinen.");
    schritte.push("Nach der Bereinigung erneut messen - die Aussage liegt im "
      + "Verlauf, nicht im einzelnen Wert.");
    return el("div", {}, [
      el("h2", { text: "Naechste Schritte" }),
      el("ul", {}, schritte.map((text) => el("li", { text: text }))),
    ]);
  }));

  return folien;
}

async function praesentationOeffnen() {
  // Die Dublettenfolie braucht die Cluster. Sie werden hier geholt, damit die
  // Abfolge vollstaendig ist, auch wenn die Ansicht noch nicht offen war.
  if (!dublettenDaten && Z.laufId) {
    try {
      dublettenDaten = await hole("/api/laeufe/" + encodeURIComponent(Z.laufId) + "/dubletten");
    } catch (fehler) {
      dublettenDaten = null;
    }
  }
  P.folien = baueFolien();
  if (!P.folien.length) {
    melden("Ohne Lauf laesst sich nichts zeigen.", "warnung");
    return;
  }
  P.index = 0;
  $("#buehne").hidden = false;
  folieZeichnen();
}

function folieZeichnen() {
  const aktuell = P.folien[P.index];
  if (!aktuell) return;
  setzen($("#folie"), [aktuell.aufbau()]);
  $("#folie-titel").textContent = aktuell.titel;
  $("#folie-zaehler").textContent = (P.index + 1) + " / " + P.folien.length;
  $("#folie-zurueck").disabled = P.index === 0;
  $("#folie-vor").disabled = P.index === P.folien.length - 1;
  $("#folie").scrollTop = 0;
}

function folieWechseln(schritt) {
  const ziel = P.index + schritt;
  if (ziel < 0 || ziel >= P.folien.length) return;
  P.index = ziel;
  folieZeichnen();
}

/** Zum Drucken werden alle Folien untereinander gestellt - je eine Seite. */
function praesentationDrucken() {
  const behaelter = $("#folie");
  const gemerkt = P.index;
  setzen(behaelter, P.folien.map((eintrag) => el("div", { class: "folie" }, [eintrag.aufbau()])));
  window.print();
  P.index = gemerkt;
  folieZeichnen();
}

/* ------------------------------------------------------------ Lauf starten */

async function laufStarten() {
  const knopf = $("#lauf-starten");
  knopf.disabled = true;
  try {
    await sende("/api/lauf/starten", {});
    $("#laufblende").hidden = false;
    fortschrittVerfolgen();
  } catch (fehler) {
    melden(fehler.message, "fehler");
    knopf.disabled = false;
  }
}

function fortschrittVerfolgen() {
  if (Z.fortschrittUhr) return;
  const schritt = async () => {
    let stand;
    try {
      stand = await hole("/api/fortschritt");
    } catch (fehler) {
      return;
    }
    const laeuft = stand.status === "laeuft";
    $("#p-status").textContent = {
      bereit: "Kein Lauf gestartet.",
      laeuft: "Der Lauf arbeitet seit " + zeitpunkt(stand.begonnen_am) + " ...",
      fertig: "Fertig: " + stand.meldung,
      fehler: "Abgebrochen: " + stand.meldung,
    }[stand.status] || stand.status;
    $("#p-status").className = laeuft ? "blinken" : "";

    const protokoll = $("#p-protokoll");
    const amEnde = protokoll.scrollTop + protokoll.clientHeight >= protokoll.scrollHeight - 20;
    protokoll.textContent = (stand.zeilen || []).join("\n");
    if (amEnde) protokoll.scrollTop = protokoll.scrollHeight;

    $("#kopf-status").textContent = laeuft ? "Lauf arbeitet ..." : "";

    if (!laeuft) {
      clearInterval(Z.fortschrittUhr);
      Z.fortschrittUhr = null;
      $("#lauf-starten").disabled = false;
      if (stand.status === "fertig") {
        melden("Lauf " + stand.lauf_id + " abgeschlossen: " + stand.meldung, "erfolg");
        await ladeLaeufe(stand.lauf_id);
      } else if (stand.status === "fehler") {
        melden(stand.meldung, "fehler");
      }
    }
  };
  schritt();
  Z.fortschrittUhr = setInterval(schritt, 1500);
}

/* ------------------------------------------------------------- Navigation */

const ANSICHTEN = {
  lagebild: { titel: "Lagebild", zeichnen: zeigeLagebild },
  befunde: { titel: "Befunde", zeichnen: zeigeBefunde },
  dubletten: { titel: "Dubletten", zeichnen: zeigeDubletten },
  coverage: { titel: "Pruefumfang", zeichnen: zeigeCoverage },
  lieferung: { titel: "Lieferung", zeichnen: zeigeLieferung },
  ausnahmen: { titel: "Ausnahmen", zeichnen: zeigeAusnahmen },
  laeufe: { titel: "Laeufe", zeichnen: zeigeLaeufe },
};

function zuAnsicht(name, zusatz) {
  Z.ansicht = name;
  if (name === "befunde") {
    Z.befunde.seite = 1;
    Z.befunde.regel = (zusatz || {}).regel || "";
  }
  for (const knopf of document.querySelectorAll(".nav")) {
    if (knopf.dataset.ansicht === name) knopf.setAttribute("aria-current", "page");
    else knopf.removeAttribute("aria-current");
  }
  for (const abschnitt of document.querySelectorAll(".ansicht")) {
    abschnitt.hidden = abschnitt.id !== "ansicht-" + name;
  }
  $("#kopf-titel").textContent = ANSICHTEN[name].titel;
  ANSICHTEN[name].zeichnen();
  window.scrollTo(0, 0);
}

function schliesseBlende() {
  $("#blende").hidden = true;
}

/* ------------------------------------------------------------------ Laden */

async function waehleLauf(laufId) {
  Z.laufId = laufId;
  Z.lauf = null;
  if (!laufId) {
    $("#kopf-unter").textContent = "Es liegt noch kein Lauf vor. Die Pruefung laesst sich links starten.";
    ANSICHTEN[Z.ansicht].zeichnen();
    return;
  }
  try {
    Z.lauf = await hole("/api/laeufe/" + encodeURIComponent(laufId));
  } catch (fehler) {
    melden(fehler.message, "fehler");
    return;
  }
  const lauf = Z.lauf;
  $("#kopf-unter").textContent =
    "Lauf " + lauf.lauf_id + " vom " + zeitpunkt(lauf.erstellt_am)
    + " - Katalog " + (lauf.regelkatalog || {}).version
    + " - Werkzeug " + lauf.werkzeug_version;
  fuelleBefundfilter();
  dublettenDaten = null;
  Z.befunde.seite = 1;
  ANSICHTEN[Z.ansicht].zeichnen();
}

async function ladeLaeufe(bevorzugt) {
  const daten = await hole("/api/laeufe");
  Z.laeufe = daten.laeufe || [];
  const auswahl = $("#lauf-auswahl");
  setzen(auswahl, Z.laeufe.map((lauf) => el("option", {
    value: lauf.lauf_id,
    text: lauf.lauf_id + (lauf.unvollstaendig ? " (unvollstaendig)" : ""),
  })));
  const brauchbar = Z.laeufe.filter((lauf) => !lauf.unvollstaendig);
  const ziel = (bevorzugt && Z.laeufe.some((lauf) => lauf.lauf_id === bevorzugt))
    ? bevorzugt
    : (brauchbar[0] || {}).lauf_id || "";
  auswahl.value = ziel;
  await waehleLauf(ziel);
}

async function starten() {
  if (!TOKEN) {
    $("#anmeldung").hidden = false;
    return;
  }

  try {
    Z.projekt = await hole("/api/projekt");
  } catch (fehler) {
    $("#anmeldung").hidden = false;
    return;
  }

  $("#rahmen").hidden = false;
  const projekt = Z.projekt;
  document.title = projekt.name + " - Stammdatenpruefung";
  $("#projekt-fuss").textContent =
    projekt.name + (projekt.kunde ? " / " + projekt.kunde : "")
    + " - Quellsystem " + (projekt.quellsystem || "unbekannt")
    + " - " + projekt.eingangsdateien.length + " Datei(en) im Eingang";

  // Bedienelemente
  for (const knopf of document.querySelectorAll(".nav")) {
    knopf.addEventListener("click", () => zuAnsicht(knopf.dataset.ansicht));
  }
  $("#lauf-auswahl").addEventListener("change", (ereignis) => waehleLauf(ereignis.target.value));
  $("#lauf-starten").addEventListener("click", laufStarten);
  $("#d-schliessen").addEventListener("click", schliesseBlende);
  $("#blende").addEventListener("click", (ereignis) => {
    if (ereignis.target === $("#blende")) schliesseBlende();
  });
  $("#p-schliessen").addEventListener("click", () => { $("#laufblende").hidden = true; });
  document.addEventListener("keydown", (ereignis) => {
    if (ereignis.key !== "Escape") return;
    schliesseBlende();
    $("#laufblende").hidden = true;
    $("#buehne").hidden = true;
  });

  let entprellung = null;
  const neuLaden = () => {
    Z.befunde.seite = 1;
    Z.befunde.regel = "";
    zeigeBefunde();
  };
  $("#b-suche").addEventListener("input", () => {
    clearTimeout(entprellung);
    entprellung = setTimeout(neuLaden, 300);
  });
  for (const id of ["#b-schweregrad", "#b-bereich", "#b-kategorie", "#b-status", "#b-vergleich", "#b-ausnahmen"]) {
    $(id).addEventListener("change", neuLaden);
  }
  $("#b-zuruecksetzen").addEventListener("click", () => {
    $("#b-suche").value = "";
    for (const id of ["#b-schweregrad", "#b-bereich", "#b-kategorie", "#b-status", "#b-vergleich"]) {
      $(id).value = "";
    }
    $("#b-ausnahmen").checked = false;
    neuLaden();
  });
  $("#b-zurueck").addEventListener("click", () => { Z.befunde.seite -= 1; zeigeBefunde(); });
  $("#b-weiter").addEventListener("click", () => { Z.befunde.seite += 1; zeigeBefunde(); });

  $("#d-suche").addEventListener("input", zeichneCluster);
  $("#d-art").addEventListener("change", zeichneCluster);
  $("#d-alle-auf").addEventListener("click", () => {
    const karten = document.querySelectorAll("#d-cluster .cluster-karte");
    const aufklappen = $("#d-alle-auf").dataset.zustand !== "auf";
    for (const karte of karten) if (karte.aufklappen) karte.aufklappen(aufklappen);
    $("#d-alle-auf").dataset.zustand = aufklappen ? "auf" : "zu";
    $("#d-alle-auf").textContent = aufklappen ? "Alle zuklappen" : "Alle aufklappen";
  });

  $("#c-suche").addEventListener("input", zeichneRegeln);
  $("#c-nur-entfallen").addEventListener("change", zeichneRegeln);
  $("#v-starten").addEventListener("click", vergleichen);

  $("#praesentation").addEventListener("click", praesentationOeffnen);
  $("#folie-vor").addEventListener("click", () => folieWechseln(1));
  $("#folie-zurueck").addEventListener("click", () => folieWechseln(-1));
  $("#folie-drucken").addEventListener("click", praesentationDrucken);
  $("#buehne-schliessen").addEventListener("click", () => { $("#buehne").hidden = true; });
  document.addEventListener("keydown", (ereignis) => {
    if ($("#buehne").hidden) return;
    if (ereignis.key === "ArrowRight" || ereignis.key === "PageDown" || ereignis.key === " ") {
      ereignis.preventDefault();
      folieWechseln(1);
    } else if (ereignis.key === "ArrowLeft" || ereignis.key === "PageUp") {
      ereignis.preventDefault();
      folieWechseln(-1);
    }
  });

  await ladeLaeufe();
  zuAnsicht("lagebild");

  // Ein Lauf kann schon arbeiten, etwa wenn die Seite neu geladen wurde.
  const stand = await hole("/api/fortschritt").catch(() => null);
  if (stand && stand.status === "laeuft") {
    $("#lauf-starten").disabled = true;
    fortschrittVerfolgen();
  }
  if (!Z.laufId) {
    melden("Es liegt noch kein Lauf vor. Mit 'Pruefung starten' wird die Lieferung "
      + "aus " + projekt.eingangsverzeichnis + " geprueft.", "hinweis");
  }
}

starten();
