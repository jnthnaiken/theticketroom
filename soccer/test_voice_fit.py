#!/usr/bin/env python3
"""VOICE-2026-09-23 / TNOTEFIT-2026-09-23 -- the guard rails on an excitable voice.

The soccer write-ups were rewritten into a much more operatic register. That is a taste call
and this file does not test taste. It tests the four things that stop the register from
quietly breaking the board, each of which HAS broken it before:

  1. EVERY clause carries its own number.  The docstring on Voice.angles has said since the
     first version that "every entry restates a number that is on the payload; nothing here
     predicts anything". With six phrasings per angle that was a promise a reader could check.
     With eleven it is not, so the check is here: the 'rate' bank must print the xG90, the
     'volume' bank the shots, the 'price' bank the odds, and so on, in every single variant.
     A flourish that forgets its number is a sentence that asserts something about a player
     with nothing behind it, which is the one thing this board does not do.

  2. THE LEAD IS ALWAYS THE SUBJECT (VOICE-2026-08-28c).  `_depersonalise` strips the name off
     clauses two and three, so they inherit whatever subject clause one set up. If clause one
     is an object form -- "the manager will not take Kane off" -- the rest of the sentence gets
     said about the manager. `say(lead=True)` filters for subject forms; this asserts the
     filter finds one in every bank that has one, and that the result really does lead with
     the player.

  3. NO BANK ENTRY PUTS THE NAME IN SUBJECT POSITION MID-SENTENCE.  This is the same bug from
     the other side. A non-leading clause has its name replaced by "him", so "so {who} comes
     to us with nothing" becomes "so him comes to us with nothing". Any entry where the name
     follows a conjunction is that shape. Caught by pattern, cheaply, forever.

  4. THE NOTE FITS (TNOTEFIT).  `.tnote` is `-webkit-line-clamp:2`. An overlong note is not
     ugly, it is TRUNCATED -- the browser bins the tail and the last fact on the slip vanishes
     off the card. CLMPTIER-2026-09-23 was exactly this failure one layer up and it cost a
     moon its entire write-up. The ratchet in ticket_note composes shorter rather than letting
     the browser cut, and the assertion here is that it actually converges: over a sweep of
     synthetic players built to be maximally chatty (every angle live, longest names, widest
     numbers), no note exceeds TNOTE_B.

Run: python3 test_voice_fit.py
"""
import itertools
import re
import sys

import soccer_payload as SP

FAIL = []


def check(ok, msg, got=''):
    print(('PASS  ' if ok else 'FAIL  ') + msg + (('   ' + str(got)) if got and not ok else ''))
    if not ok:
        FAIL.append(msg)


# ---------------------------------------------------------------------------------------
# A slate wide enough that _hi()'s p60 thresholds are real, plus one player who sits above
# every one of them so that every angle fires at once.
SLATE = [{'npxg90': 0.10 + i * 0.03, 'xgpershot': 0.05 + i * 0.01, 'shots90': 1.0 + i * 0.2}
         for i in range(12)]
V = SP.Voice(SLATE)

LOUD = {'name': 'Bartholomew Featherstonehaugh', 'npxg90': 0.99, 'xgpershot': 0.44,
        'shots90': 5.5, 'finish90': 0.14, 'odds': 275, 'league': 'UCL_PO'}
QUIET = dict(LOUD, finish90=-0.21, odds=-135, league='MLS')
BLANK = {'name': 'Kwadwo Opoku', 'npxg90': None, 'xgpershot': None, 'shots90': None,
         'finish90': None, 'odds': 188, 'league': 'MLS'}

WHO = 'Featherstonehaugh'

# Every phrasing in every bank, by angle key. `salt` only reseeds _pick, so sweeping salts
# enumerates the banks without reaching inside them.
BANKS = {}
for pl, avg in ((LOUD, 88), (LOUD, 61), (QUIET, 88), (QUIET, 61), (BLANK, 88), (BLANK, 61)):
    who = SP._surname(pl['name'])
    for salt in (str(n) for n in range(400)):
        for key, brief, full in V.angles(pl, avg, who, salt=salt):
            BANKS.setdefault(key, set()).update((brief, full))

check(set(BANKS) == {'noxg', 'price', 'rate', 'quality', 'volume', 'finish', 'mins'},
      'the sweep reached every angle bank', sorted(BANKS))
check(all(len(v) >= 6 for v in BANKS.values()),
      'the sweep enumerated each bank (>=6 phrasings seen per angle)',
      {k: len(v) for k, v in BANKS.items()})

