#!/usr/bin/env python3
"""
fit_bvp.py -- does a batter's history against THIS starter predict a home run?

THE QUESTION, IN THE OWNER'S WORDS (2026-09-12): "austin riley yesterday had a history of
8 hr's vs nola, hit his 9th. and that was never accounted for and seems like a huge tell."

It is not accounted for. The board has never carried a batter-vs-pitcher term. Before one is
added, it gets measured the same way every other signal in _SIG was measured -- on the
2015-2024 Statcast table, leak-free, in the per-slate z-space build15 actually scores in.

WHY THIS SCRIPT IS PARANOID ABOUT SAMPLE
    The same week this was asked, Josue De Paula anchored three tickets off a Kasper card
    with ONE batted ball on it (pb 100.0 / hh 100.0 -> powraw 10,000 vs a field median of
    191). That is the identical failure mode pointed the other way: a rate with nothing
    under it. An unregressed BvP term is WORSE, because the denominators are smaller -- a
    man who is 2-for-3 with a homer off tonight's starter would read 0.333 HR/meeting and
    rocket up a board built on raw rates. So every form tested here is regressed toward the
    batter's OWN baseline, and the raw form is tested too, on purpose, to show what it does.

WHAT IS MEASURED (all expanding and as-of-date -- a row never sees its own outcome or any
later meeting, so nothing here is hindsight):
    m        prior meetings between this batter and this starter
    h        prior HR by this batter in those meetings
    b_rate   the batter's own prior HR/game, itself shrunk to the league rate so a September
             call-up's first week does not read 1.000 or 0.000
    lift_K   (h + K*b_rate)/(m + K) - b_rate      <- the tested signal, for a grid of K
             K is the meeting count at which the matchup is believed half as much as the
             batter's own baseline. K=0 is the raw unregressed rate difference.

    The subtraction matters and is the whole point: the question is never "does he homer a
    lot", the model already knows that. It is "does he homer MORE off THIS arm than off
    everyone else". Riley's 8 off Nola only counts as a tell to the extent it is above the
    rate at which Riley homers generally.

REPORTED
    1. standalone grouped-CV AUC of each lift_K, and of the raw counts h and m, so a K that
       only works because it is smuggling in "this is a veteran with many meetings" shows up
    2. incremental AUC over the 5-signal proxy baseline that produced the live _SIG weights
    3. the implied _SIG weight if it were added
    4. the same thing restricted to rows with m >= floor, for a range of floors -- the
       operational question is not "does BvP predict" but "above how many meetings", and how
       often a slate even contains such a matchup
    5. a Riley check: the highest-lift rows in the table and whether they actually homered

WHAT THIS CANNOT ANSWER
    The table carries no odds, so every number is "predicts HR", never "beats the price".
    A term can be real and still be fully in the market -- BvP is the single most quoted
    stat on a broadcast, so if anything is already priced, it is this one. Treat a positive
    result here as permission to test against price, not as an edge.

    pip install pandas numpy pyarrow scikit-learn
    python3 fit_bvp.py "table/*.parquet"
"""
import sys, glob, warnings
warnings.filterwarnings('ignore')

import numpy as np
import pandas as pd
from sklearn.linear_model import LogisticRegression
from sklearn.model_selection import GroupKFold
from sklearn.metrics import roc_auc_score

BASE = ['b_brl', 'b_hh', 'b_la', 'b_xwobacon', 'p_brl']   # the 5-signal proxy basket fit_savant.py used
MIN_BIP = 20            # same trailing-window requirement as fit_savant.py, so the baseline is comparable
K_BAT = 60              # games of shrinkage on the batter's OWN baseline (his rate is also an estimate)
K_GRID = [0, 5, 10, 15, 25, 40, 60, 100, 200]
FLOORS = [0, 1, 3, 5, 10, 15, 20, 30]
SEEN = [5, 10, 15, 20]  # "has faced this arm N+ times" -- the FAMILIARITY flag, not the rate
LOOKBACK = 15           # team-games of appearance history behind a projected nine
LINEUP = 9


def hr_(t):
    print('\n' + '=' * 78); print(t); print('=' * 78, flush=True)


