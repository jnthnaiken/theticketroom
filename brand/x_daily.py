#!/usr/bin/env python3
"""
x_daily.py -- build one day's X assets for OPERATION: THE ROOM.

The 30-day plan lives in the project doc `claude/x-operation-30day-2026-09-12.md`.
This is its hands: it reads the LIVE board and emits the image(s) + a copy draft for
whichever template the calendar calls for that day. Every number on every asset is read
off D_<date>.json, so nothing is ever hand-typed onto a graphic.

WHY A ROTATION AND NOT A TEMPLATE
    X downranks repetitive, template-driven posting. The ritual is the TIME and the VOICE;
    the format has to move. CALENDAR below never puts the same template on consecutive days.

USAGE
    python3 x_daily.py                 # today, template from the calendar
    python3 x_daily.py --day 5         # force a campaign day
    python3 x_daily.py --tpl F         # force a template
    python3 x_daily.py --out /mnt/user-data/outputs/brand

Needs: playwright + chromium, the three TTFs beside this file, and the repo it lives in
(index.html, D_<date>.json, calibration.jsonl).
"""
import argparse, asyncio, datetime, glob, json, os, re, subprocess, sys, threading, http.server, socketserver

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
START = datetime.date(2026, 9, 11)          # Day 1
PORT = 8791

# Day -> (drop template, door template). See the plan doc for what each phase is doing.
CALENDAR = {
    1:('B','-'),  2:('A','D'),  3:('F','A'),  4:('C','F'),  5:('A','F'),  6:('G','F'),  7:('B','F'),
    8:('F','A'),  9:('H','F'), 10:('A','C'), 11:('H','G'), 12:('F','A'), 13:('C','F'), 14:('A','E'),
   15:('F','D'), 16:('H','A'), 17:('C','F'), 18:('A','G'), 19:('F','H'), 20:('E','A'), 21:('A','F'),
   22:('H','E'), 23:('C','F'), 24:('A','H'), 25:('F','C'), 26:('H','A'), 27:('A','F'), 28:('G','H'),
   29:('F','A'), 30:('E','D'),
}
NAMES = {'A':'REDACTED TICKET','B':'THE WIDE ROOM','C':'ONE NUMBER','D':'THE REVEAL',
         'E':'THE LEDGER','F':'NAME HIM','G':'THE DRIFT','H':'VIDEO'}


# ---------------------------------------------------------------- board reading
def board(date):
    p = os.path.join(REPO, 'D_%s.json' % date)
    if not os.path.exists(p):
        cands = sorted(glob.glob(os.path.join(REPO, 'D_2???-??-??.json')))
        if not cands: sys.exit('!! no D_<date>.json in %s' % REPO)
        p = cands[-1]
    return json.load(open(p))


def et_now():
    os.environ['TZ'] = 'America/New_York'
    try: import time; time.tzset()
    except Exception: pass
    return datetime.datetime.now()


def _lock_dt(s, day):
    m = re.match(r'(\d+):(\d+)\s*(AM|PM)', (s or '').strip(), re.I)
    if not m: return None
    h, mi, ap = int(m.group(1)), int(m.group(2)), m.group(3).upper()
    if ap == 'PM' and h != 12: h += 12
    if ap == 'AM' and h == 12: h = 0
    return datetime.datetime.combine(day, datetime.time(h, mi))


def slate(D, now=None):
    """What is still buyable, what the headline number is, and when the next door shuts."""
    now = now or et_now()
    out = []
    for t in D.get('tickets') or []:
        rr = t.get('rr') or {}
        lk = _lock_dt(t.get('lock'), now.date())
        mp = rr.get('maxprofit')
        out.append(dict(name=t['name'], kind=t.get('kind'), lock=t.get('lock'), lockdt=lk,
                        risk=rr.get('risk'), maxprofit=mp,
                        to1=round(mp / rr['risk']) if mp and rr.get('risk') else None,
                        legs=[p.get('name') for p in (t.get('players') or [])],
                        open=bool(lk and lk > now)))
    openm = [t for t in out if t['open'] and t['kind'] == 'moon']
    hero = max(openm, key=lambda t: t['maxprofit'] or 0) if openm else None
    doors = sorted({t['lock'] for t in out if t['open']},
                   key=lambda s: _lock_dt(s, now.date()) or now)
    return dict(all=out, open_moons=openm, hero=hero, next_door=doors[0] if doors else None)


