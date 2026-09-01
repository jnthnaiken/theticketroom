#!/usr/bin/env python3
"""soccer_grade.py -- settle one finished soccer board and fold it into the season ledger.
(verbatim copy of the project's soccer/soccer_grade.py -- see that file for the full rationale)"""
import json, io, sys, os


def _dec(am):
    return 1 + am / 100.0 if am > 0 else 1 + 100.0 / abs(am)


def _combos(L):
    """Every parlay a 'by 2s & 3' round robin places over L legs (plus the 4-fold when the slip is
    that wide). Enumerated over the ORIGINAL leg count, because that is what the stake was split
    across at placement -- a leg voiding hours later cannot change the denominator."""
    import itertools
    sizes = [2, 3] + ([4] if L >= 4 else [])
    return [c for z in sizes if L >= z for c in itertools.combinations(range(L), z)]


def _rrnet(dec, state, mask, risk):
    """RRVOID-2026-09-01 -- A VOID LEG REDUCES ITS PARLAYS. IT DOES NOT MOVE MONEY ONTO THE SURVIVORS.

    What this replaced took only the SURVIVING legs and re-derived the whole round robin over them,
    so `ncombo` shrank while `risk` did not:
      * ONE void on a 3-leg 2u moon put the full 2u on the single remaining double -- four times the
        0.5u actually placed.
      * TWO voids left ncombo at 0, unit at 0.0, and returned -risk unconditionally, so a slip whose
        one surviving leg scored was booked as a full loss, and booked by the still-alive check
        BEFORE that leg's match was final.
    Worked example (-138/+350/+260 at 2u, the real 'From Distance' slip):
        one void, both survivors score    +13.52 booked  ->   +8.87 real
        two voids, survivor scores         -2.00 booked  ->   +1.09 real

    The book settles by REDUCTION: a void leg drops out of every parlay it is on and that parlay pays
    on what is left; a parlay whose every leg voided refunds its own stake. `state` is 'h'/'m'/'v'
    per ORIGINAL leg; `mask` says which legs count as winners for this evaluation.
    A slip with no void leg is arithmetically identical to the RRSTAKE-2026-08-28 loop this replaces.
    Keep in lockstep with grade_night.py grade_ticket() and rrnet() in index.html."""
    L = len(state)
    cs = _combos(L)
    if not cs:
        return 0.0
    unit = risk / len(cs)
    ret = 0.0
    for combo in cs:
        live = [i for i in combo if state[i] != 'v']
        if not live:
            ret += 1.0                                  # every leg on this parlay voided -> stake back
        elif all(mask[i] for i in live):
            p = 1.0
            for i in live:
                p *= dec[i]
            ret += p
    return unit * ret - risk


def _ncombo(K):
    """Combinations a 'by 2s & 3' round robin actually places (plus 4s when the slip is that
    wide) -- the denominator the total risk is split across."""
    import math
    sizes = [2, 3] + ([4] if K >= 4 else [])
    return sum(math.comb(K, z) for z in sizes if K >= z)


def grade_ticket(t, players, finals, stake_base=1.0):
    legs = t.get('players') or []
    if not legs:
        return None
    state, decs, kept = [], [], []
    for l in legs:
        p = players.get(l['name'], {})
        hr = bool(p.get('hr'))
        if l.get('odds') in (None, 0):
            # NULLPRICE-2026-08-22, ported from grade_night.py. A leg minted with no price is not a
            # wager, and _dec(None) raises TypeError -- which here would take the whole settle run
            # down and leave the night ungraded. Void it, the same refund a scratched leg takes.
            print(f"  ::warning::void leg with no price: {t.get('name')} / {l.get('name')}")
            state.append('v'); decs.append(1.0); continue
        if not hr and (p.get('void') or p.get('out')):
            state.append('v'); decs.append(_dec(l['odds'])); continue
        state.append('h' if hr else 'm'); decs.append(_dec(l['odds']))
        kept.append({'odds': l.get('odds'), 'game': l.get('game'), 'hr': hr})
    if not kept:
        return None
    is_final = lambda g: g in finals
    fin = all(x['hr'] or is_final(x['game']) for x in kept)
    cashed = all(x['hr'] for x in kept)
    rr = t.get('rr')
    if rr:
        risk = rr.get('risk', 2.0)
        hit = [s == 'h' for s in state]
        still = [hit[i] or (state[i] != 'v' and not is_final(legs[i].get('game')))
                 for i in range(len(state))]
        # A dead slip settles at what it actually returns, NOT at a flat -risk: under reduction it
        # can still owe the refund from its all-void combinations. The flat -risk was also what made
        # this file disagree with a partially-cashing round robin on the board.
        if _rrnet(decs, state, still, risk) <= 0:
            net = _rrnet(decs, state, hit, risk)
            return {'kind': t['kind'], 'stake': risk, 'net': net, 'won': False}
        if not fin:
            return None
        net = _rrnet(decs, state, hit, risk)
        return {'kind': t['kind'], 'stake': risk, 'net': net, 'won': net > 0}
    if not cashed and not fin:
        return None
    voided = len(kept) != len(legs)
    p10 = t['payout10'] if (t.get('payout10') and not voided) else \
        10 * _prod(_dec(x['odds']) for x in kept)
    if cashed:
        return {'kind': t['kind'], 'stake': stake_base,
                'net': stake_base * (p10 / 10 - 1), 'won': True}
    return {'kind': t['kind'], 'stake': stake_base, 'net': -stake_base, 'won': False}


