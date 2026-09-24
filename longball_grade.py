#!/usr/bin/env python3
"""LONGBALL-2026-09-24 -- who hit the longest home run in baseball on a given day.

WHY
    The Long Ball Jackpot (Fanatics) pays everyone who picked the man with the day's LONGEST homer.
    When the ticket kind shipped, `grade_night.py` had no way to answer that -- `pull_boxscores`
    collects who homered, not how far -- so the slip was left ungraded and the ledger recorded
    nothing at all for it. Owner: "i still want the record kept for those 2."

    This module answers it off Baseball Savant's Statcast search, which carries `hit_distance_sc`
    on every batted ball. It is the same source `longball/winners_2026.tsv` was backfilled from,
    so the numbers are directly comparable to the backtest that chose the picking rule.

THE QUERY, AND THE TWO PARAMETERS THAT COST THE FIRST FOUR ATTEMPTS
    https://baseballsavant.mlb.com/statcast_search/csv
        ?all=true&hfGT=R|&hfSea=<year>|&hfAB=home_run|
        &game_date_gt=<date>&game_date_lt=<date>&player_type=batter&type=details

    * `hfAB` takes the event with an UNDERSCORE (`home_run`) or Savant's backslash-dot spelling
      (`home\\.\\.run`). `home%20run` returns HTTP 200 with a header row and ZERO data rows --
      a successful-looking empty answer, which is the worst failure shape: it grades every
      jackpot a loss instead of erroring.
    * the name column is `player_name` ("Last, First"). `last_name, first_name` is the
      LEADERBOARD spelling and does not exist here.
    * the CSV is fully quoted and `player_name` CONTAINS A COMMA, so it must be parsed as real
      CSV. A naive split(',') shifts every column after the name and finds no home runs.

VERIFIED, not assumed: four dates re-derived through this exact query reproduce
`longball/winners_2026.tsv` to the foot and to the name, accents included --
    2026-09-22  Moniak, Mickey   COL 431      2026-09-20  Jones, Spencer   AZ  448
    2026-08-15  Baez, Joshua     CHC 449      2026-07-04  Eldridge, Bryce  COL 458

TIES
    Distances are whole feet and ties do happen. The promo splits the pot among everyone who
    picked the winner, so a tie is a win for each man who reached the max -- `winners()` returns
    ALL of them and `is_winner()` tests membership, rather than picking one arbitrarily.

FAILURE IS NOT A LOSS
    Every error path returns None, and `grade_night` leaves the slip UNGRADED on None rather than
    scoring it 0. A blocked fetch, a WAF, an empty day: none of those are evidence our man missed.

⚠️ Savant is NOT reachable from the cloud sandbox (403 at the proxy) -- it is reachable from the
GitHub Action, which is where grading runs. Test this module with an injected `fetch`.

Run: python3 longball_grade.py 2026-09-22
"""
import csv
import io
import re
import unicodedata
import urllib.request

URL = ('https://baseballsavant.mlb.com/statcast_search/csv?all=true&hfGT=R%7C&hfSea={year}%7C'
       '&hfAB=home_run%7C&game_date_gt={date}&game_date_lt={date}'
       '&player_type=batter&type=details')
UA = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'      # Savant's WAF blocks the default urllib UA


def norm(s):
    """Same normalisation grade_night.norm() uses, so a Savant name compares to a board name."""
    s = unicodedata.normalize('NFKD', s or '')
    s = ''.join(c for c in s if not unicodedata.combining(c)).lower().replace('.', '').strip()
    s = re.sub(r'\s+(jr|sr|ii|iii|iv)$', '', s)
    return s.replace(' ', '').strip()


def flip(name):
    """Savant ships "Last, First"; the board carries "First Last"."""
    name = (name or '').strip()
    if ',' in name:
        last, first = [p.strip() for p in name.split(',', 1)]
        return (first + ' ' + last).strip()
    return name


def _fetch(url, timeout=45):
    rq = urllib.request.Request(url, headers={'User-Agent': UA})
    with urllib.request.urlopen(rq, timeout=timeout) as r:
        return r.read().decode('utf-8-sig', 'ignore')


def winners(date, fetch=_fetch):
    """[(name, distance_ft, team)] for the longest homer of `date` -- a list because of ties.

    Returns None when the answer is UNKNOWN (fetch failed, no rows, no distances). None and []
    mean different things and callers must not conflate them: None is "ask again later",
    [] cannot occur.
    """
    try:
        txt = fetch(URL.format(year=str(date)[:4], date=date))
    except Exception:
        return None
    if not txt:
        return None
    try:
        rows = list(csv.DictReader(io.StringIO(txt)))
    except Exception:
        return None
    hits = []
    for r in rows:
        if (r.get('events') or '').strip() != 'home_run':
            continue
        try:
            d = float(r.get('hit_distance_sc'))
        except (TypeError, ValueError):
            continue
        hits.append((d, flip(r.get('player_name')), (r.get('home_team') or '').strip()))
    if not hits:
        return None                       # header-only response, or a day with no Statcast distance
    top = max(h[0] for h in hits)
    return [(n, int(d), t) for d, n, t in hits if d == top]


def is_winner(name, date, fetch=_fetch, cache={}):
    """True/False whether `name` hit (or tied) the day's longest homer; None when unknown."""
    if date not in cache:
        cache[date] = winners(date, fetch)
    w = cache[date]
    if w is None:
        return None
    return norm(name) in {norm(n) for n, _d, _t in w}


if __name__ == '__main__':
    import sys
    for d in sys.argv[1:]:
        w = winners(d)
        print('%s: %s' % (d, 'UNKNOWN (fetch failed or no distances)' if w is None
                          else ', '.join('%s %dft (%s)' % (n, ft, t) for n, ft, t in w)))
