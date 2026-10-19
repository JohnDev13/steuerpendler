"""Anonymous ESTV evidence collection, separate from engine/release acceptance."""
import re
import math
import csv
import json
import hashlib
import time
import datetime
import urllib.request
import urllib.error
from pathlib import Path

SOURCE = 'https://swisstaxcalculator.estv.admin.ch/'
BASE = SOURCE.rstrip('/') + '/delegate/ost-integration/v1/lg-proxy/operation/c3b67379_ESTV/'

def digest(body):
    return hashlib.sha256(body).hexdigest()

def encoded(value):
    return json.dumps(value, ensure_ascii=False, separators=(',', ':')).encode()

class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise ValueError('Redirect blocked; inspect public source again')

class Capture:
    """Immutable cache; serial 0.4s spacing, 25s timeout, no retries or authority."""
    def __init__(self, root, offline=False):
        self.root, self.offline = Path(root), offline
        if not offline: self.root.mkdir(parents=True, exist_ok=True)
        self.requests = []
        self.opener = urllib.request.build_opener(NoRedirect())

    def fetch(self, name, url, payload=None):
        if not url.startswith(SOURCE): raise ValueError('Only official public origin allowed')
        request_body = encoded(payload) if payload is not None else b''
        response_path = self.root / (name + '.response.json')
        meta_path = self.root / (name + '.meta.json')
        request_path = self.root / (name + '.request.json')
        if meta_path.exists():
            meta = json.loads(meta_path.read_bytes())
            body = response_path.read_bytes()
            if (meta['url'] != url or meta['request_sha256'] != digest(request_body)
                or digest(request_path.read_bytes()) != digest(request_body)
                or meta['response_sha256'] != digest(body) or meta['status'] != 200):
                raise ValueError('Cache URL/request/response/status mismatch: ' + name)
        else:
            if self.offline: raise FileNotFoundError(name)
            time.sleep(0.4)
            req = urllib.request.Request(url, data=request_body if payload is not None else None,
                headers={'Content-Type':'application/json','User-Agent':'Steuerpendler-reference-audit/1.0'})
            stamp = datetime.datetime.now(datetime.timezone.utc).isoformat()
            try:
                with self.opener.open(req, timeout=25) as response:
                    status, final_url = response.status, response.url
                    content_type = response.headers.get('Content-Type', '')
                    body = response.read(16000001)
            except urllib.error.HTTPError as exc:
                status, final_url = exc.code, url
                content_type = exc.headers.get('Content-Type', '')
                body = exc.read(16000001)
            if len(body) > 16000000: raise ValueError('Response exceeds size budget')
            meta = dict(url=url, final_url=final_url, retrieved_utc=stamp, status=status,
                content_type=content_type, method='POST' if payload is not None else 'GET',
                request_sha256=digest(request_body), response_sha256=digest(body),
                authentication='none', outgoing_cookies=False, attempts=1)
            request_path.write_bytes(request_body)
            response_path.write_bytes(body)
            meta_path.write_text(json.dumps(meta, indent=2)+'\n')
            self.requests.append(meta)
            print(name, status, flush=True)
        if meta['status'] != 200: raise ValueError('HTTP barrier/failure: ' + str(meta['status']))
        if payload is None: return body
        if 'json' not in meta.get('content_type', 'application/json'):
            raise ValueError('Not JSON; stop rather than bypass login/captcha')
        return json.loads(body)

COMPONENTS = ['IncomeTaxFed', 'IncomeTaxCanton', 'IncomeTaxCity', 'IncomeTaxChurch',
              'FortuneTaxCanton', 'FortuneTaxCity', 'FortuneTaxChurch', 'PersonalTax']

def validate_result(case, result):
    loc = result['Location']
    if loc['BfsID'] != case['bfs'] or loc['Canton'] != case['canton']:
        raise ValueError('Official location mismatch')
    if result.get('Diagnosis'):
        raise ValueError('Official diagnosis: ' + str(result['Diagnosis']))
    if any(not math.isfinite(result[k]) for k in COMPONENTS + ['TotalTax', 'TaxCredit', 'TotalNetTax']):
        raise ValueError('Nonfinite official component')
    if any(result[k] != 0 for k in COMPONENTS if k.startswith('Fortune')):
        raise ValueError('Nonzero wealth tax for no-wealth profile')
    if sum(result[k] for k in COMPONENTS) != result['TotalTax']:
        raise ValueError('Component sum mismatch')
    if result['TotalTax'] + result['TaxCredit'] != result['TotalNetTax']:
        raise ValueError('Net tax mismatch')
    if result['IncomeP1']['GrossIncome'] != case['income'] or result['IncomeP2']['GrossIncome'] != 0:
        raise ValueError('Gross/partner income mismatch')
    return result['TotalNetTax']

