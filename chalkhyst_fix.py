#!/usr/bin/env python3
"""
CHALKHYST-2026-08-28 — DISARMED 2026-09-02. DO NOT RUN.

This patch fed a STORED BAN back into the draft as input, to hold an incumbent anchor's seat.
It was reverted the same week, and index.html says why in two places: *"That patch read a
stored ban back as INPUT to hold an incumbent's seat; it INVERTED THE BAN and is reverted."*
The ban exists to keep the four shortest prices OFF tickets; protecting whoever is sitting
means a currently-chalk bat keeps anchoring, which is the opposite of the rule.

⚠️ It was still sitting here armed, and it has been run by accident once (2026-09-01, during
an audit probe: it rewrote index.html 932,718 -> 935,462 B). Running it would silently
reintroduce the inverted ban into a live board.

THE PROBLEM IT AIMED AT IS REAL AND IS NOW SOLVED DIFFERENTLY.
See CHALKSTREAK-2026-09-02 in index.html: the ban's INPUT is debounced -- a bat's membership of
the top-CHALK_N must hold for 2 consecutive server builds before the committed ban changes, in
either direction -- and the resulting set is applied to everyone equally. It reads no seat and
favours no bat, so it cannot invert the ban. N=2 was measured over 78 boards, not chosen:
N>=3 lets the ban set reach FIVE when CHALK_N is 4.
"""
import sys

sys.exit(
    "DISARMED 2026-09-02 -- this script is a tombstone. Read the docstring above.\n"
    "The live rule is CHALKSTREAK-2026-09-02 in index.html."
)
