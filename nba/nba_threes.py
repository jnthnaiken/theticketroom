#!/usr/bin/env python3
"""nba_threes.py -- DOWNTOWN-2026-10-26. Player threes made: the model state, tonight's picks, and grading.

Owner, after the research (claude/nba-threes-research-2026-10-26.md): "add min and role changes" -> "yes and yes"
(build it; save FanDuel's ladder prices) -> section name "Downtown".

THE RULE (chosen on 2023-24, positive in 2024-25 +15.7u and 2025-26 +33.3u at FanDuel prices):
  FanDuel main-line OVER on a player's threes made, EV = p * decimal - 1 >= 0.20, one per game, max 5 a night, 1u.
  Posted for a game only once BOTH starting fives are confirmed (starting tonight is one of the model's signals).
  A posted pick never moves. DNP -> void (FanDuel refunds).

THE MODEL (identical to nba/research/threes/analyze.py variant 'role'; that file's walk-forward loop is the spec):
  mu = att * pct * opp^BETA * exp(A1*log((mS+1)/(mL+1)) + A2*(started - srate) + A3*missing_share)
    att   his 3PA per game played, EWMA half-life 10 games
    pct   decayed 3PM/3PA (half-life 40 games) shrunk to the league rate with 150 phantom attempts
    opp   opponent's threes allowed per game / league (half-life 15 games), shrunk toward 1 by games seen (n/(n+10))
    mS/mL his minutes, EWMA half-lives 5 and 20 games; srate start rate (half-life 10); started = in tonight's five
    missing_share  share of his team's 3PA volume carried by regulars (>= 12 min, played in one of the team's last 3)
                   who are out tonight
  X ~ negative binomial(mu, R); P(over L) = P(X >= floor(L) + 1)
State is keyed by NBA personId (nba.com box scores and the 2014-26 play-by-play share the ids); `names` maps id -> name.
"""
import json, math, re, unicodedata

HL_ATT, HL_PCT, HL_OPP, K_PCT = 10, 40, 15, 150.0
BETA, A1, A2, A3, R = 0.67, 0.46, 0.33, 0.13, 9.6          # fitted on 2023-24 (research run 2026-10-26)
EV_MIN, MAX_NIGHT = 0.20, 5
# DTUNDER-2026-10-26. Owner: "lets do the same thing for downtown. theres no way what we have is the best way" -> rule
# search (17,908 rules, chosen on 2023-24, judged on 2024-26): overs stay as they are; ADD unders. FanDuel main-line
# under, line >= 1.5, P(under) >= 0.50, EV >= 0.10, best 5 a night (any game), 1u, never the same man as an over.
# Backtest 2023-26: unders +172.4u (+9.1%), with the overs +228.9u vs +56.5u, worst slump 21.1u, every season up.
# DTUNCAP-2026-10-26. Owner: "is 5 tickets the best? why are we capping ourselves?" -- no: the search's best-on-train
# under rule was EV >= 0.05 with NO nightly cap (train +107.5u, unseen 2024-26 +161u); with the overs +325u, worst slump 25.7u.
U_EV_MIN, U_P_MIN, U_LINE_MIN, U_MAX_NIGHT = 0.05, 0.50, 1.5, 99
FANDUEL = 10
_d = lambda h: 0.5 ** (1.0 / h)
LA, LB, LP = _d(HL_ATT), _d(HL_PCT), _d(HL_OPP)
LS, LL, LR = _d(5), _d(20), _d(10)


def norm(s):
    s = unicodedata.normalize('NFKD', str(s or '')).encode('ascii', 'ignore').decode().lower()
    s = re.sub(r"[.'’\-]", ' ', s)
    return ' '.join(w for w in s.split() if w not in ('jr', 'sr', 'ii', 'iii', 'iv'))


