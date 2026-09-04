#!/usr/bin/env python3
"""
nfl_sig.py -- the commit-gate signature for a football board.

⚠️ THIS HASHES THE SCORES, NOT JUST THE NAMES, AND THAT IS THE WHOLE POINT.
soccer-build.yml gates on "the DRAFT and the PLAYERS". On 2026-09-03 a corrected xg.psv moved
every TOTAL on the live soccer board while the four ticket names stayed identical -- the gate
called that "nothing a reader would notice" and the site served pre-correction scores for hours
while three builds passed green. A score IS what a reader notices: it is the number on the chip.

So the signature covers the ticket set AND every player's TOTAL, price and weather factor. A
pure-weather pass therefore republishes, which is correct -- weather is the one thing licensed to
move a football TOTAL (claude/priceonce-doctrine.md).

⚠️ AND IT COVERS meta.season (LEDGERSIG-2026-09-04), for exactly the reason above, which this
file argued and then failed to apply to the most prominent number on the page. OWNLEDGER-2026-09-04
replaced the baseball ledger this room had been publishing -- 88 graded nights, +529.8u -- with
football's own, opening 0-0. The board rebuilt, the run went green, and Publish was SKIPPED: the
signature did not cover the tracker, so "nothing a reader would notice" was returned for a change
that rewrote every figure in the season panel. The fix reached the repo and not the site, which is
the third time in one day that a correction stopped one layer short of the reader.

A night that grades moves meta.season and now republishes, which is what should happen -- the
tracker is baked into the page.
"""
import hashlib, json, sys

def sig(path):
    d = json.load(open(path, encoding='utf-8'))
    t = [(x['kind'], x['name'], [l['name'] for l in x['players']], x.get('parlay_am'))
         for x in d['tickets']]
    p = sorted((k, v.get('TOTAL'), v.get('odds'), v.get('wf')) for k, v in d['players'].items())
    # LEDGERSIG-2026-09-04. The season panel is baked into the page and is the biggest number on
    # it; a ledger that changed without republishing left the site showing the old one.
    led = (d.get('meta') or {}).get('season') or {}
    return hashlib.sha256(json.dumps([t, p, led], sort_keys=True).encode()).hexdigest()

if __name__ == '__main__':
    print(sig(sys.argv[1]) if len(sys.argv) > 1 else '')
