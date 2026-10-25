import json, re, sys, urllib.request
UA = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/129.0 Safari/537.36'}
def nd(u):
    h = urllib.request.urlopen(urllib.request.Request(u, headers=UA), timeout=30).read().decode('utf-8', 'replace')
    m = re.search(r'<script id="__NEXT_DATA__" type="application/json">(.*?)</script>', h, re.S)
    return json.loads(m.group(1)) if m else None
g = nd('https://www.nba.com/games')['props']['pageProps']
g.pop('layout', None); g.pop('events', None)
s = json.dumps(g)
ids = sorted(set(re.findall(r'"gameId": "(00\d{8})"', s)))
print('TOPKEYS', list(g.keys())); print('IDS', ids)
open('games.json', 'w').write(s)
gid = ids[0] if ids else None
for sfx in ('box-score', 'play-by-play'):
    try:
        d = nd(f'https://www.nba.com/game/{gid}/{sfx}')
        pp = d['props']['pageProps']; pp.pop('layout', None)
        open(f'{sfx}.json', 'w').write(json.dumps(pp))
        print(sfx, 'keys', list(pp.keys()), len(json.dumps(pp)))
    except Exception as e:
        print(sfx, 'ERR', e)
