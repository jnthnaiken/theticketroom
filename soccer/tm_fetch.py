#!/usr/bin/env python3
"""tm_fetch.py -- GOALLINE-2026-10-15. Refresh soccer/tm.psv, the understat team match log the Goal Line's
luck layer reads (soccer_tot.py): one row per team per league match, current + previous season, top five.

    python3 soccer/tm_fetch.py soccer/tm.psv

Runs in GitHub Actions (soccer-tm.yml); the Claude session cannot reach understat from its shell. Reuses
history/fetch_history.py's XHR opener, which is the measured way in (cookie-primed, X-Requested-With).
A league that fails keeps its rows from the previous file, so one blip never blanks the luck layer.
"""
import os, sys, time
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), 'history'))
import fetch_history as FH

COLS = ['league', 'team', 'date', 'h_a', 'xG', 'xGA', 'npxG', 'npxGA', 'scored', 'missed']


def main(out):
    t = time.gmtime()
    cur = t.tm_year if t.tm_mon >= 7 else t.tm_year - 1
    old = {}
    if os.path.exists(out):
        for ln in open(out, encoding='utf-8'):
            p = ln.rstrip('\n').split('|')
            if len(p) == len(COLS) and p[0] != 'league':
                old.setdefault(p[0], []).append(ln.rstrip('\n'))
    rows, ok = [], []
    for lg in FH.LEAGUES:
        got = []
        try:
            for s in (cur - 1, cur):
                j = FH.get_json(f'/getLeagueData/{lg}/{s}', f'/league/{lg}/{s}')
                for tm in (j.get('teams') or {}).values():
                    for m in tm.get('history') or []:
                        got.append('|'.join(str(x) for x in (
                            lg, tm['title'], str(m['date'])[:10], m['h_a'], round(float(m['xG']), 4),
                            round(float(m['xGA']), 4), round(float(m['npxG']), 4), round(float(m['npxGA']), 4),
                            int(m['scored']), int(m['missed']))))
            rows += got; ok.append(f'{lg}:{len(got)}')
        except Exception as e:
            print(f'!! {lg}: {e} -- keeping {len(old.get(lg, []))} previous rows', flush=True)
            rows += old.get(lg, [])
    if not rows:
        sys.exit('nothing fetched and nothing to keep')
    rows = sorted(set(rows))
    with open(out, 'w', encoding='utf-8') as f:
        f.write('|'.join(COLS) + '\n' + '\n'.join(rows) + '\n')
    print(f'tm.psv: {len(rows)} rows  seasons {cur-1}-{cur}  ' + ' '.join(ok))


if __name__ == '__main__':
    main(sys.argv[1] if len(sys.argv) > 1 else 'tm.psv')
