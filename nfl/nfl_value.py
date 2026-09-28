#!/usr/bin/env python3
"""nfl_value.py -- VALUESINGLES-2026-09-27. The football board picks VALUE, not favourites.

    python3 nfl_value.py scored.json fixtures.json --date 2026-09-28 [--cache ../slates/<date>/p_hist.json]

Runs after nfl_mock.py + nfl_injuries.py and before the draft. It adds three fields to every priced row
in scored.json and marks the ones the rule rejects `novalue: true`; the draft (soccer_draft.priceOk,
cfg.VALUE_ONLY) never picks a `novalue` player.

WHY (claude/football-layer-2026-09-27.md). Measured on every price the board actually held, 9 slates:
  * The book's margin sits in the long prices (<=+100 ~fair; +200..+700 ~21% worse; +700..1200 ~55%)
    and is loaded onto RUNNING BACKS and QBs (priced 20-40% above what they score); TEs/WRs near fair.
  * Where the model's probability beats the price at <=+400, the bets won; where it did not, they lost.
The rule (owner: "safe picks + a few long shots"):
  p_value = mean(p_model [the board's own model], p_hist [7-season history model])
  pick if p_value x decimal > 1 and
      price <= +400 (any position; QBs are already off the board, NOQB), or
      price  > +400 and WR/TE -- the best LONGSHOT_CAP of those by p_value. Never a longshot RB.
p_hist: HistGradientBoosting trained on 2018-23 nflverse player-games (hist_model.joblib): AUC 0.778 on
2025, calibrated by position. Features are pre-game only -- recent usage/share EWMs, team implied points,
team/defence TD rates, and each player's share re-split among the teammates ACTIVE that game.

NEVER FATAL. Any failure building p_hist -> the rule runs on p_model alone and says so.
The first successful build of a slate writes --cache (committed beside prices.json) so later builds
of the same slate do not re-download ~170MB of play-by-play.
"""
import json, os, sys, re, math, unicodedata, tempfile, urllib.request, traceback

LONGSHOT_CAP = 4
CORE_MAX_ODDS = 400
LONGSHOT_POS = ('WR', 'TE')
H = os.path.dirname(os.path.abspath(__file__))
MODEL = os.path.join(H, 'hist_model.joblib')
REL = 'https://github.com/nflverse/nflverse-data/releases/download/'
TM = {'LAR': 'LA', 'JAC': 'JAX', 'WSH': 'WAS', 'LVR': 'LV', 'KCC': 'KC', 'GBP': 'GB', 'NEP': 'NE',
      'NOS': 'NO', 'SFO': 'SF', 'TBB': 'TB'}


def nm(s):
    s = unicodedata.normalize('NFKD', s or '')
    s = ''.join(c for c in s if not unicodedata.combining(c)).lower()
    s = re.sub(r"[.'’]", '', s)
    s = re.sub(r'\s+(jr|sr|ii|iii|iv|v)$', '', s.strip())
    return re.sub(r'\s+', ' ', s)


def dec(o): return 1 + o / 100.0 if o > 0 else 1 + 100.0 / abs(o)


def _get(url, path):
    if os.path.exists(path) and os.path.getsize(path) > 1000:
        return path
    req = urllib.request.Request(url, headers={'User-Agent': 'ticketroom-nfl/1.0'})
    with urllib.request.urlopen(req, timeout=120) as r, open(path, 'wb') as f:
        f.write(r.read())
    return path


