"""test_nfl_voice.py -- NFLVOICE-2026-09-08. The football write-ups.

What the 2026-09-09 board looked like before this module existed:

    every player card's `why` was None                        -- 26 of 26
    every ticket note was "<Surname> is on N touches a game."  -- 4 of 4, one number apart

Owner: "we need way more creative write ups for football." Then, on the first rewrite: "i said
creative. are you trying to put me to sleep?" Then, on the second: "more variety and there is
still no creativity."

🚨 WHAT THE THIRD CUT CHANGED, AND WHAT THIS FILE NOW GUARDS. Both rejected rewrites were doing
the same thing in different words: READING THE STAT STRIP BACK OUT. The rendered card already
prints, two inches above the prose:

    Touches 16.5 · Inside 10 1.25 · Model 169 · GL share 0.076 · Weather ×0.998 · Team total 23.8

so "is on 16.5 touches a game" contributes nothing, and no supply of fresh adjectives fixes a
sentence that has no job. The third cut INTERPRETS instead: what 16.5 touches and 1.25 inside the
ten MEAN is that the offence runs through him and they trust him when it gets short. That is a
claim the chart cannot make and the reader cannot get anywhere else.

So the load-bearing check in this file is `no card recites a number` -- it is the difference
between the register the owner rejected twice and the one that replaced it, and it is the check
that will catch a future edit sliding back. The rest are the things that make prose WRONG rather
than merely dull, because dullness is visible and wrongness is not:

  * no matchup claim ever -- there is no defensive term on this board, so a sentence implying one
    is a lie the reader cannot check
  * superlatives are position-relative and TRUE -- "nobody here does more of either" must not be
    said of a man who is not top of his position
  * the same card twice is the same words -- a board that re-words itself every five minutes
    looks like it changed its mind
  * a three-leg note's dashes belong to the men, not to the frame (see DASH COLLISION below)
  * and it must actually vary, in words AND in shape, which is the complaint that started it

Run:  python3 test_nfl_voice.py
"""
import re
import sys

from nfl_voice import Voice

FAILS = []


def check(label, ok, detail=None):
    print(('PASS  ' if ok else 'FAIL  ') + label)
    if not ok:
        FAILS.append(label)
        if detail is not None:
            print('      ' + repr(detail))


def row(name, pos, tch, i10, shr, imp, pm, odds, basis='prior+depth', bg=15):
    return dict(name=name, pos=pos, tchpg=tch, i10pg=i10, i10_share=shr, imp=imp,
                p_model=pm, odds=odds, basis=basis, basis_games=bg)


# A slate with two real positions, a spread of implied totals, and one man with no game log.
SLATE = [
    row('Alpha Rushton',  'RB', 18.0, 1.60, 0.089, 27.5, 0.42, -110),
    row('Bravo Callis',   'RB', 15.0, 1.20, 0.080, 24.0, 0.30, +120),
    row('Charlie Deene',  'RB',  9.0, 0.60, 0.067, 21.0, 0.18, +240),
    row('Delta Marsh',    'RB',  4.0, 0.20, 0.050, 18.5, 0.09, +420),
    row('Echo Vance',     'WR',  9.5, 0.55, 0.058, 27.5, 0.28, +140),
    row('Foxtrot Bell',   'WR',  7.0, 0.35, 0.050, 24.0, 0.20, +190),
    row('Golf Prosser',   'WR',  5.0, 0.20, 0.040, 21.0, 0.13, +300),
    row('Hotel Kearns',   'WR',  3.0, 0.05, 0.017, 18.5, 0.07, +500),
    row('India Vogel',    'TE',  5.5, 0.45, 0.082, 27.5, 0.19, +250),
    row('Juliet Sarr',    'TE',  3.0, 0.10, 0.033, 18.5, 0.08, +550),
    row('Rookie Amos',    'RB',  7.0, 0.50, 0.071, 24.0, 0.14, +320, 'depth', 0),
]
BY = {r['name']: r for r in SLATE}
V = Voice(SLATE)

cards = {r['name']: V.why(r) for r in SLATE}
print()
for n, c in cards.items():
    print('   %-14s %s' % (n, c))
