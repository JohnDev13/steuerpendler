"""Offline contract tests; published fixtures must always be real HTTP captures."""
import unittest
import estv_collector as c

class MappingTest(unittest.TestCase):
    def test_married_gross_with_children_and_same_church_partner(self):
        case = dict(civil='married', kids=2, income=150000, church='reformed')
        self.assertTrue(hasattr(c, 'request_for'), 'gross profile mapper missing')
        r = c.request_for(case, 840000000)
        self.assertEqual(r, {'SimKey':None,'TaxYear':2026,'TaxLocationID':840000000,
            'Relationship':2,'Confession1':1,'Children':[{'Age':10},{'Age':10}],
            'Age1':35,'RevenueType1':1,'Revenue1':150000,'Fortune':0,
            'Confession2':1,'Age2':35,'RevenueType2':0,'Revenue2':0,'Budget':[]})

    def test_all_spec_cases_not_destination_subset(self):
        self.assertTrue(hasattr(c, 'cases_from_spec'), 'SPEC coverage parser missing')
        from pathlib import Path
        cases = c.cases_from_spec(Path('SPEC.md').read_text())
        self.assertEqual(len(cases), 29)
        self.assertEqual(len({x['canton'] for x in cases}), 26)
        self.assertEqual(cases[1]['bfs'], 230)
        self.assertEqual(cases[16]['income'], 110000)
        with self.assertRaises(ValueError):
            c.cases_from_spec(Path('SPEC.md').read_text().replace('| Sion | VS |', '| Missing | XX |'))

    def test_evidence_rejects_wrong_location_nonfinite_diagnosis_and_sum(self):
        self.assertTrue(hasattr(c, 'validate_result'), 'official result validator missing')
        import json
        from pathlib import Path
        raw = json.loads(Path('tests/reference/estv-2026/replay-baseline.response.json').read_bytes())['response']
        case = c.cases_from_spec(Path('SPEC.md').read_text())[0]
        self.assertEqual(c.validate_result(case, raw), 16346)
        import copy
        for field, value in [('TotalTax', 1), ('TotalNetTax', float('nan')), ('Diagnosis','error')]:
            bad = copy.deepcopy(raw); bad[field] = value
            with self.assertRaises(ValueError): c.validate_result(case, bad)
        bad = copy.deepcopy(raw); bad['Location']['BfsID'] = 230
        with self.assertRaises(ValueError): c.validate_result(case, bad)

    def test_offline_never_fetches_or_accepts_corrupt_cache(self):
        self.assertTrue(hasattr(c, 'Capture'), 'auditable HTTP capture missing')
        import tempfile, json, hashlib
        from pathlib import Path
        with tempfile.TemporaryDirectory() as tmp:
            capture = c.Capture(Path(tmp), offline=True)
            with self.assertRaises(FileNotFoundError): capture.fetch('missing', c.BASE+'API_getTaxVersion', {})
            body = Path('tests/reference/estv-2026/replay-baseline.response.json').read_bytes()
            Path(tmp, 'cached.response.json').write_bytes(body)
            Path(tmp, 'cached.request.json').write_bytes(b'{}')
            Path(tmp, 'cached.meta.json').write_text(json.dumps({'url':c.BASE+'API_getTaxVersion',
                'status':200,'request_sha256':hashlib.sha256(b'{}').hexdigest(),
                'response_sha256':hashlib.sha256(body).hexdigest()}))
            self.assertEqual(capture.fetch('cached',c.BASE+'API_getTaxVersion', {})['response']['TotalNetTax'],16346)
            Path(tmp, 'cached.response.json').write_bytes(b'{}')
            with self.assertRaises(ValueError): capture.fetch('cached',c.BASE+'API_getTaxVersion', {})

    def test_signed_official_tax_credit_is_added_not_subtracted(self):
        import json
        from pathlib import Path
        case = c.cases_from_spec(Path('SPEC.md').read_text())[19]
        raw = json.loads(Path('tests/reference/estv-2026/estv-2026-20-tax.response.json').read_bytes())['response']
        self.assertEqual(raw['TaxCredit'], -200)
        self.assertEqual(c.validate_result(case, raw),4371)

    def test_cli_fails_closed_on_uncached_offline_case(self):
        import subprocess, tempfile
        with tempfile.TemporaryDirectory() as tmp:
            r = subprocess.run(['python3','scripts/reference/estv_collector.py','--offline','--output',tmp],capture_output=True)
            self.assertNotEqual(r.returncode, 0, 'offline missing evidence must block')

    def test_catalogue_validates_every_raw_request_response_and_csv_row(self):
        self.assertTrue(hasattr(c, 'validate_catalogue'), 'catalogue validator missing')
        from pathlib import Path
        report = c.validate_catalogue(
            Path('tests/reference/estv-2026'),
            Path('tests/reference/estv-2026.csv'),
            c.cases_from_spec(Path('SPEC.md').read_text()),
        )
        self.assertNotIn(b'\r', Path('tests/reference/estv-2026.csv').read_bytes())
        self.assertEqual(report['captured_cases'], 29)
        self.assertEqual(report['cantons'], 26)
        self.assertEqual(report['validated_operations'], 87)
        self.assertEqual(report['http_statuses'], {'200': 87})
        self.assertEqual(report['validated_http_captures'], 92)
        self.assertEqual(report['all_http_statuses'], {'200': 92})
        self.assertTrue(report['historical_baseline_exact'])
        self.assertTrue(report['independent_replay_exact'])
        self.assertEqual(report['independent_replay_status'], 200)
        self.assertEqual(report['checksum_files'], 282)
        self.assertEqual(report['official_gate'], 'pending_not_executed')
        self.assertEqual(report['comparability'], 'owner_pending')

if __name__ == '__main__': unittest.main()
