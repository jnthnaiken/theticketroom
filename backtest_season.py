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
MKT_W = 0.75   # shipped market/edge mix

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
nightly = []
nights = sorted(re.search(r'D_(\d{4}-\d{2}-\d{2})', f).group(1) for f in glob.glob('D_2026-*.json'))
first = None
for dt in nights:
    try:
        D0 = json.load(open(f'D_{dt}.json'))
    except Exception:
        continue
    if not has_sig(D0) or dt not in hrby:
        continue
    if first is None: first = dt
    homered = hrby[dt]
    played = set(norm(n) for n in D0['players'])
    D = copy.deepcopy(D0); rescore(D)
    try:
        AT.assemble(D)
    except Exception:
        continue
    night_net = 0.0
    for t in D.get('tickets', []):
        g = GN.grade_ticket(t, homered, played, set(), 1.0)
        if not g or g.get('won') is None:
            continue
        k = t.get('kind')
        if k not in cats: continue
        cats[k]['graded'] += 1
        cats[k]['won'] += 1 if g['won'] else 0
        cats[k]['units'] = round(cats[k]['units'] + g['net'], 2)
        cats[k]['staked'] = round(cats[k]['staked'] + g['stake'], 2)
        night_net += g['net']
    history.append(round(history[-1] + night_net, 2))
    nightly.append(night_net)

tot = round(sum(c['units'] for c in cats.values()), 2)
staked = round(sum(c['staked'] for c in cats.values()), 2)
n = len(nightly)
se = (np.std(nightly, ddof=1)/np.sqrt(n))*n if n > 1 else 0.0   # SE of the total
print(f"backtested season | model 2026-08-01 (SIG {SIG}, mix {MKT_W}/{1-MKT_W}) | {n} nights {first}..{nights[-1]}")
for c in CATS:
    r = cats[c]
    print(f"  {c:8s} {r['won']:3d}-{r['graded']-r['won']:<3d}  {r['units']:+8.1f}u  (staked {r['staked']:.0f})")
print(f"  TOTAL          {tot:+8.1f}u  (staked {staked:.0f}, ROI {tot/staked*100:+.1f}%)  +/- {se:.0f}u SE on the total")
print(f"  history points: {len(history)}  final {history[-1]:+.1f}")

out = {'basis': 'BACKTEST', 'model': '2026-08-01', 'note': 'SIMULATED performance of the current model re-drafted+re-graded over past slates -- NOT realized/placed bets. High variance; see SE.',
       'since': first, 'stake': 1, 'cats': cats, 'history': history}
json.dump(out, open('/tmp/season_backtest.json', 'w'), indent=1)
print("\nwrote /tmp/season_backtest.json")
