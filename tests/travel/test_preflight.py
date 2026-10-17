"""Preflight must be genuinely non-successful until exact metric is implemented."""
import json
import pathlib
import subprocess
import sys
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'scripts' / 'travel'))
import build


class PreflightTests(unittest.TestCase):
    def test_resource_policy_and_metric_blocker_cannot_be_overridden(self):
        small = dict(totalMemoryBytes=4*1024**3,availableMemoryBytes=2*1024**3,
                     diskFreeBytes=10*1024**3,cpuCount=4,javaVersion='21.0.8',javaVendor='Azul Systems, Inc.')
        result = build.assess_environment(small)
        self.assertIn('RAM_TOO_SMALL', [b['code'] for b in result['blockers']])
        self.assertEqual(result['suggestedHeapBytes'], (2*1024**3*3)//5)
        large = dict(small,totalMemoryBytes=16*1024**3,availableMemoryBytes=16*1024**3)
        result = build.assess_environment(large)
        self.assertNotIn('RAM_TOO_SMALL', [b['code'] for b in result['blockers']])
        self.assertEqual(result['suggestedHeapBytes'],9*1024**3)
        self.assertIn('EXACT_METRIC_UNPROVEN',[b['code'] for b in result['blockers']])
        self.assertIn('NATIONAL_PIPELINE_INCOMPLETE',[b['code'] for b in result['blockers']])
        with tempfile.TemporaryDirectory() as tmp:
            out = pathlib.Path(tmp)/'result.json'
            command = [sys.executable,str(ROOT/'scripts/travel/build.py'),'--preflight-only','--report',str(out)]
            process = subprocess.run(command,cwd=tmp,capture_output=True,text=True)
            self.assertEqual(process.returncode,2)
            report = json.loads(out.read_text())
            self.assertEqual(report['status'],'blocked')
            self.assertFalse(report['nationalDownloadsAttempted'])
            self.assertFalse((pathlib.Path(tmp)/'site').exists())


if __name__ == '__main__': unittest.main()