def _prod(it):
    m = 1.0
    for x in it:
        m *= x
    return m


ZERO = {'graded': 0, 'won': 0, 'units': 0.0, 'staked': 0.0}
KINDS = ('lunch', 'late', 'builder', 'moon', 'family')


def fold(dpath, spath):
    D = json.load(io.open(dpath, encoding='utf-8'))
    date = D['meta']['date']
    season = (json.load(io.open(spath, encoding='utf-8')) if os.path.exists(spath)
              else {'since': date, 'history': [0], 'graded_nights': [],
                    'cats': {k: dict(ZERO) for k in KINDS}, 'stake': 1})
    if date in season.get('graded_nights', []):
        print(f'  {date} already folded in -- nothing to do')
        return season
    finals = set(D['meta'].get('finals') or [])
    if not finals:
        print(f'  {date} has no finals; nothing settled, not folding')
        return season
    players = D['players']
    night, rows = 0.0, []
    for t in D['tickets']:
        g = grade_ticket(t, players, finals)
        if not g:
            rows.append((t['kind'], t['name'], 'not settled / void', 0.0))
            continue
        # BACKOUT-2026-08-26: `family` was retired and BACKED OUT of soccer_season.json, so
        # cats no longer has that key -- and this line used it as the catch-all bucket for an
        # unrecognised kind. `season['cats'][k]` would then KeyError and take the whole nightly
        # fold down, silently leaving the night ungraded, which is the exact failure the settle
        # workflow exists to prevent. setdefault creates the bucket instead of crashing; an
        # unexpected kind now shows up in the ledger as itself, which is also more honest than
        # burying it under someone else's name.
        k = g['kind']
        c = season['cats'].setdefault(k, dict(ZERO))
        c['graded'] += 1
        c['won'] += 1 if g['won'] else 0
        c['units'] = c['units'] + g['net']
        c['staked'] = c['staked'] + g['stake']
        night += g['net']
        rows.append((t['kind'], t['name'], 'WON ' if g['won'] else 'lost', g['net']))
    season['history'].append((season['history'][-1] if season['history'] else 0) + night)
    season.setdefault('graded_nights', []).append(date)
    season['since'] = min(season.get('since', date), date)
    json.dump(season, io.open(spath, 'w', encoding='utf-8'), indent=1, ensure_ascii=False)
    print(f'graded {date}: {night:+.2f}u')
    for k, n, r, u in rows:
        print(f'    {k:8s} {n:20s} {r:18s} {u:+7.2f}u')
    tot = sum(c['units'] for c in season['cats'].values())
    st = sum(c['staked'] for c in season['cats'].values())
    gr = sum(c['graded'] for c in season['cats'].values())
    wn = sum(c['won'] for c in season['cats'].values())
    print(f'  season now {wn}-{gr-wn}  {tot:+.2f}u on {st:.1f}u staked  since {season["since"]}')
    return season


if __name__ == '__main__':
    args = [a for a in sys.argv[1:] if not a.startswith('--')]
    if not args:
        sys.exit('usage: soccer_grade.py <D.json> [--season PATH]')
    sp = sys.argv[sys.argv.index('--season') + 1] if '--season' in sys.argv \
        else os.path.join(os.path.dirname(os.path.abspath(args[0])) or '.', 'soccer_season.json')
    fold(args[0], sp)