def hist_probs(scored, date, season):
    """{(name_key, team): p_hist} for the slate's players. Mirrors /home/claude/fb build/feat/layer."""
    import pandas as pd, numpy as np, joblib
    m, X = joblib.load(MODEL)
    tmp = os.environ.get('NFL_VALUE_CACHE_DIR') or tempfile.mkdtemp()
    G = pd.read_csv(_get(REL + 'schedules/games.csv', os.path.join(tmp, 'games.csv')))
    G = G[G.game_type == 'REG'].copy()
    G['date'] = pd.to_datetime(G.gameday)
    C = ['season', 'week', 'season_type', 'game_id', 'posteam', 'play_type', 'rush_attempt', 'pass_attempt',
         'rusher_player_id', 'receiver_player_id', 'yardline_100', 'touchdown', 'td_player_id',
         'two_point_attempt', 'qb_kneel', 'qb_spike']
    P = []; RO = []
    for y in range(2018, season + 1):
        p = pd.read_parquet(_get(REL + f'pbp/play_by_play_{y}.parquet', os.path.join(tmp, f'pbp_{y}.parquet')), columns=C)
        P.append(p[p.season_type == 'REG'])
        r = pd.read_parquet(_get(REL + f'weekly_rosters/roster_weekly_{y}.parquet', os.path.join(tmp, f'ro_{y}.parquet')),
                            columns=['season', 'week', 'team', 'position', 'status', 'full_name', 'gsis_id', 'game_type', 'years_exp'])
        RO.append(r)
    P = pd.concat(P, ignore_index=True); P = P[P.two_point_attempt != 1]
    D0 = pd.Timestamp(date)
    # only plays from games BEFORE the slate date (the slate itself may be live in the feed)
    gdate = G.set_index('game_id').date
    P = P[P.game_id.map(gdate) < D0]
    td = P[(P.touchdown == 1) & P.td_player_id.notna()].groupby(['game_id', 'td_player_id']).size().rename('tds').reset_index().rename(columns={'td_player_id': 'pid'})
    off = P[P.play_type.isin(['run', 'pass']) & (P.qb_kneel != 1) & (P.qb_spike != 1)].copy()
    off['rz'] = off.yardline_100 <= 20; off['i10'] = off.yardline_100 <= 10; off['i5'] = off.yardline_100 <= 5
    ru = off[off.rush_attempt == 1].dropna(subset=['rusher_player_id'])
    tg = off[(off.pass_attempt == 1) & off.receiver_player_id.notna()]
    def agg(df, idc, pre):
        return df.groupby(['game_id', 'posteam', idc]).agg(**{pre: ('rz', 'size'), pre + '_rz': ('rz', 'sum'), pre + '_i10': ('i10', 'sum'), pre + '_i5': ('i5', 'sum')}).reset_index().rename(columns={idc: 'pid'})
    pl = agg(ru, 'rusher_player_id', 'car').merge(agg(tg, 'receiver_player_id', 'tgt'), on=['game_id', 'posteam', 'pid'], how='outer').fillna(0)
    tm = off.groupby(['game_id', 'posteam']).agg(t_car=('rush_attempt', 'sum'), t_tgt=('pass_attempt', 'sum'), t_rz=('rz', 'sum'), t_i10=('i10', 'sum'), t_plays=('rz', 'size')).reset_index()
    otd = P[(P.touchdown == 1) & P.play_type.isin(['run', 'pass']) & P.td_player_id.notna()]
    tm = tm.merge(otd.groupby(['game_id', 'posteam']).size().rename('t_td').reset_index(), on=['game_id', 'posteam'], how='left').fillna({'t_td': 0})
    RO = pd.concat(RO)
    RO = RO[(RO.game_type == 'REG') & RO.position.isin(['RB', 'WR', 'TE', 'QB', 'FB']) & RO.status.isin(['ACT', 'INA']) & RO.gsis_id.notna()]
    # slate games + future roster rows
    Gs = G[(G.season == season) & (G.date == D0)]
    if not len(Gs):
        raise RuntimeError(f'no games.csv rows on {date}')
    wk = int(Gs.week.iloc[0])
    have = RO[(RO.season == season) & (RO.week == wk)]
    if not len(have):
        last = RO[RO.season == season].week.max()
        have = RO[(RO.season == season) & (RO.week == last)].copy(); have['week'] = wk
        RO = pd.concat([RO, have])
    h = G[['game_id', 'season', 'week', 'date', 'home_team', 'away_team', 'spread_line', 'total_line', 'roof', 'wind', 'temp']]
    A = pd.concat([h.assign(team=h.home_team, opp=h.away_team, home=1, imp=(h.total_line + h.spread_line) / 2),
                   h.assign(team=h.away_team, opp=h.home_team, home=0, imp=(h.total_line - h.spread_line) / 2)])
    A['dome'] = A.roof.isin(['dome', 'closed']).astype(int)
    A = A[A.date <= D0]
    TG = A.merge(tm.rename(columns={'posteam': 'team'}), on=['game_id', 'team'], how='left').sort_values(['team', 'date'])
    TG = TG.merge(tm.rename(columns={'posteam': 'opp', 't_td': 'o_td', 't_rz': 'o_rz'})[['game_id', 'opp', 'o_td', 'o_rz']], on=['game_id', 'opp'], how='left')
    for c in ['t_td', 't_rz', 't_i10', 't_plays', 't_car', 't_tgt']:
        TG['team_' + c + '_ewm'] = TG.groupby('team')[c].transform(lambda s: s.shift(1).ewm(halflife=6, min_periods=1).mean())
    d = TG[['game_id', 'opp', 'date', 't_td', 't_rz']].rename(columns={'opp': 'def', 't_td': 'a_td', 't_rz': 'a_rz'}).sort_values(['def', 'date'])
    d['def_td_ewm'] = d.groupby('def').a_td.transform(lambda s: s.shift(1).ewm(halflife=6, min_periods=1).mean())
    d['def_rz_ewm'] = d.groupby('def').a_rz.transform(lambda s: s.shift(1).ewm(halflife=6, min_periods=1).mean())
    TG = TG.merge(d[['game_id', 'def', 'def_td_ewm', 'def_rz_ewm']].rename(columns={'def': 'opp'}), on=['game_id', 'opp'], how='left')
    ro = RO.rename(columns={'gsis_id': 'pid'})
    U = ro.merge(TG[['game_id', 'season', 'week', 'team', 'opp', 'date', 'home', 'imp', 'total_line', 'spread_line', 'dome', 'wind', 'temp',
                     't_car', 't_tgt', 't_rz', 't_i10', 't_td'] + [c for c in TG.columns if c.endswith('_ewm')]], on=['season', 'week', 'team'], how='inner')
    U = U.merge(pl.drop(columns=['posteam']), on=['game_id', 'pid'], how='left').merge(td, on=['game_id', 'pid'], how='left')
    for c in ['car', 'car_rz', 'car_i10', 'car_i5', 'tgt', 'tgt_rz', 'tgt_i10', 'tgt_i5', 'tds']:
        U[c] = U[c].fillna(0)
    U['future'] = U.date == D0
    U['played'] = ((U.car + U.tgt) > 0) | (U.tds > 0) | U.future
    U['opp_i10'] = U.car_i10 + U.tgt_i10; U['opp_rz'] = U.car_rz + U.tgt_rz; U['opp_i5'] = U.car_i5 + U.tgt_i5
    U['s_car'] = U.car / U.t_car.clip(lower=1); U['s_tgt'] = U.tgt / U.t_tgt.clip(lower=1)
    U['s_rz'] = U.opp_rz / U.t_rz.clip(lower=1); U['s_i10'] = U.opp_i10 / U.t_i10.clip(lower=1)
    U = U.sort_values(['pid', 'date', 'status']).drop_duplicates(['pid', 'game_id'])
    # injury report: a priced man the board has ruled out counts as inactive for the teammates' re-split
    outk = {(nm(s['name']), TM.get(s['team'], s['team'])) for s in scored if s.get('out') or s.get('void')}
    U['inactive'] = ((U.status == 'INA') & ~U.played) | (U.future & np.array([(nm(a), b) in outk for a, b in zip(U.full_name, U.team)], dtype=bool))
    st = ['car', 'tgt', 'car_rz', 'tgt_rz', 'opp_i10', 'opp_i5', 'tds', 's_car', 's_tgt', 's_rz', 's_i10']
    Up = U[U.played & ~U.future].copy().sort_values(['pid', 'date'])
    S = Up[['pid', 'date', 'season']].copy()
    for hl in (2, 6):
        for c in st:
            S[f'{c}_h{hl}'] = Up.groupby('pid')[c].transform(lambda s: s.ewm(halflife=hl, min_periods=1).mean())
    S['n_prev'] = Up.groupby('pid').cumcount() + 1
    S['last_date'] = S.date
    S = S.rename(columns={'season': 'last_season'}).sort_values('date')
    U = pd.merge_asof(U.sort_values('date'), S, on='date', by='pid', allow_exact_matches=False)
    U['n_prev'] = U.n_prev.fillna(0)
    U['n_prev_season'] = U.groupby(['pid', 'season']).played.transform(lambda s: s.shift(1).fillna(0).cumsum())
    U['days_since'] = (U.date - U.last_date).dt.days
    F = U[U.future].copy()
    act = ~F.inactive.astype(bool)
    for c in ['s_rz_h6', 's_i10_h6', 's_car_h6', 's_tgt_h6', 's_rz_h2', 's_car_h2', 's_tgt_h2', 'tds_h6']:
        v = F[c].fillna(0).where(act, 0)
        tot = v.groupby([F.game_id, F.team]).transform('sum')
        F['a_' + c] = np.where(act, F[c].fillna(0) / tot.replace(0, np.nan), np.nan)
        F['vac_' + c] = F[c].fillna(0).groupby([F.game_id, F.team]).transform('sum') - tot
    F['team_td_exp'] = F.imp / 7.0
    for a, b in [('L_rz_a', 'a_s_rz_h6'), ('L_i10_a', 'a_s_i10_h6'), ('L_car_a', 'a_s_car_h6'), ('L_tgt_a', 'a_s_tgt_h6')]:
        F[a] = F.team_td_exp * F[b]
    F['pos'] = F.position.map({'QB': 0, 'RB': 1, 'WR': 2, 'TE': 3, 'FB': 1})
    F['L_i10'] = F.team_td_exp * F.s_i10_h6; F['L_rz'] = F.team_td_exp * F.s_rz_h6
    F['p'] = m.predict_proba(F[X])[:, 1]
    return {(nm(n), t): float(p) for n, t, p in zip(F.full_name, F.team, F.p)}


