#!/usr/bin/env python3
"""nba_kotc.py -- KOTC-2026-10-27. DraftKings' King of the Court: on NBA Tuesdays (and opening night), whoever picks the
player with the most points + rebounds + assists of the night splits a bonus-bet pool. Owner: "we need to look at king
of the court on dk" -> "both should be counted towards the ledger. you still have to bet on them to activate the promo".

So the board posts ONE 1u bet a King of the Court night: the crowned player's PRA over at the main line (median across
books; FanDuel's when it has one). It is the qualifying bet, graded like any single; the bonus-bet share is not counted.

THE CROWN. Each priced player's PRA ~ Normal(mean, sd): mean backed out of the main line and the de-vigged over chance,
sd = SD_A x mean + SD_B. 50,000 simulated nights -> P(top PRA). Popularity = mean^POP_K / sum (the public takes the
biggest stat lines). value = P(top) / popularity; the crown goes to the best value among the five likeliest -- the same
rule as King of the End Zone.
"""
import math, random

SD_A, SD_B = 0.20, 2.5     # v1; KOTCCAL replaces these with a fit on 2025-26 box scores
POP_K = 4.0
N_SIM = 50000
OPENERS = {'2026-10-21'}   # opening night ran King of the Court on a Wednesday ($5M)


def is_night(date):
    import datetime
    return date in OPENERS or datetime.date.fromisoformat(date).weekday() == 1   # Tuesday


def ninv(p):
    p = min(0.98, max(0.02, p))
    # Acklam's rational approximation is overkill here; erfinv via numpy is exact enough
    from math import sqrt
    return sqrt(2) * _erfinv(2 * p - 1)


def _erfinv(y):
    a = 0.147
    ln = math.log(1 - y * y)
    t = 2 / (math.pi * a) + ln / 2
    return math.copysign(math.sqrt(math.sqrt(t * t - ln / a) - t), y)


def crown(rows, seed=20261027):
    """rows: [{'name','team','line','pover',...}] -> same rows sorted by P(top), each with mean, sd, p, pop, value;
    exactly one carries crown=True (best value among the five likeliest)."""
    L = [dict(r) for r in rows if r.get('line') and r.get('pover') is not None]
    if not L:
        return []
    for r in L:
        sd0 = SD_A * r['line'] + SD_B
        r['mean'] = r['line'] + sd0 * ninv(r['pover'])
        r['sd'] = SD_A * r['mean'] + SD_B
    rng = random.Random(seed)                     # plain Python: the build runner has no numpy
    win = [0] * len(L); ms = [r['mean'] for r in L]; ss = [r['sd'] for r in L]; n = len(L)
    for _ in range(N_SIM):
        bi, bv = 0, -1e9
        for i in range(n):
            v = ms[i] + ss[i] * rng.gauss(0.0, 1.0)
            if v > bv: bv, bi = v, i
        win[bi] += 1
    pw = [x ** POP_K for x in ms]; tot = sum(pw)
    for i, r in enumerate(L):
        r['p'] = round(win[i] / N_SIM, 4); r['pop'] = round(pw[i] / tot, 4)
        r['value'] = round(r['p'] / r['pop'], 3) if r['pop'] > 0 else 0.0
        r['mean'] = round(r['mean'], 1); r['sd'] = round(r['sd'], 1)
    L.sort(key=lambda r: -r['p'])
    best = max(L[:5], key=lambda r: r['value'])
    for r in L: r['crown'] = r is best
    return L


def grade(pick):
    """-> 'win' | 'loss' | 'void' | None. PRA only grows, so the over is won the moment he passes the line."""
    if pick.get('dnp'): return 'void'
    v = pick.get('pra')
    if v is None: return None
    if v > pick['line']: return 'win'
    return 'loss' if pick.get('final') else None
