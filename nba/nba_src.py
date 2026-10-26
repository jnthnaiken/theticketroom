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
        s = N.summary(eid)
        # STARTERFLAG-2026-10-26: a complete play-by-play is not enough -- the grader also needs both starting fives.
        if N.complete(s) and sum(len(v) for v in N.parse(s)['starters'].values()) >= 10:
            return s
        # FIRSTLOCK-2026-10-25: nba.com's page has only the late play-by-play (a finished game) -- the first score and
        # the tip are not on it. ESPN for this one game, the last resort the owner allowed.
        g = s.get('game') or {}
        ymd = str(g.get('gameEt') or g.get('gameTimeUTC') or '')[:10]
        pair = (N.tcode((g.get('awayTeam') or {}).get('teamTricode')), N.tcode((g.get('homeTeam') or {}).get('teamTricode')))
        try:
            for row in E.scoreboard(ymd):
                if (row[1], row[2]) == pair:
                    print(f'  nba.com play-by-play or starting fives incomplete for {pair[0]}@{pair[1]} -- ESPN for this game')
                    return E.summary(row[0])
        except Exception as e:
            print(f'  ::warning::ESPN fallback {pair}: {str(e)[:100]}')
        return s
    return E.summary(eid)


def parse(s):
    return N.parse(s) if isinstance(s, dict) and s.get('_src') == 'nba' else E.parse(s)
