import json, math, sys, collections, random
sys.path.insert(0, '..')
import kasmodel as K
W = K.load_weights('v1')
EV = json.load(open('../ev_weights_v1.json')); C = EV['coef']; LO, HI = EV.get('lim_clip') or [-4.0, 1.0]
R = [json.loads(l) for l in open('../calibration.jsonl')]
R = [r for r in R if r.get('k_bip') is not None and r.get('odds') and r.get('hr') is not None]
N = collections.defaultdict(list)
for r in R: N[r['date']].append(r)
NIGHTS = sorted(N)
num = lambda x: isinstance(x, (int, float)) and not isinstance(x, bool)
bell = lambda la: math.exp(-((la - 25.0) / 14.0) ** 2)

# league priors from well-sampled bats
def prior(key, f=lambda r, k: r.get(k)):
    v = [f(r, key) for r in R if r['k_bip'] >= 300 and num(f(r, key))]
    return sum(v) / len(v)
dmg_raw = lambda r, _: (r['k_iso'] / r['k_xwobacon']) if num(r.get('k_iso')) and num(r.get('k_xwobacon')) and r['k_xwobacon'] > 0.05 and 0.0 <= r['k_iso'] <= 0.60 else None
MU = {'hh': prior('hh'), 'la': prior('la'), 'fb': prior('k_fb'), 'dmg': prior(None, dmg_raw)}

def cols(r, floor, k):
    """rebuild the four card-rate columns. floor: bats under it get None (slate mean). k: shrink constant (0 = off)."""
    c = {x: r.get(x) for x in W['inputs']}
    n = r['k_bip']
    if n < floor:
        for x in ('c_hh', 'c_la', 'c_fb', 'c_dmg'): c[x] = None
        return c
    s = (lambda v, mu: (n * v + k * mu) / (n + k)) if k else (lambda v, mu: v)
    hh, la, fb, dm = r.get('hh'), r.get('la'), r.get('k_fb'), dmg_raw(r, None)
    c['c_hh'] = s(hh, MU['hh']) if num(hh) else None
    c['c_la'] = bell(s(la, MU['la'])) if num(la) else None
    c['c_fb'] = s(fb, MU['fb']) if num(fb) else None
    # live rule: dmg needs >= 40 BIP unshrunk; with shrink every bat may carry it
    c['c_dmg'] = (s(dm, MU['dmg']) if (k or n >= 40) else None) if num(dm) else None
    return c

def rank_night(rs, floor, k, exclude_under=0):
    rows = [cols(r, floor, k) for r in rs]
    ks = K.score_rows(rows, W)
    m = sum(ks) / len(ks); sd = (sum((x - m) ** 2 for x in ks) / len(ks)) ** .5 or 1e-9
    out = []
    for r, kv in zip(rs, ks):
        if r['k_bip'] < exclude_under: continue
        o = r['odds']; imp = 100 / (o + 100) if o > 0 else -o / (-o + 100)
        L = max(LO, min(HI, math.log(imp / (1 - imp)))); z = (kv - m) / sd
        p = 1 / (1 + math.exp(-(C['b0'] + C['b_lim'] * L + C['b_lim2'] * L * L + C['b_kz'] * z)))
        dec = 1 + o / 100 if o > 0 else 1 + 100 / (-o)
        out.append((p * dec - 1, r, kv, p))
    out.sort(key=lambda t: -t[0])
    return out

def evaluate(floor, k, excl, top=22):
    picks, allp = [], []
    for d in NIGHTS:
        rk = rank_night(N[d], floor, k, excl)
        picks += [(d, t[1]) for t in rk[:top]]
        allp += [(t[3], t[1]['hr'] > 0) for t in rk]
    n = len(picks); h = sum(r['hr'] > 0 for _, r in picks)
    ret = lambda rs: sum(((r['odds'] / 100) if r['odds'] > 0 else 100 / -r['odds']) if r['hr'] > 0 else -1 for _, r in rs) / len(rs)
    # night-block bootstrap
    byd = collections.defaultdict(list)
    for d, r in picks: byd[d].append((d, r))
    random.seed(7); bs = []
    for _ in range(1000):
        s = [x for d in random.choices(NIGHTS, k=len(NIGHTS)) for x in byd[d]]
        bs.append(ret(s))
    bs.sort()
    # log loss of p_model on everyone ranked
    ll = -sum(math.log(p if y else 1 - p) for p, y in allp) / len(allp)
    thin = sum(r['k_bip'] < 80 for _, r in picks)
    return dict(n=n, hr=h / n, roi=ret(picks), lo=bs[50], hi=bs[950], ll=ll, thin_picks=thin)

if __name__ == '__main__':
    print('nights', len(NIGHTS), 'rows', len(R), 'priors', {a: round(b, 3) for a, b in MU.items()})
    # sanity: the no-shrink floor-40 replay should track the logged kas_v1
    d = NIGHTS[-1]; rk = rank_night(N[d], 40, 0)
    import statistics
    pairs = [(t[2], t[1]['kas_v1']) for t in rk if num(t[1].get('kas_v1'))]
    print('replay vs logged kas_v1 corr', round(statistics.correlation([a for a, _ in pairs], [b for _, b in pairs]), 4), 'on', d)
    for top in (22, 30):
        print(f'\n== top-{top} per night by EV')
        for lab, fl, k, ex in [('floor 40 (old)', 40, 0, 0), ('floor 80 (live)', 80, 0, 0), ('floor 80 + exclude <80', 80, 0, 80)] + \
                [(f'shrink k={k}', 0, k, 0) for k in (25, 50, 75, 100, 150, 250, 400)] + \
                [(f'shrink k={k} + floor 40', 40, k, 0) for k in (50, 100, 150)]:
            e = evaluate(fl, k, ex, top)
            print(f"  {lab:26s} HR {e['hr']:.1%}  ROI {e['roi']:+.1%} [{e['lo']:+.0%},{e['hi']:+.0%}]  logloss {e['ll']:.4f}  picks<80bip {e['thin_picks']}")
