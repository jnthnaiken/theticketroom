#!/usr/bin/env python3
"""nfl_restate.py -- NFLRESTATE-2026-09-17. Re-run every graded football night under the CURRENT
system and rewrite nfl_season.json as a RESTATED ledger, the way soccer's was on 2026-09-17.

Owner: "can you update the football ledger to reflect the new model?"

WHAT THE RESTATED LEDGER MEANS. Week 1's four nights were drafted by the old scorer: raw EV with no
price ceiling, and the usage model alone. Since then the board has changed twice -- PRICECAP
(+400 ceiling, 2026-09-15) and NFLLAYER (the layered TD model blended into p_model, 2026-09-17) --
so the posted record measures a board that no longer exists. This script re-runs each archived
slate through today's scorer and today's draft, grades it against what actually happened, and
writes the result as `restated`. The posted record is kept verbatim in nfl_season_v1_actual.json.

INPUTS, all committed, nothing re-scraped:
  slates/<date>/atd.psv + fixtures.json + prices.json   the prices we actually held (PRICEONCE)
  boards/<date>.json                                    the graded archive: who scored, who was out

WHAT IT IS NOT. It is not a backtest -- four nights of one week decide nothing, and a restated
line is a statement about the SYSTEM, not a claim that the system would have made money. The
prices are the ones the board held that night, so a rule that would have drafted a man we never
priced cannot be restated; those tickets are simply not there to grade.

    python3 nfl_restate.py [--write]      # default is a dry run that prints the comparison
"""
import contextlib, io, json, os, subprocess, sys, tempfile
H = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, H); sys.path.insert(0, os.path.join(H, '..', 'soccer'))
os.chdir(H)
import nfl_mock as M, soccer_grade as G

# The draft is the LIVE nfl_draft_cli.js, with only its `require` re-pointed: in production the
# workflow stages soccer_draft.js beside it in .work/. Generated, never hand-copied (same trick as
# backtest/run.py), so a change to the draft reaches this restatement automatically.
_CLI = open('nfl_draft_cli.js', encoding='utf-8').read().replace(
    "require('./soccer_draft.js')", "require(%r)" % os.path.abspath(os.path.join('..', 'soccer', 'soccer_draft.js')))
DRAFT = os.path.join(tempfile.mkdtemp(), 'nfl_draft_bt.js')
open(DRAFT, 'w', encoding='utf-8').write(_CLI)

SYSTEM = ('EV ranking with the +400 price cap (PRICECAP-2026-09-15), no quarterbacks (NOQB), and '
          'the layered TD model blended into p_model (NFLLAYER-2026-09-17). Prices are the ones the '
          'board held on the night; results are the graded archive in nfl/boards/<date>.json.')


def restate(date):
    b = json.load(open(f'boards/{date}.json', encoding='utf-8'))
    fx = json.load(open(f'slates/{date}/fixtures.json', encoding='utf-8'))
    season, week = int(fx['season']), int(fx['week'])
    tmp = tempfile.mkdtemp()
    prices = os.path.join(tmp, 'prices.json')
    with open(f'slates/{date}/prices.json', encoding='utf-8') as f:
        open(prices, 'w', encoding='utf-8').write(f.read())
    with contextlib.redirect_stdout(io.StringIO()) as log:
        d, _fx = M.score(season, week, f'slates/{date}/atd.psv', f'slates/{date}/fixtures.json', prices)
        scored = M.to_scored(d, fx)
    sp = os.path.join(tmp, 'scored.json'); json.dump(scored, open(sp, 'w'))
    tk = os.path.join(tmp, 'tickets.json')
    r = subprocess.run(['node', DRAFT, sp, f'slates/{date}/fixtures.json', tk],
                       capture_output=True, text=True)
    if r.returncode != 0:
        raise SystemExit(f'{date}: draft failed\n{r.stderr[-400:]}')
    slug = {}
    for k, v in fx['matches'].items():
        slug[v['home']] = k; slug[v['away']] = k
    truth = {n: dict(hr=bool(p.get('hr')), out=bool(p.get('out')) or bool(p.get('void')),
                     game=slug.get(p.get('code')))
             for n, p in b['players'].items()}
    rows, missing = [], set()
    for t in json.load(open(tk)):
        legs = [dict(name=l['name'], odds=l['odds'], game=l['match']) for l in t['legs']]
        for l in legs:
            if l['name'] not in truth:
                missing.add(l['name'])
        tt = dict(kind=t['kind'], name=t['name'], players=legs,
                  rr=(dict(risk=t['risk']) if len(legs) > 1 else None))
        g = G.grade_ticket(tt, truth, set(fx['matches']))
        if not g:
            continue
        rows.append(dict(kind=t['kind'], name=t['name'], legs=[l['name'] for l in legs],
                         odds=[l['odds'] for l in legs], stake=g['stake'],
                         net=round(g['net'], 4), won=bool(g['won'])))
    return rows, sorted(missing), log.getvalue()