def last_night(D_prev, date_prev):
    """Grade yesterday off calibration.jsonl -- the offline path the ledger corrections use."""
    try:
        sys.path.insert(0, REPO)
        from grade_night import grade_ticket, norm
        R = [json.loads(l) for l in open(os.path.join(REPO, 'calibration.jsonl'))]
        g = [r for r in R if r['date'] == date_prev]
        if not g: return None
        homered = {norm(r['name']) for r in g if r.get('hr')}
        played = {norm(r['name']) for r in g}
        res = []
        for t in D_prev.get('tickets') or []:
            r = grade_ticket(t, homered, played, set(), 1.0)
            if r: res.append((t, r))
        wins = [(t, r) for t, r in res if r.get('won')]
        best = max(wins, key=lambda x: x[1]['net']) if wins else None
        return dict(results=res, best=best, net=round(sum(r['net'] for _, r in res), 2),
                    homered=homered, players=D_prev.get('players') or {})
    except Exception as e:
        print('  (grading skipped: %s)' % e); return None


# ---------------------------------------------------------------- rendering
def serve(root):
    class H(http.server.SimpleHTTPRequestHandler):
        def __init__(self, *a, **k): super().__init__(*a, directory=root, **k)
        def log_message(self, *a): pass
    socketserver.TCPServer.allow_reuse_address = True      # back-to-back runs hit TIME_WAIT otherwise
    httpd = None
    for port in range(PORT, PORT + 12):                    # and a stale server from a crashed run
        try:
            httpd = socketserver.TCPServer(('127.0.0.1', port), H); break
        except OSError:
            continue
    if httpd is None: sys.exit('!! no free port in %d..%d' % (PORT, PORT + 11))
    globals()['PORT'] = httpd.server_address[1]
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    return httpd


FONTS = """
@font-face{font-family:Oswald;src:url(Oswald.ttf);font-weight:200 700}
@font-face{font-family:Inter;src:url(Inter.ttf);font-weight:100 900}
@font-face{font-family:'Roboto Mono';src:url(RobotoMono.ttf);font-weight:100 700}
:root{--bg:#05060a;--txt:#eef3fc;--mut:#8d9ab1;--dim:#5c6982;--cyan:#26d4f0;--lime:#4ef08a;--gold:#ffd76a;--red:#ff6b5e}
html,body{margin:0;background:#000}
.wm{position:absolute;left:80px;top:76px;font-family:Oswald;font-weight:700;font-size:38px;letter-spacing:2px;text-transform:uppercase;
  background:linear-gradient(92deg,#fff 20%,var(--cyan) 80%);-webkit-background-clip:text;background-clip:text;color:transparent}
.rule{position:absolute;left:82px;top:128px;width:284px;height:4px;border-radius:3px;background:linear-gradient(90deg,var(--cyan),var(--lime))}
.url{position:absolute;left:82px;bottom:70px;font-family:'Roboto Mono';font-weight:700;font-size:36px;color:var(--cyan)}
.fine{position:absolute;left:84px;bottom:38px;font-family:Inter;font-size:15px;color:#4a5568;letter-spacing:.04em}
.stars{position:absolute;inset:0;opacity:.5;background-image:
  radial-gradient(1.3px 1.3px at 7% 22%,#fff9,transparent),radial-gradient(1px 1px at 31% 12%,#fff8,transparent),
  radial-gradient(1.5px 1.5px at 46% 80%,#fffa,transparent),radial-gradient(1px 1px at 58% 8%,#fff7,transparent),
  radial-gradient(1.2px 1.2px at 88% 14%,#fff9,transparent),radial-gradient(1px 1px at 95% 62%,#fff7,transparent)}
"""
CHROME = '<div class="wm">The Ticket Room</div><div class="rule"></div><div class="url">theticketroom.live</div>' \
         '<div class="fine">Free. No signup, no affiliate link, no promo code. 21+</div>'


# ---- TEMPLATE A: the hero ticket, names in solid bars ------------------------------------
REDACT_CSS = """
  .leg .nm{color:transparent!important;background:#07080b;border-radius:2px;
           box-shadow:0 0 0 1px #ffffff10, inset 0 0 14px #000;padding:2px 10px}
  .leg .nm>*{opacity:0!important}
  .leg .lwhere,.leg .lmeta,.tnote{color:transparent!important;background:#0a0b0f;border-radius:2px}
  .lockline .badge{display:none!important}"""


