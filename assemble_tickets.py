"""
The Ticket Room — ticket assembler (hardcoded rules + the latest updates).

Drop this into the build step AFTER the field is scored (it consumes the same
`D` the board renders: D['players'][name] = {odds, TOTAL, game, gmatch, gtime,
late, status, void, out, ...}). Call assemble(D) and it returns D['tickets'].

WHAT'S HARDCODED
================
Existing rules (from the model/README + tierOf):
  * Eligible field   = priced bats in the lineup, not voided/scratched.
  * Anchor ranking   = model TOTAL (the full-pool re-rank), one anchor per game.
  * Tier             = premium (rank < 9), strong (rank < 32), else value.
  * Moons            = anchor + 2 longshot partners, snake-drafted so each
                       parlay pairs a stronger bat with a longer shot.
  * Salami           = four longest shots in distinct games, full round robin.
  * Builders         = leftover bats as single-leg bankroll plays.
  * Nightcap         = the late single.

THE THREE UPDATES
=================
  (1) CHALK ROUTING  — chalk = the 8 shortest-odds bats. They are eligible
      ONLY in the lunch special and the nightcap. Moons, builders, and the
      salami are chalk-free.
  (2) MOON STRUCTURE — 5 moons in a 2/2/1 split: A1 x2, A2 x2, A3 x1.
      The 4th-best anchor (A4) LEADS THE SALAMI.
  (3) CARRYOVER      — games still suspended/resuming are rolled to the next
      slate (see carryover()).
"""
import re

LUNCH_CUT_MIN = 16 * 60          # 4:00 PM ET splits the lunch window from night
CHALK_N       = 8                # the ban8: 8 shortest-odds bats
MOON_PLAN     = (0, 0, 1, 1, 2)  # anchor indices per moon -> A1,A1,A2,A2,A3 (2/2/1)


# ---------- odds / time helpers ----------
def a2d(o):                       # American -> decimal
    return 1 + (o / 100.0 if o > 0 else 100.0 / abs(o))

def d2a(d):                       # decimal -> American
    return round((d - 1) * 100) if d >= 2 else round(-100 / (d - 1))

def gmin(gt):
    m = re.match(r'(\d+):(\d+)\s*(AM|PM)', gt or '')
    if not m:
        return None
    h = int(m[1]) % 12 + (12 if m[3] == 'PM' else 0)
    return h * 60 + int(m[2])