CANTONS = set('ZH BE LU UR SZ OW NW GL ZG FR SO BS BL SH AR AI SG GR AG TG TI VD VS NE GE JU'.split())

def cases_from_spec(text):
    section = text.split('### 11.1 Tax:')[1].split('### 11.2 Travel:')[0]
    rows = []
    for line in section.splitlines():
        parts = [x.strip() for x in line.strip('|').split('|')]
        if len(parts) == 9 and parts[3] in ('single', 'married'):
            rows.append(dict(case_id=f'estv-2026-{len(rows)+1:02d}', city=parts[0],
                canton=parts[1], bfs=int(parts[2]), civil=parts[3], kids=int(parts[4]),
                income=int(parts[5].replace(',', '')), church=parts[6]))
    if len(rows) != 29 or {r['canton'] for r in rows} != CANTONS:
        raise ValueError('Expected all 29 SPEC11.1 cases and all 26 cantons')
    return rows

def request_for(case, location_id):
    married = case['civil'] == 'married'
    church = {'none': 4, 'reformed': 1, 'catholic': 2}[case['church']]
    return {'SimKey': None, 'TaxYear': 2026, 'TaxLocationID': location_id,
            'Relationship': 2 if married else 1, 'Confession1': church,
            'Children': [{'Age': 10} for _ in range(case['kids'])],
            'Age1': 35, 'RevenueType1': 1, 'Revenue1': case['income'], 'Fortune': 0,
            'Confession2': church if married else 0, 'Age2': 35 if married else 0,
            'RevenueType2': 0, 'Revenue2': 0, 'Budget': []}


