#!/usr/bin/env python3
"""nba_howto.py -- HOWTOROOMS-2026-10-17. This room's How To tab.

Owner, 2026-10-17: "update the how to pages, they should be sport appropriate". The How To tab is index.html's
baseball page -- a three-leg Moonshot round robin, bats, parks, Kasper -- and each fork had patched words into it
one seam at a time, so the football and basketball rooms still diagrammed a baseball parlay. Now the whole tab body
(anatomy slip, steps, kinds) and its callout table are replaced from HOWTO below, and the narrower seams that used
to edit pieces of it are dropped automatically (howto_seams). The sample slip is this room's real product, a
straight single. Example names are retired legends, never a live pick.
"""
import json, sys

HOWTO = {
 "sub": "Every pick on the board is a 🏀 Tip-Off single, laid out like this one. Hover a label to trace its line; on a phone, tap a number.",
 "slip": {
  "badge": "🏀",
  "name": "Jump Ball",
  "odds": "+950",
  "pay": "$10 → $105",
  "lock": "10:30 PM",
  "sum": "1u",
  "note": "Hakeem Olajuwon to score the first basket of HOU at LAL. He takes the opening tip for the Rockets, and the side that wins it usually scores first. Early in games the offense runs through him. The market is paying the star names; we are taking the value.",
  "player": "Hakeem Olajuwon",
  "b1": "⭕ tip 64%",
  "b2": "🎯 14.8%",
  "where": "Rockets · HOU@LAL · 10:30",
  "meter": 78
 },
 "cal": {
  "1": [
   "Lock",
   "projected → ✓ once the box score lists him as a starter. A posted pick never moves; if he drops out of the five before tip, he is replaced."
  ],
  "2": [
   "Stake",
   "One unit on every pick, flat. Straight bets only — no parlays."
  ],
  "3": [
   "Price",
   "FanDuel’s first-basket price when the pick posted. The bet grades at this price."
  ],
  "4": [
   "Payout",
   "What $10 (one unit) returns if he makes the first field goal."
  ],
  "5": [
   "First basket",
   "The bet: he makes the game’s first field goal. Free throws do not count."
  ],
  "6": [
   "Team · game · tip",
   "One pick per game at most, up to three a night."
  ],
  "7": [
   "Status",
   "Pending until anyone makes a field goal, then it settles on the spot — usually inside two minutes."
  ],
  "8": [
   "The pick",
   "A starter whose chance beats his price by 30% or more — or, if nobody clears that, the night’s best edge."
  ],
  "9": [
   "⚠ Flag",
   "No lineup had posted yet, so his five was read off the price list. Wait for the ✓."
  ],
  "10": [
   "Tip",
   "His team’s chance to win the opening tip, from a jump-ball rating on each side’s center."
  ],
  "11": [
   "Chance",
   "Our chance he makes the first field goal — the model, with the books blended in as one layer."
  ],
  "12": [
   "Strength",
   "His chance against the rest of tonight’s starters."
  ]
 },
 "steps": [
  [
   "Start on Tickets — tonight’s 🏀 Tip-Off picks.",
   "Each is a 1u straight bet on one starter to make his game’s first field goal. The card at the top is the season ledger, graded live."
  ],
  [
   "Check the lock line before you act on anything.",
   "Picks post once FanDuel’s first-basket prices and the projected starting fives are up, and they do not move after that. The one exception is a man who drops out of his team’s five before tip: he is replaced. The ✓ arrives when the box score lists him as a starter."
  ],
  [
   "Open Players to see the whole field.",
   "Every starter on tonight’s slate, one card each, with his chance, his team’s tip and first-score odds, and his early-shot numbers. Sort, jump to a team, or search."
  ],
  [
   "Use Research to see why.",
   "One row per starter: our chance against FanDuel’s price (Edge), the market’s own chance with the margin taken out, the tip, his share of his team’s first baskets, early shots, first shot and FG%. Click a name for the breakdown; <b>+</b> puts him on the slip tray, which follows you to every tab."
  ],
  [
   "Know how a pick settles.",
   "It wins only on the game’s first made field goal — free throws do not count — and is usually decided inside two minutes. A man who does not play is refunded; a man who plays off the bench is still a live bet."
  ]
 ],
 "kinds": [
  [
   "🏀",
   "Tip-Off",
   "First basket: the first made field goal of the game. Every starter whose chance beats his FanDuel price by 30% or more, one per game, up to three a night, 1u each. If nobody clears that bar, the single best edge on the slate. No parlays."
  ],
  [
   "⭕",
   "Why the tip",
   "The team that wins the opening tip makes the first field goal close to two times in three. Every center’s jump-ball record is rated, so the tip is called before the game, not guessed — and the books price the stars, not the man in the circle."
  ]
 ]
}
# json round-trips the int keys of `cal` as strings
HOWTO["cal"] = {int(k): tuple(v) for k, v in HOWTO["cal"].items()}

