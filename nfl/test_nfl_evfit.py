#!/usr/bin/env python3
"""test_nfl_evfit.py -- EVCAL-NFL-2026-09-11, offline, stdlib only.

  1. the fitter recovers "trust the price more than a noisier model" on a synthetic slate
  2. below MIN_ROWS / MIN_NIGHTS it writes NOTHING (today's archive: 47 rows, 6 TDs)
  3. above them it writes a CANDIDATE with proposed: null, never a live file
  4. nfl_mock only uses a weights file whose `proposed` is set
  5. the workflow stages the weights file and re-fits after a settle
"""
import io, json, math, os, random, sys, tempfile
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import nfl_ev_fit as F

fail = 0
def chk(label, ok, detail=None):
    global fail
    print(('PASS  ' if ok else 'FAIL  ') + label)
    if not ok:
        fail += 1
        if detail is not None: print('      ', detail)

def am(p):
    return round(100 * (1 - p) / p) if p < 0.5 else -round(100 * p / (1 - p))

random.seed(11)
def slate(nights, per):
    rows = []
    for n in range(nights):
        for i in range(per):
            t = random.uniform(0.03, 0.5)
            q = min(0.9, max(0.02, t * math.exp(random.gauss(0, 0.10))))
            pm = min(0.9, max(0.005, t * math.exp(random.gauss(0, 0.60))))
            a = am(min(0.9, q * 1.07))
            rows.append(dict(date=f'2026-10-{n+1:02d}', name=f'p{i}', odds=a if abs(a) >= 100 else 100,
                             p_model=pm, y=1 if random.random() < t else 0))
    return rows

w = F.fit(slate(8, 400))
chk('price term dominates a noisier model (b_lim > b_m > 0)', w[1] > w[3] > 0, [round(x, 3) for x in w])

def write_boards(d, rows):
    os.makedirs(os.path.join(d, 'boards'), exist_ok=True)
    by = {}
    for r in rows:
        by.setdefault(r['date'], {})[r['name']] = dict(odds=r['odds'], khr=round(r['p_model'] * 100, 1), hr=bool(r['y']))
    for date, P in by.items():
        json.dump({'meta': {'date': date}, 'players': P, 'tickets': []}, open(os.path.join(d, 'boards', date + '.json'), 'w'))
    json.dump({'graded_nights': sorted(by)}, open(os.path.join(d, 'season.json'), 'w'))

with tempfile.TemporaryDirectory() as d:
    write_boards(d, slate(2, 24))
    out = os.path.join(d, 'w.json')
    F.main(['x', '--boards', os.path.join(d, 'boards'), '--season', os.path.join(d, 'season.json'), '--out', out])
    chk('thin archive (2 nights) writes nothing', not os.path.exists(out))

with tempfile.TemporaryDirectory() as d:
    write_boards(d, slate(7, 400))
    out = os.path.join(d, 'w.json')
    F.main(['x', '--boards', os.path.join(d, 'boards'), '--season', os.path.join(d, 'season.json'), '--out', out])
    j = json.load(open(out)) if os.path.exists(out) else {}
    chk('enough data writes a candidate', bool(j.get('coef')))
    chk('the candidate is NOT live (proposed: null)', 'proposed' in j and j['proposed'] is None)
    chk('it carries the leave-one-night-out check', 'leave_one_night_out_top8_flat' in (j.get('fit') or {}))

src = open(os.path.join(HERE, 'nfl_mock.py'), encoding='utf-8').read()
chk('nfl_mock ignores a weights file without a proposed date', "if not j.get('proposed'):" in src and 'return None' in src)
wf = open(os.path.join(HERE, '..', '.github', 'workflows', 'nfl-build.yml')).read()
chk('nfl-build.yml stages the weights file', 'cp ev_weights_nfl_v1.json .work/' in wf)
chk('nfl-build.yml re-fits after a settle', 'python3 nfl_ev_fit.py' in wf)

print(f'\n{fail} FAILURE(S)' if fail else '\nall checks pass')
sys.exit(1 if fail else 0)
