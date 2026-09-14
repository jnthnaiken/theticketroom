#!/usr/bin/env python3
"""
boardcfg.py — BOARDCFG-2026-09-13. Loads board_config.json, the single source of truth for the
MLB board's draft shape and stake numbers.

Python owns the config. Two consumers:

  * build15.py         stamps it into D['meta']['cfg'] so the client gets it with the board
  * assemble_tickets.py imports it instead of keeping its own copy

index.html reads D.meta.cfg and falls back to its own literals when a board has no cfg, so an
archived board still renders exactly as it did.

FAILS SAFE: if the file is missing or unreadable, DEFAULTS below are used and a warning is
printed. The defaults are the values that were live on 2026-09-13, so a lost config degrades to
"the board we were already shipping", never to zeros.

    python3 boardcfg.py        # print the resolved config and where each value came from
"""
import json, os, sys

HERE = os.path.dirname(os.path.abspath(__file__))
PATH = os.path.join(HERE, 'board_config.json')

# The live values as of BOARDCFG-2026-09-13. Only used if board_config.json cannot be read.
DEFAULTS = {
    'Z_GATE': 0.75, 'GAME_CAP': 6, 'RESERVE_GAME_CAP': 4, 'ANCH': 4, 'ANCH_PER_GAME': 2, 'MOONS_PER_ANC': 2,
    'MOON_LEGS': 4, 'SHORT_MOON_FLOOR': 3, 'MOON_SLACK': 2, 'WIN': 150, 'NIGHT_WIN': 60,
    'LUNCH_CUT_MIN': 1020, 'CHALK_N': 0, 'CHEF_TICKET': False, 'DINGERS': False,
    'RR_UNIT': {2: 2.00, 3: 0.50, 4: 0.25, 5: 0.10},
}

_INT = ('GAME_CAP', 'RESERVE_GAME_CAP', 'ANCH', 'ANCH_PER_GAME', 'MOONS_PER_ANC', 'MOON_LEGS', 'SHORT_MOON_FLOOR',
        'MOON_SLACK', 'WIN', 'NIGHT_WIN', 'LUNCH_CUT_MIN', 'CHALK_N')


def load(path=PATH, quiet=False):
    cfg = dict(DEFAULTS)
    src = 'DEFAULTS (board_config.json unreadable)'
    try:
        raw = json.load(open(path, encoding='utf-8'))
        for k, v in raw.items():
            if k.startswith('_'):
                continue
            cfg[k] = v
        if 'RR_UNIT' in raw:                      # JSON keys are strings; the code wants ints
            cfg['RR_UNIT'] = {int(k): float(v) for k, v in raw['RR_UNIT'].items()}
        src = os.path.basename(path)
    except Exception as e:
        if not quiet:
            print(f"::warning::boardcfg: {os.path.basename(path)} unreadable ({e}); using DEFAULTS")
    for k in _INT:
        if k in cfg:
            cfg[k] = int(cfg[k])
    _validate(cfg)
    cfg['_source'] = src
    return cfg


def _validate(c):
    """Refuse a config that cannot produce a board. A bad number here is worse than no change."""
    bad = []
    if not (0 < c['Z_GATE'] < 5): bad.append('Z_GATE out of range')
    if c['MOON_LEGS'] < 2: bad.append('MOON_LEGS < 2')
    if c['SHORT_MOON_FLOOR'] < 2: bad.append('SHORT_MOON_FLOOR < 2 (a 2-leg round robin is a straight parlay)')
    if c['SHORT_MOON_FLOOR'] > c['MOON_LEGS']: bad.append('SHORT_MOON_FLOOR > MOON_LEGS')
    if c['GAME_CAP'] < 1: bad.append('GAME_CAP < 1')
    if c['RESERVE_GAME_CAP'] < 1: bad.append('RESERVE_GAME_CAP < 1')
    if c['WIN'] < 1: bad.append('WIN < 1')
    if c['WIN'] > 155: bad.append('WIN > 155 -- past the board\'s own lineup-timing flag; every slip would ship warned')
    if c['ANCH'] < 1: bad.append('ANCH < 1')
    for L in range(2, c['MOON_LEGS'] + 1):
        if L not in c['RR_UNIT']: bad.append(f'RR_UNIT has no entry for {L} legs')
    if bad:
        raise ValueError('board_config.json is not shippable: ' + '; '.join(bad))


CFG = load()
globals().update({k: v for k, v in CFG.items() if not k.startswith('_')})


if __name__ == '__main__':
    c = load()
    print(f"source: {c.pop('_source')}\n")
    for k, v in sorted(c.items()):
        print(f'  {k:18} {v}')
    from itertools import combinations
    print('\n  round robin sizing:')
    for L in sorted(c['RR_UNIT']):
        n = len([x for sz in range(2, L + 1) for x in combinations(range(L), sz)])
        print(f'    {L} legs -> {n:2} bets x {c["RR_UNIT"][L]:.2f}u = {n * c["RR_UNIT"][L]:.2f}u')