CAVEATS = [
 'Four nights of one week. This is a restatement of the SYSTEM, not evidence that it makes money.',
 'The draft can only pick men the board priced that night, so a rule that would have reached an '
 'unpriced player cannot be restated.',
 'Depth charts are read as they stand today, not as they stood in week 1 -- nfl_stats.load_depth '
 'takes the latest chart. It only affects players with no 2026 snaps (basis prior+depth).',
 'The blend coefficients (NFLLAYER) were fitted on 2022-25 and the price cap on 2024-25, so '
 'neither was fitted on these nights.',
]


def main():
    write = '--write' in sys.argv
    # POSTED baseline: the untouched v1 file once it exists, so re-running never restates a
    # restatement and `actual_record` keeps quoting what was actually posted.
    posted = 'nfl_season_v1_actual.json' if os.path.exists('nfl_season_v1_actual.json') else 'nfl_season.json'
    season = json.load(open('nfl_season.json', encoding='utf-8'))
    base = json.load(open(posted, encoding='utf-8'))
    nights = {}
    cats, hist, run = {}, [], 0.0
    for date in season['graded_nights']:
        rows, missing, _log = restate(date)
        nights[date] = rows
        for r in rows:
            c = cats.setdefault(r['kind'], dict(graded=0, won=0, units=0.0, staked=0.0))
            c['graded'] += 1; c['won'] += int(r['won'])
            c['units'] = round(c['units'] + r['net'], 4); c['staked'] += r['stake']
            run = round(run + r['net'], 4)
        hist.append(run)
        print(f"{date}: {len(rows):2d} tickets  {sum(r['net'] for r in rows):+7.2f}u"
              + (f"   [unpriced tonight: {', '.join(missing)}]" if missing else ''))
    print('\nRESTATED', {k: (v['won'], v['graded'], round(v['units'], 2)) for k, v in cats.items()},
          '=> total', round(sum(c['units'] for c in cats.values()), 2), 'u on',
          sum(c['staked'] for c in cats.values()), 'staked')
    print('POSTED  ', {k: (v['won'], v['graded'], round(v['units'], 2)) for k, v in base['cats'].items()},
          '=> total', round(sum(c['units'] for c in base['cats'].values()), 2))
    if not write:
        print('\n(dry run -- pass --write to rewrite nfl_season.json)')
        return 0
    if not os.path.exists('nfl_season_v1_actual.json'):
        json.dump(season, open('nfl_season_v1_actual.json', 'w'), indent=1)
        print('wrote nfl_season_v1_actual.json (the posted record, untouched)')
    out = dict(season)
    out['cats'] = cats
    out['history'] = [0.0] + hist
    out['restated'] = dict(date='2026-09-17', system=SYSTEM, caveats=CAVEATS, nights=nights,
                           actual_record='nfl/nfl_season_v1_actual.json (what was actually posted: '
                                         f"{sum(v['graded'] for v in base['cats'].values())} graded, "
                                         f"{round(sum(v['units'] for v in base['cats'].values()), 2)}u)")
    json.dump(out, open('nfl_season.json', 'w'), indent=1)
    print('wrote nfl_season.json (restated)')
    return 0


if __name__ == '__main__':
    sys.exit(main())