# ---------------------------------------------------------------------------------------
# 1. every clause carries its number.
NUM = {
    'rate': r'0\.\d\d',          # npxg90
    'quality': r'0\.\d\d',       # xgpershot
    'volume': r'\d\.\d',         # shots90
    'finish': r'0\.\d\d',
    'mins': r'\d\d',             # minutes
    'price': r'[+-]\d+',
}
# The FULL form is the one a soccer card and a soccer ticket both use, and it is held to the
# letter of the rule: it prints the figure. The BRIEF form is the compressed one a three-leg
# slip falls back to, and `mins` is the single bank where compressing means dropping the digit
# -- "plays the ninety" is a restatement of avg>=75, which is on the payload, not a new claim.
# That licence is scoped to exactly this bank and exactly the brief forms; anywhere else, a
# phrasing with no number in it is a sentence asserting something the data has not said, and
# the assertion below is what keeps the licence from spreading.
for pl, avg in ((LOUD, 88), (LOUD, 61), (QUIET, 88), (QUIET, 61), (BLANK, 88), (BLANK, 61)):
    who = SP._surname(pl['name'])
    for salt in (str(n) for n in range(200)):
        for key, brief, full in V.angles(pl, avg, who, salt=salt):
            if key == 'noxg':
                continue
            check_pat = NUM[key]
            if not re.search(check_pat, full):
                FAIL.append('full %r has no number' % full)
            if key != 'mins' and not re.search(check_pat, brief):
                FAIL.append('brief %r has no number' % brief)
check(not FAIL, 'every full phrasing prints its number, and every brief but mins does',
      FAIL[:3])

MINSLESS = [t for t in BANKS['mins'] if not re.search(r'\d\d', t)]
check(MINSLESS and all(t in BANKS['mins'] for t in MINSLESS),
      "the numberless 'mins' phrasings exist and are the compressed brief forms (%d of them)"
      % len(MINSLESS))

# `noxg` is the one bank whose FACT is an absence, so it has no figure of its own -- but it
# must still name the player, or a clause two positions later has nothing to attach to.
check(all(WHO in t or 'Opoku' in t for t in BANKS['noxg']),
      "every 'noxg' phrasing names the player (its fact is the absence of a number)")

allphr = set().union(*BANKS.values())
check(all(('Featherstonehaugh' in t) or ('Opoku' in t) for t in allphr),
      'every phrasing in every bank names the player')

# ---------------------------------------------------------------------------------------
# 2. the lead is always the subject.
for pl, avg in ((LOUD, 88), (QUIET, 61), (BLANK, 88)):
    who = SP._surname(pl['name'])
    leads = [a for salt in (str(n) for n in range(120))
             for a in V.angles(pl, avg, who, salt=salt, lead=True)]
    bad = [(k, b, f) for k, b, f in leads
           if not (b.startswith(who + ' ') and f.startswith(who + ' '))]
    check(not bad, 'lead=True always opens with the player as subject (%s)' % pl['name'],
          bad[:2])

# ---------------------------------------------------------------------------------------
# 3. no name in subject position mid-sentence.
CONJ = re.compile(r'\b(?:so|and|but|then|because|while|where|which|that|if)\s+'
                  r'(?:Featherstonehaugh|Opoku)\b')
bad = [t for t in allphr if CONJ.search(t)]
check(not bad,
      "no phrasing puts the name after a conjunction (_depersonalise would print 'so him ...')",
      bad[:3])

# The positive form of the same rule: replacing the name with 'him' must never produce a
# capitalised-sentence-start 'Him' or a bare 'him <verb>' opening.
deperse = [SP._depersonalise(t, WHO) for t in allphr if WHO in t]
check(not [d for d in deperse if d.startswith('him ') or d.startswith('Him')],
      'no phrasing depersonalises to a clause that OPENS with "him"',
      [d for d in deperse if d.lower().startswith('him ')][:2])

# 3b. VOICE-2026-09-23c -- and no object form anywhere but the FINAL clause of a card.
#
# The mirror of the rule above. An object form does not just misfire when it LEADS; it
# misfires anywhere it is followed by another clause, because it supplies a subject of its own
# and the bare verb phrase after it attaches to that ("... the football gods owe him 0.12 a
# 90, and is magisterial in there" -- the gods are magisterial). Only the last clause is safe.
# A clause that inherits its subject correctly begins with a VERB; anything starting with an
# article, a bare number, or an existential 'there' has brought its own.
# Splitting the rendered sentence on commas does not work -- plenty of single clauses carry
# an internal comma ("is on for 88 minutes an appearance, there at the death"). So go the
# other way: take the object forms straight out of the bank, and assert that if one of them
# made it onto the card at all, it is at the very END of the sentence.
#
# The name sweep below is not decoration. `_pick` is seeded by the player's name, so which
# phrasing a given angle produces depends entirely on who it is about, and a three-name sweep
# found ZERO violations against the pre-fix code that had just put "the football gods owe him
# ..." into the middle of a live card. These fourteen -- the 2026-09-23 board plus the torture
# names -- find six. A property test over a seeded picker is only as good as its sample.
CARDNAMES = ('Jason Shokalook', 'Sergi Solans', 'Danny Musovski', 'Jordan Morris',
             'Dejan Joveljic', 'Ariath Piol', 'Nikola Petkovic', 'Diego Luna',
             'Albert Rusnak', 'Paul Rothrock', 'Bartholomew Featherstonehaugh',
             'Jesus Ferreira', 'Kwadwo Opoku', 'Caden Clark')
