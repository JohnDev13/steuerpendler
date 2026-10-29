# Travel matrix

`matrix.py` / `run_matrix.py` build `site/data/travel/matrix/` from one official GTFS feed with a
standard-library Connection Scan (SPEC §6.5c): for each of the 19 workplaces, the shortest time from
first boarding at any stop in a Gemeinde (06:30–08:30 on the reference Tuesday) to arrival at the
workplace station, any number of changes, capped at 30 minutes. A separate scan gives direct-only rows.

`fetch_reference.py` fills `tests/travel/sbb-reference-2026.csv` from the SBB timetable
(transport.opendata.ch), both from the origin's main stop and from the stop the matrix boards at.
`compare_reference.py --require-complete` is the ±3 minute gate that CI runs.

Refresh everything with the **Travel evidence** workflow (Actions → Run workflow). It downloads the
newest feed through the dataset permalink, pins its SHA-256, runs the tests, builds the matrix, fetches
the reference journeys and opens a pull request with the data.

```sh
python3 -m unittest discover -s tests/travel -v
python3 scripts/travel/run_matrix.py --gtfs gtfs_fp2026_20261028.zip --date 2026-10-27 --feed-url <url>
python3 scripts/travel/fetch_reference.py --date 2026-10-27      # needs network
python3 scripts/travel/compare_reference.py --require-complete
```

Modelled: frequency-based trips (expanded per departure) and trip-pair transfer rules with their
service days (precedence over stop-pair rules). Known limit: home-to-stop walking is not measured (0 s). Earlier probes
(R5, Aarau screens, canonical event exports) are retired; their dated findings stay in `docs/travel/`
and Git history.