def main():
    a = sys.argv[1:]
    scored_p, fx_p = a[0], a[1]
    date = a[a.index('--date') + 1]
    cache = a[a.index('--cache') + 1] if '--cache' in a else None
    scored = json.load(open(scored_p, encoding='utf-8'))
    fx = json.load(open(fx_p, encoding='utf-8'))
    season = int(fx.get('season') or date[:4])
    ph, src = {}, 'none'
    if cache and os.path.exists(cache):
        ph = {tuple(k.split('|', 1)): v for k, v in json.load(open(cache)).items()}; src = 'cache'
    else:
        try:
            ph = hist_probs(scored, date, season); src = 'built'
            if cache and ph:
                os.makedirs(os.path.dirname(cache), exist_ok=True)
                json.dump({f'{k[0]}|{k[1]}': round(v, 5) for k, v in ph.items()}, open(cache, 'w'), indent=0)
        except Exception as e:
            print(f'::warning::nfl_value: history model unavailable ({e.__class__.__name__}: {e}) -- rule runs on p_model alone')
            traceback.print_exc()
    joined = 0
    for s in scored:
        k = (nm(s['name']), TM.get(s['team'], s['team']))
        s['p_hist'] = ph.get(k)
        if s['p_hist'] is not None: joined += 1
        pm = s.get('p_model')
        pv = (pm + s['p_hist']) / 2 if (pm is not None and s['p_hist'] is not None) else (pm if pm is not None else s['p_hist'])
        s['p_value'] = pv
        s['ev_value'] = (pv * dec(s['odds']) - 1) if (pv is not None and s.get('odds') is not None) else None
    ok = lambda s: s['ev_value'] is not None and s['ev_value'] > 0 and s.get('pos') != 'QB' and not s.get('out') and not s.get('void')
    core = [s for s in scored if ok(s) and s['odds'] <= CORE_MAX_ODDS]
    longs = sorted([s for s in scored if ok(s) and s['odds'] > CORE_MAX_ODDS and s.get('pos') in LONGSHOT_POS],
                   key=lambda s: -s['p_value'])[:LONGSHOT_CAP]
    keep = {s['name'] for s in core + longs}
    for s in scored:
        s['novalue'] = s['name'] not in keep
        s['value_kind'] = ('core' if s in core else 'longshot') if s['name'] in keep else None
    json.dump(scored, open(scored_p, 'w', encoding='utf-8'), indent=1)
    print(f'VALUESINGLES: p_hist {src}, joined {joined}/{len(scored)}; picks {len(core)} core (<=+{CORE_MAX_ODDS}) + '
          f'{len(longs)} longshot WR/TE (cap {LONGSHOT_CAP})')
    for s in sorted(core + longs, key=lambda s: -s['ev_value']):
        print(f"   {s['value_kind']:8s} {s['name']:24s} {s.get('pos',''):2s} {s['odds']:+5d}  p_model {s.get('p_model') or 0:.3f}"
              f"  p_hist {s['p_hist'] if s['p_hist'] is not None else float('nan'):.3f}  p {s['p_value']:.3f}  ev {s['ev_value']:+.3f}")


if __name__ == '__main__':
    main()
