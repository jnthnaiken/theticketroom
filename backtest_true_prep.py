#!/usr/bin/env python3
"""backtest_true, stage 1 -- pick usable nights + rescore each under every condition.

Scans D_2026-*.json in the repo root for signal-complete boards (additive-model era:
_zxpow/_zmkt baked, hh/la present), then rebuilds blend/baseTotal/TOTAL per player under
each condition, mirroring build15.py exactly: per-slate z over non-null values, edge
skips missing signals, both halves re-standardized, blend = a*mz + (1-a)*ez,
TOTAL = (100+30*blend)*wxMult(wf) with K=1 CAP=0.10.

Writes bt_nights.json + bt_patches.json. Pure stdlib, no network.

Conditions:
  new5   -- the LIVE 2026-08-13 refit basket @ 50/50
  old3   -- the pre-refit .45/.35/.20 basket @ 50/50
  mix75  -- new basket @ 75/25 (the mix backtest_*.py called "shipped" but never was)
  mkt    -- market only (alpha=1.0): the PRICE BENCHMARK the model has to beat
"""
import json, math, glob, re

la_window = lambda la: math.exp(-((la - 25.0) / 14.0) ** 2)
def wxMult(wf):
    return 1.0 if wf is None else max(0.9, min(1.1, 1 + (wf - 1)))

NEW5 = [('_zxpow', .029), ('_zxwcon', .193), ('_zars', .011), ('_zhh', .432), ('_zla', .335)]
OLD3 = [('_zxpow', .45), ('_zxwcon', .35), ('_zars', .20)]
CONDS = {'new5': (NEW5, 0.5), 'old3': (OLD3, 0.5), 'mkt': (OLD3, 1.0), 'mix75': (NEW5, 0.75)}

def ms(vals):
    v = [x for x in vals if x is not None]
    if len(v) < 2: return (0.0, 1.0)
    m = sum(v) / len(v)
    sd = (sum((x - m) ** 2 for x in v) / len(v)) ** 0.5
    return (m, sd or 1e-9)

nights = []
for f in sorted(glob.glob('D_2026-*.json')):
    dt = re.search(r'D_(\d{4}-\d{2}-\d{2})', f).group(1)
    try: D = json.load(open(f))
    except Exception: continue
    P = D.get('players', {})
    if sum(1 for p in P.values() if p.get('_zxpow') is not None) <= 20: continue
    if sum(1 for p in P.values() if p.get('hh') is not None and p.get('la') is not None) <= 20: continue
    if sum(1 for p in P.values() if p.get('_zmkt') is not None) <= 20: continue
    nights.append(dt)

out = {}
for dt in nights:
    D = json.load(open(f'D_{dt}.json'))
    P = D['players']
    for n, p in P.items():
        p['_zhh'] = p.get('hh')
        p['_zla'] = la_window(p['la']) if p.get('la') is not None else None
    out[dt] = {}
    for cond, (SIG, alpha) in CONDS.items():
        st = {k: ms([p.get(k) for p in P.values()]) for k, _ in SIG}
        mkm, mks = ms([p.get('_zmkt') for p in P.values()])
        e0, m0 = {}, {}
        for n, p in P.items():
            e = 0.0
            for k, w in SIG:
                x = p.get(k)
                if x is None: continue
                mu, sd = st[k]; e += w * ((x - mu) / sd)
            e0[n] = e
            xm = p.get('_zmkt')
            m0[n] = ((xm - mkm) / mks) if xm is not None else 0.0
        emu, esd = ms(list(e0.values())); mmu, msd = ms(list(m0.values()))
        patch = {}
        for n, p in P.items():
            ez = (e0[n] - emu) / esd; mz = (m0[n] - mmu) / msd
            bl = alpha * mz + (1 - alpha) * ez
            base = 100 + 30 * bl
            patch[n] = [round(bl, 4), round(base, 1), round(base * wxMult(p.get('wf')), 1)]
        out[dt][cond] = patch

json.dump(nights, open('bt_nights.json', 'w'))
json.dump(out, open('bt_patches.json', 'w'))
print(f'{len(nights)} usable nights {nights[0] if nights else "-"}..{nights[-1] if nights else "-"} x {len(CONDS)} conditions')
