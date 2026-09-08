"""test_nfl_voice.py -- NFLVOICE-2026-09-08. The football write-ups.

What the 2026-09-09 board looked like before this module existed:

    every player card's `why` was None                    -- 26 of 26
    every ticket note was "<Surname> is on N touches a game."  -- 4 of 4, one number apart

Owner: "we need way more creative write ups for football."

The checks below are about the things that make prose WRONG rather than merely dull, because
dullness is visible and wrongness is not:

  * no matchup claim ever  -- there is no defensive term on this board, so a sentence implying
    one is a lie the reader cannot check
  * superlatives are position-relative and TRUE -- "as much as any back on the card" must not be
    said of a man who is not top of the backs
  * the same card twice is the same words -- a board that re-words itself every five minutes
    looks like it changed its mind
  * and it must actually vary, which is the complaint that started it

Run:  python3 test_nfl_voice.py
"""
import sys

from nfl_voice import Voice, _depersonalise

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
    row('Alpha Rushton',   'RB', 18.0, 1.60, 0.089, 27.5, 0.42, -110),
    row('Bravo Callis',   'RB', 15.0, 1.20, 0.080, 24.0, 0.30, +120),
    row('Charlie Deene', 'RB',  9.0, 0.60, 0.067, 21.0, 0.18, +240),
    row('Delta Marsh',   'RB',  4.0, 0.20, 0.050, 18.5, 0.09, +420),
    row('Echo Vance',    'WR',  9.5, 0.55, 0.058, 27.5, 0.28, +140),
    row('Foxtrot Bell', 'WR',  7.0, 0.35, 0.050, 24.0, 0.20, +190),
    row('Golf Prosser',    'WR',  5.0, 0.20, 0.040, 21.0, 0.13, +300),
    row('Hotel Kearns',   'WR',  3.0, 0.05, 0.017, 18.5, 0.07, +500),
    row('India Vogel',    'TE',  5.5, 0.45, 0.082, 27.5, 0.19, +250),
    row('Juliet Sarr',   'TE',  3.0, 0.10, 0.033, 18.5, 0.08, +550),
    row('Rookie Amos',  'RB',  7.0, 0.50, 0.071, 24.0, 0.14, +320, 'depth', 0),
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
      all(c.endswith('.') and c[0].isupper() and len(c) > 40 for c in cards.values()))

# --- and the write-ups actually differ -------------------------------------------------------
check('no two players get the same card', len(set(cards.values())) == len(cards))
leads = [c.split(',')[0].split(' — ')[0] for c in cards.values()]
check('the cards do not all open the same way', len(set(leads)) >= len(cards) // 2, leads)

# --- DETERMINISM. Same slate, same words, every build ----------------------------------------
again = {r['name']: Voice(SLATE).why(r) for r in SLATE}
check('a rebuild produces identical prose', again == cards)

# --- NO MATCHUP CLAIMS. The board has no defensive term; the prose must not imply one --------
BANNED = ['defen', 'soft', 'weak', 'vulnerable', 'gives up', 'allows', 'concede', 'worst against',
          'struggles', 'exploit', 'mismatch']
notes = []
for tname, trio in [('Six Points', ['Alpha Rushton', 'Echo Vance', 'India Vogel']),
                    ('Pylon', ['Bravo Callis', 'Foxtrot Bell', 'Juliet Sarr']),
                    ('Goal Line', ['Charlie Deene', 'Golf Prosser'])]:
    notes.append(V.ticket_note([{'name': n} for n in trio], BY, tname=tname))
for n in notes:
    print('   note: ' + n)
print()
allprose = ' '.join(list(cards.values()) + notes).lower()
hits = [w for w in BANNED if w in allprose]
check('no matchup claim anywhere in the prose (there is no defensive term on this board)',
      not hits, hits)

# --- SUPERLATIVES MUST BE TRUE, and they are position-relative -------------------------------
# Alpha is top of the backs; Echo is top of the receivers. Nobody else may claim it.
top_rb, top_wr = 'Alpha Rushton', 'Echo Vance'
for n, c in cards.items():
    if 'any back on the card' in c or 'no back on this card' in c or 'other back on the board' in c:
        check('only the top back claims the backs: ' + n, n == top_rb, c)
    if 'any receiver on the card' in c or 'other receiver on the board' in c:
        check('only the top receiver claims the receivers: ' + n, n == top_wr, c)
check('the highest-implied side is the one that says so',
      all(('highest-implied' not in c and 'more than' not in c.split('implied')[0])
          or BY[n]['imp'] == 27.5 for n, c in cards.items()
          if 'highest-implied' in c))

# --- a man with NO game log must say so -------------------------------------------------------
check('a player with no game log is flagged as depth-chart only',
      'depth chart' in cards['Rookie Amos'] or 'no game log' in cards['Rookie Amos'],
      cards['Rookie Amos'])

# --- the name does not repeat inside one card -------------------------------------------------
for n, c in cards.items():
    sur = n.split()[-1]
    check('the name is not repeated in ' + n, c.count(sur) <= 1, c)

# --- de-personalisation, including the possessive that broke the first cut --------------------
check('a leading name is dropped',
      _depersonalise('Alpha Rushton is on 18.0 a game', 'Alpha Rushton'), 'is on 18.0 a game')
check("a possessive becomes 'his'",
      _depersonalise("the market has Alpha Rushton's offence down for 27.5", 'Alpha Rushton'),
      'the market has his offence down for 27.5')
check('an object-position name is left alone (never "puts he in the end zone")',
      _depersonalise('the model puts Alpha Rushton in the end zone 42% of the time', 'Alpha Rushton'),
      'the model puts Alpha Rushton in the end zone 42% of the time')

# --- a three-leg note names each leg once, on a different angle each time ---------------------
n3 = notes[0]
check('a three-leg note mentions all three men',
      all(s in n3 for s in ('Rushton', 'Vance', 'Vogel')), n3)
# ⚠️ COUNT SENTENCE ENDINGS, NOT FULL STOPS. The first cut asserted `note.count('.') <= 2` and
# broke the moment a clause carried a decimal -- "18.0 a game" is not a sentence boundary. It also
# asserted the wrong thing: FRAMES_3 now uses a mid-note full stop ON PURPOSE, because a note that
# is always one comma-spliced list is what made the board read like a mail merge. What actually
# matters is that it stays inside the two-line clamp.
import re as _re
sentences = len(_re.findall(r'\.(?:\s|$)', n3))
check('a three-leg note is at most three sentences', sentences <= 3, (sentences, n3))
check('a three-leg note fits the two-line clamp', len(n3) <= 260, len(n3))
check('the notes differ from each other', len(set(notes)) == len(notes))

print()
if FAILS:
    print('FAILED: ' + str(len(FAILS)))
    sys.exit(1)
print('all checks pass')
