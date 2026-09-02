#!/usr/bin/env python3
"""
SEED-CHALKEVER — DISARMED 2026-09-02. DO NOT RUN.

NOT IDEMPOTENT. Flagged in the 2026-09-01 audit and confirmed by accident the same day: a second
run appended a DUPLICATE carry block to regen15.py. It has no count guard and no marker check, so
nothing stops it doing that again.

`meta.chalkever` is maintained by index.html itself now (LOCKEVICT-2026-08-29 reads the prior
value off the payload and unions today's ban into it), so there is nothing left to seed.
"""
import sys

sys.exit(
    "DISARMED 2026-09-02 -- this script is a tombstone. Read the docstring above.\n"
    "The live rule is CHALKSTREAK-2026-09-02 in index.html."
)