def validate_catalogue(out, csv_path, cases):
    """Validate every published byte, mapping and CSV row without network access."""
    out, csv_path = Path(out), Path(csv_path)
    with csv_path.open(newline='') as handle:
        rows = list(csv.DictReader(handle))
    by_id = {row['case_id']: row for row in rows}
    if len(rows) != 29 or len(by_id) != 29:
        raise ValueError('Expected exactly 29 unique CSV rows')
    if {case['case_id'] for case in cases} != set(by_id):
        raise ValueError('CSV/SPEC case set mismatch')

    operation_urls = {
        'lookup': BASE + 'API_searchLocation',
        'tax': BASE + 'API_calculateDetailedTaxes',
        'budget': BASE + 'API_calculateTaxBudget',
    }
    statuses = {}
    case_results = []
    validated_operations = 0
    forbidden_meta = re.compile(r'authorization|set-cookie|csrf|bearer|password|secret|token', re.I)

    for case in cases:
        key = case['case_id']
        evidence = {}
        for kind, expected_url in operation_urls.items():
            request_path = out / f'{key}-{kind}.request.json'
            response_path = out / f'{key}-{kind}.response.json'
            meta_path = out / f'{key}-{kind}.meta.json'
            request_body, response_body = request_path.read_bytes(), response_path.read_bytes()
            meta = json.loads(meta_path.read_bytes())
            if any(forbidden_meta.search(name) for name in meta):
                raise ValueError('Authority-bearing metadata persisted: ' + meta_path.name)
            if (meta.get('url') != expected_url or meta.get('final_url') != expected_url
                or meta.get('method') != 'POST' or meta.get('status') != 200
                or 'json' not in meta.get('content_type', '')
                or meta.get('authentication') != 'none' or meta.get('outgoing_cookies') is not False
                or meta.get('request_sha256') != digest(request_body)
                or meta.get('response_sha256') != digest(response_body)):
                raise ValueError('Invalid evidence metadata: ' + meta_path.name)
            request = json.loads(request_body)
            response = json.loads(response_body)
            evidence[kind] = (request, response, meta)
            status = str(meta['status'])
            statuses[status] = statuses.get(status, 0) + 1
            validated_operations += 1

        lookup_request, lookup_response, _ = evidence['lookup']
        if lookup_request != {'Search': case['city'].replace(' (UR)', ''), 'Language': 1, 'TaxYear': 2026}:
            raise ValueError('Lookup request/profile mismatch: ' + key)
        tax_request, tax_response, tax_meta = evidence['tax']
        if tax_request != request_for(case, tax_request['TaxLocationID']):
            raise ValueError('Tax request/profile mismatch: ' + key)
        matching_locations = [loc for loc in lookup_response.get('response', [])
            if loc.get('TaxLocationID') == tax_request['TaxLocationID']
            and loc.get('BfsID') == case['bfs'] and loc.get('Canton') == case['canton']]
        if not matching_locations:
            raise ValueError('Tax location absent from official lookup: ' + key)
        result = tax_response['response']
        official = validate_result(case, result)
        budget_request, budget_response, _ = evidence['budget']
        if budget_request != {**tax_request, 'Language': 1}:
            raise ValueError('Budget request/profile mismatch: ' + key)
        budget_entries = budget_response.get('response')
        if not isinstance(budget_entries, list) or not budget_entries:
            raise ValueError('Missing native default calculation steps: ' + key)

        row = by_id[key]
        expected_strings = {
            'city': case['city'], 'canton': case['canton'], 'bfs': str(case['bfs']),
            'civil': case['civil'], 'kids': str(case['kids']), 'income': str(case['income']),
            'church': case['church'], 'tax_year': '2026', 'age': '35', 'partner_income': '0',
            'child_ages': ';'.join(['10'] * case['kids']), 'wealth': '0',
            'income_basis': 'gross_employment', 'budget': 'ESTV_native_defaults',
            'partner_age': '35' if case['civil'] == 'married' else '',
            'official_chf': str(official), 'source_url': tax_meta['url'],
            'retrieved_utc': tax_meta['retrieved_utc'],
            'response_sha256': tax_meta['response_sha256'],
            'request_sha256': tax_meta['request_sha256'],
            'evidence': str(out / f'{key}-tax.response.json'),
            'capture_status': 'captured', 'comparability': 'owner_pending',
            'engine_chf': '', 'frontend_chf': '', 'release_id': '', 'official_gate': 'pending',
        }
        expected_strings.update({field: str(result[field]) for field in COMPONENTS + ['TotalTax', 'TaxCredit', 'TotalNetTax']})
        for field, expected in expected_strings.items():
            if row.get(field) != expected:
                raise ValueError(f'CSV mismatch {key} {field}: {row.get(field)!r} != {expected!r}')
        case_results.append({'case_id': key, 'bfs': case['bfs'], 'canton': case['canton'],
                             'official_chf': official})

    verification = json.loads((out / 'verification.json').read_bytes())
    if (verification.get('captured_cases') != 29 or verification.get('cantons') != 26
        or verification.get('case_results') != case_results
        or verification.get('official_gate') != 'pending_not_executed'
        or verification.get('comparability') != 'owner_pending'):
        raise ValueError('Verification summary mismatch')

    auxiliary_statuses = dict(statuses)
    validated_http_captures = validated_operations

    def validate_auxiliary(name, expected_url, expected_method, expected_content_type):
        nonlocal validated_http_captures
        request_body = (out / f'{name}.request.json').read_bytes()
        response_body = (out / f'{name}.response.json').read_bytes()
        meta = json.loads((out / f'{name}.meta.json').read_bytes())
        if any(forbidden_meta.search(field) for field in meta):
            raise ValueError('Authority-bearing auxiliary metadata persisted: ' + name)
        if (meta.get('url') != expected_url or meta.get('final_url') != expected_url
            or meta.get('method') != expected_method or meta.get('status') != 200
            or expected_content_type not in meta.get('content_type', '')
            or meta.get('authentication') != 'none' or meta.get('outgoing_cookies') is not False
            or meta.get('request_sha256') != digest(request_body)
            or meta.get('response_sha256') != digest(response_body)):
            raise ValueError('Invalid auxiliary evidence: ' + name)
        status = str(meta['status'])
        auxiliary_statuses[status] = auxiliary_statuses.get(status, 0) + 1
        validated_http_captures += 1
        return request_body, response_body, meta

    source_request, source_response, _ = validate_auxiliary('source-page', SOURCE, 'GET', 'text/html')
    if source_request or b'<script' not in source_response:
        raise ValueError('Invalid official source-page capture')
    for name, operation in [('year-range', 'API_getTaxYearRangeCanton'), ('version', 'API_getTaxVersion')]:
        request_body, response_body, _ = validate_auxiliary(name, BASE + operation, 'POST', 'json')
        if json.loads(request_body) != {} or 'response' not in json.loads(response_body):
            raise ValueError('Invalid official auxiliary response: ' + name)

    first_request = (out / f"{cases[0]['case_id']}-tax.request.json").read_bytes()
    first_response = (out / f"{cases[0]['case_id']}-tax.response.json").read_bytes()
    replay_current_request, replay_current_response, _ = validate_auxiliary(
        'replay-current', BASE + 'API_calculateDetailedTaxes', 'POST', 'json')
    replay_request, replay_response, replay_meta = validate_auxiliary(
        'replay-independent', BASE + 'API_calculateDetailedTaxes', 'POST', 'json')
    replay_exact = (replay_current_request == first_request == replay_request
                    and replay_current_response == first_response == replay_response)
    baseline_exact = (out / 'replay-baseline.response.json').read_bytes() == first_response
    if not replay_exact or not baseline_exact:
        raise ValueError('Current/historical replay mismatch')

    checksum_root = csv_path.parent
    manifest_path = checksum_root / 'SHA256SUMS'
    declared = {}
    for line in manifest_path.read_text().splitlines():
        checksum, relative = line.split('  ', 1)
        if not re.fullmatch(r'[0-9a-f]{64}', checksum) or relative in declared:
            raise ValueError('Invalid checksum manifest entry')
        declared[relative] = checksum
    files = sorted(path for path in checksum_root.rglob('*')
                   if path.is_file() and path != manifest_path)
    observed = {path.relative_to(checksum_root).as_posix(): digest(path.read_bytes()) for path in files}
    if declared != observed:
        raise ValueError('Checksum manifest/file set mismatch')

    return {'captured_cases': len(case_results), 'cantons': len({case['canton'] for case in cases}),
            'validated_operations': validated_operations, 'http_statuses': statuses,
            'validated_http_captures': validated_http_captures,
            'all_http_statuses': auxiliary_statuses,
            'historical_baseline_exact': baseline_exact,
            'independent_replay_exact': replay_exact,
            'independent_replay_status': replay_meta['status'],
            'checksum_files': len(observed),
            'official_gate': verification['official_gate'],
            'comparability': verification['comparability']}



