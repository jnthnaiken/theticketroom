# ⚠ DEPRECATED 2026-08-13 -- superseded by backtest_true_*.py + .github/workflows/backtest-true.yml.
# This script grades assemble_tickets.py (NOT the engine that ships), assumes every carded bat took a PA
# (so refunds grade as losses), and its SIG / MKT_W constants were never the shipped model. Kept as history.
import json, glob, re, copy, unicodedata
import numpy as np
import assemble_tickets as AT
import grade_night as GN

def norm(s):
    s = unicodedata.normalize('NFKD', s or '')
    return ''.join(c for c in s if not unicodedata.combining(c)).lower().replace('.', '').replace(' ', '').strip()

hrby = {}
for l in open('calibration.jsonl'):
    d = json.loads(l)
    hrby.setdefault(d['date'], set())
    if d['hr']:
        hrby[d['date']].add(norm(d['name']))

def wxMult(wf):
    return 1.0 if wf is None else max(0.9, min(1.1, 1+(wf-1)))
def zstd(v):
    a = np.array([x for x in v if x is not None], float)
    if len(a) < 2: return (0.0, 1.0)
    sd = a.std(); return (a.mean(), sd if sd > 1e-9 else 1e-9)

SIG = [('_zxpow', 0.346), ('_zxwcon', 0.288), ('_zars', 0.366)]  # corrected 2026-08-02: 8/01 wts were raw-space; model z-scores signals -> arsenal deserves ~0.37 not 0.06 (see build15.py _SIG)
MKT_W = 0.75

def rescore(D):
    P = D['players']; names = list(P)
    st = {k: zstd([P[n].get(k) for n in names]) for k, _ in SIG}
    mm, ms = zstd([P[n].get('_zmkt') for n in names])
    e0, m0 = {}, {}
    for n in names:
        p = P[n]; e = 0.0
        for k, w in SIG:
            x = p.get(k)
            if x is None: continue
            mu, sd = st[k]; e += w*((x-mu)/sd)
        e0[n] = e
        xm = p.get('_zmkt'); m0[n] = ((xm-mm)/ms) if xm is not None else 0.0
    emu, esd = zstd(list(e0.values())); mmu, msd = zstd(list(m0.values()))
    for n in names:
        bl = MKT_W*((m0[n]-mmu)/msd) + (1-MKT_W)*((e0[n]-emu)/esd)
        P[n]['blend'] = round(bl, 4); P[n]['baseTotal'] = round(100+30*bl, 1)
        P[n]['TOTAL'] = round((100+30*bl)*wxMult(P[n].get('wf')), 1)

def has_sig(D):
    return sum(1 for p in D.get('players', {}).values() if p.get('_zxpow') is not None) > 20

CATS = ['moon', 'biggest', 'late', 'builder', 'lunch']
cats = {c: {'graded': 0, 'won': 0, 'units': 0.0, 'staked': 0.0} for c in CATS}
history = [0.0]
split = {'real': 0.0, 'backtest': 0.0}
rows = []
nights = sorted(re.search(r'D_(\d{4}-\d{2}-\d{2})', f).group(1) for f in glob.glob('D_2026-*.json'))
first = None
for dt in nights:
    if dt not in hrby:
        continue
    try:
        D0 = json.load(open(f'D_{dt}.json'))
    except Exception:
        continue
    if 'players' not in D0:
        continue
    homered = hrby[dt]
    played = set(norm(n) for n in D0['players'])
    if has_sig(D0):
        basis = 'backtest'
        D = copy.deepcopy(D0)
        rescore(D)
        try:
            AT.assemble(D)
        except Exception:
            continue
        tickets = D.get('tickets', [])
    else:
        basis = 'real'                       # June: no signals -> grade the shipped board as-is
        tickets = D0.get('tickets', [])
    if first is None:
        first = dt
    night_net = 0.0
    for t in tickets:
        g = GN.grade_ticket(t, homered, played, set(), 1.0)
        if not g or g.get('won') is None:
            continue
        k = t.get('kind')
        if k not in cats:
            continue
        cats[k]['graded'] += 1
        cats[k]['won'] += 1 if g['won'] else 0
        cats[k]['units'] = round(cats[k]['units'] + g['net'], 2)
        cats[k]['staked'] = round(cats[k]['staked'] + g['stake'], 2)
        night_net += g['net']
    split[basis] += night_net
    history.append(round(history[-1] + night_net, 2))
    rows.append((dt, basis, round(night_net, 1)))

tot = round(sum(c['units'] for c in cats.values()), 2)
print(f"HYBRID tracker | {len(rows)} nights {first}..{nights[-1]}")
print(f"  June real (no signals): {sum(1 for _,b,_ in rows if b=='real')} nights -> {split['real']:+.1f}u")
print(f"  New-model backtest:     {sum(1 for _,b,_ in rows if b=='backtest')} nights -> {split['backtest']:+.1f}u")
print(f"  COMBINED TOTAL: {tot:+.1f}u")
for c in CATS:
    r = cats[c]
    print(f"    {c:8s} {r['won']:3d}-{r['graded']-r['won']:<3d}  {r['units']:+8.1f}u")

out = {'basis': 'hybrid', 'model': '2026-08-02 (SIG 0.346/0.288/0.366, mix 0.75/0.25) from 6/30; real shipped board before that',
       'since': first, 'stake': 1, 'cats': cats, 'history': history}
json.dump(out, open('/tmp/season_hybrid.json', 'w'), indent=1)
print("\nwrote /tmp/season_hybrid.json  (" + str(len(json.dumps(out))) + " chars)")
