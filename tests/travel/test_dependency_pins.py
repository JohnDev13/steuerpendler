"""Regression: preflight must inspect the real checked-in version pins."""
import json
import pathlib
import subprocess
import sys
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[2]


class DependencyPinTests(unittest.TestCase):
    def test_checked_in_pins_are_loaded_and_build_stays_blocked(self):
        requirements = ROOT / 'scripts/travel/requirements.txt'
        pins = [line for line in requirements.read_text().splitlines()
                if line and not line.startswith('#')]
        self.assertTrue(all('==' in line for line in pins))
        self.assertIn('r5py==1.1.7', pins)
        self.assertIn('geopandas==1.2.0', pins)
        self.assertIn('pandas==3.0.6', pins)
        with tempfile.TemporaryDirectory() as directory:
            report_path = pathlib.Path(directory) / 'preflight.json'
            result = subprocess.run(
                [sys.executable, str(ROOT / 'scripts/travel/build.py'),
                 '--preflight-only', '--report', str(report_path)],
                cwd=directory, capture_output=True, text=True)
            self.assertEqual(result.returncode, 2)
            report = json.loads(report_path.read_text())
            codes = {item['code'] for item in report['blockers']}
            self.assertNotIn('LOCK_MISSING', codes)
            self.assertIn('EXACT_METRIC_UNPROVEN', codes)
            self.assertIn('NATIONAL_PIPELINE_INCOMPLETE', codes)
            self.assertIn('dependencyMismatches', report)
            self.assertFalse(report['siteDataWritten'])
            self.assertFalse(report['nationalDownloadsAttempted'])
            self.assertFalse((pathlib.Path(directory) / 'site').exists())


if __name__ == '__main__':
    unittest.main()
