"""Dublettenerkennung (FA-501 bis FA-505).

Vier Schritte: normalisieren, blocken, vergleichen, gruppieren. Die
Reihenfolge ist wesentlich - ohne Normalisierung findet der Vergleich zu
wenig, ohne Blocking dauert er bei Millionen Sätzen zu lange.
"""