async def shoot_ticket(pg, slipname, path, redact=True):
    await pg.goto('http://127.0.0.1:%d/index.html' % PORT, wait_until='load')
    await pg.wait_for_timeout(5000)
    await pg.evaluate("""(css)=>{
      [...document.querySelectorAll('*')].filter(e=>/live data unavailable/.test(e.textContent)&&e.getBoundingClientRect().width<400).forEach(t=>t.style.display='none');
      const w=document.createTreeWalker(document.body,NodeFilter.SHOW_TEXT); let n;
      while(n=w.nextNode()){ if(/ET ET/.test(n.nodeValue)) n.nodeValue=n.nodeValue.replace('ET ET','ET'); }
      if(css){const s=document.createElement('style'); s.textContent=css; document.head.appendChild(s);}
    }""", REDACT_CSS if redact else '')
    await pg.wait_for_timeout(800)
    h = await pg.evaluate_handle("""(nm)=>[...document.querySelectorAll('.slip')]
        .find(s=>(s.querySelector('.tname')?.textContent||'').trim().toUpperCase()===nm.toUpperCase())""", slipname)
    el = h.as_element()
    if not el: return False
    await el.screenshot(path=path)
    return True


def tpl_A(S, ctx):
    return f"""<!doctype html><html><head><meta charset="utf-8"><style>{FONTS}
#P{{position:relative;width:1600px;height:900px;overflow:hidden;font-family:Inter;color:var(--txt);
 background:radial-gradient(900px 700px at 1180px 450px,#ffd76a14,transparent 72%),
            radial-gradient(700px 460px at 60px 60px,#26d4f014,transparent 70%),var(--bg)}}
.tk{{position:absolute;left:742px;top:6px;width:846px;transform:rotate(-2.6deg);filter:drop-shadow(0 40px 90px #000c)}}
.tk img{{width:846px;display:block;border-radius:20px;box-shadow:0 0 0 2px #ffd76a3d,0 0 120px 26px #ffd76a1a}}
.scan{{position:absolute;inset:0;opacity:.35;background:repeating-linear-gradient(0deg,#0000 0 3px,#0000000f 3px 4px)}}
.vig{{position:absolute;inset:0;background:linear-gradient(90deg,var(--bg) 0%,var(--bg) 28%,#05060ad9 39%,#05060a55 48%,transparent 58%),
 linear-gradient(0deg,#05060af2 0%,transparent 22%),linear-gradient(180deg,#05060ae6 0%,transparent 18%)}}
.h1{{position:absolute;left:78px;top:262px;font-family:Oswald;font-weight:700;font-size:96px;line-height:.93;text-transform:uppercase}}
.h1 em{{font-style:normal;color:var(--gold)}}
.meta{{position:absolute;left:84px;top:592px;font-family:'Roboto Mono';font-weight:700;font-size:23px;letter-spacing:.17em;color:var(--mut);text-transform:uppercase;line-height:1.75}}
.meta b{{color:var(--gold)}}
</style></head><body><div id="P">
<div class="tk"><img src="hero.png"></div><div class="scan"></div><div class="vig"></div>
<div class="h1">We blacked out<br>the names.<br><em>Not the score.</em></div>
<div class="meta">{len(S['open_moons'])} moonshots open<br>one pays <b>{ctx['to1']} to 1</b><br>doors close <b>{ctx['door']}</b></div>
{CHROME}</div></body></html>"""


