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
  ansicht: "uebersicht",
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

function kachel(titel, wert, zusatz, klasse) {
  return el("div", { class: "kachel " + (klasse || "") }, [
    el("div", { class: "titel", text: titel }),
    el("div", { class: "wert", text: wert }),
    zusatz ? el("div", { class: "zusatz", text: zusatz }) : null,
  ]);
}

const farbeSchweregrad = (grad) =>
  "var(--" + (SCHWEREGRADE.includes(grad) ? grad : "low") + ")";

/* ------------------------------------------------------------ Uebersicht */

function zeigeUebersicht() {
  const lauf = Z.lauf;
  if (!lauf) {
    setzen($("#u-kennzahlen"), []);
    setzen($("#u-schweregrade"), [el("p", { class: "nichts", text: "Kein Lauf ausgewaehlt." })]);
    setzen($("#u-bereiche"), []);
    setzen($("#u-bewertung"), []);
    setzen($("#u-regeln"), []);
    return;
  }

  const befunde = lauf.befunde || {};
  const coverage = lauf.coverage || {};
  const bewertung = lauf.bewertung || {};
  const jeGrad = befunde.je_schweregrad || {};

  setzen($("#u-kennzahlen"), [
    kachel("Geprueft", zahl(lauf.saetze_verarbeitet), "Saetze in " + dauer(lauf.laufzeit_sekunden)),
    kachel("Offene Befunde", zahl(befunde.effektiv),
      (befunde.ausnahmen || 0) + " als Ausnahme anerkannt"),
    kachel("Kritisch", zahl(jeGrad.critical || 0),
      zahl(jeGrad.high || 0) + " hoch, " + zahl(jeGrad.medium || 0) + " mittel",
      (jeGrad.critical || 0) > 0 ? "critical" : "gut"),
    kachel("Pruefumfang", prozent(coverage.anteil),
      (coverage.ausfuehrbar || 0) + " von " + (coverage.regeln_gesamt || 0) + " Regeln",
      (coverage.anteil || 0) < 0.7 ? "warnung" : "gut"),
    kachel("Bewertung",
      bewertung.gesamt === null || bewertung.gesamt === undefined
        ? "-" : String(bewertung.gesamt).replace(".", ","),
      "von 100 Punkten",
      (bewertung.gesamt || 0) < 70 ? "warnung" : "gut"),
    kachel("Regelfehler", zahl(lauf.regelfehler),
      lauf.regelfehler ? "Ergebnis unvollstaendig" : "keine",
      lauf.regelfehler ? "critical" : "gut"),
  ]);

  setzen($("#u-schweregrade"), [balken(
    SCHWEREGRADE.filter((grad) => jeGrad[grad]).map((grad) => ({ name: grad, wert: jeGrad[grad] })),
    (eintrag) => farbeSchweregrad(eintrag.name),
  )]);

  setzen($("#u-bereiche"), [balken(
    Object.entries(befunde.je_bereich || {})
      .map(([schluessel, wert]) => ({ name: bereichName(schluessel), wert: wert }))
      .sort((a, b) => b.wert - a.wert),
  )]);

  setzen($("#u-bewertung"), [tabelle([
    { titel: "Bereich", zelle: (z) => bereichName(z.bereich) },
    { titel: "Punkte", zahl: true, zelle: (z) => z.score === null ? "-" : String(z.score).replace(".", ",") },
    { titel: "Einordnung", zelle: (z) => z.einordnung },
    { titel: "Befunde", zahl: true, zelle: (z) => zahl(z.befunde) },
    { titel: "Saetze", zahl: true, zelle: (z) => zahl(z.gepruefte_saetze) },
    { titel: "Regeln", zahl: true, zelle: (z) => z.regeln_ausfuehrbar + " / " + z.regeln_gesamt },
    { titel: "Vorbehalt", zelle: (z) => z.vorbehalt || "" },
  ], bewertung.bereiche || [])]);

  const nachBefunden = (lauf.regellauf || [])
    .filter((eintrag) => eintrag.befunde > 0)
    .sort((a, b) => b.befunde - a.befunde)
    .slice(0, 12);
  setzen($("#u-regeln"), [tabelle([
    { titel: "Regel", fest: true, zelle: (z) => z.id },
    { titel: "Bezeichnung", zelle: (z) => z.name },
    { titel: "Befunde", zahl: true, zelle: (z) => zahl(z.befunde) },
    { titel: "Dauer", zahl: true, zelle: (z) => dauer(z.dauer_sekunden) },
    { titel: "", zelle: () => el("span", { class: "leise", text: "ansehen" }) },
  ], nachBefunden, (zeile) => {
    $("#b-suche").value = "";
    zuAnsicht("befunde", { regel: zeile.id });
  })]);
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
    waehleLauf(zeile.lauf_id).then(() => zuAnsicht("uebersicht"));
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
  uebersicht: { titel: "Uebersicht", zeichnen: zeigeUebersicht },
  lieferung: { titel: "Lieferung", zeichnen: zeigeLieferung },
  coverage: { titel: "Pruefumfang", zeichnen: zeigeCoverage },
  befunde: { titel: "Befunde", zeichnen: zeigeBefunde },
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

  $("#c-suche").addEventListener("input", zeichneRegeln);
  $("#c-nur-entfallen").addEventListener("change", zeichneRegeln);
  $("#v-starten").addEventListener("click", vergleichen);

  await ladeLaeufe();
  zuAnsicht("uebersicht");

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
