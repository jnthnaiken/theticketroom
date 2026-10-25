"""nba_src.py -- NONESPN-2026-10-25. nba.com first, ESPN only as the last resort (owner: "only use them for a last
resort"). Same three calls as nba_espn; event ids from nba.com carry an 'nba:' prefix so summary/parse route right."""
import nba_espn as E
import nba_nbacom as N

LAST = {'scoreboard': None}


def scoreboard(ymd):
    try:
        sb = N.scoreboard(ymd)
        if sb:
            LAST['scoreboard'] = 'nba.com'
            return sb
    except Exception as e:
        print(f'  ::warning::nba.com scoreboard {ymd}: {str(e)[:120]} -- ESPN fallback')
    LAST['scoreboard'] = 'espn'
    return E.scoreboard(ymd)


def summary(eid):
    if str(eid).startswith('nba:'):
        return N.summary(eid)
    return E.summary(eid)


def parse(s):
    return N.parse(s) if isinstance(s, dict) and s.get('_src') == 'nba' else E.parse(s)