# ---- TEMPLATE C: one enormous number ------------------------------------------------------
def tpl_C(S, ctx):
    return f"""<!doctype html><html><head><meta charset="utf-8"><style>{FONTS}
#P{{position:relative;width:1600px;height:900px;overflow:hidden;font-family:Inter;color:var(--txt);
 background:radial-gradient(1000px 760px at 800px 470px,#ffd76a16,transparent 70%),var(--bg)}}
.big{{position:absolute;left:0;right:0;top:238px;text-align:center;font-family:Oswald;font-weight:700;
 font-size:340px;line-height:.82;color:var(--gold);letter-spacing:-4px;text-shadow:0 0 120px #ffd76a3d}}
.to1{{position:absolute;left:0;right:0;top:600px;text-align:center;font-family:Oswald;font-weight:700;
 font-size:86px;letter-spacing:6px;text-transform:uppercase;color:var(--txt)}}
.sub{{position:absolute;left:0;right:0;top:722px;text-align:center;font-family:'Roboto Mono';font-weight:700;
 font-size:24px;letter-spacing:.22em;color:var(--mut);text-transform:uppercase}}
</style></head><body><div id="P"><div class="stars"></div>
<div class="big">{ctx['to1']}</div><div class="to1">to one</div>
<div class="sub">{len(S['open_moons'])} moonshots open · doors close {ctx['door']}</div>
{CHROME}</div></body></html>"""


# ---- TEMPLATE F: everything except the name ----------------------------------------------
def tpl_F(S, ctx, D):
    """Loewenstein: a SMALL, specific, nearly-closable gap beats a blackout. Give them the
    team, the slot, the arm, the price -- withhold only the man."""
    P = D.get('players') or {}
    hero = S['hero'] or (S['open_moons'][0] if S['open_moons'] else None)
    rows = ''
    for nm in (hero['legs'] if hero else [])[:3]:
        p = P.get(nm) or {}
        opp = (p.get('opp') or ['the arm'])[0]
        slot = p.get('slot')
        rows += f"""<div class="r"><div class="bar"></div><div class="cl">
          <div class="t">{p.get('team') or p.get('code') or '—'}{(' · bats ' + str(slot)) if slot else ''}</div>
          <div class="o">vs {opp}</div></div><div class="p">+{p.get('odds') or '—'}</div></div>"""
    return f"""<!doctype html><html><head><meta charset="utf-8"><style>{FONTS}
#P{{position:relative;width:1600px;height:900px;overflow:hidden;font-family:Inter;color:var(--txt);
 background:radial-gradient(900px 700px at 1120px 450px,#26d4f014,transparent 72%),var(--bg)}}
.h1{{position:absolute;left:78px;top:250px;font-family:Oswald;font-weight:700;font-size:104px;line-height:.93;text-transform:uppercase}}
.h1 em{{font-style:normal;color:var(--cyan)}}
.k{{position:absolute;left:84px;top:500px;font-family:Inter;font-size:29px;color:var(--mut);width:520px;line-height:1.45}}
.box{{position:absolute;left:800px;top:196px;width:700px}}
.r{{display:flex;align-items:center;gap:20px;padding:26px 0;border-bottom:1px solid #18202e}}
.bar{{width:210px;height:38px;border-radius:3px;background:#0b0d12;box-shadow:0 0 0 1px #ffffff12,inset 0 0 16px #000;flex:none}}
.cl{{flex:1}} .t{{font-size:23px;font-weight:700}} .o{{font-family:'Roboto Mono';font-size:16px;color:var(--dim);margin-top:4px}}
.p{{font-family:'Roboto Mono';font-size:30px;font-weight:700;color:var(--gold)}}
</style></head><body><div id="P"><div class="stars"></div>
<div class="h1">Name<br><em>him.</em></div>
<div class="k">Three men on tonight's biggest slip.<br>You get everything but who they are.</div>
<div class="box">{rows}</div>
{CHROME}</div></body></html>"""


