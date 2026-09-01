#!/usr/bin/env python3
"""
PSA-2026-08-31 -- a standing warning at the top of both ticket rooms.

    owner: "we need to put a psa (public service announcement) at the top of the two ticket
            rooms too that tells people to wait to place a ticket until all players on it are
            confirmed, the board will redraft as lineups release, and vegas odds and live
            weather update"

WHY A SCRIPT AND NOT A HAND EDIT. index.html is rebuilt and committed by the pipeline every ~5
minutes -- regen15.py swaps the `const D=...,WX=D.meta.wx;` block and pushes -- so the base file
moves under you. Editing a checkout and uploading it REVERTS THE PAYLOAD to whatever slate that
checkout happened to hold. Same reasoning as retire_dingers.py and seatcap_fix.py: re-apply the
change set to whatever is current, immediately before committing.

WHAT IT SAYS, AND WHY EACH CLAUSE IS THERE

The board already tells a reader what IS confirmed -- the ✓ / ⏳ legend, `confleg`, the CONFIRMED
counter. What it never said is what that means for HIM: that an unconfirmed card is a projection,
and that the thing he is looking at will be re-drafted underneath him. Every doctrine on this
board exists because the card moves -- CONFLOCK freezes only when every leg is confirmed,
MINTGUARD refuses to create a slip past its own kickoff, the re-draft swaps dead legs -- and none
of that was ever said to the person placing the bet.

SOCCER GETS DIFFERENT WORDS, THROUGH THE FORK'S OWN SEAM MECHANISM (soccer_fork.py, `add('psa')`),
and the differences are factual, not stylistic:

  * "a posted lineup" -> "a published XI". That is what the soccer board actually reads, and
    TRUST-2026-08-25 sets the bar: eleven starters a side before a sheet is believed at all.
  * "and the weather updates" is DROPPED for soccer. That board carries NO weather -- no precip
    band, no wx chip, `wxsum` is zeroed in mkTicket. Promising a reader that something updates
    when the board does not even display it would be a lie in the one place on the page whose
    whole job is to stop him betting on a stale card.

The banner markup lives in index.html and forks across with everything else, so there is one
source for the layout and one seam for the wording.
"""
import io
import sys

F = sys.argv[1] if len(sys.argv) > 1 else 'index.html'
s = io.open(F, encoding='utf-8').read()

if 'class="psa"' in s:
    sys.exit('ABORT: a PSA banner is already present -- refusing to add a second')

CSS = (
    ".psa{display:flex;gap:10px;align-items:flex-start;margin:14px 0 2px;padding:11px 14px;"
    "border:1px solid var(--line2);border-left:3px solid var(--amber);border-radius:10px;"
    "background:linear-gradient(90deg,#ffc24d14,transparent 60%);color:var(--mut);"
    "font-size:13px;line-height:1.5}\n"
    ".psa .psa-i{color:var(--amber);font-size:14px;line-height:1.4;flex:0 0 auto}\n"
    ".psa b{color:var(--txt);font-weight:600}\n"
    ".psa .psa-k{color:var(--lime);font-weight:700}\n"
    "@media(max-width:560px){.psa{font-size:12.5px;padding:10px 12px}}\n"
)
STYLE_END = '</style></head><body>'
if s.count(STYLE_END) != 1:
    sys.exit(f'ABORT: expected exactly 1 `{STYLE_END}`, found {s.count(STYLE_END)}')
s = s.replace(STYLE_END, CSS + STYLE_END, 1)

# ⚠️ ANCHORED ON THE TAGLINE, NOT ON <header> OR A LINE NUMBER. The tagline is a fixed string that
# the fork already seams (soccer_fork.add('tagline', ...)), so if it ever moves, BOTH files fail
# loudly in the same place rather than this one silently planting the banner somewhere odd.
PSA = (
    '\n <div class="psa"><span class="psa-i">⚠️</span><div><b>Wait for the '
    '<span class="psa-k">✓</span> before you place.</b> A ticket is only final once every '
    'player on it is confirmed in a posted lineup. This board keeps re-drafting: '
    'as lineups drop, Vegas odds move and the weather updates, legs get swapped and slips can '
    'leave the card entirely. What you see until then is a projection, not the final ticket.</div></div>'
)
ANCHOR = ('<div class="tagline">“Every strike brings me closer to the next home run.”'
          '<span class="cite">— Babe Ruth</span></div>')
if s.count(ANCHOR) != 1:
    sys.exit(f'ABORT: expected exactly 1 tagline anchor, found {s.count(ANCHOR)}')
s = s.replace(ANCHOR, ANCHOR + PSA, 1)

io.open(F, 'w', encoding='utf-8').write(s)
print(f'psa_fix: patched {F} ({len(s)} bytes)')