def statsapi_names(ids):
    """id -> full name, from StatsAPI. Display only; a failure here cannot change a number."""
    import json, urllib.request
    ids = [int(i) for i in ids if pd.notna(i)]
    out = {}
    for i in range(0, len(ids), 100):
        chunk = ','.join(str(x) for x in ids[i:i + 100])
        try:
            u = 'https://statsapi.mlb.com/api/v1/people?personIds=%s' % chunk
            with urllib.request.urlopen(u, timeout=20) as r:
                for p in json.load(r).get('people', []):
                    out[p['id']] = p.get('fullName') or str(p['id'])
        except Exception as e:
            print('  (name lookup failed, showing ids: %s)' % e)
            break
    return out


def zbyslate(df, cols):
    """Z-score each feature WITHIN game_date -- build15 standardizes per slate, so the fit must too."""
    out = df[cols].copy()
    g = df.groupby('game_date')
    for c in cols:
        mu = g[c].transform('mean')
        sd = g[c].transform('std').replace(0, np.nan)
        out[c] = ((df[c] - mu) / sd).fillna(0.0)
    return out


def cv_auc(X, y, groups, n=5):
    gk = GroupKFold(n_splits=n)
    aucs, coefs = [], []
    for tr, te in gk.split(X, y, groups):
        m = LogisticRegression(max_iter=2000, C=1.0)
        m.fit(X[tr], y[tr])
        aucs.append(roc_auc_score(y[te], m.predict_proba(X[te])[:, 1]))
        coefs.append(m.coef_[0])
    return float(np.mean(aucs)), float(np.std(aucs)), np.mean(coefs, axis=0)


def build_bvp(d, league):
    """Expanding, leak-free BvP history. Every column here is strictly PRIOR to the row's own game."""
    d = d.sort_values(['game_date', 'game_pk']).reset_index(drop=True)

    # --- prior meetings and prior HR vs THIS starter -------------------------------------
    pair = d.groupby(['batter_id', 'sp_id'])
    d['m'] = pair.cumcount()                                  # games before this one
    d['h'] = pair['hr'].cumsum() - d['hr']                    # HR before this one (own outcome removed)

    # --- the batter's OWN prior rate, shrunk to league so early careers are not 0.000/1.000
    bat = d.groupby('batter_id')
    n_b = bat.cumcount()
    h_b = bat['hr'].cumsum() - d['hr']
    d['b_rate'] = (h_b + K_BAT * league) / (n_b + K_BAT)

    for K in K_GRID:
        d['lift_%d' % K] = ((d['h'] + K * d['b_rate']) / (d['m'] + K).replace(0, np.nan)
                            - d['b_rate']).fillna(0.0)
    return d


def oof(X, y, groups, n=5):
    """Out-of-fold predicted probability. Every row is scored by a model that never saw it,
    and folds are whole slates -- so a board built from these numbers is a board the model
    could actually have built on the night, not hindsight."""
    gk = GroupKFold(n_splits=n)
    p = np.zeros(len(y))
    for tr, te in gk.split(X, y, groups):
        m = LogisticRegression(max_iter=2000, C=1.0)
        m.fit(X[tr], y[tr])
        p[te] = m.predict_proba(X[te])[:, 1]
    return p


