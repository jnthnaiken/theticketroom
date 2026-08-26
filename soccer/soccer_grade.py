#!/usr/bin/env python3
"""soccer_grade.py -- settle one finished soccer board and fold it into the season ledger.
(verbatim copy of the project's soccer/soccer_grade.py -- see that file for the full rationale)"""
import json, io, sys, os


def _dec(am):
    return 1 + am / 100.0 if am > 0 else 1 + 100.0 / abs(am)


def _rrnet(dec, mask, risk):
    K = len(dec)
    s = -risk
    for a in range(K):
        for b in range(a + 1, K):
            if mask[a] and mask[b]:
                s += dec[a] * dec[b]
    for a in range(K):
        for b in range(a + 1, K):
            for c in range(b + 1, K):
                if mask[a] and mask[b] and mask[c]:
                    s += dec[a] * dec[b] * dec[c]
    if K >= 4:
        for a in range(K):
            for b in range(a + 1, K):
                for c in range(b + 1, K):
                    for d in range(c + 1, K):
                        if mask[a] and mask[b] and mask[c] and mask[d]:
                            s += dec[a] * dec[b] * dec[c] * dec[d]
    return s


def grade_ticket(t, players, finals, stake_base=1.0):
    legs = t.get('players') or []
    if not legs:
        return None
    kept = []
    for l in legs:
        p = players.get(l['name'], {})
        hr = bool(p.get('hr'))
        if not hr and (p.get('void') or p.get('out')):
            continue
        kept.append({'odds': l.get('odds'), 'game': l.get('game'), 'hr': hr})
    if not kept:
        return None
    is_final = lambda g: g in finals
    fin = all(x['hr'] or is_final(x['game']) for x in kept)
    cashed = all(x['hr'] for x in kept)
    rr = t.get('rr')
    if rr:
        dec = [_dec(x['odds']) for x in kept]
        risk = rr.get('risk', 2.0)
        still = [x['hr'] or not is_final(x['game']) for x in kept]
        if _rrnet(dec, still, risk) <= 0:
            return {'kind': t['kind'], 'stake': risk, 'net': -risk, 'won': False}
        if not fin:
            return None
        net = _rrnet(dec, [x['hr'] for x in kept], risk)
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
        k = g['kind'] if g['kind'] in season['cats'] else 'family'
        c = season['cats'][k]
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
