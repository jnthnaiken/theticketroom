#!/usr/bin/env python3
"""soccer_unfold.py -- take ONE night back out of soccer_season.json, exactly.

    python3 soccer_unfold.py boards/2026-09-03.json --season soccer_season.json [--dry]

WHY. A settled night is folded once and never revisited -- `graded_nights` is the guard that
makes the settle cron idempotent. That is right for a night that was graded correctly. It is
wrong when the RULE changes underneath it: SUPERSUB-2026-09-04 makes a leg follow the man who
replaced him, and 2026-09-03 was folded the day before under the rule it replaces (Giroud lost;
Ueda, who came on for him, scored the only goal of the match). The owner's call, 2026-09-04, was
to regrade rather than let the night stand wrong on the board's own new terms.

Unfolding by hand is how a ledger quietly stops adding up, so this does it arithmetically and
refuses to guess.

THE SAFETY PROPERTY, and it is the whole point of the file. The night is not unwound by trusting
a number typed in from somewhere. It is unwound by RE-GRADING the archived board with the same
grade_ticket() that folded it, and then checking that total against `history` -- the difference
between the last two history entries is, by construction, what this night contributed. If those
two disagree, the board on disk is no longer the board that was folded and NOTHING is written:
subtracting a number that does not match would corrupt every figure downstream of it, and a
refusal costs one console message.

⚠️ RUN IT BEFORE RE-SETTLING, NEVER AFTER. soccer_settle.js REWRITES the board's `hr` fields
from the live feed. Once it has run under a new rule, the archived board no longer describes the
grades that were folded, the reconciliation above fails (correctly), and the night can no longer
be unwound cleanly. Order is: unfold -> settle -> grade.

WHAT IT DOES NOT TOUCH. `since`, and any other night. `stake`. It appends a line to
`regrades` recording what was taken out and why, on the model of `backout_note` from the
2026-08-26 family retirement -- a ledger that changes silently is not a ledger.
"""
import argparse, io, json, os, sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from soccer_grade import grade_ticket, ZERO


def unfold(dpath, spath, reason, dry=False):
    D = json.load(io.open(dpath, encoding='utf-8'))
    date = D['meta']['date']
    season = json.load(io.open(spath, encoding='utf-8'))

    nights = season.get('graded_nights', [])
    if date not in nights:
        print(f'  {date} is not folded in -- nothing to unwind')
        return season
    if nights[-1] != date:
        # history is a running series; only the last entry can be popped without rewriting
        # every figure after it, and rewriting them is a different, larger job than this.
        sys.exit(f'ABORT: {date} is not the most recently folded night ({nights[-1]} is). '
                 f'Unwinding it would require rebuilding the history series after it.')

    finals = set(D['meta'].get('finals') or [])
    if not finals:
        sys.exit(f'ABORT: {date} has no finals on the archived board; cannot re-derive its grades')

    players, night, rows = D['players'], 0.0, []
    for t in D['tickets']:
        g = grade_ticket(t, players, finals)
        if not g:
            continue
        rows.append((g['kind'], t['name'], g['won'], g['net'], g['stake']))
        night += g['net']

    hist = season.get('history') or []
    if len(hist) < 2:
        sys.exit('ABORT: history too short to carry a night')
    recorded = hist[-1] - hist[-2]
    if abs(recorded - night) > 1e-6:
        sys.exit(f'ABORT: the archived board re-grades to {night:+.4f}u but history recorded '
                 f'{recorded:+.4f}u for {date}. The board on disk is not the board that was '
                 f'folded -- most likely it has already been re-settled. Nothing written.')

    for kind, name, won, net, stake in rows:
        c = season['cats'].setdefault(kind, dict(ZERO))
        c['graded'] -= 1
        c['won'] -= 1 if won else 0
        c['units'] = c['units'] - net
        c['staked'] = c['staked'] - stake
    hist.pop()
    nights.remove(date)
    season.setdefault('regrades', []).append(
        f'{date} unfolded {night:+.3f}u ({len(rows)} tickets, '
        f'{sum(1 for r in rows if r[2])} won) -- {reason}')

    print(f'unfolded {date}: {night:+.3f}u removed, reconciles with history')
    for kind, name, won, net, stake in rows:
        print(f'    {kind:8s} {name[:22]:24s} {"WON " if won else "lost":5s} {net:+7.2f}u')
    print(f'  season back to {hist[-1]:+.3f}u, {len(nights)} nights')

    if dry:
        print('  --dry: nothing written')
        return season
    json.dump(season, io.open(spath, 'w', encoding='utf-8'), indent=1, ensure_ascii=False)
    return season


if __name__ == '__main__':
    ap = argparse.ArgumentParser()
    ap.add_argument('board')
    ap.add_argument('--season', default='soccer_season.json')
    ap.add_argument('--reason', default='rule change')
    ap.add_argument('--dry', action='store_true')
    A = ap.parse_args()
    unfold(A.board, A.season, A.reason, A.dry)
