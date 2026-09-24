#!/usr/bin/env python3
"""FORKSEAMS-2026-09-24 -- the football page is forked from BASEBALL's index.html, so a rename
over there breaks it here. This test is the alarm that rings without a football slate.

WHAT HAPPENED
    2026-09-24, SPECIALS: baseball's two specials were renamed (Lunch Special / Nightcap ->
    Daily Dinger / Long Ball Jackpot). `nfl_fork.py` rewrites baseball markup into football markup
    by EXACT STRING, and six of its seams pointed at the old wording. The fork exited 4 --
    correctly; it refuses to publish a football page built off markup it no longer recognises.

WHY NOBODY NOTICED FOR HOURS
    `nfl-build.yml` gates every step on `steps.slate.outputs.go == 'true'`. With no slate committed
    for the day the whole build SKIPS, and skipping is GREEN. Eight consecutive green NFL runs
    while the fork could not have published anything. The breakage would have surfaced at the exact
    moment it was most expensive: committing tonight's slate, hours before kickoff.

    So the seam guard is a fine guard and a terrible alarm. It only fires on a day the room has
    something to build. This test fires on every run, slate or no slate.

WHAT IT ASSERTS
    Run the real `nfl_fork.py` against the CURRENT `../index.html` and the newest committed
    football payload. Exit 0 and every seam applied. Nothing is mocked -- a seam that drifts by one
    character fails here the same way it would fail in CI.

⚠️ This does NOT check that the football wording is RIGHT, only that every seam still matches
something. A seam retargeted to the wrong string still applies. Read the page after a rename.

Run: python3 test_nfl_forkseams.py        (from nfl/)
"""
import os
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
FAIL = []


def check(ok, msg, got=''):
    print(('PASS  ' if ok else 'FAIL  ') + msg + (('   ' + str(got)) if got and not ok else ''))
    if not ok:
        FAIL.append(msg)


mlb = os.path.join(HERE, '..', 'index.html')
payload = os.path.join(HERE, 'nfl_D.json')
check(os.path.exists(mlb), "baseball's index.html is where the fork expects it", mlb)
check(os.path.exists(payload), 'a committed football payload exists to fork against', payload)
if FAIL:
    sys.exit(1)

out = os.path.join(tempfile.mkdtemp(), 'nfl_index.html')
r = subprocess.run([sys.executable, os.path.join(HERE, 'nfl_fork.py'), mlb, payload, out],
                   capture_output=True, text=True, cwd=HERE)
txt = (r.stdout or '') + (r.stderr or '')

check(r.returncode == 0,
      'nfl_fork.py applies every seam against the CURRENT baseball index.html',
      'exit %d\n%s' % (r.returncode, txt.strip()[:900]))
check('SEAM MISMATCH' not in txt,
      'and reports no seam mismatch -- a baseball rename has not orphaned a football seam',
      [l for l in txt.splitlines() if 'matched 0' in l][:8])

if r.returncode == 0:
    check(os.path.exists(out) and os.path.getsize(out) > 200_000,
          'and writes a football page of plausible size',
          os.path.getsize(out) if os.path.exists(out) else 'missing')
    html = open(out, encoding='utf-8').read()
    # The football wording must actually be present -- a seam can apply and still leave the page
    # reading like the baseball one if the replacement was retargeted carelessly.
    for want in ('Early Window', 'Sunday Night', 'Paydirt'):
        check(want in html, 'the forked page carries football wording: %r' % want)
    # And baseball's specials must not be VISIBLE on it. They survive in code comments and in a
    # ticket-name pool for a kind football never drafts, so this checks the rendered strings only.
    for bad in ('<span class="tsech">Daily Dinger</span>',
                '<b>Long Ball Jackpot</b>'):
        check(bad not in html, 'and does not show a baseball special: %r' % bad)

print()
if FAIL:
    print('%d FAILED' % len(FAIL))
    for f in FAIL:
        print('  - ' + f)
    sys.exit(1)
print('ALL GREEN -- the football fork still recognises the baseball page it is cut from')