class State:
    def __init__(self, d=None):
        d = d or {}
        self.pl = d.get('pl', {})            # pid -> {a,w,pm,pa,n, mS,wS,mL,wL, sr,ws, team, tg}
        self.oa = d.get('oa', {})            # team -> {all, w, n}
        self.lg = d.get('lg', {'all': 0.0, 'w': 0.0, 'm': 0.0, 'a': 0.0})
        self.tg = d.get('tg', {})            # team -> games played
        self.names = d.get('names', {})      # pid -> name
        self.meta = d.get('meta', {'through': None})

    def dump(self):
        return dict(pl=self.pl, oa=self.oa, lg=self.lg, tg=self.tg, names=self.names, meta=self.meta)

    def pid_of(self, name, team=None):
        n = norm(name)
        hits = [p for p, nm in self.names.items() if norm(nm) == n]
        if len(hits) > 1 and team: hits = [p for p in hits if (self.pl.get(p) or {}).get('team') == team] or hits
        if len(hits) == 1: return hits[0]
        sur, ini = (n.split() or [''])[-1], n[:1]
        hits = [p for p, nm in self.names.items() if norm(nm).split()[-1:] == [sur] and norm(nm)[:1] == ini
                and (team is None or (self.pl.get(p) or {}).get('team') == team)]
        return hits[0] if len(hits) == 1 else None

    def regulars(self, team):
        out = []
        for pid, q in self.pl.items():
            if q.get('team') != team or not q.get('wS'): continue
            if q['mS'] / q['wS'] < 12 or self.tg.get(team, 0) - q.get('tg', -99) > 3: continue
            out.append(pid)
        return out

    def att(self, pid):
        q = self.pl.get(pid) or {}
        return q['a'] / q['w'] if q.get('w') else 0.0

    def features(self, pid, opp, started, missing_share):
        q = self.pl.get(pid)
        if not q or q.get('n', 0) < 3: return None
        lp3 = (self.lg['m'] / self.lg['a']) if self.lg.get('a', 0) > 50 else 0.36
        att = q['a'] / q['w']
        pct = (q['pm'] + K_PCT * lp3) / (q['pa'] + K_PCT)
        t = self.oa.get(opp)
        ft = 1.0
        if t and t['w'] > 0 and self.lg['w'] > 0:
            ft = (t['all'] / t['w']) / (self.lg['all'] / self.lg['w'])
            ft = 1 + (ft - 1) * t['n'] / (t['n'] + 10)
        mS = q['mS'] / q['wS'] if q.get('wS') else 0.0
        mL = q['mL'] / q['wL'] if q.get('wL') else mS
        srate = q['sr'] / q['ws'] if q.get('ws') else 0.0
        return dict(att=att, pct=pct, ft=ft, mS=mS, mL=mL, srate=srate, started=float(started), msh=missing_share)

    def update_day(self, rows):
        """rows: one dict per player-game of ONE date: pid, name, team, opp, gid, tpa, tpm, mins, started (bool).
        Same order of operations as the research loop: players, league, then opponents, then team game counts."""
        for r in rows:
            pid = str(r['pid'])
            q = self.pl.setdefault(pid, dict(a=0.0, w=0.0, pm=0.0, pa=0.0, n=0, mS=0.0, wS=0.0, mL=0.0, wL=0.0,
                                             sr=0.0, ws=0.0, team=None, tg=-99))
            q['a'] = q['a'] * LA + r['tpa']; q['w'] = q['w'] * LA + 1
            q['pm'] = q['pm'] * LB + r['tpm']; q['pa'] = q['pa'] * LB + r['tpa']; q['n'] += 1
            q['mS'] = q['mS'] * LS + r['mins']; q['wS'] = q['wS'] * LS + 1
            q['mL'] = q['mL'] * LL + r['mins']; q['wL'] = q['wL'] * LL + 1
            q['sr'] = q['sr'] * LR + float(r['started']); q['ws'] = q['ws'] * LR + 1
            q['team'] = r['team']; q['tg'] = self.tg.get(r['team'], 0) + 1
            self.lg['m'] = self.lg.get('m', 0.0) * 0.9995 + r['tpm']; self.lg['a'] = self.lg.get('a', 0.0) * 0.9995 + r['tpa']
            if r.get('name'): self.names[pid] = r['name']
        games = {}
        for r in rows: games.setdefault((r['gid'], r['opp']), 0.0); games[(r['gid'], r['opp'])] += r['tpm']
        for (gid, opp), made in games.items():
            t = self.oa.setdefault(opp, {'all': 0.0, 'w': 0.0, 'n': 0})
            t['all'] = t['all'] * LP + made; t['w'] = t['w'] * LP + 1; t['n'] += 1
        for t_ in {r['team'] for r in rows}: self.tg[t_] = self.tg.get(t_, 0) + 1
        self.lg['all'] = self.lg.get('all', 0.0) * 0.999 + sum(r['tpm'] for r in rows)
        self.lg['w'] = self.lg.get('w', 0.0) * 0.999 + len(games)


