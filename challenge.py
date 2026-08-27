#!/usr/bin/env python3
"""
challenge.py -- the CHALLENGE step. Does a proposed board change beat the live one on slates
that were NOT available when it was proposed?

WHY THIS EXISTS. Every _SIG change so far has been measured on the archive that was already in
hand: DMGRATIO-2026-08-23's own comment records "MEASUREMENT ON RECORD, 23 nights / 5,454 bats /
563 HR". That number is honest about what it is, but it cannot separate a real improvement from a
formula that happens to fit the nights it was chosen on. There is no way to tell from inside the
sample. The only test that can is a LATER one: freeze the proposal date, then judge it solely on
slates logged after it.

    python3 challenge.py --proposed 2026-08-23 --challenger total
    python3 challenge.py --proposed 2026-08-13 --incumbent mkt_z --challenger blend

WHAT IT DOES NOT DO. It does not score anything. Both columns must already be in
calibration.jsonl -- the incumbent because the board writes it every night, the challenger because
something logged it as a shadow (see calibrate.py's _z* passthrough list). That separation is the
point: this file can never change what the board shows, and a challenger can never reach the board
by being evaluated.

THE SCOREBOARD IS RANKING, NOT PRICE. Owner's call, 2026-08-27: "we're not trying to beat the
market, that's irrelevant." So the two questions asked here are the two EdgeHunter's protocol asks
separately, and neither is ROI-against-book:

    1. TOP-N HIT RATE -- of the bats the board would actually have shown, how many homered?
       This is the product. It is what a reader sees and it is the number worth defending.
    2. AUC -- does the column order the whole field better? A diagnostic, not the verdict.
       A change can lift (2) while hurting (1) by re-ordering bats nobody would ever see.

Uncertainty is bootstrapped by SLATE, not by row. Bats on the same night share a park, a weather
front and an umpire, so rows are not independent and a row-level bootstrap will report a confidence
interval several times too narrow. This mirrors fit_savant.py's grouped-by-game_date CV for the
same reason.

EXIT CODES:  0 = challenger wins on top-N hit rate and the interval excludes zero
             1 = not proven -- either it lost, or there is not enough unseen data yet
             2 = bad usage / column not present
"""
import json, sys, argparse, random, math
from collections import defaultdict

LOG = "calibration.jsonl"
MIN_SLATES = 14          # below this the interval is too wide to conclude anything. Not a
                         # statistical threshold -- a floor to stop anyone reading noise as a win.


def load(path):
    rows = []
    with open(path) as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                rows.append(json.loads(line))
            except Exception:
                continue
    return rows


def by_slate(rows, cols):
    """{date: [row, ...]} keeping only rows where every needed column is numeric and hr is graded."""
    out = defaultdict(list)
    for r in rows:
        if r.get('hr') not in (0, 1) or not r.get('date'):
            continue
        if any(not isinstance(r.get(c), (int, float)) for c in cols):
            continue
        out[r['date']].append(r)
    return out


def topn_hits(slates, col, n):
    """(home runs found, bats shown, slates counted) taking the top n by `col` on each slate."""
    hit = shown = used = 0
    for d, rs in slates.items():
        if len(rs) < n:
            continue
        top = sorted(rs, key=lambda r: -r[col])[:n]
        hit += sum(r['hr'] for r in top)
        shown += len(top)
        used += 1
    return hit, shown, used


def auc(pairs):
    """Mann-Whitney AUC with tie correction. pairs = [(score, hr), ...]"""
    v = sorted(pairs)
    n = len(v)
    rk = [0.0] * n
    i = 0
    while i < n:
        j = i
        while j + 1 < n and v[j + 1][0] == v[i][0]:
            j += 1
        avg = (i + j) / 2.0 + 1
        for t in range(i, j + 1):
            rk[t] = avg
        i = j + 1
    npos = sum(1 for _, y in v if y)
    nneg = n - npos
    if not npos or not nneg:
        return None
    P = sum(rk[i] for i in range(n) if v[i][1])
    return (P - npos * (npos + 1) / 2.0) / (npos * nneg)