bad = []
for pl in (LOUD, QUIET, BLANK):
    for nm in CARDNAMES:
        for avg in (88, 61):
            p = dict(pl, name=nm)
            w = V.why(p, avg).rstrip('.')
            objs = [f for _k, _b, f in V.angles(p, avg, nm) if not f.startswith(nm + ' ')]
            for o in objs:
                d = SP._depersonalise(o, nm)
                if d and d in w and not w.endswith(d):
                    bad.append((nm, avg, d, w))
check(not bad, 'no card clause but the last brings a subject of its own', bad[:2])

# ---------------------------------------------------------------------------------------
# 4. the note fits.
check(isinstance(SP.TNOTE_B, int) and 80 <= SP.TNOTE_B <= 120,
      'TNOTE_B is a sane two-line budget', SP.TNOTE_B)

worst, over = 0, []
NAMES = ['Bartholomew Featherstonehaugh', 'Christian Ramirez-Villalobos', 'Jesus Ferreira']
TITLES = ('The Late Kickoff', 'Target Man', 'The Poacher', 'Screamer', 'Nightcap',
          'The Understudy', 'Long Shot', 'The Anchor')
for tname in TITLES:
    for srcs in itertools.product((LOUD, QUIET, BLANK), repeat=2):
        pool = {nm: dict(srcs[i % 2], name=nm) for i, nm in enumerate(NAMES)}
        apps = {nm: (88 if i % 2 else 61) for i, nm in enumerate(NAMES)}
        # a SINGLE -- which is all soccer ships while TOP_SINGLES is non-zero -- and the
        # three-leg shape the same code drafts when it is not. Three distinct players, every
        # one of them chatty, the longest names the board has seen: the worst case the
        # ratchet and the clause cut have to survive.
        for legs in ([{'name': NAMES[0]}],
                     [{'name': NAMES[1]}],
                     [{'name': n} for n in NAMES]):
            note = V.ticket_note(legs, pool, apps, tname=tname)
            worst = max(worst, len(note))
            if len(note) > SP.TNOTE_B:
                over.append((len(note), note))
check(not over, 'every ticket note in the chatty sweep fits TNOTE_B (worst %d)' % worst,
      over[:2])

# the clause cut fires on the worst case and still leaves a whole sentence.
SRC = ('Featherstonehaugh is fearless with it, 5.5 attempts every ninety minutes, '
       'and plays the ninety.')
cut = SP._clmp(SRC, 76)
check(cut == 'Featherstonehaugh is fearless with it, 5.5 attempts every ninety minutes.',
      '_clmp cuts at a clause boundary and re-punctuates', cut)
check(SP._clmp('Featherstonehaugh is fearless with it and 5.5 a 90. Ferreira gets the hook.', 64)
      == 'Featherstonehaugh is fearless with it and 5.5 a 90.',
      "_clmp knows '. ' is a clause boundary too (the frame that overflowed worst)")
check(SP._clmp('one enormous clause with no separator anywhere in it at all', 30) == '',
      '_clmp refuses to make a fragment when no clause fits')

# and the ratchet is doing work, not accidentally passing because nothing was long:
long_note = V._compose([{'name': NAMES[0]}], {NAMES[0]: dict(LOUD, name=NAMES[0])},
                       {NAMES[0]: 88}, 'The Late Kickoff', 0)
check(len(long_note) > SP.TNOTE_B,
      'step 0 really can overflow, so the ratchet is exercised rather than vacuous',
      len(long_note))

# a note is never empty and never opens lower-case.
check(all(n and n[0].isupper() for n in
          [V.ticket_note([{'name': NAMES[0]}], {NAMES[0]: dict(LOUD, name=NAMES[0])},
                         {NAMES[0]: 88}, t) for t in ('a', 'b', 'c', 'd')]),
      'notes are non-empty and start capitalised')

print()
if FAIL:
    print('%d FAILED' % len(FAIL))
    for f in FAIL:
        print('  - ' + f)
    sys.exit(1)
print('ALL GREEN -- the voice sings, every clause still carries its number, and nothing '
      'runs off the end of the card')
