import { expect, it } from 'vitest';
import { strings } from './strings';

it('does not report zero reachable Gemeinden when Aarau travel has not been verified', () => {
  expect(strings.reachabilityOverview(false, 0, 'Aarau', 20, 15, 2110))
    .toBe("Aarau: Erreichbarkeit für 2'110 Wohngemeinden bei max. 20 Min. Fahrzeit und 15 Min. Fussweg noch ungeprüft. Keine Gemeinde als erreichbar oder ausgeschlossen bestätigt.");
});

it('reports an actual zero only after travel becomes available', () => {
  expect(strings.reachabilityOverview(true, 0, 'Aarau', 20, 15, 2110))
    .toBe('0 vergleichbare Gemeinden in Reichweite');
});

it('states a missing matrix row as a timetable finding, not as unreachable', () => {
  expect(strings.matrixNoRoute(20)).toBe('Keine Verbindung bis 20 Min. im Fahrplan gefunden');
  expect(strings.matrixNoRoute(20)).not.toContain('unerreichbar');
});