def boot_diff(slates, fn, reps, seed=17):
    """Bootstrap a paired difference by RESAMPLING SLATES. fn(sample) -> (challenger, incumbent)."""
    dates = list(slates)
    rnd = random.Random(seed)
    ds = []
    for _ in range(reps):
        pick = {}
        for k in range(len(dates)):
            d = dates[rnd.randrange(len(dates))]
            pick[f"{d}#{k}"] = slates[d]          # unique key so one night can be drawn twice
        a, b = fn(pick)
        if a is not None and b is not None:
            ds.append(a - b)
    ds.sort()
    if not ds:
        return None
    lo = ds[int(0.025 * len(ds))]
    hi = ds[min(len(ds) - 1, int(0.975 * len(ds)))]
    return sum(ds) / len(ds), lo, hi


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--proposed', required=True, metavar='YYYY-MM-DD',
                    help="the date the change was proposed. Only slates AFTER this count.")
    ap.add_argument('--challenger', required=True, help="column holding the proposed score")
    ap.add_argument('--incumbent', default='total', help="column holding the live score (default: total)")
    ap.add_argument('--top', type=int, default=30, help="board size to judge on (default: 30)")
    ap.add_argument('--log', default=LOG)
    ap.add_argument('--reps', type=int, default=600)
    ap.add_argument('--min-slates', type=int, default=MIN_SLATES)
    a = ap.parse_args()

    rows = load(a.log)
    if not rows:
        print(f"!! {a.log} is empty or missing"); return 2
    for c in (a.challenger, a.incumbent):
        if not any(isinstance(r.get(c), (int, float)) for r in rows):
            print(f"!! column '{c}' is not numeric on any row of {a.log}.\n"
                  f"   A challenger has to be LOGGED before it can be judged -- add it to the\n"
                  f"   shadow passthrough in calibrate.py and let it accrue.")
            return 2

    allsl = by_slate(rows, (a.challenger, a.incumbent))
    unseen = {d: rs for d, rs in allsl.items() if d > a.proposed}
    seen = {d: rs for d, rs in allsl.items() if d <= a.proposed}

    print(f"CHALLENGE  {a.challenger}  vs  {a.incumbent}   (proposed {a.proposed})")
    print(f"  in-sample  : {len(seen):3d} slates  -- IGNORED, this is the data it was chosen on")
    print(f"  unseen     : {len(unseen):3d} slates  -- the only evidence that counts")
    if not unseen:
        print("\n  VERDICT: no unseen slates yet. Come back later."); return 1

    ch, sh, used = topn_hits(unseen, a.challenger, a.top)
    ih, _, _ = topn_hits(unseen, a.incumbent, a.top)
    if not used:
        print(f"\n  VERDICT: no unseen slate carries {a.top} eligible bats."); return 1
    print(f"\n  TOP-{a.top} HIT RATE over {used} unseen slates ({sh} bats shown)")
    print(f"    challenger {a.challenger:<10s} {ch:4d} HR   {100*ch/sh:5.2f}%")
    print(f"    incumbent  {a.incumbent:<10s} {ih:4d} HR   {100*ih/sh:5.2f}%")
    print(f"    difference                {100*(ch-ih)/sh:+5.2f} points")

    r = boot_diff(unseen,
                  lambda s: (topn_hits(s, a.challenger, a.top)[0] / max(1, topn_hits(s, a.challenger, a.top)[1]),
                             topn_hits(s, a.incumbent,  a.top)[0] / max(1, topn_hits(s, a.incumbent,  a.top)[1])),
                  a.reps)
    if r:
        m, lo, hi = r
        print(f"    slate bootstrap           {100*m:+5.2f}  95% CI [{100*lo:+5.2f}, {100*hi:+5.2f}]")

    flat = [x for rs in unseen.values() for x in rs]
    ac = auc([(x[a.challenger], x['hr']) for x in flat])
    ai = auc([(x[a.incumbent], x['hr']) for x in flat])
    print(f"\n  AUC over the whole unseen field ({len(flat)} bats) -- diagnostic only")
    print(f"    challenger {ac:.4f}   incumbent {ai:.4f}   difference {ac-ai:+.4f}")

    print()
    if used < a.min_slates:
        print(f"  VERDICT: NOT PROVEN -- {used} unseen slates, {a.min_slates} is the floor.")
        print(f"           Nothing here is strong enough to move the board on. Keep logging.")
        return 1
    if r and r[1] > 0:
        print(f"  VERDICT: CHALLENGER WINS on top-{a.top} hit rate, interval excludes zero.")
        print(f"           Promote it -- and record this run's numbers in the _SIG comment.")
        return 0
    if ch > ih:
        print(f"  VERDICT: NOT PROVEN -- challenger is ahead by {100*(ch-ih)/sh:.2f} points but the")
        print(f"           interval includes zero. Ahead is not the same as proven. Keep logging.")
        return 1
    print(f"  VERDICT: CHALLENGER LOSES on the data it did not get to pick.")
    return 1


if __name__ == '__main__':
    sys.exit(main())
