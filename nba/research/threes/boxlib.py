"""boxlib.py -- DOWNTOWN-2026-10-26: per-game threes, minutes and starters from shufinskiy nbastatsv3 (shared by
analyze.py's logic and seed_state.py)."""
import glob, os, re
import pandas as pd


def _clk(c):
    m = re.match(r'PT(\d+)M(\d+(?:\.\d+)?)S', str(c or ''))
    return int(m.group(1)) * 60 + float(m.group(2)) if m else None


def minutes_of(d):
    """ROLE-2026-10-26: minutes and starters from the substitution stream. nbastatsv3 leaves subType blank on a
    Substitution and writes "SUB: <in> FOR <out>" (family names) -- so both names are read off the description and
    mapped to personIds inside that game and team. A man is on the floor at a period's start if his first event of
    the period is anything but coming IN; a sub opens/closes stints; the period end closes everyone still on."""
    out = {}
    order = 'actionId' if 'actionId' in d else 'actionNumber'
    d = d.sort_values(['gameId', 'period', order])
    for gid, gg in d.groupby('gameId', sort=False):
        who = {}
        for pid, tm, nm in zip(gg.personId.values, gg.teamTricode.values, gg.playerName.values):
            if pid > 0 and isinstance(nm, str) and nm: who.setdefault((tm, nm.strip().lower()), set()).add(pid)
        def pidof(tm, nm):
            c = who.get((tm, str(nm).strip().lower()))
            return next(iter(c)) if c and len(c) == 1 else None
        for per, g in gg.groupby('period', sort=False):
            plen = 720.0 if per <= 4 else 300.0
            ev = []   # (elapsed, kind, pid)  kind: 'act' | 'in' | 'out'
            for pid, tm, at, desc, ck in zip(g.personId.values, g.teamTricode.values, g.actionType.values,
                                             g.description.values, g.clock.values):
                t = _clk(ck); el = plen - t if t is not None else None
                if str(at).lower() == 'substitution':
                    m = re.match(r'\s*SUB:\s*(.+?)\s+FOR\s+(.+?)\s*$', str(desc))
                    if not m or el is None: continue
                    pi, po = pidof(tm, m.group(1)), pidof(tm, m.group(2))
                    if po: ev.append((el, 'out', po))
                    if pi: ev.append((el, 'in', pi))
                elif pid > 0:
                    ev.append((el, 'act', pid))
            first = {}
            for el, kind, pid in ev:
                if pid not in first: first[pid] = kind
            on = {pid: 0.0 for pid, k in first.items() if k != 'in'}
            if per == 1:
                for pid in on: out.setdefault((gid, pid), [0.0, False])[1] = True
            for el, kind, pid in ev:
                if el is None: continue
                if kind == 'in': on.setdefault(pid, el)
                elif kind == 'out' and pid in on:
                    out.setdefault((gid, pid), [0.0, False])[0] += max(0.0, el - on.pop(pid))
            for pid, t0 in on.items():
                out.setdefault((gid, pid), [0.0, False])[0] += max(0.0, plen - t0)
    return pd.DataFrame([(g, p, v[0] / 60.0, v[1]) for (g, p), v in out.items()], columns=['gameId', 'personId', 'mins', 'started'])


