"""FBL-REBUILD feature replay. FirstBasketLand's four stat families rebuilt from PBP, strictly pre-game, for every
starter of every 2014-25 regular-season game, in fbr/games2.json order (so rows line up with fbr/X.npy):
  T  opening tips      -- predicted jumper, career tip win %, head-to-head vs tonight's jumper, team tip %
  M  first basket methods -- first-basket / first-team-basket rate per start (career, season, recent),
                           share of team makes, how he scores (rim / three / FT share)
  P  positional matchups -- role (big / wing / guard from shot mix) x what the opponent allows to that role
  F  first 3 minutes   -- points in the first 3:00 per start, share of team's early points, team & opponent early pace
Windows: career (shrunk counts), season-to-date (shrunk), recent (EWMA, half-life 8 starts)."""
import json, math, sys, collections
import numpy as np
G = json.load(open('/home/claude/fbr/games2.json'))
X = json.load(open('extra.json')); NM = {int(k): v for k, v in json.load(open('pidnames.json')).items()}
A8 = 1 - 0.5 ** (1 / 8.0)

def lg(x): return math.log(max(min(x, 0.98), 0.005))
def sh(k, n, p0, w): return (k + p0 * w) / (n + w)        # shrunk rate

class Acc(dict):
    """career / season / recent accumulators for a rate k/n"""
    def add(self, key, k, n, season):
        c = self.setdefault(key, [0.0, 0.0, None, 0.0, 0.0, 0.0, 0.0])
        if c[2] != season: c[2], c[3], c[4] = season, 0.0, 0.0
        c[0] += k; c[1] += n; c[3] += k; c[4] += n
        c[5] = c[5] * (1 - A8) + k; c[6] = c[6] * (1 - A8) + n
    def get(self, key, season, p0, w=10):
        c = self.get_(key)
        if not c: return (p0, p0, p0, 0.0)
        s3, s4 = (c[3], c[4]) if c[2] == season else (0.0, 0.0)
        return (sh(c[0], c[1], p0, w), sh(s3, s4, p0, w), sh(c[5], c[6], p0, w / 2), c[1])
    get_ = dict.get

P = Acc(); T = Acc(); J = Acc(); H2H = collections.Counter(); ROLE = {}
OPP = Acc()          # (team, role) -> first-team-baskets allowed to that role
NAMES = []
rows, meta = [], []

def role_of(n):
    r = ROLE.get(n)
    if not r or r['m'] < 15: return 'wing'
    rim = (r['dunk'] + r['layup'] + r['hook']) / r['m']; thr = r['three'] / r['m']
    if rim >= 0.55 or r['jump'] >= 5: return 'big'
    if thr >= 0.40 and r['ast'] >= r['m'] * 0.25: return 'guard'
    return 'wing' if thr >= 0.25 else 'guard'