def main():
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--offline', action='store_true')
    parser.add_argument('--output', type=Path, default=Path('tests/reference/estv-2026'))
    parser.add_argument('--discovery', type=Path, default=Path('/home/hermes/artifacts/steuerpendler-build/estv-discovery'))
    args = parser.parse_args()
    out = args.output
    cap = Capture(out, args.offline)
    cases = cases_from_spec(Path('SPEC.md').read_text())
    # Current public page/bundle must be inspected before reusing the native contract.
    page = cap.fetch('source-page', SOURCE)
    asset = re.search(r'<script[^>]+src="([^"]+\.js)"', page.decode()).group(1)
    bundle_url = SOURCE.rstrip('/') + asset
    if args.offline:
        contract = json.loads((out/'contract.json').read_bytes())
        if contract['bundle_url'] != bundle_url: raise ValueError('Bundle changed')
    else:
        discovery = Capture(args.discovery / 'current')
        bundle = discovery.fetch('bundle', bundle_url)
        text = bundle.decode()
        snippets = []
        for needle, before, after in [
            ('e[e.SINGLE=1]',0,380),('e[e.REFORMED=1]',0,220),
            ('function lb(',0,360),('function sb(',0,200),
            ('function Ms(',0,1500),('qe=()=>{let t={};if(Te())',0,1400),
            ('Age1:35,Age2:35',40,80)]:
            offset = text.index(needle)
            snippets.append(dict(offset=offset, text=text[max(0,offset-before):offset+after]))
        contract = dict(bundle_url=bundle_url, bundle_sha256=digest(bundle),
            retrieved_utc=json.loads((discovery.root/'bundle.meta.json').read_bytes())['retrieved_utc'], snippets=snippets,
            spec_sha256=digest(Path('SPEC.md').read_bytes()), source_revision='4361c1ca8b4f0ba9ea13285b04719cf15cc89992',
            approvals={'child_age_10':'owner_pending','partner_age_35_same_confession':'owner_pending',
                       'default_budget_comparability':'owner_pending','official_frontend_gate':'pending'})
        (out/'contract.json').write_text(json.dumps(contract,ensure_ascii=False,indent=2)+'\n')
    cap.fetch('year-range', BASE+'API_getTaxYearRangeCanton', {})
    cap.fetch('version', BASE+'API_getTaxVersion', {})
    # Replay known exact public request independently; no historic metadata/headers copied.
    prior = out/'replay-baseline.response.json'
    replay_request = request_for(cases[0], 800000000)
    replay = cap.fetch('replay-current', BASE+'API_calculateDetailedTaxes', replay_request)
    replay_hash = digest((out/'replay-current.response.json').read_bytes())
    if replay_hash != digest(prior.read_bytes()): raise ValueError('Independent historical replay drift')
    records = []
    for case in cases:
        key = case['case_id']
        search = case['city'].replace(' (UR)', '')
        locations = cap.fetch(key+'-lookup', BASE+'API_searchLocation',
            dict(Search=search, Language=1, TaxYear=2026))['response']
        matches = [loc for loc in locations if loc['BfsID']==case['bfs'] and loc['Canton']==case['canton']]
        if not matches: raise ValueError('No official BFS/canton location: '+key)
        loc = sorted(matches, key=lambda x:(x['City']!=search, x['TaxLocationID']))[0]
        payload = request_for(case, loc['TaxLocationID'])
        result = cap.fetch(key+'-tax', BASE+'API_calculateDetailedTaxes',payload)['response']
        total = validate_result(case,result)
        cap.fetch(key+'-budget', BASE+'API_calculateTaxBudget', {**payload,'Language':1})
        meta = json.loads((out/(key+'-tax.meta.json')).read_bytes())
        records.append({**case, 'tax_year':2026,'age':35,'partner_income':0,
            'child_ages':';'.join(['10']*case['kids']), 'wealth':0,
            'income_basis':'gross_employment','budget':'ESTV_native_defaults',
            'partner_age':35 if case['civil']=='married' else '',
            'official_chf':total, **{k:result[k] for k in COMPONENTS+['TotalTax','TaxCredit','TotalNetTax']},
            'source_url':meta['url'],'retrieved_utc':meta['retrieved_utc'],
            'response_sha256':meta['response_sha256'],'request_sha256':meta['request_sha256'],
            'evidence':str(out/(key+'-tax.response.json')),
            'capture_status':'captured','comparability':'owner_pending',
            'engine_chf':'','frontend_chf':'','release_id':'','official_gate':'pending'})
    csv_path = out.parent / 'estv-2026.csv'
    with csv_path.open('w',newline='') as handle:
        writer = csv.DictWriter(handle, fieldnames=list(records[0]), lineterminator='\n')
        writer.writeheader()
        writer.writerows(records)
    summary = dict(captured_cases=len(records),cantons=len({r['canton'] for r in records}),
        historical_replay_sha256=replay_hash,historical_replay_exact=True,
        official_gate='pending_not_executed',comparability='owner_pending',
        case_results=[dict(case_id=r['case_id'],bfs=r['bfs'],canton=r['canton'],official_chf=r['official_chf']) for r in records])
    if not args.offline:
        summary['actual_requests'] = [json.loads(p.read_bytes()) for p in sorted(out.glob('*.meta.json'))]
        summary['discovery_requests'] = [json.loads((discovery.root/'bundle.meta.json').read_bytes())]
        (out/'verification.json').write_text(json.dumps(summary,indent=2)+'\n')
    else:
        original = json.loads((out/'verification.json').read_bytes())
        for k,v in summary.items():
            if original[k] != v: raise ValueError('Offline replay mismatch: '+k)
    print(json.dumps({k:v for k,v in summary.items() if k not in ('actual_requests','discovery_requests','case_results')},indent=2))

if __name__ == '__main__':
    main()
