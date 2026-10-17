# Map navigation — local verification

## Current integration, SPEC v1.2 (17 October 2026)

Navigation labels are now centralized in `src/strings.ts`. The integrated suite passes 26 unit tests and 16 production-build Playwright tests, including the separate all-2,110-residence/19-workplace scope, native touch scrolling and completed taps in autocomplete, held-stationary drag suppression and cleared ARIA active-descendant state. These counts replace the isolated-worker counts below. Tax/timetable/owner/production gates remain open.

The following is preserved **isolated-worker evidence** from `feat/map-navigation` (`4e5aba0b5b1c58630baf0ed7d2cfea0917619ac1`), before parent scope integration, label centralization and the independent-review fixes. It is not the current integrated build or a CI-success claim.

## Original worker baseline

Implemented on `feat/map-navigation` without changing workplace/residence scope, tax/travel data, main, strings, dependencies or SPEC. All 2,113 municipality paths remain (2,110 tax municipalities plus three existing source-only no-data areas). Existing municipality selection/arrow-key handling, review styling, overlays and labels remain intact.

## Interaction/API

- SVG viewBox navigation, national overview `0 0 960 560`, zoom clamped to 1–16×; pan constrained to national viewBox bounds.
- Labelled native + / − / reset buttons, disabled at their respective bounds; keyboard + / = / − / 0 / Home on the map or its descendants.
- Wheel zoom anchored at the pointer, mouse/touch pointer drag, two-finger pinch and midpoint pan. Screen coordinates use inverse SVG CTM, including letterboxing. Pointer capture is on the original hit element so ordinary municipality clicks survive capture. Drag/pinch-generated clicks are suppressed; keyboard activation is retained.
- `createMap(...).update(results, workplace, selected, review)` signature unchanged. Updates only change content/styling; they no longer reset or auto-fit the viewport. Added `.reset()` to explicitly restore the national overview. This intentionally prioritizes the user's explicit persistent-navigation requirement over the previous unconditional reachable-area fitting.
- Own CSS is imported by map.ts. German navigation strings are local constants pending parent centralization; no strings.ts edits.

## Actual RED/GREEN evidence

Production static server, project base `/steuerpendler/`, Chromium via Playwright, using:

```
PAGES_BASE=/steuerpendler/ LD_LIBRARY_PATH=/home/hermes/.cache/steuerpendler-browser-deps/root/usr/lib/x86_64-linux-gnu npx playwright test
```

1. Initial focused test failed because `Karte vergrössern` did not exist; implemented controls/persistent viewBox; 1 passed.
2. Wheel/pinch tests failed with unchanged `0 0 960 560`; implemented pointer/wheel navigation; 3 passed.
3. Ordinary mouse municipality click regression test failed (Bern never selected): SVG-level capture retargeted clicks. Fixed capture to original hit element; all 11 E2E tests passed (14.7s), including all four navigation tests.

Navigation E2E exercises actual wheel input, mouse drag and selection suppression, reset, keyboard max disabled/min disabled, Enter selection retaining zoom, ordinary municipality mouse selection, CDP real two-finger pinch plus touch pan, all 2,113 paths, and 400px page horizontal-overflow check. Browser tests rebuild and serve real production assets, not a development server.

`npm test`: 10 files / 25 tests passed (19.29s).

`PAGES_BASE=/steuerpendler/ npm run build`: TypeScript and Vite passed; 157 modules transformed. Explicit build output: JS 50.30 kB / gzip 20.18 kB, CSS 8.88 kB / gzip 2.86 kB. Latest full E2E run also rebuilt successfully after the pointer-capture fix.

No external service/dependency was added. These results establish local navigation/integration behavior only: no official tax/SBB/travel, CI, rights, owner UX, physical-phone or production launch gate is claimed passed. Existing source-only IDs retain the existing grey/no-data treatment. Parent still owns workplace destination restrictions and label centralization.
