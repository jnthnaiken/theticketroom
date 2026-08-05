#!/usr/bin/env python3
"""
savant_gate.py — refuse to publish a board whose edge signals silently died.

WHY THIS EXISTS (2026-08-05)
----------------------------
`build15.py` pulls nine edge signals off Baseball Savant leaderboards. When one of
those fetches times out or returns 0 rows the signal does NOT fail loudly — it
collapses to a neutral default (all-None, or all-zero z-scores). The board still
scores, still assembles and still publishes, but `edge_z` is now missing a term, so
every TOTAL shifts a point or two, `strength` re-orders, and tickets reshuffle.

Observed on 2026-08-05: at 3:31pm `_zspray` collapsed (156 distinct values -> 73) and
the chef ticket flipped Schwarber -> Murakami; at 3:32pm `_zpvd` went to ZERO distinct
values (dead for all 390 bats) and the run still committed. The board flip-flopped for
an hour. The workflow already gates on a stale StatsAPI pull (zero HR/9 arms); this is
the same idea for the Savant half.

HOW IT DECIDES
--------------
For each `_z*` signal it counts DISTINCT non-null values across the field. A healthy
signal has many (spray ~150, arsenal ~320, tracking ~285); a collapsed one has 0 (all
None) or a handful (all pinned to the same neutral value). Absolute thresholds don't
work — the counts differ per signal and per slate size — so it compares against the
LAST COMMITTED board for the same date (`git show HEAD:D_<date>.json`), which is a
same-slate, same-field baseline from minutes earlier.

A signal trips the gate when:
  * it had values last build and has NONE now                (dead outright), or
  * it had >= MIN_BASE distinct values and lost > DROP_FRAC  (collapsed to neutral).

Per-pitcher signals legitimately sit near ~28 distinct values and binary flags at 2,
which is why the relative check only applies above MIN_BASE.

Usage:
    python3 savant_gate.py 2026-08-05            # in the repo root
Exit 0 = signals healthy, safe to assemble + publish.
Exit 1 = a signal died; caller should discard this board and wait for the next run.
Writes `signals=ok|bad` to $GITHUB_OUTPUT when running under Actions.
"""
import json, os, subprocess, sys

SIGNALS = ['_zbg', '_zxpow', '_zars', '_zxptr', '_zpvel',
           '_zspray', '_zpvd', '_zbtrk', '_zpark']

MIN_BASE  = 20    # only apply the relative check to signals with a real spread
DROP_FRAC = 0.40  # >40% of the distinct values gone = collapsed, not drift


def distinct(players, sig):
    """Distinct non-null values of `sig` across the field."""
    vals = set()
    for p in players:
        v = p.get(sig)
        if v is not None:
            try:
                vals.add(round(float(v), 6))
            except (TypeError, ValueError):
                vals.add(str(v))
    return len(vals)


def counts(doc):
    players = list((doc.get('players') or {}).values())
    return {s: distinct(players, s) for s in SIGNALS}, len(players)


def prev_doc(path):
    """The last committed board for this date, or None on the first build of the day."""
    try:
        blob = subprocess.run(['git', 'show', f'HEAD:{path}'],
                              capture_output=True, check=True).stdout
        return json.loads(blob)
    except Exception:
        return None


def emit(ok):
    out = os.environ.get('GITHUB_OUTPUT')
    if out:
        with open(out, 'a') as fh:
            fh.write(f"signals={'ok' if ok else 'bad'}\n")


def main():
    if len(sys.argv) < 2:
        print("usage: savant_gate.py <YYYY-MM-DD>")
        return 2
    date = sys.argv[1]
    path = f"D_{date}.json"
    if not os.path.exists(path):
        print(f"::warning::{path} not found — nothing to gate.")
        emit(True)
        return 0

    new, n_new = counts(json.load(open(path)))
    prev = prev_doc(path)

    print(f"=== savant_gate {date} ===")
    if prev is None:
        print(f"no committed {path} to compare against (first build of the day).")
        dead = [s for s, c in new.items() if c == 0]
        for s in SIGNALS:
            print(f"  {s:9} {new[s]:5} distinct" + ("   <-- DEAD" if new[s] == 0 else ""))
        if dead:
            print("::warning::no baseline yet, but these signals have no values at all: "
                  + ", ".join(dead))
        print("\nRESULT: PASS (no baseline)")
        emit(True)
        return 0

    old, n_old = counts(prev)
    print(f"field: {n_old} -> {n_new} bats\n")
    print(f"  {'signal':9} {'prev':>6} {'now':>6}  {'change':>8}")
    bad = []
    for s in SIGNALS:
        o, c = old[s], new[s]
        pct = (c - o) / o * 100 if o else 0.0
        flag = ''
        if o > 0 and c == 0:
            flag = '  <-- DEAD'
            bad.append(f"{s}: {o} distinct values last build, ZERO now (fetch returned nothing)")
        elif o >= MIN_BASE and c < o * (1 - DROP_FRAC):
            flag = '  <-- COLLAPSED'
            bad.append(f"{s}: {o} -> {c} distinct ({pct:+.0f}%), collapsed toward its neutral default")
        print(f"  {s:9} {o:6} {c:6}  {pct:+7.0f}%{flag}")

    if bad:
        print("\n::warning::Savant edge signals degraded on this run — discarding the board:")
        for b in bad:
            print(f"  ! {b}")
        print("A neutralised signal shifts every TOTAL, re-orders strength and reshuffles the\n"
              "tickets, so this board would flip-flop against the last good one. Keeping the\n"
              "published board as-is; the next run rebuilds once Savant answers properly.")
        print("\nRESULT: FAIL — do not assemble or publish")
        emit(False)
        return 1

    print("\nRESULT: PASS — signals healthy, safe to assemble + publish")
    emit(True)
    return 0


if __name__ == '__main__':
    sys.exit(main())
