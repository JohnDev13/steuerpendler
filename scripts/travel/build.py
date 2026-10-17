#!/usr/bin/env python3
"""Fail-closed T3 preflight. NEVER downloads national data or emits site data.

Exit 2 is deliberate: public r5py APIs have not established the required exact
first-boarding metric, and nationwide generation is not implemented. Inspect
--report for actionable gates. No CLI flag or manifest can override those gates.
"""
import argparse
import datetime as dt
import hashlib
import importlib.metadata
import json
import os
import pathlib
import platform
import re
import shutil
import subprocess
import sys

ROOT = pathlib.Path(__file__).resolve().parents[2]
GIB = 1024**3


def assess_environment(snapshot):
    """Conservative admission check, not a pilot/full-run capacity certification."""
    blockers = []
    def block(code, message):
        blockers.append({'code':code,'message':message})
    if snapshot['totalMemoryBytes'] < 15_000_000_000:
        block('RAM_TOO_SMALL','Use measured approximately 16 GB public runner/local host (>=15 billion usable bytes), not this 4 GB host. Owner approves paid/external alternatives.')
    if snapshot['availableMemoryBytes'] < 8*GIB:
        block('RAM_AVAILABLE_LOW','Free at least 8 GiB before the 50-workplace pilot; JVM defaults to floor(60% available), capped at 9 GiB.')
    if snapshot['cpuCount'] < 4:
        block('CPU_TOO_SMALL','Use >=4 available CPUs for the public-runner pilot.')
    if snapshot['diskFreeBytes'] < 8*GIB:
        block('DISK_LOW','Need >=8 GiB initial free disk; pilot must separately prove input/temp/output budget and >=20% headroom.')
    if snapshot.get('javaVersion') != '21.0.8' or snapshot.get('javaVendor') != 'Azul Systems, Inc.':
        block('JDK_MISSING_OR_UNPINNED','Install user-space Zulu 21.44.17 CA JDK 21.0.8+9 from environment.lock.json, verify SHA-256 and JAVA_HOME; pip does not install JDK.')
    block('EXACT_METRIC_UNPROVEN','r5py 1.1.7/R5 7.5.1: minute percentile matrix and random-sampled DetailedItineraries do not prove §8 exact first-boarding minimum. Develop/review a pinned R5-backed adapter; pass every tiny edge/second/transfer/parent/no-service fixture before downloads.')
    block('NATIONAL_PIPELINE_INCOMPLETE','No national generator/checkpoint/pilot/release writer exists yet. Implement real spatial/calendar/OSM/STATPOP joins, extended route transformations, RFC8785 release validation and measured pilot/full run after metric proof; no empty outputs are emitted.')
    return {'blockers':blockers,'suggestedHeapBytes':min(snapshot['availableMemoryBytes']*3//5,9*GIB),
            'capacityAccepted':False,'pilotBatchSize':50,'requiredHeadroomFraction':0.2,
            'fullRunWallLimitSeconds':5*3600}


def system_snapshot():
    memory = {}
    for line in pathlib.Path('/proc/meminfo').read_text().splitlines():
        parts = line.split()
        if parts[0] in ('MemTotal:','MemAvailable:'):
            memory[parts[0][:-1]] = int(parts[1])*1024
    total, available = memory['MemTotal'], memory['MemAvailable']
    # Respect cgroup v2/v1 caps when present (the OS view may expose host RAM).
    cgroup = {}
    for limit_path, usage_path in [('/sys/fs/cgroup/memory.max','/sys/fs/cgroup/memory.current'),
                                   ('/sys/fs/cgroup/memory/memory.limit_in_bytes','/sys/fs/cgroup/memory/memory.usage_in_bytes')]:
        try:
            limit, usage = pathlib.Path(limit_path).read_text().strip(), int(pathlib.Path(usage_path).read_text())
            if limit != 'max':
                cap = int(limit)
                total, available = min(total,cap), min(available,max(0,cap-usage))
                cgroup = {'limitBytes':cap,'usageBytes':usage}
                break
        except (OSError,ValueError):
            pass
    java = pathlib.Path(os.environ.get('JAVA_HOME','/nonexistent'))/'bin'/'java'
    executable = str(java) if java.is_file() else shutil.which('java')
    java_info = ''
    if executable:
        process = subprocess.run([executable,'-XshowSettings:properties','-version'],capture_output=True,text=True,timeout=15)
        java_info = process.stderr + process.stdout
    def prop(name):
        match = re.search(r'^\s*'+re.escape(name)+r'\s*=\s*(.+)$',java_info,re.M)
        return match.group(1).strip() if match else None
    return {'totalMemoryBytes':total,'availableMemoryBytes':available,'cgroup':cgroup,
            'cpuCount':len(os.sched_getaffinity(0)) if hasattr(os,'sched_getaffinity') else os.cpu_count(),
            'diskFreeBytes':shutil.disk_usage(ROOT).free,'pythonVersion':platform.python_version(),
            'platform':platform.platform(),'javaExecutable':executable,
            'javaVersion':prop('java.version'),'javaRuntimeVersion':prop('java.runtime.version'),
            'javaVendor':prop('java.vendor')}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--preflight-only',action='store_true',help='Diagnose gates only; still exits 2 while blocked')
    parser.add_argument('--inputs',type=pathlib.Path,help='Local frozen input manifest (never a URL)')
    parser.add_argument('--report',type=pathlib.Path,default=pathlib.Path('artifacts/travel/preflight.json'))
    args = parser.parse_args()
    snapshot = system_snapshot()
    report = {'status':'blocked','observedUtc':dt.datetime.now(dt.timezone.utc).isoformat(),
              'nationalDownloadsAttempted':False,'siteDataWritten':False,'environment':snapshot,
              **assess_environment(snapshot)}
    if snapshot['pythonVersion'] != '3.11.15':
        report['blockers'].append({'code':'PYTHON_UNPINNED','message':'Use Python 3.11.15 in a venv per environment.lock.json.'})
    try:
        installed = {line.split('==',1)[0].lower().replace('_','-'):line.split('==',1)[1]
                     for line in (ROOT/'scripts/travel/requirements.txt').read_text().splitlines()
                     if '==' in line and not line.startswith('#')}
        mismatched = []
        for name, version in installed.items():
            try: actual = importlib.metadata.version(name)
            except importlib.metadata.PackageNotFoundError: actual = None
            if actual != version: mismatched.append({'package':name,'expected':version,'actual':actual})
        report['dependencyMismatches'] = mismatched
        if mismatched:
            report['blockers'].append({'code':'PYTHON_DEPENDENCIES','message':'Install requirements.txt in a venv; see dependencyMismatches.'})
    except FileNotFoundError:
        report['blockers'].append({'code':'LOCK_MISSING','message':'Pinned dependency requirements.txt is absent.'})
    # Only record local configuration presence/hash: do not claim this is full
    # §6.7 input validation. No potentially huge input is opened here.
    if args.inputs and args.inputs.is_file():
        if args.inputs.stat().st_size > 1_000_000:
            report['blockers'].append({'code':'INPUT_MANIFEST_TOO_LARGE','message':'Expected <=1 MB local input manifest, not a dataset.'})
        else:
            report['configuredInputManifest'] = {'path':str(args.inputs),
                'sha256':hashlib.sha256(args.inputs.read_bytes()).hexdigest(),'validated':False}
            report['blockers'].append({'code':'INPUTS_NOT_VALIDATED','message':'Manifest supplied but §6.7 national input validator is not implemented. No input accepted merely because present.'})
    else:
        report['blockers'].append({'code':'REAL_INPUTS_REQUIRED','message':'Supply --inputs local frozen-input manifest only after metric gate is fixed: GTFS original/transformed, OSM, STATPOP/fallback, real tax authority/map ID join, all-canton holiday evidence, overrides and hashes. No current date/feed is assumed.'})
    args.report.parent.mkdir(parents=True,exist_ok=True)
    args.report.write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps(report,indent=2))
    return 2


if __name__ == '__main__': sys.exit(main())
