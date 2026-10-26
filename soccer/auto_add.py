#!/usr/bin/env python3
"""FDSOCCER-2026-10-26: add-only merge for a frozen auto slate.

    python3 auto_add.py soccer/slates/<date> .auto

A match with no goalscorer rows in the committed ags.psv, that the fresh fetch (.auto) did price and that kicks off
30+ minutes from now, has its rows APPENDED to ags.psv / fgs.psv in .auto. Committed rows are never changed, so
PRICEONCE keeps every price already on the board. Touches .auto/ADDED when something was added.
"""
import json, os, sys, time
S, A = sys.argv[1:3]
fx = json.load(open(os.path.join(S, 'fixtures.json')))
base = time.mktime(time.strptime(fx['date'], '%Y-%m-%d')) - time.timezone
def rows(p):
    try: return [l for l in open(p, encoding='utf-8').read().splitlines() if l.strip()]
    except FileNotFoundError: return []
added = []
for f in ('ags.psv', 'fgs.psv'):
    old, new = rows(os.path.join(S, f)), rows(os.path.join(A, f))
    have = {l.split('|')[0] for l in old}
    ok = set()
    for slug, m in fx['matches'].items():
        if slug not in have and base + m['kickoff'] * 60 - time.time() > 1800: ok.add(slug)
    add = [l for l in new if l.split('|')[0] in ok]
    if f == 'ags.psv': added = sorted({l.split('|')[0] for l in add})
    with open(os.path.join(A, f), 'w', encoding='utf-8') as fh: fh.write('\n'.join(old + add) + ('\n' if old or add else ''))
    print(f'auto_add {f}: {len(old)} kept, {len(add)} added')
if added:
    open(os.path.join(A, 'ADDED'), 'w').write('\n'.join(added) + '\n'); print('added matches:', ', '.join(added))
else:
    print('nothing new to add')