def tickets(d, legs=4, min_bats=50, deep=10):
    """THE SCOREBOARD THAT IS NOT AUC.

    Build a <legs>-leg slip on every slate three ways, then count what actually happened.
    No odds exist in this table, so this is 'did the legs hit', not 'did it beat the price'
    -- but a leg that hits is the thing a ticket is made of, and that is the currency the
    question was asked in.

        A  BOARD        top <legs> by the model, out-of-fold
        B  BOARD+BvP    top <legs> by the same model with the BvP term added
        C  FORCE        top <legs>-1 by the model, plus the slate's single biggest tell
                        (most lift, >= <deep> prior meetings) -- the rule the question
                        actually proposes: if a guy owns tonight's starter, put him on.
    """
    out = {}
    for label, col in (('A  BOARD', 'p_base'), ('B  BOARD+BvP', 'p_bvp')):
        legs_hit = swaps = 0
        cash = {k: 0 for k in range(2, legs + 1)}
        slates = 0
        for _, g in d.groupby('game_date'):
            if len(g) < min_bats: continue
            slates += 1
            pick = g.nlargest(legs, col)
            k = int(pick.hr.sum()); legs_hit += k
            for j in range(2, legs + 1):
                if k >= j: cash[j] += 1
        out[label] = (slates, legs_hit, cash, swaps)

    legs_hit = swaps = 0
    cash = {k: 0 for k in range(2, legs + 1)}
    slates = 0
    for _, g in d.groupby('game_date'):
        if len(g) < min_bats: continue
        slates += 1
        core = g.nlargest(legs - 1, 'p_base')
        rest = g.drop(core.index)
        tell = rest[rest.m >= deep]
        if len(tell):
            pick = pd.concat([core, tell.nlargest(1, 'lift_25')]); swaps += 1
        else:
            pick = g.nlargest(legs, 'p_base')
        k = int(pick.hr.sum()); legs_hit += k
        for j in range(2, legs + 1):
            if k >= j: cash[j] += 1
    out['C  FORCE the tell'] = (slates, legs_hit, cash, swaps)

    print('  %d-leg slip, one per slate, %d slates with >= %d usable bats\n' % (legs, out['A  BOARD'][0], min_bats))
    print('  %-20s %10s %9s %10s %10s' % ('', 'legs hit', 'hit rate', '2+ legs', '%d legs' % legs))
    base = None
    for label in ('A  BOARD', 'B  BOARD+BvP', 'C  FORCE the tell'):
        s, lh, c, sw = out[label]
        tot = s * legs
        line = '  %-20s %10d %8.2f%% %10d %10d' % (label, lh, 100 * lh / tot, c[2], c[legs])
        if base is None: base = lh
        else: line += '   (%+d legs)' % (lh - base)
        print(line)
    sw = out['C  FORCE the tell'][3]
    print('\n  C swapped a tell onto the slip on %d of %d slates (%.0f%%) -- on the rest there was'
          % (sw, out['C  FORCE the tell'][0], 100 * sw / max(1, out['C  FORCE the tell'][0])))
    print('  no bat with %d+ meetings available, so C is identical to A there. The difference' % deep)
    print('  below is therefore concentrated in those %d slates, not diluted across all of them.' % sw)


def seen_flag(d):
    """'Give him a boost if he has faced this arm 15+ times.' A DIFFERENT claim from the rate
    one -- not 'he owns this guy' but 'he has seen the stuff, he knows what is coming'. It
    deserves its own test, and it is the only variable in this whole study that beat a coin
    flip standalone (m, AUC 0.5140), so it gets the honest version.

    The comparison is each flagged row against THAT HITTER'S OWN leak-free prior rate
    (`b_rate`), summed -- not against the league. Comparing to the league would 'prove' the
    flag works when all it has found is that good hitters accumulate meetings."""
    print('  %-10s %9s %11s %9s %10s %9s %7s' %
          ('flag', 'rows', 'per slate', 'HR obs', 'HR exp*', 'diff', 'z'))
    for T in SEEN:
        g = d[d.m >= T]
        if not len(g):
            print('  m >= %-5d %9d  -- never fires' % (T, 0)); continue
        obs = float(g.hr.sum()); exp = float(g.b_rate.sum())
        sd = float((g.b_rate * (1 - g.b_rate)).sum()) ** 0.5
        z = (obs - exp) / sd if sd > 0 else 0.0
        print('  m >= %-5d %9d %11.2f %9.0f %10.1f %+9.1f %+7.2f'
              % (T, len(g), len(g) / d.game_date.nunique(), obs, exp, obs - exp, z))
    print('\n  * expected AT THE HITTER\'S OWN RATE. "diff" is the entire value of the flag:')
    print('    every homer above the league rate that is not in "diff" is just the hitter,')
    print('    and the board already prices the hitter.')

    print('\n  IS IT EVEN AVAILABLE? m >= 15 by season (fires per slate):')
    d = d.copy(); d['yr'] = d.game_date.dt.year
    for yr, g in d.groupby('yr'):
        n = int((g.m >= 15).sum()); sl = g.game_date.nunique()
        print('    %d  %6d rows / %4d slates = %.2f per slate' % (yr, n, sl, n / sl))
    print('\n  A flag that fires on under one bat a night cannot move a board, however right')
    print('  it is. Note also the schedule: fewer intra-division starts and shorter outings')
    print('  mean the deep matchup is rarer NOW than this ten-season average makes it look.')