# ---- TEMPLATE D: the reveal ---------------------------------------------------------------
def tpl_E(hist, ctx):
    """THE LEDGER. Plotted with the drawdowns visible on purpose -- a line that only goes up
    is the tell of a fake, and ours genuinely doesn't. Phase III proof."""
    h = [x for x in hist if isinstance(x, (int, float))][-70:]
    if len(h) < 2: h = [0, 0]
    lo, hi = min(h), max(h)
    rng = (hi - lo) or 1.0
    W, H = 700.0, 330.0
    pts = ' '.join('%.1f,%.1f' % (i * W / (len(h) - 1), H - (v - lo) / rng * H) for i, v in enumerate(h))
    peak = max(h); cur = h[-1]
    dd = peak - cur
    return f"""<!doctype html><html><head><meta charset="utf-8"><style>{FONTS}
#P{{position:relative;width:1600px;height:900px;overflow:hidden;font-family:Inter;color:var(--txt);
 background:radial-gradient(900px 700px at 1100px 450px,#26d4f014,transparent 72%),var(--bg)}}
.h1{{position:absolute;left:78px;top:250px;font-family:Oswald;font-weight:700;font-size:104px;line-height:.93;text-transform:uppercase}}
.h1 em{{font-style:normal;color:var(--lime)}}
.k{{position:absolute;left:84px;top:498px;font-family:Inter;font-size:29px;color:var(--mut);width:540px;line-height:1.45}}
.k b{{color:var(--txt)}}
.chart{{position:absolute;left:790px;top:250px;width:700px;height:330px}}
.stat{{position:absolute;left:790px;top:614px;display:flex;gap:56px}}
.s1{{font-family:'Roboto Mono';font-size:15px;letter-spacing:.16em;color:var(--dim);text-transform:uppercase}}
.s2{{font-family:Oswald;font-weight:700;font-size:44px;margin-top:6px}}
.up{{color:var(--lime)}} .dn{{color:var(--red)}}
</style></head><body><div id="P"><div class="stars"></div>
<div class="h1">Every<br><em>night.</em></div>
<div class="k">Published before the games. Graded after.<br><b>Including the parts that went backwards.</b></div>
<div class="chart"><svg viewBox="0 0 {W:.0f} {H:.0f}" width="700" height="330" preserveAspectRatio="none">
 <polyline points="{pts}" fill="none" stroke="#4ef08a" stroke-width="3" stroke-linejoin="round"/>
</svg></div>
<div class="stat">
 <div><div class="s1">Season</div><div class="s2 up">+{cur:.0f}u</div></div>
 <div><div class="s1">Peak</div><div class="s2">+{peak:.0f}u</div></div>
 <div><div class="s1">Off peak</div><div class="s2 dn">-{dd:.0f}u</div></div>
 <div><div class="s1">Nights</div><div class="s2">{ctx.get('nights', len(h))}</div></div>
</div>
{CHROME}</div></body></html>"""


def tpl_D(ctx):
    legs = ''
    for nm, odds, hit in ctx['legs']:
        legs += f"""<div class="leg {'':s}{'' if hit else 'dead'}"><div class="tick {'yes' if hit else 'no'}">{'✓' if hit else '✕'}</div>
          <div class="nm">{nm}</div><div class="pr">+{odds}</div></div>"""
    return f"""<!doctype html><html><head><meta charset="utf-8"><style>{FONTS}
#P{{position:relative;width:1600px;height:900px;overflow:hidden;font-family:Inter;color:var(--txt);
 background:radial-gradient(760px 560px at 1120px 450px,#4ef08a1f,transparent 70%),var(--bg)}}
.h1{{position:absolute;left:78px;top:258px;font-family:Oswald;font-weight:700;font-size:112px;line-height:.94;text-transform:uppercase}}
.h1 em{{font-style:normal;color:var(--lime)}}
.kick{{position:absolute;left:84px;top:498px;font-family:Inter;font-weight:500;font-size:31px;line-height:1.42;color:var(--mut);width:600px}}
.kick b{{color:var(--txt);font-weight:700}}
.card{{position:absolute;left:872px;top:196px;width:600px;border-radius:18px;padding:30px 34px 34px;
 background:linear-gradient(180deg,#111726,#0c111c);border:1px solid #4ef08a55;box-shadow:0 0 0 3px #4ef08a2e,0 0 90px 18px #4ef08a24,0 34px 80px #0009}}
.ct{{display:flex;align-items:baseline;justify-content:space-between}}
.cn{{font-family:Oswald;font-weight:700;font-size:37px;text-transform:uppercase}} .cn span{{color:var(--cyan)}}
.cd{{font-family:'Roboto Mono';font-size:17px;color:var(--dim);letter-spacing:.12em;text-transform:uppercase}}
.meta{{margin-top:8px;font-family:'Roboto Mono';font-size:17px;color:var(--dim);letter-spacing:.1em;text-transform:uppercase}}
.leg{{display:flex;align-items:center;gap:16px;padding:21px 0 19px;border-bottom:1px solid #1d2636}}
.tick{{width:36px;height:36px;border-radius:50%;display:grid;place-items:center;font-size:21px;font-weight:800;flex:none}}
.yes{{background:#4ef08a1f;color:var(--lime);border:2px solid #4ef08a}}
.no{{background:#ff6b5e12;color:var(--red);border:2px solid #ff6b5e66}}
.nm{{font-size:30px;font-weight:700;flex:1}} .pr{{font-family:'Roboto Mono';font-size:27px;font-weight:700;color:var(--gold)}}
.dead .nm{{color:#66748c}} .dead .pr{{color:#5c6982}}
.pay{{margin-top:26px;display:flex;align-items:baseline;justify-content:space-between}}
.pl{{font-family:'Roboto Mono';font-size:18px;letter-spacing:.16em;color:var(--mut);text-transform:uppercase}}
.pv{{font-family:Oswald;font-weight:700;font-size:62px;color:var(--lime);line-height:1}}
</style></head><body><div id="P"><div class="stars"></div>
<div class="h1">{ctx['head1']}<br><em>{ctx['head2']}</em></div>
<div class="kick">{ctx['kick']}</div>
<div class="card"><div class="ct"><div class="cn">{ctx['slip1']} <span>{ctx['slip2']}</span></div><div class="cd">{ctx['when']}</div></div>
<div class="meta">{ctx['struct']}</div>{legs}
<div class="pay"><div class="pl">Paid</div><div class="pv">{ctx['paid']}</div></div></div>
{CHROME}</div></body></html>"""


