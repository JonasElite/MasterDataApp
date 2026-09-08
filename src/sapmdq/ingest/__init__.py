"""Ingestion: Eingangsdateien erkennen, lesen und normalisiert ablegen.

Die Schicht kennt keine Pruefregeln. Ihr Ergebnis ist je Tabelle eine
Parquet-Datei im Arbeitsverzeichnis, deren Spalten technische DDIC-Namen
tragen und deren Werte korrekt typisiert sind. Damit ist der Lauf
wiederaufsetzbar, ohne erneut einzulesen (Architekturprinzip Kapitel 7).
"""
