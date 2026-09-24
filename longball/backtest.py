#!/usr/bin/env python3
"""LONGBALL-2026-09-24 -- can we pick the man who hits the longest home run of the day?

Owner is replacing the Lunch Special and the Nightcap with two free-to-play picks: FanDuel's
Daily Dinger (pick a bat, he homers, you get a profit-boost token) and Fanatics' Long Ball
Jackpot. The second one is NOT a longest-odds market, which is what I assumed first and was
corrected on: you attach it to a qualifying bet, and if your man hits the LONGEST home run in
baseball that day you split a FanCash pot with everyone else who picked him.

So the question is not "will he go deep" but "will his be the furthest", and that is a
different model -- one this repo had no data for, because no puller kept `hit_distance_sc`.

WHAT WAS MEASURED
    5,394 home runs pulled from Baseball Savant, 2026-03-26 .. 2026-09-22, 179 days.
    The day's longest homer for each of those days is in winners_2026.tsv.
    Per-player distance profiles from the FIRST half only are in profile_h1.txt
    (max distance, mean distance, max exit velocity; 3+ HR minimum, 331 players).
    Everything is then tested on 2026-07-01 onward, against our own archived boards, so a pick
    can only ever be a bat the board actually carded that night.

THE BASELINE THAT MATTERS
    ~30 men homer on a normal day, so blindly naming one who homers wins 3.3% of the time.
    Any rule has to beat that to be worth calling a pick.

FIRST PASS -- nothing beat chance. 78 nights, ~2.6 hits expected:

    our model score (P of a HR)          2 hits   2.6%
    powidx / barrel / hh / iso / la      0-1 hits 0.0-1.3%
    trailing max DISTANCE                0 hits   0.0%
    trailing max EXIT VELO               1 hit    1.3%
    park, then max DISTANCE              2 hits   2.6%
    park, then max EXIT VELO             2 hits   2.6%

WHY, AND IT IS ARITHMETIC RATHER THAN A MODELLING FAILURE
    Park is a real and large signal about WHICH DAY:

        COL  won 26 of 72 days it produced a homer   36.1%   median HR +25ft vs league
        ATH  17/75  22.7%      STL 9/62  14.5%       AZ 10/71  14.1%
        SD   0/68    0%        HOU 1.3%              LAD 2.7%

    Coors is an 11x lift on the 3.3% baseline. But a dozen-plus bats play in that park, and
    36% divided by twelve is 3%. Knowing the park narrows the day and not the man, which is
    exactly what the backtest shows.

    Player identity carries almost nothing either: 120 distinct winners in 179 days, and the
    most frequent (Schwarber, Adell, Caminero) won 5 times each -- 2.8%, indistinguishable
    from the baseline.

WHAT THIS DOES NOT SAY
    78 nights can rule out a big edge, not a small one. A rule that genuinely won 6% of the
    time would not separate from 3.3% at this sample size. So this is "no edge demonstrated",
    not "no edge exists".

SECOND PASS -- THE FIRST PASS USED THE WRONG PARK VARIABLE. Owner: "a game isnt played in
coors every night so you need to look into a different data point or layer of multiple.
remember, there is always order in chaos." Both halves of that were right.

    * `parkhr`, the board's own park factor, is NEGATIVELY related to the longest homer --
      winner-game percentile 0.374, below chance. It measures how EASY a park is to homer in,
      and cheap-homer parks produce 370ft wall-scrapers. The variable that matters is park
      CARRY, specifically the TAIL: the 90th-percentile HR distance at that park.
      COL +50ft over league, ATH +47, TB +36 (a dome: no wind, consistent carry), against
      HOU +16 and LAD +17. NYY is the clean counterexample -- a low median (-7ft, short porch)
      with no tail (+27), so it is cheap homers and never the longest.
    * Park tail is available EVERY night, which Coors is not. Learned on the first half and
      tested on the second: the winner's game sits at mean percentile 0.643 / median 0.733,
      about 4 sigma off chance. Top-quartile tail parks produced 49% of winners against 25% at
      chance; bottom-quartile parks 9%.
    * And the second layer is already in the board. WITHIN the winner's own game, our own model
      score puts him at mean percentile 0.701 (median 0.778) across 73 nights -- roughly 6
      sigma. Max exit velocity is much weaker at 0.567. So: park tail picks the GAME, our
      existing score picks the MAN.

    Blended, z(park tail) + z(model score): 4 hits in 78, 5.1% against a 3.3% baseline -- a
    1.5x lift. NOT SIGNIFICANT on its own: 4 against 2.6 expected arises by chance about a
    quarter of the time. The components are significant; the end-to-end rate needs more nights.

    Note that HARD-FILTERING to the best tail park does worse (1 hit) than blending. Filtering
    throws the score signal away and leaves you with the best bat in Coors rather than the best
    combination on the slate.

WHAT WOULD CHANGE THE ANSWER
    The pot SPLITS among everyone who picked the same man. Since no rule beats chance on
    picking the winner, the only remaining lever is picking a bat with ordinary credentials in
    an extraordinary park -- same win probability, fewer people to divide with. That needs
    Fanatics' pick distribution, which they do not appear to publish. Worth establishing before
    any edge is claimed on the board.

    `hit_distance_sc` was added to build_savant_training.py's KEEP list on 2026-09-24, so the
    pipeline now banks distance on every pull. This backtest used a Savant backfill instead,
    because the cache is keyed by day and will not re-pull the season.

Run: python3 longball/backtest.py       (from the repo root)
"""
import collections
import glob
import json
import os
import re
import sys
import unicodedata

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
SPLIT = '2026-07-01'          # profiles learned before this, picks tested on and after
BASELINE = 0.033              # 1 / (typical homers per day)