# ---------------------------------------------------------------- main
async def render(html_path, out, w=1600, h=900, scale=2):
    from playwright.async_api import async_playwright
    async with async_playwright() as p:
        b = await p.chromium.launch()
        pg = await b.new_page(viewport={'width': w, 'height': h}, device_scale_factor=scale)
        await pg.goto('http://127.0.0.1:%d/%s' % (PORT, html_path), wait_until='load')
        await pg.wait_for_timeout(1800)
        await pg.screenshot(path=out)
        await b.close()


async def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--day', type=int); ap.add_argument('--tpl')
    ap.add_argument('--out', default='/mnt/user-data/outputs/brand')
    ap.add_argument('--date')
    a = ap.parse_args()
    os.makedirs(a.out, exist_ok=True)

    now = et_now()
    today = a.date or now.strftime('%Y-%m-%d')
    dnum = a.day or (datetime.date.fromisoformat(today) - START).days + 1
    drop, door_tpl = CALENDAR.get(dnum, ('A', 'F'))
    tpl = a.tpl or drop

    D = board(today)
    S = slate(D, now)
    hero = S['hero']
    ctx = dict(to1=hero['to1'] if hero else '—', door=S['next_door'] or 'tonight',
               hero=hero['name'] if hero else '—')
    print('DAY %d (%s) | template %s = %s | %d moonshots open | hero %s @ %s to 1 | next door %s'
          % (dnum, today, tpl, NAMES.get(tpl, '?'), len(S['open_moons']), ctx['hero'], ctx['to1'], ctx['door']))

    work = os.path.join(HERE, '_work'); os.makedirs(work, exist_ok=True)
    for f in ('Oswald.ttf', 'Inter.ttf', 'RobotoMono.ttf'):
        src = os.path.join(HERE, f)
        if os.path.exists(src) and not os.path.exists(os.path.join(work, f)):
            subprocess.run(['cp', src, work], check=False)
    # index.html has to be reachable for the board-scraping templates
    idx = os.path.join(REPO, 'index.html')
    if os.path.exists(idx): subprocess.run(['cp', idx, work], check=False)
    httpd = serve(work)

    outs = []
    if tpl == 'A':
        from playwright.async_api import async_playwright
        async with async_playwright() as p:
            b = await p.chromium.launch()
            pg = await b.new_page(viewport={'width': 1280, 'height': 900}, device_scale_factor=4)
            ok = await shoot_ticket(pg, ctx['hero'], os.path.join(work, 'hero.png'))
            await b.close()
        if not ok: sys.exit('!! could not find the hero slip on the board')
        open(os.path.join(work, 'p.html'), 'w').write(tpl_A(S, ctx))
    elif tpl == 'C':
        open(os.path.join(work, 'p.html'), 'w').write(tpl_C(S, ctx))
    elif tpl == 'F':
        open(os.path.join(work, 'p.html'), 'w').write(tpl_F(S, ctx, D))
    elif tpl == 'E':
        hist = ((D.get('meta') or {}).get('season') or {}).get('history') or []
        nights = len(((D.get('meta') or {}).get('season') or {}).get('graded_nights') or [])
        open(os.path.join(work, 'p.html'), 'w').write(tpl_E(hist, dict(nights=nights)))
    elif tpl == 'D':
        prev = (datetime.date.fromisoformat(today) - datetime.timedelta(days=1)).isoformat()
        pp = os.path.join(REPO, 'D_%s.json' % prev)
        if not os.path.exists(pp): sys.exit('!! no board for %s -- cannot build a reveal' % prev)
        LN = last_night(json.load(open(pp)), prev)
        if not LN or not LN['best']:
            sys.exit('!! nothing cashed on %s -- the plan does not post a reveal after a losing '
                     'night. Use the day\'s drop template instead.' % prev)
        t, r = LN['best']
        P = LN['players']
        legs = [(nm, (P.get(nm) or {}).get('odds') or '?',
                 __import__('sys').modules['grade_night'].norm(nm) in LN['homered'])
                for nm in [p.get('name') for p in (t.get('players') or [])]]
        hit = sum(1 for _, _, h in legs if h)
        paid = '%.0f to 1' % (r['net'] / r['stake']) if r['stake'] else '—'
        w1, w2 = (t['name'].split(' ', 1) + [''])[:2] if ' ' in t['name'] else (t['name'], '')
        ctxD = dict(head1='%s of' % ('Two' if hit == 2 else 'One' if hit == 1 else 'All'),
                    head2='%s.' % ('three' if len(legs) == 3 else str(len(legs))),
                    kick=('The third one never showed up.<br><b>The slip paid anyway.</b>'
                          if hit < len(legs) else '<b>Every one of them.</b>'),
                    slip1=w1, slip2=w2,
                    when=datetime.date.fromisoformat(prev).strftime('%b %-d'),
                    struct='%su round robin · %s' % (r['stake'], (t.get('rr') or {}).get('struct', '')),
                    paid=paid, legs=legs)
        print('  reveal: %s went %d/%d, paid %s (night net %+.2fu)'
              % (t['name'], hit, len(legs), paid, LN['net']))
        open(os.path.join(work, 'p.html'), 'w').write(tpl_D(ctxD))
    else:
        print('  template %s has no renderer yet -- falling back to A' % tpl)
        from playwright.async_api import async_playwright
        async with async_playwright() as p:
            b = await p.chromium.launch()
            pg = await b.new_page(viewport={'width': 1280, 'height': 900}, device_scale_factor=4)
            await shoot_ticket(pg, ctx['hero'], os.path.join(work, 'hero.png'))
            await b.close()
        open(os.path.join(work, 'p.html'), 'w').write(tpl_A(S, ctx))

    png = os.path.join(a.out, 'day%02d-%s-%s.png' % (dnum, today, tpl))
    await render('p.html', png)
    outs.append(png)
    httpd.shutdown(); httpd.server_close()

    copy = {
        'A': "Today's board is live.\n\n%d moonshots open. One pays %s to 1.\n\nWe blacked out the names. Not the score.\n\nDoors close %s." % (len(S['open_moons']), ctx['to1'], ctx['door']),
        'C': "%s to one.\n\nThat's the longest thing on today's board, and it is free to look at.\n\n%d moonshots open. Doors close %s." % (ctx['to1'], len(S['open_moons']), ctx['door']),
        'F': "Three men on tonight's biggest slip.\n\nYou get the team, the spot, the arm and the price. Not the name.\n\nReply with the one you'd take. Names go up at %s." % (ctx['door'] or 'lock'),
    }.get(tpl, '')
    meta = dict(day=dnum, date=today, template=tpl, template_name=NAMES.get(tpl),
                door_template=door_tpl, open_moons=len(S['open_moons']), hero=ctx['hero'],
                to1=ctx['to1'], next_door=ctx['door'], image=png, copy=copy,
                first_reply="Free. No signup, no affiliate link, no promo code.\ntheticketroom.live")
    mp = os.path.join(a.out, 'day%02d-%s.json' % (dnum, today))
    json.dump(meta, open(mp, 'w'), indent=1)
    print('\n--- COPY ---\n%s\n\n--- FIRST REPLY ---\n%s\n' % (copy, meta['first_reply']))
    print('wrote %s\n      %s' % (png, mp))


if __name__ == '__main__':
    asyncio.run(main())