for gi, g in enumerate(G):
    H, V, season = g['H'], g['V'], g['season']
    st = {Tm: g['starters'][Tm] for Tm in (H, V)}
    ex = X.get(str(g['gid']), {})
    # ---------------- pre-game features ----------------
    jr = {n: P.get(('jump', n), season, 0.0, 2)[0] for Tm in (H, V) for n in st[Tm]}
    Jp = {Tm: max(st[Tm], key=lambda n: jr[n]) for Tm in (H, V)}
    tipw = {Tm: J.get(('tw', Jp[Tm]), season, 0.5, 10)[0] for Tm in (H, V)}
    h2h_h = H2H[(Jp[H], Jp[V])]; h2h_v = H2H[(Jp[V], Jp[H])]
    ttip = {Tm: T.get(('tip', Tm), season, 0.5, 10)[1] for Tm in (H, V)}
    feats = []
    for Tm in (H, V):
        O = V if Tm == H else H
        tipd = lg(tipw[Tm]) - lg(tipw[O]); h2h = ((h2h_h - h2h_v) if Tm == H else (h2h_v - h2h_h)) / (h2h_h + h2h_v + 2)
        tsf = T.get(('first', Tm), season, 0.5, 10); oaf = T.get(('allow', O), season, 0.5, 10)
        tf3 = T.get(('f3', Tm), season, 0.0, 1); of3 = T.get(('f3a', O), season, 0.0, 1)
        for n in st[Tm]:
            fb = P.get(('fb', n), season, 0.1, 20); tfb = P.get(('tfb', n), season, 0.2, 10)
            shm = P.get(('shm', n), season, 0.2, 3); sc3 = P.get(('s3', n), season, 0.3, 5)
            p3 = P.get(('p3', n), season, 0.6, 5); sh3 = P.get(('sh3', n), season, 0.2, 3)
            r = ROLE.get(n) or {}; m = r.get('m', 0)
            rim = (r.get('dunk', 0) + r.get('layup', 0) + r.get('hook', 0) + 2) / (m + 5)
            thr = (r.get('three', 0) + 1) / (m + 5); ftr = (r.get('ft', 0) + 1) / (m + r.get('ft', 0) + 5)
            rl = role_of(n)
            oppr = OPP.get((O, rl), season, 0.2, 10)
            lgr = OPP.get(('LG', rl), season, 0.2, 10)
            feats.append([
                1.0 if n == Jp[Tm] else 0.0, tipd, h2h, lg(ttip[Tm]) - lg(ttip[O]),                       # T
                lg(fb[0]), lg(fb[1]), lg(fb[2]), lg(tfb[0]), lg(tfb[1]), lg(tfb[2]),                      # M rates
                lg(shm[1]), lg(shm[2]), rim - .45, thr - .3, ftr - .2, 1.0 if fb[3] < 10 else 0.0,        # M mix
                lg(oppr[1]) - lg(lgr[1]), lg(oppr[2]) - lg(lgr[2]),                                       # P
                1.0 if rl == 'big' else 0.0, 1.0 if rl == 'guard' else 0.0,
                lg(sc3[1]), lg(sc3[2]), math.log(1 + p3[2]), lg(sh3[1]), lg(sh3[2]),                      # F player
                tf3[1] - of3[1] if False else (tf3[2] + of3[2]) / 2 - 1.0,                                # F team pace
                lg(tsf[1]) - lg(oaf[1]) if False else tsf[1] - oaf[1],                                     # team first
            ])
    names10 = st[H] + st[V]
    y = names10.index(g['fb']) if g['fb'] in names10 else -1
    rows.append(feats); meta.append({'gid': g['gid'], 'season': g['season'], 'names': names10, 'y': y})
    # ---------------- update ----------------
    jm, tip = g.get('jumpers'), g.get('tip')
    for Tm in (H, V):
        for n in st[Tm]: P.add(('jump', n), 1.0 if (jm and n in jm) else 0.0, 1, season)
    if jm and jm[0] and jm[1] and tip in (H, V):
        hw = 1.0 if tip == H else 0.0
        J.add(('tw', jm[0]), hw, 1, season); J.add(('tw', jm[1]), 1 - hw, 1, season)
        H2H[(jm[0], jm[1]) if hw else (jm[1], jm[0])] += 1
        T.add(('tip', H), hw, 1, season); T.add(('tip', V), 1 - hw, 1, season)
    made = {NM.get(int(k), None): v for k, v in ex.get('made', {}).items()}
    ftm = {NM.get(int(k), None): v for k, v in ex.get('ftm', {}).items()}
    f3 = {NM.get(int(k), None): v for k, v in ex.get('f3', {}).items()}
    tfb = {t: NM.get(int(p)) for t, p in ex.get('tfb', {}).items()}
    for Tm in (H, V):
        O = V if Tm == H else H
        T.add(('first', Tm), 1.0 if g.get('fbT') == Tm else 0.0, 1, season)
        T.add(('allow', O), 1.0 if g.get('fbT') == Tm else 0.0, 1, season)
        tpts3 = sum(v for n, v in f3.items() if g['team_of'].get(n) == Tm)
        T.add(('f3', Tm), tpts3, 1, season); T.add(('f3a', O), tpts3, 1, season)
        tmade = sum(sum(v.values()) for n, v in made.items() if g['team_of'].get(n) == Tm)
        tb = tfb.get(Tm)
        if tb:
            rl = role_of(tb)
            for r_ in ('big', 'wing', 'guard'):
                OPP.add((O, r_), 1.0 if rl == r_ else 0.0, 1, season); OPP.add(('LG', r_), 1.0 if rl == r_ else 0.0, 1, season)
        ast = collections.Counter(s[6] for s in g['shots'] if s[6])
        for n in st[Tm]:
            P.add(('fb', n), 1.0 if g.get('fb') == n else 0.0, 1, season)
            P.add(('tfb', n), 1.0 if tb == n else 0.0, 1, season)
            mv = made.get(n, {}); mm = sum(mv.values())
            if tmade: P.add(('shm', n), mm, tmade, season)
            P.add(('s3', n), 1.0 if f3.get(n) else 0.0, 1, season)
            P.add(('p3', n), float(f3.get(n, 0)), 1, season)
            if tpts3: P.add(('sh3', n), f3.get(n, 0), tpts3, season)
            r = ROLE.setdefault(n, collections.Counter())
            for k_, v_ in mv.items(): r[k_] += v_
            r['m'] += mm; r['ft'] += ftm.get(n, 0); r['ast'] += ast.get(n, 0)
            if jm and n in jm: r['jump'] += 1
NAMES = ['t_isj', 't_tipd', 't_h2h', 't_team',
         'm_fb_car', 'm_fb_sea', 'm_fb_rec', 'm_tfb_car', 'm_tfb_sea', 'm_tfb_rec',
         'm_shm_sea', 'm_shm_rec', 'm_rim', 'm_three', 'm_ftr', 'm_new',
         'p_opp_sea', 'p_opp_rec', 'p_big', 'p_guard',
         'f_sc3_sea', 'f_sc3_rec', 'f_p3_rec', 'f_sh3_sea', 'f_sh3_rec', 'f_pace', 'f_tfirst']
A = np.array(rows, dtype=np.float32); print(A.shape, len(NAMES))
np.save('X3.npy', A); json.dump({'games': meta, 'names': NAMES}, open('meta3.json', 'w'))