def _nb_logpmf(k, mu, r):
    return math.lgamma(k + r) - math.lgamma(r) - math.lgamma(k + 1) + r * math.log(r / (r + mu)) + k * math.log(mu / (r + mu))


def mu_of(f):
    base = f['att'] * f['pct']
    lm = math.log(min(max((f['mS'] + 1) / (f['mL'] + 1), 0.2), 5))
    x = A1 * lm + A2 * (f['started'] - f['srate']) + A3 * f['msh']
    return max(base * (min(max(f['ft'], 0.3), 3) ** BETA) * math.exp(min(max(x, -2), 2)), 0.02)


def p_over(f, line):
    kmin = int(math.floor(line + 0.5))
    mu = mu_of(f)
    cdf = sum(math.exp(_nb_logpmf(k, mu, R)) for k in range(kmin))
    return min(max(1 - cdf, 1e-6), 1 - 1e-6), mu


def dec(am):
    am = float(am)
    return 1 + am / 100 if am > 0 else 1 + 100 / abs(am)


def grade(pick):
    """-> 'win' | 'loss' | 'void' | None (pending)"""
    if pick.get('dnp'): return 'void'
    m = pick.get('made')
    if m is None: return None
    if pick.get('side') == 'U':          # DTUNDER: an under dies the moment he reaches the number, cashes at the final
        if m >= pick['kmin']: return 'loss'
        return 'win' if pick.get('final') else None
    if m >= pick['kmin']: return 'win'
    return 'loss' if pick.get('final') else None


# Owner: "use like funky jazz names like semi-pro the movie with will ferrell vibes for the ticket names too" (the
# Flint Tropics' "Downtown" is what put the section name in his head). Original names in that '70s-ABA spirit.
DT_NAMES = ['Velvet Afro Jumper', 'Eight-Track Heater', 'Lava Lamp Lefty', 'Shag Carpet Swish', 'Bell-Bottom Bomb',
            'Mirror Ball Moonball', 'Polyester Splash', 'Platform Shoe Pull-Up', 'Roller Rink Rainbow', 'Groove Tube',
            'Sugar Shack Shooter', 'Cosmic Corner Three', 'Funk Factory', 'Butterscotch Bomb', 'Boom Box Bucket',
            'Afro Pick Pull-Up', 'Saturday Night Splash', 'Disco Ball Dagger', 'Wah-Wah Wing Three', 'Leisure Suit Launch',
            'Velour Tracksuit Trey', 'Strobe Light Swish', 'Hot Tub Heat Check', 'Mood Ring Moonshot', 'Gold Chain Gunner',
            'Sideburn Sniper', 'Smooth Groove Rainmaker', 'Pinball Wizard Pull-Up', 'Satin Shorts Shooter', 'Lava Flow Lob Three']


def pick_name(date, i):
    import datetime as _dt
    doy = _dt.date.fromisoformat(date).timetuple().tm_yday
    return DT_NAMES[(doy * 7 + i) % len(DT_NAMES)]
