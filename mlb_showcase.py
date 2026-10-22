"""mlb_showcase.py -- SHOWCASE-2026-10-22. The baseball room's winter page: a replay of a real night from last
season under an "Enjoy the World Series / See you next season" banner.

Owner, 10-22: "on the baseball page, can we show last season's results and like a mock page so people who havent
seen it before can see how we did and what it looks like. that way they come back when next season starts. so
make the cover page clickable again. but make it all translucent or something and still say the enjoy the world
series, see you next season thing".

    python3 mlb_showcase.py board D_2026-09-20.json season.json calibration.jsonl mlb_showcase_D.json   (once)
    python3 mlb_showcase.py index.html mlb_showcase_D.json _site/mlb/index.html                   (deploy)

* The PAGE is the real baseball room (repo index.html, the same code the season ran on).
* The BOARD is an archived night (D_<date>.json), with every bat's home-run outcome stamped from
  calibration.jsonl, every game marked final, every slip locked and every bat confirmed -- so the page
  renders the night as it finished, without needing a live feed.
* The TRACKER is the final season ledger (season.json), so the season panel shows the whole year.
* An overlay banner says the room is closed and what this is, and the board underneath is dimmed.

deploy-pages.yml runs this into _site/mlb/index.html while mlb_offseason.html exists (OFFSEASON).
NEXT SEASON: delete the showcase step and mlb_offseason.html; /mlb/ goes back to plain index.html.
"""
import json
import re
import sys

SHOWCASE_DATE = '2026-09-20'


def stamp(D, cal_path):
    date = D['meta']['date']
    hr = {}
    for line in open(cal_path, encoding='utf-8'):
        try:
            r = json.loads(line)
        except Exception:
            continue
        if r.get('date') == date and r.get('name') is not None:
            hr[r['name']] = bool(r.get('hr'))
    games = set()
    for n, p in D['players'].items():
        p['hr'] = hr.get(n, False)
        if not p.get('out') and not p.get('void'):
            p['status'] = 'confirmed'
        if p.get('game') is not None:
            games.add(p['game'])
    D['meta']['finals'] = sorted(games)
    for t in D['tickets']:
        t['locked'] = True
        t['final'] = True
    return sum(1 for v in hr.values() if v)


BANNER_CSS = r"""
<style id="showcase-css">
/* SHOWCASE-2026-10-22: the winter replay. The board sits dimmed under a fixed banner. */
.wrap,header,main{opacity:.5;filter:saturate(.75);transition:opacity .25s ease}
.wrap:hover,header:hover,main:hover{opacity:.82}
#showcase{position:fixed;top:0;left:0;right:0;z-index:2147483000;display:flex;justify-content:center;padding:12px 16px;
  background:linear-gradient(180deg,#05070cf2,#05070cd9);backdrop-filter:blur(6px);-webkit-backdrop-filter:blur(6px);
  border-bottom:1px solid #26d4f033}
#showcase .sc{max-width:980px;width:100%;display:flex;flex-wrap:wrap;align-items:center;gap:8px 18px;justify-content:space-between}
#showcase .t b{display:block;font-family:'Roboto Mono',monospace;font-weight:500;font-size:12px;letter-spacing:.2em;
  text-transform:uppercase;color:#26d4f0}
#showcase .t span{display:block;margin-top:2px;font-family:'Roboto Mono',monospace;font-size:10px;letter-spacing:.14em;
  text-transform:uppercase;color:#9aa7bd}
#showcase .s{font-family:Inter,system-ui,sans-serif;font-size:12.5px;color:#cfd8e8;line-height:1.45}
#showcase .s em{font-style:normal;color:#4ef08a;font-weight:600}
#showcase a{color:#26d4f0;text-decoration:none;border:1px solid #26d4f04d;border-radius:999px;padding:4px 10px;
  font-family:'Roboto Mono',monospace;font-size:10px;letter-spacing:.14em;text-transform:uppercase;white-space:nowrap}
#livectl{display:none!important}
body{padding-top:var(--scH,74px)}
</style>
<script>/* SHOWCASE: a finished replay -- no live feed may re-grade it. */
(function(){var f=window.fetch;window.fetch=function(u){if(/statsapi|espn|mlb\.com/i.test(String(u&&u.url||u)))
return Promise.reject(new Error('showcase replay'));return f.apply(this,arguments)}})();
addEventListener('DOMContentLoaded',function(){var b=document.getElementById('showcase');function fit(){if(b)document.body.style.setProperty('--scH',b.offsetHeight+'px')}fit();addEventListener('resize',fit)});</script>
"""


def banner(D, season):
    # No figures of its own: the Season panel below is the page's own ledger, and a second set of
    # numbers in the banner would only disagree with it on rounding or on which kinds it counts.
    import datetime
    nice = datetime.date.fromisoformat(D['meta']['date']).strftime('%B %-d, %Y')
    return (f'<div id="showcase" role="note"><div class="sc">'
            f'<div class="t"><b>Enjoy the World Series</b><span>See you next season</span></div>'
            f'<div class="s">The baseball room is closed for the winter. Last season&rsquo;s full record is in the '
            f'<em>Season</em> panel.<br>Below is a replay of a real board from {nice}, exactly as it finished.</div>'
            f'<a href="../">Other rooms</a></div></div>')


def make_board(board_path, season_path, cal_path, out_board):
    """One-off: stamp an archived night and the final ledger into mlb_showcase_D.json (committed)."""
    D = json.load(open(board_path, encoding='utf-8'))
    n_hr = stamp(D, cal_path)
    D['meta']['season'] = json.load(open(season_path, encoding='utf-8'))
    D['meta']['showcase'] = True
    json.dump(D, open(out_board, 'w', encoding='utf-8'), ensure_ascii=False)
    print(f'mlb_showcase: board {D["meta"]["date"]}, {len(D["tickets"])} slips, {n_hr} bats homered -> {out_board}')


def render(index_path, board_path, out_path):
    """Deploy step: the live repo index.html + the committed showcase board -> /mlb/index.html."""
    src = open(index_path, encoding='utf-8').read()
    D = json.load(open(board_path, encoding='utf-8'))
    dj = 'const D=' + json.dumps(D, ensure_ascii=True) + ',WX=D.meta.wx;'
    src, n = re.subn(r'const D=[\s\S]*?,WX=D\.meta\.wx;', lambda m: dj, src, count=1)
    assert n == 1, 'const D block not found'
    src = src.replace('</head>', BANNER_CSS + '</head>', 1)
    src, n = re.subn(r'<body([^>]*)>', lambda m: m.group(0) + banner(D, D['meta'].get('season') or {}), src, count=1)
    assert n == 1, '<body> not found'
    src = src.replace('<title>The Baseball Room', '<title>The Baseball Room &middot; See you next season', 1)
    open(out_path, 'w', encoding='utf-8').write(src)
    print(f'mlb_showcase: rendered {D["meta"]["date"]} replay -> {out_path}')


if __name__ == '__main__':
    a = sys.argv[1:]
    if len(a) == 5 and a[0] == 'board':
        make_board(*a[1:])
    elif len(a) == 3:
        render(*a)
    else:
        print('usage: mlb_showcase.py board D_<date>.json season.json calibration.jsonl mlb_showcase_D.json\n'
              '       mlb_showcase.py index.html mlb_showcase_D.json out.html'); sys.exit(2)