def projected(d, feats):
    """THE LINEUP FIX.

    The table has a row only for a batter who PLAYED, so picking from it is picking from a
    lineup card that did not exist yet. That is hindsight and it invalidated the first ticket
    run. Here the pool is rebuilt from what was knowable: each team's likely nine, by
    appearances in that team's previous LOOKBACK games ONLY. A projected bat who then does
    not appear stays on the slip and VOIDS -- the same refund grade_night gives a late
    scratch. Features and BvP counts for a void row are carried forward from his last game,
    which is what a real board would have had.

    This is a stand-in for RotoWire projections, not the real thing. It is wrong in
    individual cases. It is right about the SHAPE of the problem: you commit before you know."""
    d = d.sort_values(['game_date', 'game_pk']).reset_index(drop=True)
    starters = d.groupby(['game_date', 'team'])['sp_id'].first().reset_index()

    # --- each team's projected nine, from prior games only -------------------------------
    from collections import Counter, deque
    rows = []
    for team, g in d.groupby('team'):
        hist, cnt = deque(), Counter()
        for dt, day in g.groupby('game_date'):
            if hist:
                for b in [b for b, _ in cnt.most_common(LINEUP)]:
                    rows.append((dt, team, b))
            roster = list(day.batter_id.unique())
            hist.append(roster); cnt.update(roster)
            if len(hist) > LOOKBACK:
                cnt.subtract(hist.popleft()); cnt += Counter()
    proj = pd.DataFrame(rows, columns=['game_date', 'team', 'batter_id'])
    proj = proj.merge(starters, on=['game_date', 'team'], how='left').dropna(subset=['sp_id'])
    proj['sp_id'] = proj['sp_id'].astype(int)

    # --- who actually played -------------------------------------------------------------
    keep = ['game_date', 'batter_id', 'hr'] + feats + ['b_rate', 'm', 'h', 'lift_25']
    out = proj.merge(d[keep], on=['game_date', 'batter_id'], how='left', suffixes=('', '_y'))
    out['void'] = out.hr.isna()

    # --- carry forward for the ones who did not: features, own rate ----------------------
    src = d[['batter_id', 'game_date'] + feats + ['b_rate']].sort_values('game_date')
    miss = out[out.void].sort_values('game_date')
    if len(miss):
        filled = pd.merge_asof(miss[['game_date', 'batter_id']], src, on='game_date',
                               by='batter_id', direction='backward', allow_exact_matches=False)
        for c in feats + ['b_rate']:
            out.loc[out.void, c] = filled[c].values

        # --- and the pair counts, exactly: the state left by their last actual meeting ----
        pair = d[['batter_id', 'sp_id', 'game_date', 'm', 'h', 'hr']].copy()
        pair['m_after'] = pair.m + 1
        pair['h_after'] = pair.h + pair.hr
        pair = pair[['batter_id', 'sp_id', 'game_date', 'm_after', 'h_after']].sort_values('game_date')
        pm = pd.merge_asof(miss[['game_date', 'batter_id', 'sp_id']].sort_values('game_date'),
                           pair, on='game_date', by=['batter_id', 'sp_id'],
                           direction='backward', allow_exact_matches=False)
        out.loc[out.void, 'm'] = pm['m_after'].fillna(0).values
        out.loc[out.void, 'h'] = pm['h_after'].fillna(0).values
        out.loc[out.void, 'lift_25'] = 0.0

    out['hr'] = out.hr.fillna(0).astype(int)
    out = out.dropna(subset=feats + ['b_rate'])
    return out