def _slip(s):
    return f"""<div class="stage" id="stage">
    <svg class="leaders" id="leaders"></svg>
    <div class="zone ht-t" id="colT"></div>
    <div class="stagegrid">

      <div class="col left" id="colL"></div>

      <div class="cardcol">
        <div class="slip" id="card">
          <div class="top">
            <div class="toprow">
              <div class="ttitle">
                <span class="tbadge">{s['badge']}</span>
                <div class="tname">{s['name']}</div>
              </div>
              <div class="parlay">
                <div class="od" data-cal="3">{s['odds']}</div>
                <div class="pay" data-cal="4">{s['pay']}</div>
              </div>
            </div>
            <div class="lockline">
              <span class="badge" data-cal="1">projected</span>
              <span>Lock {s['lock']} ET</span>
              <span class="wxsum" data-cal="2">{s['sum']}</span>
            </div>
            <div class="tnote">{s['note']}</div>
          </div>
          <div class="legs">
            <div class="leg t-premium">
              <span class="dot" data-cal="7"></span>
              <span class="nm" data-cal="8"><span class="lst p">⏳</span>{s['player']}</span>
              <span class="od" data-cal="5">{s['odds']}</span>
              <span class="lmeta">
                <span class="wbadge" data-cal="10">{s['b1']}</span>
                <span class="bbadge" data-cal="11">{s['b2']}</span>
                <span class="lbrk"></span>
                <span class="sbadge" data-cal="9">⚠</span>
                <span class="lwhere" data-cal="6">{s['where']}</span>
              </span>
              <span class="meter" data-cal="12"><i style="width:{s['meter']}%"></i></span>
            </div>
          </div>
        </div>
      </div>

      <div class="col right" id="colR"></div>
    </div>
    <div class="zone ht-b" id="colB"></div>
  </div>"""


def _block(H):
    steps = '\n'.join(f"      <li>\n        <b>{b}</b>\n        {t}\n      </li>" for b, t in H['steps'])
    kinds = '\n'.join(f'    <div class="kind"><span class="ke">{e}</span><div><b>{b}</b><span>{t}</span></div></div>' for e, b, t in H['kinds'])
    return f"""  <div class="htead">
    <div class="htkick">How to read the board</div>
    <h1 class="hth1">Anatomy of a ticket</h1>
    <p class="htsub">{H['sub']}</p>
    <div class="expill">● Example only — not a live pick</div>
  </div>

  {_slip(H['slip'])}

  <div class="mlist" id="mlist"></div>


  <div class="steps">
    <h2 class="steph">Using the board</h2>
    <ol class="steplist">
{steps}
    </ol>
  </div>

  <div class="kinds">
{kinds}
  </div>


"""


def _cal(H):
    side = {1: 'T', 2: 'T', 3: 'T', 4: 'R', 5: 'R', 6: 'R', 7: 'L', 8: 'L', 9: 'L', 10: 'B', 11: 'B', 12: 'B'}
    rows = []
    for n in range(1, 13):
        t, d = H['cal'][n]
        ax = " ax:'right'," if n == 12 else ''
        rows.append(" {n:%d, side:'%s',%s t:%s, d:%s}" % (n, side[n], ax, json.dumps(t, ensure_ascii=False).replace('"', "'") if "'" not in t else json.dumps(t, ensure_ascii=False),
                                                       json.dumps(d, ensure_ascii=False)))
    return 'var CAL = [\n' + ',\n'.join(rows) + '\n];'


def howto_seams(S, src):
    """Swap the How To tab's whole body and its callout table (CAL) for this room's, and drop every
    narrower seam that edited a piece of either -- those pieces no longer exist in this room.
    Anchors must each appear once, and a dropped seam must not ALSO match outside the How To
    (it would silently stop applying there) -- both fail the build loudly."""
    A = '  <div class="htead">'
    if src.count(A) != 1:
        sys.exit(f'!! HOWTOROOMS: How To anchor found {src.count(A)}x -- index.html moved')
    a = src.index(A)
    k = src.index('<div class="kinds">', a)
    e = src.index('</section>\n<section id="v-o"', k)
    block = src[a:e]
    if src.count('var CAL = [') != 1:
        sys.exit('!! HOWTOROOMS: CAL table not found exactly once')
    c0 = src.index('var CAL = ['); c1 = src.index('];', c0) + 2
    cal = src[c0:c1]
    keep, dropped = [], []
    for s in S:
        label, old = s[0], s[1]
        if label != 'payload' and (old in block or old in cal):
            if src.count(old) != block.count(old) + cal.count(old):
                sys.exit(f'!! HOWTOROOMS: seam {label!r} matches inside AND outside the How To -- split it')
            dropped.append(label)
            continue
        keep.append(s)
    i = 1 if keep and keep[0][0] == 'payload' else 0
    keep[i:i] = [('howto-block', block, _block(HOWTO), 1), ('howto-cal', cal, _cal(HOWTO), 1)]
    return keep, dropped
