#!/usr/bin/env python3
"""
nfl_wx.py -- stadium weather for one slate. Open-Meteo -> wx.json, keyed by fixture slug.

⚠️ WEATHER IS THE ONLY THING THAT MAY MOVE A FOOTBALL TOTAL. Owner's rule
(claude/priceonce-doctrine.md): "soccer and football price ONE TIME at build, like baseball. any
changes in model total would be due to live weather updates etc." A price is written once; this
file is the sanctioned source of movement, so it runs on every build.

⚠️ RUNNER-ONLY. api.open-meteo.com is not reachable from the dev container (403 at the egress
proxy, same as ESPN). Absent wx.json the payload falls back to the no-wind default and every
factor is ~1.0 -- which is SILENT, so the workflow logs the count it fetched.

WHAT THE TRIM IS WORTH, measured within usage quartiles on outdoor games 2021-2025:
    0-3 mph -0.2pp | 3-7 +1.4 | 7-11 -0.0 | 11-15 -1.5 | 15+ -1.6 | indoor +1.4
An earlier note in this project claimed the windiest decile scored 18.0% against 24.0% for the
calmest. That was NOT usage-controlled and overstated the effect roughly four-fold. Wind is a
trim, not a headline, and the factors in nfl_mock.wx_mult are sized accordingly.

⚠️ A DOME IS NOT A FORECAST. Indoor and closed-roof games take the indoor factor regardless of
what the sky is doing outside, so they are never fetched -- `roof` from games.csv decides.
Retractable roofs are treated as OUTDOOR unless games.csv says closed, because the operator's
decision is not knowable at build time and the honest default is the one that can be wrong in
the visible direction.
"""
import argparse, json, sys, urllib.request, urllib.parse
from datetime import datetime, timedelta

# Home stadium coordinates. Only the HOME team's venue matters -- the away side does not carry
# its weather with it, which is obvious and is exactly the kind of thing that gets coded wrong.
STADIUM = {
 'ARI': (33.5277, -112.2626), 'ATL': (33.7554, -84.4009), 'BAL': (39.2780, -76.6227),
 'BUF': (42.7738, -78.7870),  'CAR': (35.2258, -80.8528), 'CHI': (41.8623, -87.6167),
 'CIN': (39.0955, -84.5161),  'CLE': (41.5061, -81.6995), 'DAL': (32.7473, -97.0945),
 'DEN': (39.7439, -105.0201), 'DET': (42.3400, -83.0456), 'GB':  (44.5013, -88.0622),
 'HOU': (29.6847, -95.4107),  'IND': (39.7601, -86.1639), 'JAX': (30.3239, -81.6373),
 'KC':  (39.0489, -94.4839),  'LA':  (33.9535, -118.3392),'LAC': (33.9535, -118.3392),
 'LV':  (36.0909, -115.1833), 'MIA': (25.9580, -80.2389), 'MIN': (44.9736, -93.2578),
 'NE':  (42.0909, -71.2643),  'NO':  (29.9511, -90.0812), 'NYG': (40.8135, -74.0745),
 'NYJ': (40.8135, -74.0745),  'PHI': (39.9008, -75.1675), 'PIT': (40.4468, -80.0158),
 'SEA': (47.5952, -122.3316), 'SF':  (37.4030, -121.9700),'TB':  (27.9759, -82.5033),
 'TEN': (36.1665, -86.7713),  'WAS': (38.9077, -76.8645),
}
INDOOR = ('dome', 'closed')

def fetch(lat, lon, day):
    q = urllib.parse.urlencode(dict(
        latitude=lat, longitude=lon,
        hourly='temperature_2m,wind_speed_10m,precipitation_probability',
        start_date=day, end_date=day,
        temperature_unit='fahrenheit', wind_speed_unit='mph', timezone='America/New_York'))
    with urllib.request.urlopen(f'https://api.open-meteo.com/v1/forecast?{q}', timeout=30) as r:
        return json.load(r)

def build(fixtures_path, out_path):
    fx = json.load(open(fixtures_path, encoding='utf-8'))
    day = fx['date']
    out, indoor, fetched, failed = {}, 0, 0, []
    for slug, mm in fx['matches'].items():
        if str(mm.get('roof') or '').lower() in INDOOR:
            out[slug] = dict(indoor=True, wind=0, precip=0, temp=None); indoor += 1; continue
        ll = STADIUM.get(mm['home'])
        if not ll:
            failed.append(f'{slug} (no coords for {mm["home"]})'); continue
        try:
            j = fetch(ll[0], ll[1], day)
            hrs = j['hourly']['time']
            # kickoff is ET minutes past midnight and the feed is requested in America/New_York,
            # so the hour index is a straight lookup rather than a timezone conversion.
            want = f"{day}T{mm['kickoff']//60:02d}:00"
            i = hrs.index(want) if want in hrs else min(range(len(hrs)),
                    key=lambda k: abs(int(hrs[k][11:13]) * 60 - mm['kickoff']))
            out[slug] = dict(indoor=False,
                             wind=round(float(j['hourly']['wind_speed_10m'][i] or 0), 1),
                             precip=int(j['hourly']['precipitation_probability'][i] or 0),
                             temp=round(float(j['hourly']['temperature_2m'][i] or 0)))
            fetched += 1
        except Exception as e:
            failed.append(f'{slug} ({e})')
    json.dump(out, open(out_path, 'w'), indent=1)
    print(f'{out_path}: {len(out)}/{len(fx["matches"])} games '
          f'({fetched} fetched, {indoor} indoor, {len(failed)} failed)')
    for f in failed: print(f'  ::warning::wx miss {f}')
    if fetched:
        w = [v['wind'] for v in out.values() if not v['indoor']]
        if w: print(f'  wind {min(w):.0f}-{max(w):.0f} mph')
    # A total wipeout is not a warning -- every TOTAL would silently lose its only live term.
    if not out: sys.exit('!! no weather at all; refusing to write an empty wx.json')

if __name__ == '__main__':
    ap = argparse.ArgumentParser()
    ap.add_argument('fixtures'); ap.add_argument('out', nargs='?', default='wx.json')
    A = ap.parse_args()
    build(A.fixtures, A.out)