def tickets_void(d, legs=4, min_bats=50, deep=15):
    """Same three rules, graded the way the product grades: a void leg is a REFUND, not a
    loss. It shrinks the slip -- an N-leg slip with v voids cashes when the other N-v hit --
    which is exactly why durability is worth something and why it has to be counted, not
    argued about."""
    res = {}
    rules = [('A  BOARD', 'p_base', None), ('B  BOARD+BvP', 'p_bvp', None),
             ('C  FORCE 15+ seen', 'p_base', 'm')]
    for label, col, force in rules:
        hits = voids = cash = fired = slates = 0
        for _, g in d.groupby('game_date'):
            if len(g) < min_bats: continue
            slates += 1
            if force:
                core = g.nlargest(legs - 1, col)
                pool = g.drop(core.index)
                tell = pool[pool.m >= deep]
                pick = pd.concat([core, tell.nlargest(1, 'lift_25')]) if len(tell) else g.nlargest(legs, col)
                fired += 1 if len(tell) else 0
            else:
                pick = g.nlargest(legs, col)
            v = int(pick['void'].sum()); k = int(pick.hr.sum())
            voids += v; hits += k
            if v < legs and k == legs - v: cash += 1
        res[label] = (slates, hits, voids, cash, fired)

    print('  %d-leg slip, %d slates, pool = PROJECTED nine per team (no lineup foresight)\n'
          % (legs, res['A  BOARD'][0]))
    print('  %-20s %9s %8s %9s' % ('', 'legs hit', 'voids', 'cashed'))
    base = None
    for label, _, _ in rules:
        s, hits, voids, cash, fired = res[label]
        line = '  %-20s %9d %8d %9d' % (label, hits, voids, cash)
        if base is None: base = (hits, cash)
        else: line += '   (%+d legs, %+d cashes)' % (hits - base[0], cash - base[1])
        print(line)
    fired = res['C  FORCE 15+ seen'][4]
    print('\n  C found a 15+-meeting bat to swap in on %d of %d slates (%.0f%%).'
          % (fired, res['C  FORCE 15+ seen'][0], 100 * fired / max(1, res['C  FORCE 15+ seen'][0])))


def statsapi_id(name):
    import json, urllib.request
    try:
        u = 'https://statsapi.mlb.com/api/v1/people/search?names=%s' % name.replace(' ', '%20')
        with urllib.request.urlopen(u, timeout=20) as r:
            ppl = json.load(r).get('people', [])
        return ppl[0]['id'] if ppl else None
    except Exception:
        return None


def pair_report(d, pairs):
    """Every start one named hitter made against one named arm, inside the table's window."""
    for bname, pname in pairs:
        bid, pid = statsapi_id(bname), statsapi_id(pname)
        if not bid or not pid:
            print('  (could not resolve %s / %s)' % (bname, pname)); continue
        g = d[(d.batter_id == bid) & (d.sp_id == pid)].sort_values('game_date')
        if g.empty:
            print('  %s vs %s: no starts in the table window' % (bname, pname)); continue
        own = d[d.batter_id == bid]
        print('  %s vs %s, %s .. %s' % (bname, pname, d.game_date.min().date(), d.game_date.max().date()))
        print('    starts faced        : %d' % len(g))
        print('    HR in those starts  : %d  (%.1f%% of games)' % (g.hr.sum(), 100 * g.hr.mean()))
        print('    his rate vs EVERYONE: %.1f%% of games  (%d HR in %d games)'
              % (100 * own.hr.mean(), own.hr.sum(), len(own)))
        print('    league              : %.1f%%' % (100 * d.hr.mean()))
        print('\n    Read the middle line first. The gap between line 2 and line 3 is the whole')
        print('    claim -- everything above line 3 is just the hitter, and the board already')
        print('    knows the hitter. NOTE the table stops in 2024, so later meetings are absent.')


