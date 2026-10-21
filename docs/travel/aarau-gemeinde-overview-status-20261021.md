# Aarau Wohn-Gemeinden: verifizierter Stand, 21. Oktober 2026

**Ergebnis:** Noch keine Wohngemeinde wurde als innerhalb oder ausserhalb der individuell gewählten Grenzen verifiziert. **Unbekannt ist nicht null erreichbar.** Die Anwendung führt 2'110 Schweizer Gemeinden als Wohnort-Kandidaten und 19 ausgewählte Hauptorte als Arbeitsorte; Aarau (BFS 4001) ist bereits wählbar. Das Arbeitsort-Subset schränkt die Wohnortmenge nicht ein. Aus diesem Datenstand lässt sich die verlangte Liste «welche Gemeinden erfüllen meine Distanz/Zeit?» nicht seriös erzeugen.

## Aarau-Pilot: begrenzte Beobachtungen, keine Gemeinde-Urteile

Für das Beispiel gelten **höchstens 15 Minuten externer Fussweg zur Haltestelle** und **höchstens 20 Minuten vom ersten Einstieg bis Aarau** getrennt; bei aktivierter Option wird der Fussweg zusätzlich auf das Fahrzeitbudget angerechnet. Der erste Einstieg muss zwischen 06:30:00 und 08:30:00 Europe/Zurich inklusive liegen. Umsteige-Wartezeiten und publizierte Mindestzeiten zählen zur ÖV-Zeit; kein Zuschlag für die Suche des Einstiegperrons.

| Wohn-Gemeinde (BFS) | Echte, aber unvollständige Fahrplanprobe ab benannter Haltestelle | Wohnort → Haltestelle | Gemeinde erfüllt die Grenzen? |
|---|---|---|---|
| Lenzburg (4201) | Bahnhof Lenzburg → Aarau 6 Min. | nicht verifiziert | **unbekannt** |
| Staufen (4210) | Lindenplatz → Aarau via Lenzburg 18 Min. einschliesslich publiziertem 240-Sekunden-Umstieg | nicht verifiziert | **unbekannt** |
| Niederlenz (4204) | Dorfplatz → Aarau via Lenzburg 22 Min.; *diese eine Route* überschreitet 20 Min. | nicht verifiziert; andere Haltestellen/Routen nicht ausgeschlossen | **unbekannt** |
| Alle übrigen Wohngemeinden | kein vollständiger, akzeptierter Wohnort→Aarau-Nachweis | nicht verifiziert | **unbekannt** |

Die drei Stop-Proben stammen aus einer **Vier-Fahrten-Teilmenge** des echten GTFS am **provisorischen 17. November 2026**, nicht aus einer vollständigen Suche oder einer zugelassenen Referenzwoche. Die Zugangszeit wurde in dieser Probe ausdrücklich mit **null ab der genannten Haltestelle**, nicht ab einer Wohnung, angesetzt. Die spätere Vollquellen-Abtastung am ebenfalls **nicht genehmigten 27. Oktober 2026** erfasste 877 potenzielle erste Einstiege an 79 Kind-Haltestellen nahe drei Beispielpunkten; sie fand weder Wege ab Wohnadressen noch Ankünfte in Aarau. Aus 877/79 folgt **keine** Gemeindeanzahl.

## Arbeitsorte und vorhandene Nebenarbeiten

`src/destinations.ts` enthält bereits 19 Hauptorte deutschsprachiger Kantone, darunter Aarau. In anderen, **nicht gemergten und nicht freigegebenen** Arbeitsverzeichnissen liegen ein 19-Hauptorte-zu-19-Hauptorte-Fahrplansnapshot und Hauptstadt-Steuerprototypen. Sie sind keine Abdeckung von 2'110 Wohn-Gemeinden und keine Begründung, Wohnorte auf Hauptorte zu reduzieren oder zusätzliche Nicht-Hauptorte stillschweigend als Arbeitsorte aufzunehmen. Soll der Arbeitsortkreis erweitert werden, ist eine eigene Scope- und Quellenentscheidung nötig; der Wohnortkreis bleibt unabhängig davon vollständig.

## Repository-Aufräumung und Integrationsentscheidung

