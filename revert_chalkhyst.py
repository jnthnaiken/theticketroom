#!/usr/bin/env python3
"""
REVERT-CHALKHYST — DISARMED 2026-09-02. DO NOT RUN.

The undo for chalkhyst_fix.py, which is itself disarmed (see its tombstone). CHALKHYST is not in
index.html and has not been since it was reverted, so this script has nothing to revert; against
a current file its anchors either miss or match something they were not written for.

The live rule is CHALKSTREAK-2026-09-02. To change or remove THAT, edit index.html directly --
do not reach for a stale patch pair.
"""
import sys

sys.exit(
    "DISARMED 2026-09-02 -- this script is a tombstone. Read the docstring above.\n"
    "The live rule is CHALKSTREAK-2026-09-02 in index.html."
)