print()

# --- it produces prose at all, which is the whole complaint ---------------------------------
check('every player gets a write-up', all(cards.values()),
      [n for n, c in cards.items() if not c])
check('every write-up is a real sentence',
      all(c.endswith('.') and c[0].isupper() and len(c) > 30 for c in cards.values()),
      [c for c in cards.values() if not (c.endswith('.') and c[0].isupper() and len(c) > 30)])

# =============================================================================================
# 🚨 THE ONE THAT MATTERS. NO CARD RECITES A NUMBER.
# =============================================================================================
# This is the whole third rewrite in one assertion. The stat strip above the prose already prints
# touches, inside-10, GL share, model %, weather and team total; a sentence that repeats one of
# them is the register the owner rejected twice. Prose earns its place by saying what the numbers
# MEAN, and a meaning has no digits in it.
#
# ⚠️ IF YOU ARE HERE BECAUSE THIS FAILED: do not add the offending figure to an allow-list. The
# question to ask is what that number means, and then write THAT. The only numbers with any claim
# to appear are ones the strip cannot show because they need a comparison -- and those read as
# words ("nobody in his shirt sees it more"), not as figures.
for n, c in cards.items():
    check('no digits in the card for ' + n, not re.search(r'\d', c), c)

# --- and the write-ups actually differ -------------------------------------------------------
check('no two players get the same card', len(set(cards.values())) == len(cards))
leads = [c.split('.')[0] for c in cards.values()]
check('the cards do not all open the same way', len(set(leads)) >= len(cards) - 1, leads)

# ⚠️ VARIETY OF SHAPE, NOT ONLY OF WORDS. The second rewrite varied its vocabulary and still read
# like a form, because every card was one clause of the same length. `why()` gives some men one
# sentence and some three on purpose. If a build ever flattens that, the board goes back to
# reading like a mail merge even though every assertion above still passes.
lengths = {n: len(re.findall(r'\.(?:\s|$)', c)) for n, c in cards.items()}
check('cards vary in length (not every man gets the same number of sentences)',
      len(set(lengths.values())) >= 2, lengths)

# --- DETERMINISM. Same slate, same words, every build ----------------------------------------
again = {r['name']: Voice(SLATE).why(r) for r in SLATE}
check('a rebuild produces identical prose', again == cards)

# --- NO MATCHUP CLAIMS. The board has no defensive term; the prose must not imply one --------
BANNED = ['defen', 'soft', 'weak', 'vulnerable', 'gives up', 'allows', 'concede', 'worst against',
          'struggles', 'exploit', 'mismatch']
notes = []
for tname, trio in [('Six Points', ['Alpha Rushton', 'Echo Vance', 'India Vogel']),
                    ('Pylon', ['Bravo Callis', 'Foxtrot Bell', 'Juliet Sarr']),
                    ('Goal Line', ['Charlie Deene', 'Golf Prosser']),
                    ('The Workhorse', ['Delta Marsh'])]:
    notes.append(V.ticket_note([{'name': n} for n in trio], BY, tname=tname))
for n in notes:
    print('   note: ' + n)
print()
allprose = ' '.join(list(cards.values()) + notes).lower()
hits = [w for w in BANNED if w in allprose]
check('no matchup claim anywhere in the prose (there is no defensive term on this board)',
      not hits, hits)

# =============================================================================================
# EVERY HEADLINE BRANCH IS EXERCISED, because a phrase bank is where a typo hides.
# =============================================================================================
# The `story` angle has six mutually exclusive branches and each one calls pick() several times.
# A missing key argument is a TypeError that only fires for the players who take that branch --
# which on a real slate can be nobody for days. Force each branch and demand a well-formed
# (key, lead, fragment) triple out of every one.
BRANCH = [
    ('no game log',      row('Zed Nolog',  'RB',  7.0, 0.50, 0.071, 24.0, 0.14, +320, 'depth', 0)),
    ('bell cow',         row('Zed Bell',   'RB', 40.0, 9.00, 0.200, 27.5, 0.50, -200)),
    ('volume, no stripe', row('Zed Vol',   'RB', 40.0, 0.01, 0.001, 24.0, 0.20, +200)),
    ('goal-line special', row('Zed Spec',  'RB',  0.5, 9.00, 0.900, 24.0, 0.35, +150)),
]
for label, r in BRANCH:
    slate = SLATE + [r]
    v = Voice(slate)
    angs = v.angles(r, r['name'])
    ok = (angs and angs[0][0] == 'story' and len(angs[0]) == 3
          and all(isinstance(x, str) and x.strip() for x in angs[0][1:]))
    check('headline branch fires and is well formed: ' + label, ok, angs[:1])
    card = v.why(r)
    check('  ...and yields a card: ' + label, bool(card) and card.endswith('.'), card)

