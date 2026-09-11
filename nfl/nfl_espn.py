#!/usr/bin/env python3
"""nfl_espn.py -- ESPNFETCH-2026-09-11. One way to read ESPN's site API from the build runner.

WHY. The first automatic football settle never happened. Every nfl-build.yml pass since the
9/10 TNF game went final logged

    2026-09-10: scoreboard unreachable (HTTP Error 403: Forbidden) -- left for the next build

because nfl_settle.py fetched with Python's urllib, and ESPN's edge answers urllib with a 403 --
same URL, same runner, where the soccer room's Node `fetch()` (soccer_teamnews_fetch.js,
soccer_settle.js) has been reading ESPN unattended since 08-26. The failure was invisible: the
settle step is deliberately non-fatal and "network" means "try again next build", so it retried
every five minutes, forever, green.

So ESPN is read the way that demonstrably works on this runner: Node's fetch, shelled out. urllib
with a browser User-Agent is kept only as a fallback for a machine without node. Both failing
raises, and callers keep their own "leave it for the next build" handling -- but the error now
says which transports were tried, so a 403 is not mistaken for an outage again.
"""
import json, shutil, subprocess, urllib.request

ESPN = 'https://site.api.espn.com/apis/site/v2/sports/football/nfl/'
_UA = ('Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
       '(KHTML, like Gecko) Chrome/126.0 Safari/537.36')
_NODE = ("fetch(process.argv[1],{headers:{'cache-control':'no-store'}})"
         ".then(r=>{if(!r.ok)throw new Error('HTTP '+r.status);return r.text()})"
         ".then(t=>process.stdout.write(t)).catch(e=>{console.error(String(e));process.exit(7)})")


def getj(url, timeout=40):
    errs = []
    node = shutil.which('node')
    if node:
        try:
            r = subprocess.run([node, '-e', _NODE, url], capture_output=True, text=True, timeout=timeout)
            if r.returncode == 0 and r.stdout.strip():
                return json.loads(r.stdout)
            errs.append(f'node: {(r.stderr or "empty body").strip()[:80]}')
        except Exception as e:
            errs.append(f'node: {str(e)[:80]}')
    try:
        rq = urllib.request.Request(url, headers={'User-Agent': _UA, 'Accept': 'application/json'})
        with urllib.request.urlopen(rq, timeout=timeout) as r:
            return json.load(r)
    except Exception as e:
        errs.append(f'urllib: {str(e)[:80]}')
    raise RuntimeError('; '.join(errs))
