#!/usr/bin/env python3
"""test_statecheck.py -- the two false alarms that took `state.py --check` red, and the two real
faults it must still catch. TIEBREAK / JSONKEYS-2026-09-18.

WHY THIS TEST EXISTS. `state.py --check` runs in tests.yml BEFORE the suite, so when it fails the
suite does not run at all. It failed on every commit from 2026-09-15 to 2026-09-18 for two
reasons, NEITHER of which was a real disagreement between the code and the board:

  JSONKEYS  `meta.cfg` comes back out of JSON with RR_UNIT's keys as STRINGS ({'2': 2}), while
            boardcfg.load() hands out ints and floats ({2: 2.0}). Every board built since
            BOARDCFG-2026-09-13 reported "board was built with a different config".
  TIEBREAK  `ranks_like_ev` asked whether the top 10 by TOTAL was the same ORDERED LIST as the
            top 10 by ev. TOTAL is rounded to one decimal and ev is not, so one tie in TOTAL
            reorders the list and the check says the board stopped ranking on EV. On 2026-09-17
            that was Isaac Paredes (-0.1814) and Wilyer Abreu (-0.1813), both at TOTAL 137.6.

A check that cries wolf in front of the suite is worse than no check: the suite stops running and
nobody reads the red. So both are pinned here -- and so is the fault each one was ACTUALLY for,
because the cure for a false alarm must not be a check that passes everything.

    python3 test_statecheck.py
"""
import copy, importlib.util, os, sys

HERE = os.path.dirname(os.path.abspath(__file__))


def load():
    spec = importlib.util.spec_from_file_location('state', os.path.join(HERE, 'state.py'))
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def main():
    st = load()
    fails = []

    def check(label, got, want):
        if got != want:
            fails.append(f'{label}: got {got!r}, want {want!r}')

    # ---- JSONKEYS: spelling is not drift -------------------------------------------------
    check('JSON string keys equal int keys',
          st.cfg_canon({'2': 2, '3': 0.5}) == st.cfg_canon({2: 2.0, 3: 0.50}), True)
    check('int equals float of the same value', st.cfg_canon(6) == st.cfg_canon(6.0), True)
    # ...but a real difference is still a difference, and a flag is not a number.
    check('a changed stake is drift', st.cfg_canon({'3': 0.75}) == st.cfg_canon({3: 0.5}), False)
    check('False is not 0', st.cfg_canon(False) == st.cfg_canon(0), False)
    check('False is not True', st.cfg_canon(False) == st.cfg_canon(True), False)

    # ---- TIEBREAK: a tie in the rounded TOTAL is not a re-ranking -------------------------
    tie = [{'nm': 'a', 'TOTAL': 137.7, 'ev': -0.1800},
           {'nm': 'b', 'TOTAL': 137.6, 'ev': -0.1813},     # these two round onto one TOTAL
           {'nm': 'c', 'TOTAL': 137.6, 'ev': -0.1814},
           {'nm': 'd', 'TOTAL': 137.4, 'ev': -0.1819}]
    check('a tie in TOTAL still ranks like ev', st.ranks_like(tie, 'ev'), True)
    # ...and a genuine re-rank is still caught, which is the whole point of the check.
    flip = copy.deepcopy(tie)
    flip[0]['TOTAL'], flip[3]['TOTAL'] = flip[3]['TOTAL'], flip[0]['TOTAL']
    check('a real inversion is caught', st.ranks_like(flip, 'ev'), False)
    # a column the board does not carry is not a failure, it is an absence
    check('a missing column is vacuously true', st.ranks_like(tie, 'no_such_key'), True)

    # ---- and the two faults still reach check() through a real board ----------------------
    real = st.board()
    if real is None:
        fails.append('no D_2026-*.json to check against -- test is invalid')
    else:
        def with_board(mut):
            b = copy.deepcopy(real)
            mut(b)
            old, st.board = st.board, (lambda: b)
            try:
                return st.check()
            finally:
                st.board = old

        said = lambda bad, s: any(s in x for x in bad)
        check('the live board passes both checks',
              (said(with_board(lambda b: None), 'different config'),
               said(with_board(lambda b: None), 'rank like ev')), (False, False))
        if real.get('cfg'):
            check('a drifted GAME_CAP is reported',
                  said(with_board(lambda b: b['cfg'].update(GAME_CAP=99)), 'different config'), True)
        check('a re-ranked board is reported',
              said(with_board(lambda b: b.update(ranks_like_ev=False)), 'rank like ev'), True)

    if fails:
        print('FAIL')
        for f in fails:
            print('  ' + f)
        sys.exit(1)
    print('PASS  --check ignores JSON spelling and TOTAL ties, and still catches real config '
          'drift and a real re-ranking')


if __name__ == '__main__':
    main()
