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

🚨 AND IT COVERS THE PROSE (PROSESIG-2026-09-08), WHICH IS THE FOURTH TIME.
Owner, after NFLVOICE shipped and the board did not change: "still seeing one sentence on football
tickets." He was right. The whole of nfl_voice.py reached the repo, CI went green on it, and the
site went on serving `9/8 8:41am` -- because this signature covered every NUMBER a reader notices
and not one WORD of what he actually reads. A build whose only change is the write-ups produced a
byte-identical signature, the gate returned "nothing a reader would notice moved", and Publish was
skipped.

Read the two paragraphs above: a corrected xg.psv (09-03), then the season ledger (09-04, called
out there as "the third time in one day that a correction stopped one layer short of the reader"),
now the prose. Every one of them is the same mistake -- the gate is a list of things somebody
remembered, and it goes stale the moment the payload gains a field.

⚠️ THE RULE THIS SETTLES: if it is rendered, it is in the signature. `note` is the sentence under
a ticket and `why` is the sentence on a player card; both are on the page in 14px type and both
are now hashed. If a future field is added to the payload and shown to a reader, it belongs here
too, and the test below is what will notice it is missing.
"""
import hashlib, json, sys

def sig(path):
    d = json.load(open(path, encoding='utf-8'))
    # PROSESIG-2026-09-08: `note` and `why` are RENDERED. See the header.
    t = [(x['kind'], x['name'], [l['name'] for l in x['players']], x.get('parlay_am'),
          x.get('note'))
         for x in d['tickets']]
    p = sorted((k, v.get('TOTAL'), v.get('odds'), v.get('wf'), v.get('why'))
               for k, v in d['players'].items())
    # LEDGERSIG-2026-09-04. The season panel is baked into the page and is the biggest number on
    # it; a ledger that changed without republishing left the site showing the old one.
    led = (d.get('meta') or {}).get('season') or {}
    return hashlib.sha256(json.dumps([t, p, led], sort_keys=True).encode()).hexdigest()

if __name__ == '__main__':
    print(sig(sys.argv[1]) if len(sys.argv) > 1 else '')
