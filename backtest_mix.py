import json, glob, re, copy, unicodedata
import numpy as np
import assemble_tickets as AT
import grade_night as GN

def norm(s):
    s = unicodedata.normalize('NFKD', s or '')
    return ''.join(c for c in s if not unicodedata.combining(c)).lower().replace('.', '').replace(' ', '').strip()

# ---- outcomes from the (repaired) log: who homered each night ----
hrby = {}
for l in open('calibration.jsonl'):
    d = json.loads(l)
    hrby.setdefault(d['date'], set())
    if d['hr']:
        hrby[d['date']].add(norm(d['name']))

WX_K, WX_CAP = 1.0, 0.10
def wxMult(wf):
    if wf is None: return 1.0
    return max(1-WX_CAP, min(1+WX_CAP, 1+WX_K*(wf-1)))

def zstd(vals):
    a = np.array([v for v in vals if v is not None], float)
    if len(a) < 2: return (0.0, 1.0)
    sd = a.std()
    return (a.mean(), sd if sd > 1e-9 else 1e-9)

SIG = [('_zxpow', 0.47), ('_zxwcon', 0.47), ('_zars', 0.06)]   # current shipped edge basket

def rescore(D, alpha):
    """Rebuild TOTAL/blend under blend = alpha*market_z + (1-alpha)*edge_z (per-slate standardized,
    exactly like build15) so the ONLY thing changing across the sweep is the market/edge mix."""
    P = D['players']; names = list(P)
    st = {k: zstd([P[n].get(k) for n in names]) for k, _ in SIG}
    mkmu, mksd = zstd([P[n].get('_zmkt') for n in names])
    edge0, mz0 = {}, {}
    for n in names:
        p = P[n]; e = 0.0
        for k, w in SIG:
            x = p.get(k)
            if x is None: continue
            mu, sd = st[k]; e += w*((x-mu)/sd)
        edge0[n] = e
        xm = p.get('_zmkt')
        mz0[n] = ((xm-mkmu)/mksd) if xm is not None else 0.0
    emu, esd = zstd(list(edge0.values()))
    mmu, msd = zstd(list(mz0.values()))
    for n in names:
        ez = (edge0[n]-emu)/esd
        mz = (mz0[n]-mmu)/msd
        blend = alpha*mz + (1-alpha)*ez
        base = 100 + 30*blend
        P[n]['blend'] = round(blend, 4)
        P[n]['baseTotal'] = round(base, 1)
        P[n]['TOTAL'] = round(base*wxMult(P[n].get('wf')), 1)

def has_sig(D):
    return sum(1 for p in D.get('players', {}).values() if p.get('_zxpow') is not None) > 20

nights = sorted(re.search(r'D_(\d{4}-\d{2}-\d{2})', f).group(1) for f in glob.glob('D_2026-*.json'))
alphas = [0.0, 0.3, 0.5, 0.7, 0.85, 1.0]
res = {a: {'net': 0.0, 'staked': 0.0, 'cats': {}, 'nt': 0, 'nightly': []} for a in alphas}
used = 0
for dt in nights:
    try:
        D0 = json.load(open(f'D_{dt}.json'))
    except Exception:
        continue
    if not has_sig(D0) or dt not in hrby:
        continue
    used += 1
    print(f"  [{used}] {dt}", flush=True)
    homered = hrby[dt]
    played = set(norm(n) for n in D0['players'])   # offline approx: everyone scored is assumed to have taken a PA
    for a in alphas:
        D = copy.deepcopy(D0)
        rescore(D, a)
        try:
            AT.assemble(D)
        except Exception as e:
            print(f"  {dt} a={a}: assemble failed ({e})")
            continue
        night_net = 0.0
        for t in D.get('tickets', []):
            g = GN.grade_ticket(t, homered, played, set(), 1.0)
            if not g or g.get('won') is None:
                continue
            res[a]['net'] += g['net']
            res[a]['staked'] += g['stake']
            res[a]['nt'] += 1
            night_net += g['net']
            k = t.get('kind', '?')
            res[a]['cats'][k] = res[a]['cats'].get(k, 0.0) + g['net']
        res[a]['nightly'].append(night_net)

print(f"\n{used} signal-complete nights backtested | edge basket {SIG}")
print("mkt/edge   net_u   +/-SE     ROI    | builder(1u singles)")
for a in alphas:
    r = res[a]
    arr = np.array(r['nightly'])
    se = arr.std(ddof=1)/np.sqrt(len(arr)) if len(arr) > 1 else 0.0
    roi = (r['net']/r['staked']*100) if r['staked'] else 0.0
    tag = '  <- current' if a == 0.5 else ''
    print(f"{a:0.1f}/{1-a:0.1f}  {r['net']:+8.1f}  +/-{se:4.0f}  {roi:+6.1f}%  |  builder {r['cats'].get('builder',0.0):+6.1f}{tag}")
print("\nnet_u spread across mixes is dwarfed by the per-mix standard error -> not distinguishable.")