def main():
    src = sys.argv[1] if len(sys.argv) > 1 else None
    cand = sorted(glob.glob(src)) if src else sorted(glob.glob('**/savant_training*.parquet', recursive=True))
    if not cand:
        sys.exit('!! no savant_training*.parquet found')
    src = cand[0]

    print(f'reading {src} ...', flush=True)
    df = pd.read_parquet(src)
    need = ['batter_id', 'sp_id', 'game_date', 'game_pk', 'hr']
    miss = [c for c in need if c not in df.columns]
    if miss:
        sys.exit(f'!! table is missing {miss} -- cannot build BvP history from it')
    df = df.dropna(subset=['batter_id', 'sp_id']).copy()
    df['game_date'] = pd.to_datetime(df['game_date'])
    league = float(df['hr'].mean())
    print(f'  {len(df):,} batter-games | {int(df.hr.sum()):,} HR ({100*league:.2f}%) '
          f'| {df.game_date.min().date()} .. {df.game_date.max().date()}')

    hr_('1. BUILDING LEAK-FREE BvP HISTORY')
    d = build_bvp(df, league)
    print(f'  distinct batter-starter pairs: {d.groupby(["batter_id","sp_id"]).ngroups:,}')
    for f in FLOORS:
        g = d[d.m >= f]
        print('  rows with m >= %-3d : %8d (%5.1f%% of table) | HR %5.2f%%'
              % (f, len(g), 100*len(g)/len(d), 100*g.hr.mean() if len(g) else 0))
    print('\n  THE SHAPE OF THE PROBLEM: the deep-history matchups the question is about are rare.')
    print('  Whatever the signal is worth, it can only be worth it on that slice of a slate.')

    hr_('2. STANDALONE AUC -- does BvP predict a home run AT ALL?')
    feats = sorted(set(BASE) & set(d.columns))
    dd = d.dropna(subset=feats + ['b_n']).copy()
    dd = dd[dd['b_n'] >= MIN_BIP]
    if 'p_n' in dd.columns:
        dd = dd[dd['p_n'] >= MIN_BIP]
    dd = dd.sort_values('game_date').reset_index(drop=True)
    y = dd['hr'].astype(int).values
    groups = dd['game_date'].values
    print(f'  usable rows (>= {MIN_BIP} BIP both sides, complete features): {len(dd):,} '
          f'| {int(dd.hr.sum()):,} HR')

    print('\n  %-12s %8s  %s' % ('signal', 'AUC', 'read'))
    for c in ['m', 'h'] + ['lift_%d' % K for K in K_GRID]:
        Z = zbyslate(dd, [c]).values
        a, s, _ = cv_auc(Z, y, groups)
        tag = ('raw meeting count' if c == 'm' else
               'raw prior HR count' if c == 'h' else
               'UNREGRESSED rate diff -- the De Paula form' if c == 'lift_0' else
               'shrunk, K=%s' % c.split('_')[1])
        print('  %-12s %8.4f  %s' % (c, a, tag))
    print('\n  0.5000 is a coin flip. For scale: the whole 5-signal basket is ~0.596 on this table.')

    hr_('3. INCREMENTAL -- does it add anything the board does not already have?')
    Zb = zbyslate(dd, feats).values
    ab, sb, _ = cv_auc(Zb, y, groups)
    print(f'  baseline {feats} : AUC {ab:.4f} (sd {sb:.4f})')
    best = None
    for K in K_GRID:
        c = 'lift_%d' % K
        Z = zbyslate(dd, feats + [c]).values
        a, s, coef = cv_auc(Z, y, groups)
        pos = np.clip(coef, 0, None)
        w = pos[-1] / pos.sum() if pos.sum() > 0 else 0.0
        print('  + %-10s : AUC %.4f (%+.4f)  coef %+.4f  implied _SIG weight %.4f'
              % (c, a, a - ab, coef[-1], w))
        if best is None or a > best[1]:
            best = (c, a, w)
    print('\n  DECISION RULE, SET BEFORE LOOKING: ship only if the best incremental AUC clears the')
    print('  baseline by more than the fold sd above (%.4f). Anything smaller is noise dressed as' % sb)
    print('  a finding, and this board already carries one unfitted weight (W_PSW) too many.')

    hr_('4. THE SAME THING, ONLY ON DEEP MATCHUPS')
    print('  If BvP is real anywhere it is where the history is thick. Restricting to m >= floor,')
    print('  best-K incremental AUC on that slice (n shown -- watch it collapse):')
    cbest = best[0]
    for f in FLOORS[1:]:
        g = dd[dd.m >= f]
        if len(g) < 5000 or g.hr.sum() < 300 or g.game_date.nunique() < 50:
            print('  m >= %-3d : n=%-7d -- too few to fit' % (f, len(g)))
            continue
        yg = g['hr'].astype(int).values; gg = g['game_date'].values
        a0, s0, _ = cv_auc(zbyslate(g, feats).values, yg, gg)
        a1, s1, _ = cv_auc(zbyslate(g, feats + [cbest]).values, yg, gg)
        print('  m >= %-3d : n=%-7d HR=%-6d  base %.4f -> +%s %.4f  (%+.4f, fold sd %.4f)'
              % (f, len(g), int(g.hr.sum()), a0, cbest, a1, a1 - a0, s0))

    hr_('5. THE RILEY CHECK -- the biggest tells in ten seasons, and what they did')
    # TABLEBUG-2026-09-12: the table's `batter` column is NOT the batter. build_savant_training.py
    # fills it with player_name.first() inside a batter-group, and Statcast's player_name on a
    # pitch row is the PITCHER -- so it holds whichever arm happened to be on the mound first.
    # Nothing measured above touches it (every join and groupby uses the numeric batter_id and
    # sp_id, which are correct), but printing it put relievers in a list of hitters. Names are
    # resolved from StatsAPI here instead. Left unfixed in the table itself: rebuilding a 17 MB
    # ten-season artifact to correct a display label is not worth the runner minutes, and
    # fit_savant.py never printed names, which is why this sat unnoticed.
    top = d[d.m >= 15].nlargest(25, 'lift_%d' % K_GRID[3])[
        ['game_date', 'batter_id', 'sp_id', 'm', 'h', 'b_rate', 'lift_%d' % K_GRID[3], 'hr']].copy()
    names = statsapi_names(set(top.batter_id) | set(top.sp_id))
    top.insert(1, 'hitter', top.batter_id.map(names).fillna(top.batter_id.astype(str)))
    top.insert(2, 'vs_starter', top.sp_id.map(names).fillna(top.sp_id.astype(str)))
    top = top.drop(columns=['batter_id', 'sp_id'])
    with pd.option_context('display.width', 200, 'display.max_columns', 20):
        print(top.to_string(index=False))
    deep = d[(d.m >= 15) & (d.h >= 5)]
    if len(deep):
        print('\n  rows with >= 15 meetings AND >= 5 prior HR off that arm: %d' % len(deep))
        print('    they homered %.2f%% of the time' % (100 * deep.hr.mean()))
        print('    those same batters homered %.2f%% of the time overall'
              % (100 * d[d.batter_id.isin(deep.batter_id.unique())].hr.mean()))
        print('    league %.2f%%' % (100 * league))
        print('\n  The middle number is the honest comparison. A "he owns this guy" row belongs to a')
        print('  hitter who owns most guys -- that is why he got 15 meetings against a starter who')
        print('  kept his job. Beating the LEAGUE rate is not the test. Beating his OWN is.')

    hr_('6. THE NAMED CASE -- Riley vs Nola, since that is the one that started this')
    pair_report(d, [('Austin Riley', 'Aaron Nola')])

    hr_('7. TICKETS -- the only scoreboard that matters. Not AUC. Legs that hit.')
    print('  CAVEAT ON THIS SECTION, stated up front: the pool here is every batter who')
    print('  ACTUALLY PLAYED, because that is the only kind of row the table has. That is')
    print('  lineup foresight no board ever has. Section 9 redoes it without. Read 9, not 7.')
    dd = dd.copy()
    dd['p_base'] = oof(zbyslate(dd, feats).values, y, groups)
    dd['p_bvp'] = oof(zbyslate(dd, feats + ['lift_25']).values, y, groups)
    for legs in (2, 3, 4):
        print('\n  ' + '-' * 74)
        tickets(dd, legs=legs)

    hr_('8. THE FLAG ON ITS OWN -- "boost him if he has seen this arm 15+ times"')
    seen_flag(d)

    hr_('9. TICKETS AGAIN, WITHOUT LINEUP FORESIGHT')
    print('  Pool = each team\'s projected nine from its previous %d games. A pick who does' % LOOKBACK)
    print('  not play VOIDS (refund), which is how the live product grades a scratch.\n')
    pj = projected(d, feats)
    pj['p_base'] = 0.0; pj['p_bvp'] = 0.0
    Zb = zbyslate(pj, feats).values
    Zv = zbyslate(pj, feats + ['lift_25']).values
    yy = pj['hr'].astype(int).values; gg = pj['game_date'].values
    pj['p_base'] = oof(Zb, yy, gg)
    pj['p_bvp'] = oof(Zv, yy, gg)
    print('  projected-pool rows: %d | voids: %d (%.1f%% of picks-eligible bats)'
          % (len(pj), int(pj['void'].sum()), 100 * pj['void'].mean()))
    for legs in (2, 3, 4):
        print('\n  ' + '-' * 74)
        tickets_void(pj, legs=legs)

    print('\ndone.', flush=True)


if __name__ == '__main__':
    main()
