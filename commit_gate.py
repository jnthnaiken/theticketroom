#!/usr/bin/env python3
"""
Should this build actually be committed (and therefore deployed)?

WHY
---
The board is a snapshot. The browser re-drafts on every page load against live lineups, so it
learns about a scratch the moment MLB posts it; the server only learns at its next build. Between
those two moments the archive (D_<date>.json, which grade_night.py grades) can disagree with what a
person was looking at -- and for a Chef's Table seat that window decides refund-vs-substitute,
because the seat is held with a Missed Reservation stamp once its own game is underway.

The only real fix is to build more often, so the last build before each first pitch is close enough
to the lock that it sees the same lineup the browser does. But every build rewrites two timestamps
(meta.build in the board, pulled_at in slate_auto), so every build committed -- meaning a denser
cron would mean a Pages deploy every few minutes, all day, almost all of them publishing nothing.

So: build every 5 minutes, commit only when something REAL changed. This script is that test.
It compares each staged file against HEAD with those two timestamps normalized away, and reports
a material change if anything else moved -- a scratch, an odds move, a weather refresh, a re-draft,
a graded night, a new calibration row.

SAFETY
------
A false "nothing changed" only delays publication: MAX_STALE_MIN forces a commit regardless once
index.html has gone that long without one, so a missed change self-heals within ~25 minutes and the
board's build stamp never looks frozen. Failing open (exit 0) on any internal error keeps a broken
gate from silently stopping the board.

exit 0 -> commit    exit 1 -> skip
"""
import json, os, re, subprocess, sys, time

MAX_STALE_MIN = 25          # never let the published board go longer than this without a commit

# The two fields that change on EVERY build and mean nothing on their own.
#   index.html + D_<date>.json : "build": "8/3 2:56pm"     (meta.build, set by build15)
#   slate_auto_<date>.json     : "pulled_at": "2026-...Z"  (set by fetch_mlb)
_STAMPS = (re.compile(r'"build":\s*"[^"]*"'), re.compile(r'"pulled_at":\s*"[^"]*"'))


def _norm(txt):
    if txt is None:
        return None
    for rx in _STAMPS:
        txt = rx.sub('"~stamp~"', txt)
    return txt


def _head(path):
    r = subprocess.run(['git', 'show', 'HEAD:' + path], capture_output=True, text=True)
    return r.stdout if r.returncode == 0 else None


def _run(*args):
    return subprocess.run(args, capture_output=True, text=True).stdout.strip()


def main():
    staged = [p for p in _run('git', 'diff', '--staged', '--name-only').splitlines() if p]
    if not staged:
        print('  commit gate: nothing staged')
        return 1

    material = []
    for p in staged:
        before = _head(p)
        try:
            after = open(p, encoding='utf-8').read()
        except OSError:
            material.append(p + ' (removed)')          # deletion is always material
            continue
        if before is None:
            material.append(p + ' (new)')              # brand-new file (a new slate's D_, etc.)
        elif _norm(before) != _norm(after):
            material.append(p)

    if material:
        print('  commit gate: material change in ' + ', '.join(material[:6])
              + (f' (+{len(material)-6} more)' if len(material) > 6 else ''))
        return 0

    # Only the build stamps moved. Hold the commit -- unless the repo has gone quiet long enough
    # that a reader would start to wonder whether the board is still updating.
    # Measured off HEAD, not `git log -- index.html`: the runner checks out with fetch-depth 1, so
    # there is exactly one commit in the clone and per-path history does not mean what it looks like.
    # HEAD's timestamp is well defined at any clone depth and is the right proxy anyway -- it answers
    # "how long since anything was published", which is what the stale build stamp would signal.
    ts = _run('git', 'log', '-1', '--format=%ct')
    age = (time.time() - int(ts)) / 60.0 if ts.isdigit() else 1e9
    if age >= MAX_STALE_MIN:
        print(f'  commit gate: only timestamps moved, but index.html is {age:.0f}m old -> committing to refresh the stamp')
        return 0
    print(f'  commit gate: only build timestamps moved ({", ".join(staged[:4])}) -- '
          f'skipping commit/deploy (last publish {age:.0f}m ago)')
    return 1


if __name__ == '__main__':
    try:
        sys.exit(main())
    except Exception as e:                              # fail OPEN: a broken gate must never stop the board
        print(f'  commit gate: check failed ({str(e)[:120]}) -> committing anyway')
        sys.exit(0)
