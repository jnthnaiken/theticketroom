#!/usr/bin/env python3
"""
build_savant_training.py — all-time HR training table from Baseball Savant (Statcast).

WHY: the calibration.jsonl fits keep being starved for sample (3 nights of Kasper
extras, 22 of pitcher data). Statcast is public and goes back to 2015 for every
player, so we can build a training table of tens of thousands of batter-games and
settle "does contact / whiff / kHR-style stuff predict HR" on real volume — instead
of a handful of nights. This does NOT need Kasper and does NOT touch the daily
pipeline; it's a research puller.

WHAT IT PRODUCES: one row per (batter, game) with the HR outcome for that game and
POINT-IN-TIME features (batter's trailing-window batted-ball profile + the opposing
starter's trailing-window ALLOWED profile), every feature computed STRICTLY from
data BEFORE that game so nothing leaks the result.

    batter_id, batter, game_date, game_pk, team, opp, sp_id, sp,
    hr,                                  # outcome: did this batter homer in this game
    b_hh, b_brl, b_fb, b_pull, b_sweet, b_la, b_xwobacon, b_swstr, b_csw, b_n,   # batter pre-game
    p_hh, p_brl, p_fb, p_pull, p_sweet, p_la, p_xwobacon, p_swstr, p_csw, p_n    # opp SP allowed pre-game

WHERE IT RUNS: anywhere with internet + pip. NOT this offline sandbox — run it on
the GitHub Action or your laptop. Resumable: each day's raw Statcast is cached under
--cache, so a killed run picks up where it left off and re-runs are cheap.

    pip install pybaseball pandas numpy pyarrow
    python3 build_savant_training.py 2021-04-01 2024-10-01 --window 21 --out savant_training.parquet
    # quick sanity pass first:
    python3 build_savant_training.py 2024-06-01 2024-06-14

Then fit exactly like the calibration tests (grouped-by-game-date CV logistic, AUC),
e.g. does b_hh / p_swstr add over the batter expected-power core. The one thing this
CAN'T supply is historical odds (the market), so it answers "predicts HR" — not
"beats the price". Log odds forward, or source an odds archive, for that half.
"""
import sys, os, argparse, datetime as dt

def _need(mod):
    try:
        return __import__(mod)
    except ImportError:
        sys.exit(f"!! missing dependency '{mod}'. Run:  pip install pybaseball pandas numpy pyarrow")

pd = _need("pandas"); np = _need("numpy")

# ---- Statcast column subset we keep (smaller cache, faster) ----
KEEP = ['game_date','game_pk','batter','pitcher','player_name','events','description',
        'type','bb_type','launch_speed','launch_angle','estimated_woba_using_speedangle',
        'barrel','hc_x','hc_y','stand','p_throws','home_team','away_team','inning_topbot',
        'at_bat_number','pitch_number']

# swing descriptions (denominator for whiff/SwStr and CSW)
SWINGS = {'hit_into_play','foul','foul_tip','swinging_strike','swinging_strike_blocked',
          'foul_bunt','missed_bunt','bunt_foul_tip'}
WHIFFS = {'swinging_strike','swinging_strike_blocked','foul_tip','missed_bunt','bunt_foul_tip'}
CALLED = {'called_strike'}


def pull_day(day, cache):
    """One day of Statcast, cached to <cache>/<day>.parquet. Returns a (possibly empty) DataFrame."""
    fp = os.path.join(cache, f"{day}.parquet")
    if os.path.exists(fp):
        try:
            return pd.read_parquet(fp)
        except Exception:
            os.remove(fp)  # corrupt cache -> refetch
    pyb = _need("pybaseball")
    try:
        df = pyb.statcast(start_dt=day, end_dt=day, verbose=False)
    except Exception as e:
        print(f"  ! {day}: statcast pull failed ({e}) -> skipped (rerun to retry)")
        return pd.DataFrame(columns=KEEP)
    if df is None or df.empty:
        df = pd.DataFrame(columns=KEEP)
    else:
        df = df[[c for c in KEEP if c in df.columns]].copy()
    os.makedirs(cache, exist_ok=True)
    df.to_parquet(fp, index=False)
    return df


def daterange(a, b):
    d0 = dt.date.fromisoformat(a); d1 = dt.date.fromisoformat(b)
    d = d0
    while d <= d1:
        yield d.isoformat(); d += dt.timedelta(days=1)


