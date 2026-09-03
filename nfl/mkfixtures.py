#!/usr/bin/env python3
"""Build nfl fixtures.json for one Sunday slate, plus the oddschecker slug map.

⚠️ ODDSCHECKER NAMES A FIXTURE "<away> at <home>". The soccer room learned the mirror of this the
hard way on 2026-09-03: ESPN titles a match "Celta Vigo at Real Sociedad" and the listed-FIRST
side is AWAY. Same convention here, and it is asserted below against games.csv rather than
trusted -- if oddschecker ever flips, the build fails instead of drafting a backwards board.
"""
import json, re, sys
import nfl_stats

FULL = {
 'ARI':'arizona-cardinals','ATL':'atlanta-falcons','BAL':'baltimore-ravens','BUF':'buffalo-bills',
 'CAR':'carolina-panthers','CHI':'chicago-bears','CIN':'cincinnati-bengals','CLE':'cleveland-browns',
 'DAL':'dallas-cowboys','DEN':'denver-broncos','DET':'detroit-lions','GB':'green-bay-packers',
 'HOU':'houston-texans','IND':'indianapolis-colts','JAX':'jacksonville-jaguars','KC':'kansas-city-chiefs',
 'LA':'los-angeles-rams','LAC':'los-angeles-chargers','LV':'las-vegas-raiders','MIA':'miami-dolphins',
 'MIN':'minnesota-vikings','NE':'new-england-patriots','NO':'new-orleans-saints','NYG':'new-york-giants',
 'NYJ':'new-york-jets','PHI':'philadelphia-eagles','PIT':'pittsburgh-steelers','SEA':'seattle-seahawks',
 'SF':'san-francisco-49ers','TB':'tampa-bay-buccaneers','TEN':'tennessee-titans','WAS':'washington-commanders',
}

def build(season, week, weekday='Sunday'):
    s = nfl_stats.load_sched()
    s = s[(s.season==season)&(s.game_type=='REG')&(s.week==week)]
    if weekday: s = s[s.weekday==weekday]
    matches, ocmap = {}, {}
    for _,r in s.iterrows():
        slug = f'{r.away_team}-at-{r.home_team}'
        hh,mm = str(r.gametime).split(':')[:2]
        matches[slug] = dict(home=r.home_team, away=r.away_team,
                             kickoff=int(hh)*60+int(mm),          # ET minutes past midnight
                             gametime=str(r.gametime),
                             espn=['nfl', str(r.game_id)],
                             roof=(None if str(r.roof)=='nan' else str(r.roof)))
        oc = f'{FULL[r.away_team]}-at-{FULL[r.home_team]}'
        ocmap[oc] = slug
    return dict(date=str(s.gameday.iloc[0]), season=season, week=week,
                weekday=weekday, matches=matches), ocmap

if __name__=='__main__':
    season,week = int(sys.argv[1]), int(sys.argv[2])
    fx, ocmap = build(season,week)
    json.dump(fx, open('fixtures.json','w'), indent=1)
    json.dump(ocmap, open('ocmap.json','w'), indent=1)
    print(f'{fx["date"]} {fx["weekday"]} -- {len(fx["matches"])} games')
    for k,v in fx['matches'].items():
        print(f'  {k:12} {v["gametime"]}  roof={v["roof"]}')
