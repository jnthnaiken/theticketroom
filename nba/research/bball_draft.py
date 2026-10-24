"""BASEBALL-STYLE DRAFT for first basket, backtested (owner 10-23: "build the ticket draft process the exact same
as baseball with the anchors and shit and test it").

Baseball's board (index.html assembleClient / assemble_tickets.py, as of 09-20):
  * pool  = priced, alive bats whose blended z-score >= Z_GATE (0.75) above the slate mean; at most GAME_CAP (4) per game
  * strength = TOTAL (model + market blend) -- decides every role
  * anchors = the 4 strongest in the pool (ANCHORS); each gets a 1u single ("Anchors" / builder)
  * moons   = 2 per anchor: anchor + 3 partners (MOON_LEGS 4), every leg a different game, partners snake-drafted
              from the rest of the pool by strength, each bat used once across moons; full round robin of
              doubles/trebles/four-fold, 11 bets x 0.25u = 2.75u
Not modelled: lunch/nightcap chalk singles and the jackpot (losing / unrelated lines), the 120-min leg window
(no tip times in the price archive).
"""
import itertools, collections, json, math, sys
from rules import days, SEASONS

def rr(legs, unit):
    st = ret = 0.0
    for k in range(2, len(legs) + 1):
        for cb in itertools.combinations(legs, k):
            st += unit
            if all(b['y'] for b in cb):
                m = 1.0
                for b in cb: m *= b['dfd']
                ret += unit * m
    return st, ret

def draft(R, strength='pb', z_gate=0.75, game_cap=4, n_anchors=4, moons_per=2, legs=4, ev_floor=None):
    el = [b for b in R if b['dfd'] and b.get('pb') is not None]
    if len(el) < 8: return [], []
    key = (lambda b: b['pb']) if strength == 'pb' else (lambda b: b['pb'] * b['dfd'])
    v = [key(b) for b in el]; m = sum(v) / len(v); sd = (sum((x - m) ** 2 for x in v) / len(v)) ** .5 or 1e-9
    cand = sorted([b for b in el if (key(b) - m) / sd >= z_gate], key=lambda b: -key(b))
    if ev_floor is not None: cand = [b for b in cand if b['pb'] * b['dfd'] - 1 >= ev_floor]
    pool, per = [], collections.Counter()
    for b in cand:
        if per[b['gid']] >= game_cap: continue
        pool.append(b); per[b['gid']] += 1
    anchors = pool[:n_anchors]
    rest = [b for b in pool if b not in anchors]
    moons = [[a] for a in anchors for _ in range(moons_per)]
    used = set()
    # snake draft: round r goes forward on even rounds, backward on odd
    for r in range(legs - 1):
        order = range(len(moons)) if r % 2 == 0 else reversed(range(len(moons)))
        for i in order:
            mn = moons[i]; games = {x['gid'] for x in mn}
            for b in rest:
                if id(b) in used or b['gid'] in games: continue
                mn.append(b); used.add(id(b)); break
    moons = [mn for mn in moons if len(mn) == legs]
    return anchors, moons

def test(label, **kw):
    res = collections.defaultdict(lambda: {'a_n': 0, 'a_h': 0, 'a_u': 0.0, 'm_n': 0, 'm_c': 0, 'm_st': 0.0, 'm_u': 0.0, 'legs': 0, 'legh': 0})
    for (S, d), R in days.items():
        if S not in SEASONS: continue
        A, Mn = draft(R, **kw); r = res[S]
        for b in A:
            r['a_n'] += 1; r['a_h'] += b['y']; r['a_u'] += (b['dfd'] - 1) if b['y'] else -1
        for mn in Mn:
            st, ret = rr(mn, 0.25); r['m_n'] += 1; r['m_c'] += ret > 0; r['m_st'] += st; r['m_u'] += ret - st
            r['legs'] += len(mn); r['legh'] += sum(b['y'] for b in mn)
    t = {k: sum(v[k] for v in res.values()) for k in res[SEASONS[0]]}
    print(f'{label}')
    print(f'   anchors  n={t["a_n"]:5d} hit={t["a_h"]/max(t["a_n"],1):5.1%} units={t["a_u"]:+8.1f} roi={t["a_u"]/max(t["a_n"],1):+6.1%} | '
          + ' '.join(f'{s%100}:{v["a_u"]:+.0f}' for s, v in sorted(res.items())))
    print(f'   moons    n={t["m_n"]:5d} leg-hit={t["legh"]/max(t["legs"],1):5.1%} cashed={t["m_c"]:4d} staked={t["m_st"]:7.1f} units={t["m_u"]:+8.1f} roi={t["m_u"]/max(t["m_st"],1):+6.1%} | '
          + ' '.join(f'{s%100}:{v["m_u"]:+.0f}' for s, v in sorted(res.items())))
    tot = t['a_u'] + t['m_u']; stk = t['a_n'] + t['m_st']
    print(f'   BOARD    units={tot:+8.1f} on {stk:.0f} staked  roi={tot/max(stk,1):+6.1%} | '
          + ' '.join(f'{s%100}:{v["a_u"]+v["m_u"]:+.0f}' for s, v in sorted(res.items())))

if __name__ == '__main__':
    test('EXACT BASEBALL: strength = chance to score (favorites), z>=.75, 4 anchors x 2 moons x 4 legs')
    test('same, strength = value (chance x price)', strength='ev')
    test('same, favorites but only legs with value (EV>=0)', ev_floor=0.0)
    test('favorites, 3-leg moons', legs=3)
    test('favorites, 1 moon per anchor', moons_per=1)
    test('favorites, no z-gate (all priced starters)', z_gate=-9)