def flags(df):
    """Add batted-ball / plate-discipline flags used by the rolling aggregates."""
    df = df.copy()
    ev = df['events'].fillna(''); desc = df['description'].fillna('')
    ls = pd.to_numeric(df['launch_speed'], errors='coerce')
    la = pd.to_numeric(df['launch_angle'], errors='coerce')
    inplay = df['type'].eq('X') | ev.isin(['single','double','triple','home_run']) | df['bb_type'].notna()
    df['is_bip']  = inplay.astype(float)                    # batted ball (denominator for contact rates)
    df['is_hh']   = ((ls >= 95) & inplay).astype(float)     # hard-hit
    if 'barrel' in df.columns:
        df['is_brl'] = (pd.to_numeric(df['barrel'], errors='coerce').fillna(0) > 0).astype(float)
    else:                                                   # derive barrel band if flag absent
        df['is_brl'] = (inplay & (ls >= 98) & la.between(26, 30)).astype(float)
    df['is_fb']    = (inplay & la.between(25, 50)).astype(float)   # fly ball
    df['is_sweet'] = (inplay & la.between(8, 32)).astype(float)    # sweet-spot LA
    pull = pd.Series(False, index=df.index)                 # pull = hit to pull field (hc geometry by handedness)
    if {'hc_x','hc_y'}.issubset(df.columns):
        ang = np.degrees(np.arctan2(pd.to_numeric(df['hc_x'],errors='coerce')-125.42,
                                    198.27-pd.to_numeric(df['hc_y'],errors='coerce')))
        pull = np.where(df['stand'].eq('R'), ang < -10, ang > 10)
    df['is_pull'] = (inplay & pd.Series(pull, index=df.index)).astype(float)
    df['la_val']  = np.where(inplay, la, np.nan)
    df['xwobacon']= np.where(inplay, pd.to_numeric(df['estimated_woba_using_speedangle'],errors='coerce'), np.nan)
    df['is_swing']= desc.isin(SWINGS).astype(float)
    df['is_whiff']= desc.isin(WHIFFS).astype(float)
    df['is_csw']  = (desc.isin(WHIFFS) | desc.isin(CALLED)).astype(float)   # CSW = called + swinging strike
    df['is_pitch']= 1.0
    return df


AGG = {'is_bip':'sum','is_hh':'sum','is_brl':'sum','is_fb':'sum','is_sweet':'sum','is_pull':'sum',
       'la_sum':'sum','xw_sum':'sum','xw_n':'sum','is_swing':'sum','is_whiff':'sum','is_csw':'sum','is_pitch':'sum'}


def daily_sums(df, id_col):
    """Collapse pitch rows to per-(player, date) sums so we can roll them by day."""
    d = df.copy()
    d['la_sum'] = d['la_val'].fillna(0); d['la_n'] = d['la_val'].notna().astype(float)
    d['xw_sum'] = d['xwobacon'].fillna(0); d['xw_n'] = d['xwobacon'].notna().astype(float)
    g = d.groupby([id_col,'game_date']).agg({**AGG,'la_n':'sum'}).reset_index()
    g['game_date'] = pd.to_datetime(g['game_date'])
    return g.rename(columns={id_col:'id'})


