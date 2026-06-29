#!/usr/bin/env python3
"""
Auto-grader  ->  keeps season.json current with ZERO daily input.

Run as STEP 1 of the morning pipeline, before build15:
    python grade_night.py && python build15.py && python regen15.py

What it does:
  - Reads season.json to find the last graded night.
  - For every night AFTER it, up to yesterday, that is FULLY FINAL in the MLB
    feed, it grades that night's board (D_<date>.json) leg-by-leg off real
    play-by-play home runs and folds the net into season.json (history, cats,
    graded_nights). Postponed games void their legs (refund). It never grades a
    night that isn't final yet (so a lagged feed just means it folds that night
    the next morning instead), and never double-grades a night already in the
    ledger. Net result: the tracker is always current before the new slate builds.

Grading mirrors the published board's gradeTicket() exactly (round-robin moons/
salami, single-leg builders/lunch/nightcap, american->decimal payouts).
"""
import json, os, re, sys, unicodedata, datetime, itertools, urllib.request
from calibrate import build_rows, load_extras   # reuse the pure row-builder so each graded night also logs to calibration.jsonl (+ full Kasper stat sidecar)

SA   = "https://statsapi.mlb.com/api/v1"
ROOT = os.path.dirname(os.path.abspath(__file__))
# our team-code -> StatsAPI abbreviation aliases (only the ones that differ)
ALIAS = {"AZ":"AZ","ARI":"AZ","CWS":"CWS","CHW":"CWS","ATH":"ATH","SF":"SF","SD":"SD","TB":"TB","KC":"KC","WSH":"WSH"}

def norm(s):
    s = unicodedata.normalize('NFKD', s or '')
    return ''.join(c for c in s if not unicodedata.combining(c)).lower().replace('.', '').replace(' ', '').strip()

def getj(u):
    with urllib.request.urlopen(u, timeout=30) as r:
        return json.load(r)

def dec(a):  # american -> decimal
    return 1 + a/100.0 if a > 0 else 1 + 100.0/abs(a)

# ---------- pull a night's outcomes from the feed ----------
def results_for(date):
    """(homered:set[norm name], all_final:bool, ppd_codes:set[abbr]) for `date`."""
    try:
        sch = getj(f"{SA}/schedule?sportId=1&date={date}&hydrate=team")
    except Exception:
        return set(), False, set()
    dates = sch.get('dates') or []
    games = dates[0].get('games', []) if dates else []
    if not games:
        return set(), False, set()
    homered, ppd, all_final = set(), set(), True
    for g in games:
        st = g.get('status') or {}
        ds, ab = (st.get('detailedState') or ''), (st.get('abstractGameState') or '')
        if re.search('postpon', ds, re.I):
            for sd in ('away', 'home'):
                try: ppd.add(g['teams'][sd]['team']['abbreviation'])
                except Exception: pass
            continue
        if not (re.search('final|completed|over', ds, re.I) or ab.lower() == 'final'):
            all_final = False
            continue
        try:
            pbp = getj(f"{SA}/game/{g['gamePk']}/playByPlay"
                       f"?fields=allPlays,result,eventType,matchup,batter,fullName")
        except Exception:
            all_final = False
            continue
        for p in pbp.get('allPlays', []):
            if (p.get('result') or {}).get('eventType') == 'home_run':
                nm = ((p.get('matchup') or {}).get('batter') or {}).get('fullName')
                if nm: homered.add(norm(nm))
    return homered, all_final, ppd