# ⚠️ FRAGMENTS ARE NAMELESS BY CONSTRUCTION. They are used as second and third sentences, where
# the man has already been named; a fragment that carries a surname is what produced "Rhamondre
# Stevenson ... Stevenson ... Stevenson" in the first cut.
badfrag = []
for r in SLATE:
    sur = r['name'].split()[-1]
    for key, ldr, frag in V.angles(r, r['name']):
        if sur in frag or r['name'] in frag:
            badfrag.append((r['name'], key, frag))
check('no fragment carries the player name', not badfrag, badfrag)

# --- SUPERLATIVES MUST BE TRUE, and they are position-relative -------------------------------
# Alpha is top of the backs; Echo is top of the receivers. Nobody else may claim it.
SUPER = ['nobody here does more', 'nobody in his shirt sees', 'than any', 'than the other',
         'more than anyone', 'first in the queue', 'the one they trust',
         'is expected to score least', 'the loudest game', 'the quietest game',
         'the highest-implied', 'the lowest-implied']
tops = {}
for pos in ('RB', 'WR', 'TE'):
    rs = [r for r in SLATE if r['pos'] == pos]
    tops[pos] = (max(rs, key=lambda r: r['i10pg'])['name'],
                 max(rs, key=lambda r: r['tchpg'])['name'])
for n, c in cards.items():
    low = c.lower()
    if 'nobody in his shirt sees more' in low or 'first in the queue near the stripe' in low \
            or 'the one they trust from a yard' in low:
        check('only the goal-line leader of his position claims the stripe: ' + n,
              n == tops[BY[n]['pos']][0], c)
    if 'the ball finds' in low or 'nobody in his shirt sees it more' in low:
        check('only the volume leader of his position claims the ball: ' + n,
              n == tops[BY[n]['pos']][1], c)
    if 'loudest game' in low or 'highest-implied' in low:
        check('only the highest-implied side says so: ' + n, BY[n]['imp'] == 27.5, c)
    if 'quietest game' in low or 'lowest-implied' in low or 'score least' in low:
        check('only the lowest-implied side says so: ' + n, BY[n]['imp'] == 18.5, c)

# --- a man with NO game log must say so -------------------------------------------------------
# ⚠️ CHECKED AGAINST THE MODULE'S OWN PHRASE BANK, not against a copy of one phrasing. The first
# cut of this check hardcoded 'depth chart', which is one of four wordings, so it went red the
# moment the rotation handed Rookie Amos a different one -- a test failing on a synonym teaches
# people to edit tests. Ask the module what it would say and check the card says one of those.
nolog_leads = [a[1] for a in V.angles(BY['Rookie Amos'], 'Rookie Amos') if a[0] == 'story']
check('a player with no game log gets the depth-chart headline',
      bool(nolog_leads) and any(l.lower() in cards['Rookie Amos'].lower() for l in nolog_leads),
      (cards['Rookie Amos'], nolog_leads))
check('and that headline is about the missing evidence, not about form',
      any(w in cards['Rookie Amos'].lower()
          for w in ('depth chart', 'projection', 'without a game', 'game log', 'nobody has seen')),
      cards['Rookie Amos'])

# --- the name does not repeat inside one card -------------------------------------------------
for n, c in cards.items():
    sur = n.split()[-1]
    check('the name is not repeated in ' + n, c.count(sur) <= 1, c)

