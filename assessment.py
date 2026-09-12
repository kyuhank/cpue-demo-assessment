"""Fit four illustrative age-structured cases to prepared annual catch and CPUE."""
import csv
import math
from pathlib import Path
import platform
import json
import time
import hashlib
import os

started = time.perf_counter()

OUT = Path('outputs')
manifest = json.loads((OUT / 'manifest.json').read_text())
input_bytes = (OUT / 'assessment-input.csv').read_bytes()
if hashlib.sha256(input_bytes).hexdigest() != manifest['input_preparation']['output_sha256']:
    raise SystemExit('Prepared assessment input checksum differs from its record')
indices = list(csv.DictReader((OUT / 'assessment-input.csv').open()))
import sys
sys.path.insert(0, str(Path(__file__).resolve().parent))
from settings import assessment_cases
cases = assessment_cases()
requested = os.getenv('TOY_ASSESSMENT_CASE', '')
if requested:
    cases = [case for case in cases if case['key'] == requested]
    if not cases:
        raise SystemExit('Unknown assessment case')
if not {case['choice'] for case in cases} <= {row['choice'] for row in indices}:
    raise SystemExit('The prepared input does not supply the requested CPUE choice')

import sys
sys.path.insert(0, str(Path(__file__).resolve().parent))
from age_model import fit, AGES, WEIGHT, SELECTIVITY, MATURITY

summary, series = [], []
for case in cases:
    choice, setting, scenario, mortality = case['choice'], case['setting'], case['key'], case['M']
    data = sorted((x for x in indices if x['choice'] == choice), key=lambda x: int(x['year']))
    result = fit([float(x['index']) for x in data], [float(x['catch_t']) for x in data], mortality)
    summary.append([choice, setting, scenario, data[-1]['year'], result['R0'], result['B0'], result['SB0'],
                    result['q'], mortality, float(data[-1]['index']), result['rows'][-1]['SB_over_SB0'],
                    result['log_index_SSE'], result['boundary_fit']])
    series.extend([x['year'], choice, setting, scenario, row['biomass'], row['spawning_biomass'],
                   row['SB_over_SB0'], row['F'], x['index'], result['q'] * row['vulnerable_biomass']]
                  for x, row in zip(data, result['rows']))
for name, header, data in [
    ('summary.csv', ['choice','setting','scenario','year','R0','B0','SB0','q','M','final_index','final_SB_over_SB0','log_index_SSE','boundary_fit'], summary),
    ('biomass.csv', ['year','choice','setting','scenario','biomass','spawning_biomass','SB_over_SB0','F','observed_index','fitted_index'], series),
]:
    with (OUT / name).open('w', newline='') as f:
        w = csv.writer(f); w.writerow(header); w.writerows(data)
manifest['assessment_biology'] = {'ages': AGES, 'plus_group': 10, 'weight_t': WEIGHT,
    'selectivity': SELECTIVITY, 'maturity': MATURITY, 'M_units': 'per year',
    'recruitment': 'constant fitted R0', 'initial_state': 'unfished equilibrium',
    'catch_equation': 'Baranov; solve annual F to match removals',
    'index': 'q times beginning-year vulnerable biomass',
    'scope': 'illustrative values; no age compositions, recruitment deviations or uncertainty propagation'}
(OUT / 'assessment-session.txt').write_text(f'Python {platform.python_version()}; standard library only; coarse bracket and bounded golden-section optimisation\n')
print(f'ASSESSMENT complete: {len(cases)} age-structured fit(s); recorded natural mortality assumptions; no uncertainty propagation')

job = os.getenv('GITHUB_JOB', requested or 'assessment')
manifest.setdefault('stage_compute_seconds', {})[job] = time.perf_counter() - started
manifest['assessment_runs'] = {case['key']: {**case, 'job': os.getenv('GITHUB_JOB', case['key']),
    'prepared_by': manifest['input_preparation']['job'],
    'input_sha256': manifest['input_preparation']['output_sha256'],
    **{name + '_sha256': hashlib.sha256((OUT / name).read_bytes()).hexdigest()
       for name in ('summary.csv', 'biomass.csv')}} for case in cases}
(OUT / 'manifest.json').write_text(json.dumps(manifest, indent=2) + '\n')