# ---------- grade one ticket (faithful port of the board's gradeTicket) ----------
def grade_ticket(t, homered, ppd_codes, stake):
    legs = t.get('players') or []
    if not legs:
        return None
    def voided(l):
        code = (l.get('team') or l.get('code') or '')[:3].upper()
        return code in ppd_codes
    # leg state: True=HR, False=miss, None=void(ppd, refund)
    kept = []
    for l in legs:
        if voided(l):
            continue
        kept.append((l, norm(l.get('name')) in homered))
    if not kept:
        return {'kind': t['kind'], 'stake': 0.0, 'net': 0.0, 'won': None}   # whole ticket voided
    if t.get('rr'):
        risk = float(t['rr'].get('risk') or 0)
        d  = [dec(l['odds']) for l, _ in kept]
        hh = [h for _, h in kept]
        K  = len(kept)
        sizes = [2, 3] + ([4] if K >= 4 else [])
        net = -risk
        for sz in sizes:
            for combo in itertools.combinations(range(K), sz):
                if all(hh[i] for i in combo):
                    p = 1.0
                    for i in combo: p *= d[i]
                    net += p
        return {'kind': t['kind'], 'stake': risk, 'net': round(net, 2), 'won': net > 0}
    # single leg / straight (payout10 path)
    cashed = all(h for _, h in kept)
    pay10 = t.get('payout10')
    if pay10 is None:
        dd = 1.0
        for l, _ in kept: dd *= dec(l['odds'])
        pay10 = 10 * dd
    if cashed:
        return {'kind': t['kind'], 'stake': stake, 'net': round(stake*(pay10/10.0 - 1), 2), 'won': True}
    return {'kind': t['kind'], 'stake': stake, 'net': -float(stake), 'won': False}

# ---------- fold one graded night into the season ledger ----------
def fold(season, date, graded):
    cats = season.setdefault('cats', {})
    net_total = 0.0
    for g in graded:
        if not g or g.get('won') is None:
            continue
        c = cats.setdefault(g['kind'], {'graded': 0, 'won': 0, 'units': 0.0, 'staked': 0.0})
        c['graded'] += 1
        if g['won']: c['won'] += 1
        c['units']  = round(c['units']  + g['net'],   2)
        c['staked'] = round(c['staked'] + g['stake'], 2)
        net_total  += g['net']
    hist = season.setdefault('history', [0.0])
    hist.append(round(hist[-1] + net_total, 2))
    season.setdefault('graded_nights', []).append(date)
    return round(net_total, 2)

def main():
    spath = os.path.join(ROOT, 'season.json')
    season = json.load(open(spath))
    stake = season.get('stake', 1)
    graded = set(season.get('graded_nights', []))
    today = (datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(hours=4)).date()
    # candidate nights: any dated board we have that isn't graded yet, up to yesterday
    nights = sorted(re.match(r'D_(\d{4}-\d{2}-\d{2})\.json$', f).group(1)
                    for f in os.listdir(ROOT) if re.match(r'D_\d{4}-\d{2}-\d{2}\.json$', f))
    folded = []
    for date in nights:
        if date in graded:                     continue
        if datetime.date.fromisoformat(date) >= today:  # never grade today/future
            continue
        homered, all_final, ppd = results_for(date)
        if not all_final:
            print(f"{date}: not final in the feed yet -> will fold next run")
            break                              # keep nights in order; stop at first unsettled
        D = json.load(open(os.path.join(ROOT, f'D_{date}.json')))
        gr = [grade_ticket(t, homered, ppd, stake) for t in D.get('tickets', [])]
        net = fold(season, date, gr)
        # calibration logging is handled SEPARATELY by `calibrate.py` (idempotent, self-healing
        # backfill run as its own pipeline step), so grade_night never silently drops rows.
        cashed = sum(1 for g in gr if g and g.get('won'))
        print(f"{date}: graded {len(gr)} tickets, {cashed} cashed, net {net:+.2f}u "
              f"-> season {season['history'][-1]:.2f}u")
        folded.append(date)
    if folded:
        json.dump(season, open(spath, 'w'), indent=1)
        print(f"folded {len(folded)} night(s); ledger now {season['history'][-1]:.2f}u through {folded[-1]}")
    else:
        print("nothing new to grade; ledger unchanged at "
              f"{season.get('history',[0])[-1]:.2f}u")

if __name__ == '__main__':
    main()
