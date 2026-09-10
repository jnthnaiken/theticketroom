#!/usr/bin/env python3
"""
kasmodel.py -- KASV0-2026-09-10. Scores the Kasper challenger from the c_* columns. LOG-ONLY.

Owner, 2026-09-10: "yes" -- freeze a first version now so the unseen-night clock starts. The weights
live in kas_weights_v0.json and are FROZEN: a change is a new file (v1, v2, ...) with its own
`proposed` date, never an edit. challenge.py counts only slates AFTER `proposed`:

    python3 challenge.py --proposed 2026-09-10 --challenger kas_v0 --incumbent total
    python3 challenge.py --proposed 2026-09-10 --challenger kas_v0 --incumbent mkt_z

SCORING mirrors the fit exactly (see the weights file's `fit` block):
  1. orient: the `negate` columns are flipped so higher is always better for the hitter
  2. z-score each input WITHIN the night, over that night's logged bats
  3. clip to +-winsor; a missing value is 0 (the night's mean)
  4. score = sum(coef * z)          (the intercept only matters for a probability, not a ranking)
No price anywhere in it. It never touches the board.
"""
import json, os

HERE = os.path.dirname(os.path.abspath(__file__))


def _num(x):
    return isinstance(x, (int, float)) and not isinstance(x, bool)


def load_weights(version='v0', here=HERE):
    return json.load(open(os.path.join(here, f"kas_weights_{version}.json")))


def score_night(rows, W):
    """rows: one night's calibration rows (dicts, modified in place). Adds W['model'] (e.g. kas_v0)."""
    col = W['model']
    neg = set(W.get('negate') or [])
    lim = float(W.get('winsor', 3.0))
    zs = {}
    for c in W['inputs']:
        vals = []
        for r in rows:
            v = r.get(c)
            vals.append((-v if c in neg else v) if _num(v) else None)
        got = [v for v in vals if v is not None]
        if len(got) < 2:
            zs[c] = [0.0] * len(rows); continue
        m = sum(got) / len(got)
        sd = (sum((v - m) ** 2 for v in got) / len(got)) ** 0.5
        zs[c] = [0.0 if (v is None or not sd) else max(-lim, min(lim, (v - m) / sd)) for v in vals]
    for i, r in enumerate(rows):
        r[col] = round(sum(W['coef'].get(c, 0.0) * zs[c][i] for c in W['inputs']), 5)
    return rows


def score_rows(rows, W, ref=None):
    """KASLIVE-2026-09-10: like score_night, but the per-slate mean/sd come from `ref` (default: rows).
    build15 standardises over the bats IN a lineup and scores every carded bat with those stats, so a
    bat who is scratched back in later keeps a comparable number. Returns [score, ...] aligned to rows."""
    ref = rows if ref is None else ref
    neg = set(W.get('negate') or [])
    lim = float(W.get('winsor', 3.0))
    tot = [0.0] * len(rows)
    for c in W['inputs']:
        orient = (lambda v: -v) if c in neg else (lambda v: v)
        got = [orient(r.get(c)) for r in ref if _num(r.get(c))]
        if len(got) < 2:
            continue
        m = sum(got) / len(got)
        sd = (sum((v - m) ** 2 for v in got) / len(got)) ** 0.5
        if not sd:
            continue
        w = W['coef'].get(c, 0.0)
        for i, r in enumerate(rows):
            v = r.get(c)
            if _num(v):
                tot[i] += w * max(-lim, min(lim, (orient(v) - m) / sd))
    return [round(x, 5) for x in tot]