Neunzehn der ursprünglich 33 alten Git-Worktrees wurden nach Inventarisierung **ohne Verlust von Quell- oder Nutzerdaten** entfernt; darunter vier lokale Branch-Referenzen, deren Commits bereits in `main` liegen. Die übrigen entfernten Checkouts waren sauber, ihre nicht gemergten Branch-Referenzen sind weiterhin verfügbar. Nach Abschluss der Dokumentations-Integration bleiben vierzehn Worktrees bestehen. Der ältere Feature-Checkout `feat/verified-comparison` wurde **nicht** zurückgesetzt: fünf veränderte getrackte Dateien, ein ungetracktes Worker-Vertragsdokument und eine Abhängigkeiten-Verknüpfung sind erhalten. Weitere Worktrees enthalten ungetrackten Hauptstadt-, Referenz- oder Routing-Quellcode und eingefrorene Evidenz; diese sind weder Build-Müll noch geprüfte neue Produktdaten und bleiben unangetastet. Die in mehreren Checkouts vorhandenen `node_modules`-Symlinks sind Verknüpfungen auf eine gemeinsame Installation; die tatsächlich genutzte Installation wurde nicht gelöscht.

Zwei offene Pull Requests wurden nicht ungeprüft eingegliedert: **#11** ist ein Draft für CI-Prüfungen, dessen bewusst fehlerschlagender Steuer-Genauigkeits-Job eine separate Freigabesperre ist; **#14** ist konflikthaft und seine ESTV-Referenzvergleiche stehen weiter bei **9/29 bestanden, 20/29 nicht bestanden**. Die unabhängig geprüfte Korrektur des irreführenden «0 Gemeinden»-Hinweises und dieses Statusdokument wurden über PR #26 in `main` integriert; daraus folgt keine Freigabe von Fahrplan- oder Steuerergebnissen.

## Freigabekette und Drift

1. Frühesten zulässigen Dienstag nach Version/Erwerb des eingefrorenen GTFS **für alle 26 Kantone einschliesslich lokaler/regionaler Schul- und gesetzlicher Feiertage** nachweisen.
2. Repräsentative Wohnpunkte und echte, begehbare Eingangs-/Haltestellen-Verbindungen belegen; aktuell **null angenommene Wohnort-Fusswege**. Verschiedene plausible Zugänge vergleichen, nicht Rathaus oder Hauptbahnhof erzwingen.
3. Vollständige GTFS-Fahrten bis Aarau samt Alternativen, Frequenz- und Umsteigeregeln unter dem getrennten 15-/20-Minuten-Budget prüfen und unabhängig gegenprüfen. Erst dann den Gemeinde-Status *qualifiziert / nicht qualifiziert / weiterhin unbekannt* berechnen.
4. Die Web-Anwendung zeigt währenddessen beim gewählten Arbeitsort und Zeitbudget explizit **«noch ungeprüft»**, statt fälschlich «0 vergleichbare Gemeinden in Reichweite». Die Reise- und ESTV-Freigaben bleiben unabhängig voneinander geschlossen.

**Quellen-/Code-Version:** GTFS-/Pilot-Basis `main`-Commit `f19a620abf30fad6129e72248cfad7ead876e137` (PR #25); UI-/Status-Stand `81501e253e75612536c56dc3a13c77b03cebf105` (PR #26); `SPEC.md` §§6.3–6.5/8, `src/destinations.ts`, `docs/travel/aarau-access-option-four-trip-smoke-20261020.md`, `docs/travel/aarau-first-boarding-cone-20261020.md`, `docs/travel/aarau-pedestrian-audit-20261020.md` und `docs/travel/aarau-residential-entrance-probe-20261020.md`. GTFS `gtfs_fp2026_20261017.zip`, SHA-256 `d5b312e1ff398b505f9a6efef60c365f3c864857f73c55e87b383960a6b3418e`. Rohdaten/Provenienz: `/home/hermes/data/steuerpendler/2026-10-19/SOURCE-SNAPSHOT.json` und `aarau-first-boarding-cone-20261027.json`; vier echte Fahrten: `aarau-access-four-trip/`. Jede spätere Quell-, SPEC-, Zielort- oder Frontend-Revision erfordert erneute Prüfung statt stiller Wiederverwendung dieser Aussagen. Die Produkt-Manifest-Gates bleiben `travel:false`, `sbb:false`, `estv:false`.