def _words(s):
    s = unicodedata.normalize('NFKD', s or '')
    s = ''.join(c for c in s if not unicodedata.combining(c)).lower()
    s = re.sub(r'\b(jr|sr|ii|iii|iv)\b', '', s)
    return re.sub(r'[^a-z ]', '', s).split()


def key(s):
    """(first, last), accent- and suffix-free. Savant says 'Acuña Jr., Ronald'; we say
    'Ronald Acuna'. Without this the join silently finds nothing and every rule scores zero,
    which looks exactly like a real negative result."""
    w = _words(s)
    return (w[0], w[-1]) if len(w) >= 2 else ((w[0], w[0]) if w else ('', ''))


def key_lastfirst(s):
    if ',' in s:
        last, first = [x.strip() for x in s.split(',', 1)]
        return key(first + ' ' + last)
    return key(s)


def load():
    winners = {}
    with open(os.path.join(HERE, 'winners_2026.tsv'), encoding='utf-8') as fh:
        for ln in fh:
            if not ln.strip():
                continue
            d, n, park, dist = ln.rstrip('\n').split('\t')
            winners[d] = {'key': key_lastfirst(n), 'name': n, 'park': park, 'dist': int(dist)}
    prof = {}
    with open(os.path.join(HERE, 'profile_h1.txt'), encoding='utf-8') as fh:
        for ln in fh:
            m = re.match(r'^(.*?) (\d+) (\d+) (\d+) ([\d.]+)\s*$', ln.rstrip('\n'))
            if m:
                prof[key_lastfirst(m.group(1))] = {
                    'hr': int(m.group(2)), 'maxd': int(m.group(3)),
                    'avgd': int(m.group(4)), 'maxev': float(m.group(5))}
    cal = collections.defaultdict(dict)
    cpath = os.path.join(ROOT, 'calibration.jsonl')
    if os.path.exists(cpath):
        with open(cpath) as fh:
            for ln in fh:
                try:
                    o = json.loads(ln)
                except Exception:
                    continue
                if o.get('date') and o.get('name'):
                    cal[o['date']][key(o['name'])] = o
    return winners, prof, cal


def main():
    winners, prof, cal = load()
    park_rank = collections.Counter(v['park'] for d, v in winners.items() if d < SPLIT)

    rules = {
        'model score (P of a HR)':  lambda x: (x['cal'].get('total') or -1,),
        'trailing max DISTANCE':    lambda x: (x['prof']['maxd'],) if x['prof'] else None,
        'trailing max EXIT VELO':   lambda x: (x['prof']['maxev'],) if x['prof'] else None,
        'park, then max DISTANCE':  lambda x: (park_rank.get(x['park'], 0), x['prof']['maxd']) if x['prof'] else None,
        'park, then max EXIT VELO': lambda x: (park_rank.get(x['park'], 0), x['prof']['maxev']) if x['prof'] else None,
        'park, then model score':   lambda x: (park_rank.get(x['park'], 0), x['cal'].get('total') or -1),
    }
    hits = collections.Counter()
    tested = 0
    for path in sorted(glob.glob(os.path.join(ROOT, 'D_2026-*.json'))):
        date = os.path.basename(path)[2:-5]
        if date < SPLIT or date not in winners:
            continue
        try:
            board = json.load(open(path))
        except Exception:
            continue
        cands = []
        for nm, p in (board.get('players') or {}).items():
            if p.get('out') or p.get('void'):
                continue
            gm = p.get('gmatch') or ''
            if '@' not in gm:
                continue
            cands.append({'nm': nm, 'park': gm.split('@')[1],
                          'prof': prof.get(key(nm)), 'cal': cal.get(date, {}).get(key(nm), {})})
        if len(cands) < 10:
            continue
        tested += 1
        want = winners[date]['key']
        for label, rank in rules.items():
            scored = [(rank(c), c) for c in cands]
            scored = [(s, c) for s, c in scored if s is not None]
            if not scored:
                continue
            # key= on the score only: max() falls through to comparing the candidate dicts
            # on a tie, which raises rather than picking one.
            best = max(scored, key=lambda sc: sc[0])[1]
            if key(best['nm']) == want:
                hits[label] += 1

    if not tested:
        sys.exit('!! nothing to test -- no archived board on or after %s joined a winner' % SPLIT)
    print('LONGBALL backtest -- %d nights from %s' % (tested, SPLIT))
    print('baseline %.1f%% (a random man who homered) = %.1f hits\n' % (BASELINE * 100, tested * BASELINE))
    for label in rules:
        n = hits[label]
        print('  %-26s %2d hits  %4.1f%%%s'
              % (label, n, 100.0 * n / tested, '   <-- beats baseline' if n > tested * BASELINE else ''))
    print('\npark win rate learned before %s (top 6): %s'
          % (SPLIT, ', '.join('%s %d' % kv for kv in park_rank.most_common(6))))
    if max(hits.values() or [0]) <= tested * BASELINE:
        print('\nNo rule beat chance. See this file\'s header for why, and for what it does not prove.')


if __name__ == '__main__':
    main()