def rolling_pre(daily, window):
    """Trailing-`window`-day sums per player, EXCLUDING the current day (closed='left' ->
    strictly-before). Rate features are ratios of these leak-free sums."""
    cols = ['is_bip','is_hh','is_brl','is_fb','is_sweet','is_pull','la_sum','la_n',
            'xw_sum','xw_n','is_swing','is_whiff','is_csw','is_pitch']
    out = []
    for pid, g in daily.groupby('id'):
        g = g.sort_values('game_date').set_index('game_date')
        r = g[cols].rolling(f'{window}D', closed='left').sum()
        r['id'] = pid
        out.append(r.reset_index())
    R = pd.concat(out, ignore_index=True)
    def rate(num, den): return np.where(R[den] > 0, R[num] / R[den], np.nan)
    feat = pd.DataFrame({
        'id': R['id'], 'game_date': R['game_date'],
        'hh': rate('is_hh','is_bip'),    'brl': rate('is_brl','is_bip'),
        'fb': rate('is_fb','is_bip'),    'pull': rate('is_pull','is_bip'),
        'sweet': rate('is_sweet','is_bip'), 'la': rate('la_sum','la_n'),
        'xwobacon': rate('xw_sum','xw_n'),
        'swstr': rate('is_whiff','is_pitch'), 'csw': rate('is_csw','is_pitch'),
        'n': R['is_bip'],
    })
    return feat


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('start'); ap.add_argument('end')
    ap.add_argument('--window', type=int, default=21, help='trailing days for pre-game features (default 21)')
    ap.add_argument('--cache', default='savant_cache')
    ap.add_argument('--out', default='savant_training.parquet')
    a = ap.parse_args()

    days = list(daterange(a.start, a.end))
    print(f"pulling {len(days)} days {a.start}..{a.end} (cache={a.cache}) ...")
    frames = []
    for i, day in enumerate(days, 1):
        df = pull_day(day, a.cache)
        if not df.empty:
            frames.append(df)
        if i % 20 == 0 or i == len(days):
            print(f"  {i}/{len(days)} days ({sum(len(f) for f in frames):,} pitches)")
    if not frames:
        sys.exit("no data pulled")
    raw = pd.concat(frames, ignore_index=True)
    raw = raw.dropna(subset=['batter','pitcher','game_pk']).copy()
    raw['batter'] = raw['batter'].astype(int); raw['pitcher'] = raw['pitcher'].astype(int)
    fl = flags(raw)

    # ---- outcomes + who batted vs whom: one row per (game, batter) ----
    fl['bat_team'] = np.where(fl['inning_topbot'].eq('Top'), fl['away_team'], fl['home_team'])
    fl['pit_team'] = np.where(fl['inning_topbot'].eq('Top'), fl['home_team'], fl['away_team'])
    # opposing STARTER = pitcher on the lowest at_bat_number this team faced this game
    starts = (fl.sort_values('at_bat_number')
                .groupby(['game_pk','bat_team']).first().reset_index()[['game_pk','bat_team','pitcher']]
                .rename(columns={'pitcher':'sp_id'}))
    bg = (fl.groupby(['game_pk','game_date','batter','bat_team','pit_team'])
            .agg(hr=('events', lambda s: int((s == 'home_run').any())),
                 batter_name=('player_name','first'))
            .reset_index()
            .merge(starts, on=['game_pk','bat_team'], how='left'))
    bg['game_date'] = pd.to_datetime(bg['game_date'])

    # ---- point-in-time features ----
    print("building trailing-window features (leak-free) ...")
    bfeat = rolling_pre(daily_sums(fl, 'batter'), a.window)
    pfeat = rolling_pre(daily_sums(fl, 'pitcher'), a.window)

    tr = (bg.merge(bfeat.add_prefix('b_'), left_on=['batter','game_date'],
                   right_on=['b_id','b_game_date'], how='left')
            .merge(pfeat.add_prefix('p_'), left_on=['sp_id','game_date'],
                   right_on=['p_id','p_game_date'], how='left'))
    tr = tr.rename(columns={'batter':'batter_id','bat_team':'team','pit_team':'opp','batter_name':'batter'})
    drop = [c for c in tr.columns if c in ('b_id','b_game_date','p_id','p_game_date')]
    tr = tr.drop(columns=drop)
    keep = ['batter_id','batter','game_date','game_pk','team','opp','sp_id','hr',
            'b_hh','b_brl','b_fb','b_pull','b_sweet','b_la','b_xwobacon','b_swstr','b_csw','b_n',
            'p_hh','p_brl','p_fb','p_pull','p_sweet','p_la','p_xwobacon','p_swstr','p_csw','p_n']
    tr = tr[[c for c in keep if c in tr.columns]]

    tr.to_parquet(a.out, index=False)
    nhr = int(tr['hr'].sum()); haveb = int(tr['b_n'].fillna(0).gt(0).sum())
    print(f"\nwrote {a.out}: {len(tr):,} batter-games | {nhr:,} HR ({100*nhr/len(tr):.1f}%) "
          f"| {haveb:,} with a pre-game batter window ({a.window}d)")
    print("columns:", ', '.join(tr.columns))
    print("\nfit example (grouped-by-date CV, like calibration.jsonl):")
    print("  does batter hard-hit add over expected-contact? compare AUC of [b_xwobacon] vs [b_xwobacon,b_hh]")


if __name__ == '__main__':
    main()
