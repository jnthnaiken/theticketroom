#!/usr/bin/env python3
"""soccer_howto.py -- HOWTOROOMS-2026-10-17. This room's How To tab.

Owner, 2026-10-17: "update the how to pages, they should be sport appropriate". The How To tab is index.html's
baseball page -- a three-leg Moonshot round robin, bats, parks, Kasper -- and each fork had patched words into it
one seam at a time, so the football and basketball rooms still diagrammed a baseball parlay. Now the whole tab body
(anatomy slip, steps, kinds) and its callout table are replaced from HOWTO below, and the narrower seams that used
to edit pieces of it are dropped automatically (howto_seams). The sample slip is this room's real product, a
straight single. Example names are retired legends, never a live pick.
"""
import json, sys

HOWTO = {
 "sub": "Every 🥅 Top Bin pick is a straight single, laid out like this one. Hover a label to trace its line; on a phone, tap a number.",
 "slip": {
  "badge": "🥅",
  "name": "Upper Ninety",
  "odds": "+120",
  "pay": "$10 → $22",
  "lock": "10:00 AM",
  "sum": "🟢1",
  "note": "Henry is getting the best looks on the card (0.18 xG a shot) and has played nearly every minute.",
  "player": "Thierry Henry",
  "b1": "📊 174.6",
  "b2": "🎯 0.68",
  "where": "Arsenal · ARS v CHE · 10:00",
  "meter": 80
 },
 "cal": {
  "1": [
   "Lock",
   "projected → ✓ when the starting XI is published, about an hour before kickoff → 🔒."
  ],
  "2": [
   "Substitute cover",
   "Who you inherit if he goes off: 🟢 strong, 🟡 thin, 🔴 none. Display only — the price does not move."
  ],
  "3": [
   "Price",
   "Best available anytime-goalscorer price across books, frozen the first time the board prices him."
  ],
  "4": [
   "Payout",
   "What $10 (one unit) returns if he scores."
  ],
  "5": [
   "Anytime goal",
   "Any goal he scores in normal time, stoppage time included. Extra time and own goals do not count."
  ],
  "6": [
   "Club · match · kickoff",
   "Two players from one match at most."
  ],
  "7": [
   "Tier",
   "Rank on tonight’s slate: green premium, orange strong, pink value."
  ],
  "8": [
   "The pick",
   "A confirmed starter we rate 45% or better to score, sold as a straight single."
  ],
  "9": [
   "Form & flags",
   "Form and trend: ↑ rising → steady ↓ cooling. ⚠ = rotation risk."
  ],
  "10": [
   "Model score",
   "What everything ranks on — half the market’s implied probability, half a house-brewed edge basket."
  ],
  "11": [
   "xG this match",
   "Non-penalty xG per 90 scaled by his expected minutes — goal expectancy in this match."
  ],
  "12": [
   "Strength",
   "The model score normalised across tonight’s pool."
  ]
 },
 "steps": [
  [
   "Start on Tickets — tonight’s board, already drafted.",
   "Read it top to bottom: 👟 The Brace, 🧤 The Goal Line, 🥅 Top Bin. The card at the top is the running season ledger. The View chips filter to one kind at a time."
  ],
  [
   "Check the lock line before you act on anything.",
   "Anything still <code>projected</code> can change as team news lands; the ✓ arrives with the published XI. The board re-reads the results feed every few minutes: goals, red cards and full time settle themselves on the card."
  ],
  [
   "Open Players to see the field the board drafted from.",
   "Every player who cleared the pool gate, one card each. Sort by model score, shortest price, confirmed first, team or name, or search."
  ],
  [
   "Use Research to see why.",
   "One row per player: xG, minutes, the defence he faces, and our chance against the price. Switch the View to Goals for the team-totals model behind the Goal Line. Click a name for the breakdown; <b>+</b> puts him on the slip tray, which follows you to every tab."
  ],
  [
   "Know how a pick settles.",
   "An anytime goal counts in normal time and stoppage time, not extra time, and own goals do not count. A player who does not play is refunded. Goal Line legs settle on the final score."
  ]
 ],
 "kinds": [
  [
   "👟",
   "The Brace",
   "Our pick of the day, one ticket at 2u. Of the starters already on the board at +250 or shorter, the man whose xG sits furthest above his price gets both units on one slip instead of a 1u single. Anytime goalscorer. Board players only."
  ],
  [
   "🧤",
   "The Goal Line",
   "One parlay a day on goals, not scorers: game totals, team totals and both teams to score, one leg per match. The slate sets the size: one leg on a one-match day, two on 2-5 matches, three on 6-11, four on 12 or more. Each leg is a line our goals model rates most likely to land that still pays -250 or better."
  ],
  [
   "🥅",
   "Top Bin",
   "Every confirmed starter we rate 45% or better to score (two a match at most), each a straight 1u single."
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