# ---------- selection ----------
def assemble(D):
    P  = D['players']
    gs = D.get('meta', {}).get('gs', {})            # live game-state map
    susp = lambda n: gs.get(str(P[n]['game'])) == 'susp'

    elig = [n for n, p in P.items()
            if p.get('odds') and not p.get('out') and not p.get('void')]
    byT  = lambda names: sorted(names, key=lambda n: P[n]['TOTAL'], reverse=True)
    byO  = lambda names: sorted(names, key=lambda n: P[n]['odds'])      # shortest first

    chalk    = set(byO(elig)[:CHALK_N])             # update (1): the ban8
    nonchalk = [n for n in elig if n not in chalk]

    latest      = max((gmin(P[n]['gtime']) or 0) for n in elig)
    lunch_games = {P[n]['game'] for n in elig if (gmin(P[n]['gtime']) or 0) < LUNCH_CUT_MIN}
    night_games = {P[n]['game'] for n in elig if (gmin(P[n]['gtime']) or 0) == latest}

    # anchors: best non-chalk by TOTAL, one per game, never a suspended game
    anchors, seen = [], set()
    for n in byT(nonchalk):
        g = P[n]['game']
        if g in seen or susp(n):
            continue
        anchors.append(n); seen.add(g)
        if len(anchors) >= 4:
            break

    tickets, used = [], set()

    def leg(n):
        p = P[n]
        return {"name": n, "team": p['team'], "total": p['TOTAL'], "aT": p['aT'],
                "wf": p['wf'], "gmatch": p['gmatch'], "gtime": p['gtime'],
                "game": p['game'], "late": bool(p.get('late')), "odds": p['odds'],
                "status": p['status']}

    def duo(anchor_game):
        out = []
        for n in byT([x for x in nonchalk if x not in anchors and x not in used]):
            if P[n]['game'] == anchor_game or any(P[n]['game'] == P[d]['game'] for d in out):
                continue
            out.append(n); used.add(n)
            if len(out) == 2:
                break
        return out

    def add(name, kind, badge, names, rr=None):
        legs = [leg(n) for n in names]
        t = {"name": name, "kind": kind, "badge": badge, "note": "",
             "players": legs, "nlegs": len(legs), "anchor": names[0],
             "lock": min(l['gtime'] for l in legs), "has_late": any(l['late'] for l in legs),
             "final": False, "rr": rr}
        tickets.append(t)

    # update (2): 5 moons, 2/2/1
    for ai in MOON_PLAN:
        if ai < len(anchors):
            a = anchors[ai]
            add("Moonshot", "moon", "\U0001f680", [a] + duo(P[a]['game']),
                rr={"struct": "by 2s & 3", "risk": 4.0})

    # update (2): A4 leads the salami (4 longest shots, distinct games, chalk-free)
    if len(anchors) >= 4:
        sal, segg = [anchors[3]], {P[anchors[3]]['game']}
        for n in byO([x for x in nonchalk if x not in anchors and x not in used])[::-1]:
            if P[n]['game'] in segg:
                continue
            sal.append(n); segg.add(P[n]['game']); used.add(n)
            if len(sal) == 4:
                break
        add("Grand Salami", "biggest", "\U0001f96a", sal,
            rr={"struct": "by 2s, 3s & 4", "risk": 11.0})

    # update (1): chalk only here — nightcap (late game) + lunch special (day games)
    ncap = byO([n for n in chalk if P[n]['game'] in night_games])
    if ncap:
        add("The Nightcap", "late", "\U0001f303", [ncap[0]])
    lunchc = byO([n for n in chalk if P[n]['game'] in lunch_games])
    if lunchc:
        add("Lunch Special", "lunch", "\U0001f371", [lunchc[0]])

    # builders: leftover non-chalk singles
    spent = set(anchors) | used | {t['anchor'] for t in tickets}
    for n in byT([x for x in nonchalk if x not in spent])[:6]:
        add("Bank-Roll Builder", "builder", "\U0001f4b0", [n])

    # price every ticket (same correlation rule the board uses)
    for i, t in enumerate(tickets, 1):
        t['n'] = i
        pr = [l for l in t['players'] if l['odds']]
        t['priced'] = t['confleg'] = len(pr)
        t['sum']  = round(sum(l['aT'] for l in t['players']), 1)
        t['msum'] = round(sum(l['total'] for l in t['players']), 1)
        if len(pr) == t['nlegs'] and pr:
            if len(pr) == 2 and pr[0]['game'] == pr[1]['game']:
                q1, q2 = 1 / a2d(pr[0]['odds']), 1 / a2d(pr[1]['odds'])
                rho = 0.12 if pr[0]['team'] == pr[1]['team'] else 0.06
                d = 1 / (q1 * q2 + rho * (q1 * (1 - q1) * q2 * (1 - q2)) ** 0.5)
            else:
                d = 1
                for l in pr:
                    d *= a2d(l['odds'])
            t['parlay_am'], t['payout10'] = d2a(d), round(10 * d, 2)
        else:
            t['parlay_am'] = t['payout10'] = None

    D['tickets'] = tickets
    D.setdefault('meta', {})['tickets'] = len(tickets)
    return tickets


# ---------- update (3): suspended-game carryover ----------
def carryover(D_today, D_prev):
    """Roll any game left suspended/resuming on the previous slate into today.

    Call once, before assemble(D_today): it pulls every player from a prior
    game whose state was 'susp' and merges them into today's field (and marks
    the game suspended) so the resuming legs stay live on the new board.
    """
    prev_gs = D_prev.get('meta', {}).get('gs', {})
    susp_games = {g for g, st in prev_gs.items() if st == 'susp'}
    if not susp_games:
        return D_today
    carried = {n: p for n, p in D_prev['players'].items()
               if str(p['game']) in susp_games}
    D_today['players'].update(carried)
    D_today.setdefault('meta', {}).setdefault('gs', {})
    for g in susp_games:
        D_today['meta']['gs'][g] = 'susp'
    return D_today


if __name__ == "__main__":
    import json
    s = open('/mnt/user-data/outputs/index.html').read()
    D = json.loads(re.search(r'const D=(\{.*?\}),WX=D\.meta\.wx;', s, re.S).group(1))
    ts = assemble(D)
    print(f"{len(ts)} tickets built\n")
    for t in ts:
        legs = " + ".join(f"{l['name']}(+{l['odds']})" for l in t['players'])
        pay  = f"  $10->${t['payout10']}" if t['payout10'] else ""
        print(f"  [{t['kind']:8}] {legs}{pay}")
