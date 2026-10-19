#!/usr/bin/env python3
"""nfl_howto.py -- HOWTOROOMS-2026-10-17. This room's How To tab.

Owner, 2026-10-17: "update the how to pages, they should be sport appropriate". The How To tab is index.html's
baseball page -- a three-leg Moonshot round robin, bats, parks, Kasper -- and each fork had patched words into it
one seam at a time, so the football and basketball rooms still diagrammed a baseball parlay. Now the whole tab body
(anatomy slip, steps, kinds) and its callout table are replaced from HOWTO below, and the narrower seams that used
to edit pieces of it are dropped automatically (howto_seams). The sample slip is this room's real product, a
straight single. Example names are retired legends, never a live pick.
"""
import json, sys

HOWTO = {
 "sub": "Every 🏈 Red Zone pick is a straight single, laid out like this one. Hover a label to trace its line; on a phone, tap a number.",
 "slip": {
  "badge": "🏈",
  "name": "The Workhorse",
  "odds": "+188",
  "pay": "$10 → $28.80",
  "lock": "1:00 PM",
  "sum": "💨1",
  "note": "Payton gets his work down in the red zone, where it’s tight, and it’s nasty, and I love it. He’s got grass stains on his grass stains.",
  "player": "Walter Payton",
  "b1": "💨 133.8",
  "b2": "🎯 34.7%",
  "where": "Bears · GB@CHI · 1:00",
  "meter": 74
 },
 "cal": {
  "1": [
   "Lock",
   "projected → ✓ when the inactives list posts, 90 minutes before kickoff → 🔒 at kickoff."
  ],
  "2": [
   "Weather",
   "Wind, rain and cold at the stadium. Weather is the only thing that moves a model total once prices are set."
  ],
  "3": [
   "Price",
   "Best consensus anytime-touchdown price, frozen the first time the board prices him."
  ],
  "4": [
   "Payout",
   "What $10 (one unit) returns if he scores."
  ],
  "5": [
   "Anytime TD",
   "Any touchdown he scores himself — rushing, receiving or a return. A touchdown he throws does not count."
  ],
  "6": [
   "Team · game · kickoff",
   "Who he plays for, the game, and when it kicks off."
  ],
  "7": [
   "Tier",
   "Rank on tonight’s slate: green premium, orange strong, pink value."
  ],
  "8": [
   "The pick",
   "A player the value rule backs at his price: our chance beats the book’s."
  ],
  "9": [
   "⚠ Flag",
   "Inactive risk — his status was still open when the board was built."
  ],
  "10": [
   "Weather & score",
   "The weather lean and his model score; about 100 is slate-average."
  ],
  "11": [
   "Model chance",
   "Our chance he finds the end zone, before the price."
  ],
  "12": [
   "Strength",
   "His score against the rest of tonight’s pool."
  ]
 },
 "steps": [
  [
   "Start on Tickets — tonight’s board, already drafted.",
   "Read it top to bottom: 🏁 Opening Drive, then 🏈 Red Zone (and 👑 King of the End Zone on one-game nights). The card at the top is the running season ledger."
  ],
  [
   "Check the lock line before you act on anything.",
   "Prices are set once. What moves after that is weather and the inactives list, which posts 90 minutes before kickoff; the ✓ arrives then, and the slip locks at kickoff."
  ],
  [
   "Open Players to see the field the board drafted from.",
   "Every player who cleared the pool gate, one card each. Sort by model score, shortest price, confirmed first, team or name, or search."
  ],
  [
   "Use Research to see why.",
   "One row per player: our chance against the book’s price (Edge), touches per game, his share of the work inside the 10, goal-line share, his team’s implied total and the weather. Click a name for the breakdown; <b>+</b> puts him on the slip tray, which follows you to every tab."
  ],
  [
   "Know how a pick settles.",
   "Anytime touchdown means any touchdown he scores himself; a passing touchdown does not count. A player ruled inactive is refunded. Opening Drive wins only on the game’s first touchdown."
  ]
 ],
 "kinds": [
  [
   "🏁",
   "Opening Drive",
   "First touchdown. One pick a slate, placed before kickoff: the player most likely to score his game’s <i>first</i> touchdown, from the football alone — his share of the touches, his share near the goal line, how often he scores, and his offence against their defence. The odds do not pick him. 1u."
  ],
  [
   "🏈",
   "Red Zone",
   "Every player the value rule backs at his price, one straight 1u bet each. No parlays."
  ],
  [
   "👑",
   "King of the End Zone",
   "One-game nights only. A DraftKings promo, not a free bet: place a qualifying bet on the game and pick who scores its longest touchdown, and the right pickers split the bonus-bet pot. The price shown is his anytime touchdown. Not on our ledger."
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
