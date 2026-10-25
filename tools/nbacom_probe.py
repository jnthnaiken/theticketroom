import json, re, sys, urllib.request
UA = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/129.0 Safari/537.36'}
def nd(u):
    h = urllib.request.urlopen(urllib.request.Request(u, headers=UA), timeout=30).read().decode('utf-8', 'replace')
    m = re.search(r'<script id="__NEXT_DATA__" type="application/json">(.*?)</script>', h, re.S)
    return json.loads(m.group(1)) if m else None
def walk(o, path='', depth=0, out=None):
    if out is None: out = []
    if depth > 6: return out
    if isinstance(o, dict):
        for k, v in o.items():
            out.append(f"{path}/{k}:{type(v).__name__}{'['+str(len(v))+']' if isinstance(v,(list,dict)) else '='+str(v)[:40]}")
            walk(v, path + '/' + k, depth + 1, out)
    elif isinstance(o, list) and o:
        walk(o[0], path + '[0]', depth + 1, out)
    return out
g = nd('https://www.nba.com/games')
print('\n'.join(walk(g['props']['pageProps'])[:120]))