# 🗑️ THE DE-PERSONALISATION CHECKS ARE GONE WITH THE FUNCTION THEY TESTED. `_depersonalise()`
# scrubbed a name back out of a second clause, which the number-reciting register needed because
# every clause was a full sentence about the man. The rewrite makes fragments nameless at the
# source, so the scrub has no callers and was deleted rather than left sitting there looking like
# a live safety net. What those three checks were protecting -- a card that says "Stevenson" three
# times -- is now covered upstream by `no fragment carries the player name` and downstream by
# `the name is not repeated in <player>`, which is the property that actually matters and does not
# care how it is achieved.

# =============================================================================================
# TICKET NOTES.
# =============================================================================================
n3 = notes[0]
check('a three-leg note mentions all three men',
      all(s in n3 for s in ('Rushton', 'Vance', 'Vogel')), n3)

# 🚨 DASH COLLISION -- THE BUG THIS CHECK EXISTS FOR. A three-leg note is built of "Surname —
# beat" pairs. Running those through FRAMES_3, which inserts dashes of its own, produced:
#
#     Price — nobody has seen him — Smith-Njigba — in the loudest game on the board
#
# which no reader can parse: there is no way to tell which dash separates men and which separates
# a man from his beat. Semicolons now separate the men and the dash belongs to each man's own
# beat, so a well-formed three-leg note has EXACTLY ONE em dash per leg.
for note, legs in zip(notes[:2], (3, 3)):
    check('a %d-leg note has one em dash per man, not a chain of them' % legs,
          note.count('—') == legs, note)
check('the men in a three-leg note are separated by semicolons', n3.count(';') == 2, n3)

# ⚠️ COUNT SENTENCE ENDINGS, NOT FULL STOPS. An earlier cut asserted `note.count('.') <= 2` and
# broke the moment a clause carried a decimal -- "18.0 a game" is not a sentence boundary. That
# particular trap is gone now that notes carry no digits at all, but the correct spelling stays:
# the thing that matters is the two-line clamp, not the punctuation census.
sentences = len(re.findall(r'\.(?:\s|$)', n3))
check('a three-leg note is at most three sentences', sentences <= 3, (sentences, n3))
check('every note fits the two-line clamp', all(len(n) <= 260 for n in notes),
      [(len(n), n) for n in notes if len(n) > 260])
check('the notes differ from each other', len(set(notes)) == len(notes))
check('no note recites a number either', not any(re.search(r'\d', n) for n in notes),
      [n for n in notes if re.search(r'\d', n)])

# 🚨 EVERY LEG OF THE SLIP IS NAMED. THIS ONE WAS SILENTLY BROKEN AND NOTHING CAUGHT IT.
# `ticket_note` gave every man a lead AND a fragment whenever the slip was not a treble, so a
# two-leg slip built four bits, sailed past the two-bit frame into the one-clause fallback, and
# printed one sentence about the first man with no mention of the second at all. The board showed
# a two-name ticket whose write-up knew about one name. A dull note is a complaint; a note that
# omits a leg is the reader holding a bet the page never explains. Check EVERY slip length.
two = notes[2]
check('a two-leg note names BOTH men', 'Deene' in two and 'Prosser' in two, two)
check('a two-leg note is one thought, not two paragraphs',
      len(re.findall(r'\.(?:\s|$)', two)) <= 2 and len(two) <= 260, two)

# A SINGLE is a whole slip with one man on it. One four-word fragment is a telegram, so it gets a
# lead and a fragment -- two beats, not one, and the second beat carries NO name because it is
# still the same man.
single = notes[3]
check('a one-leg note is more than a single fragment',
      len(single) > 40 and single.count('.') >= 1, single)
check('a one-leg note names its man', 'Marsh' in single, single)
check('a one-leg note names him ONCE', single.count('Marsh') == 1, single)

# Angles are consumed once per slip: the same reason must not be given for two different men.
beats = [b.split('—', 1)[1].strip() for b in n3.split(';') if '—' in b]
check('no two men on a slip are sold on the same beat', len(set(beats)) == len(beats), beats)

print()
if FAILS:
    print('FAILED: ' + str(len(FAILS)))
    sys.exit(1)
print('all checks pass')
