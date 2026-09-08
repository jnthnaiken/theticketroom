"""nfl_voice.py -- the write-ups for the football board.

WHY THIS EXISTS. Owner, 2026-09-08: "we need way more creative write ups for football."
He was being generous. Measured on the 2026-09-09 board, 26 players and 4 slips:

    every player card's `why` was None          -- 26 of 26, the field was hardcoded null
    every ticket note was ONE sentence          -- "<Surname> is on N touches a game."

`note_for()` was a four-branch if/elif with one fixed sentence per branch, and the fourth branch
caught nearly everybody. The soccer board has had a proper voice since VOICE-2026-08-28; football
never got one. This is that module, built to the same shape so the two sports read like one house.

WHAT IS BORROWED FROM soccer_payload.Voice, deliberately and by name:
  * angles()          -- [(key, brief, full)] per player, one entry per ANGLE, several phrasings
  * _pick / _h        -- deterministic variety: same key, same phrasing, every build
  * _rot              -- rotate the angle order per player AND per slip, so the same back does
                         not lead with touches on every card (VOICE-2026-08-28's actual fix)
  * lead-vs-fragment registers (soccer's brief/full pair, renamed for what they now do)
It is a COPY, not an import: soccer_payload does module-level work on import (it reads
fixtures.json off the cwd), so importing it from the football build would run a soccer pipeline.
The helpers below are twenty lines and the duplication is honest; the alternative is a shared
module that neither sport owns.

⚠️ NO MATCHUP CLAIMS, EVER. nfl_payload's original note carried this warning and it survives here
untouched: there is no defensive term on this board -- `hr9`/`phr9` are written None and the model
has nothing that says a defence is soft. Every clause below restates a number that is ON the
payload. Nothing here predicts anything, and nothing implies a matchup the model did not measure.

⚠️ POSITION IS PART OF THE SENTENCE, not decoration. Sixteen touches is a workhorse back; eight is
a WR who is the first read; five is a tight end who only eats near the stripe. The same number
means three different things and the old note said "is on N touches a game" to all of them.
"""
import re


def _h(s):
    """FNV-1a. Stable across processes and python versions -- hash() is salted per-run and would
    give a different board every build."""
    h = 0x811c9dc5
    for ch in str(s):
        h = ((h ^ ord(ch)) * 0x01000193) & 0xffffffff
    return h


def _pick(options, key):
    return options[_h(key) % len(options)]


def _rot(seq, key, pin_last=('price',), pin_first=()):
    """Rotate an angle list, holding the weak angles at the back.

    Same reasoning as soccer's VOICE-2026-08-28b: `angles()` returns a fixed priority order, so
    taking the first unused one made every card lead with the same thing. Rotating by the SLIP as
    well as the player means a back leads on his goal-line looks here and his workload there.
    PRICE is pinned last because "+130 for Price" is not a reason to back him -- it is the number
    already printed two inches to the right. BASIS is pinned with it: a caveat is worth saying,
    but it is not what a card opens on.
    """
    first = [a for a in seq if a[0] in pin_first]
    head = [a for a in seq if a[0] not in pin_last and a[0] not in pin_first]
    tail = [a for a in seq if a[0] in pin_last and a[0] not in pin_first]
    if not head:
        return first + tail
    i = _h(key) % len(head)
    return first + head[i:] + head[:i] + tail


# 🗑️ `_depersonalise()` LIVED HERE AND IS GONE, 2026-09-08c. It stripped a leading name off a
# second or third clause -- "Price is on 16.5 touches" -> "is on 16.5 touches" -- and rewrote a
# possessive to "his", after a card printed "Rhamondre Stevenson" three times in one sentence.
# It was the right fix for the register that RECITED numbers, where every clause was a full
# sentence about the man and the name had to be scrubbed back out afterwards.
#
# The rewrite removed the need rather than the symptom: `angles()` now returns a LEAD (names him,
# used once, first) and a FRAGMENT (nameless by construction, used for every later clause), so
# there is no name left to strip. A helper with no callers is worse than no helper -- it reads as
# a live safety net, so the next person writing a phrase bank assumes the scrub will catch a name
# they drop into a fragment. It will not. test_nfl_voice asserts the property at the source
# instead: "no fragment carries the player name", checked over every angle of every man.


def _sentence(bits):
    bits = [b for b in bits if b]
    if not bits:
        return ''
    if len(bits) == 1:
        body = bits[0]
    elif len(bits) == 2:
        body = bits[0] + ' and ' + bits[1]
    else:
        body = ', '.join(bits[:-1]) + ', and ' + bits[-1]
    return body[0].upper() + body[1:] + '.'


OPENERS_3 = ['Three that can all find paint', 'Three names, one Sunday', 'If all three get in',
             'Everything has to land', 'The lot has to come off', 'All three or nothing',
             'Nothing here is a formality', 'Three men, three end zones', 'Hold your nerve',
             'Three shouts at it', 'Needs all three', 'Three that fancy the short field']
OPENERS_1 = ['One name', 'Straight up', 'Nothing fancy', 'The plain one', 'No frills',
             'Just the one', 'Keep it simple', 'One shout']

# ⚠️ THE FRAMES ARE HALF THE VOICE. Every note used to be "{a}, {b}, and {c}." -- a list with
# commas, which is what made a board full of different facts still read like one sentence typed
# eleven times. A full stop mid-note, a dash, a colon: same clauses, completely different pulse.
FRAMES_3 = ['{a}, {b}, and {c}.', '{o}: {a}, {b}, {c}.', '{a}. {b}, and {c}.',
            '{o} — {a}, {b}, and {c}.', '{a} and {b}. {c}.', '{a}; {b}; {c}.',
            '{a} — {b}. And {c}.', '{o}. {a}, {b}, {c}.', '{a}. Then {b}, and {c}.']
# TWO MEN, two full clauses. "and" and a comma are fine here: both halves are LEADS, each with
# its own subject -- "Deene is in the huddle at goal-to-go, and Prosser is priced better than the
# model rates him."
FRAMES_2 = ['{a} and {b}.', '{o}: {a}, {b}.', '{a}, and {b}.', '{o} — {a}, and {b}.',
            '{a}. {b}.', '{a} — {b}.']

# 🚨 ONE MAN, AND THE SECOND HALF IS A FRAGMENT. FRAMES_2 CANNOT BE USED HERE, and it was, and it
# reached the live board: "Everything runs through Smith-Njigba and no seventy-yarder required."
# A fragment has no subject -- it is written to stand alone as its own sentence after a full stop,
# which is exactly how why() uses it -- so bolting it on with "and" or a comma produces a sentence
# that does not parse. Only the separators that START SOMETHING NEW work: a full stop, a dash, a
# colon. Caught by reading the RENDERED NOTE rather than the payload, which is the third time
# today that a correction was only visible at the reader's end.
FRAMES_1 = ['{a} — {b}.', '{a}. {b}.', '{o}: {a} — {b}.', '{a}: {b}.', '{o}. {a} — {b}.']

# What a touch MEANS depends on the position. These are the words, not a model term.
_ROLE = {
    'RB': ('carries and catches', 'back'),
    'WR': ('targets', 'receiver'),
    'TE': ('targets', 'tight end'),
    'QB': ('designed looks', 'quarterback'),
}


def _surname(name):
    parts = [p for p in str(name).split() if p]
    return parts[-1] if parts else str(name)


class Voice:
    """Writes the prose. Holds the SLATE's own distribution, so 'heavy' means heavy this week.

    A fixed threshold would call 1.0 goal-line looks a lot in week one and a lot in week
    seventeen, which is how every player ends up described as dangerous.

    Two registers, as on the soccer board. A CARD has room for a full sentence; a TICKET note is
    clamped to two lines and may carry three legs, so it gets the same fact in a shorter form.
    Same angle, same number, different length -- never a different claim.
    """

    def __init__(self, scored):
        rows = [s for s in (scored or []) if s.get('odds') is not None]
        self.n = len(rows)

        def band(rs, key, lo=0.60, hi=0.85):
            vals = sorted(v for v in (r.get(key) for r in rs) if isinstance(v, (int, float)))
            if not vals:
                return (None, None)
            return (vals[int(lo * (len(vals) - 1))], vals[int(hi * (len(vals) - 1))])

        # 🚨 BANDS ARE PER POSITION, and this is not a refinement -- the first cut called A.J.
        # Brown "the workhorse here, 7.7 targets a game" because the slate's touch distribution
        # is mostly receivers and tight ends, so a WR's 7.7 cleared a pooled 85th percentile that
        # a running back would laugh at. Sixteen carries and eight targets are not the same
        # quantity and must not be ranked against each other. Falls back to the pooled band when
        # a position has too few men to have a distribution of its own.
        self.band_all = {k: band(rows, k) for k in ('i10pg', 'tchpg', 'i10_share')}
        self.by_pos, self.max_by_pos = {}, {}
        for pos in {(r.get('pos') or '').upper() for r in rows}:
            rs = [r for r in rows if (r.get('pos') or '').upper() == pos]
            if len(rs) >= 4:
                self.by_pos[pos] = {k: band(rs, k) for k in ('i10pg', 'tchpg', 'i10_share')}
            self.max_by_pos[pos] = {
                k: max([v for v in (r.get(k) for r in rs) if isinstance(v, (int, float))] or [None])
                for k in ('i10pg', 'tchpg', 'i10_share')}

        # 🚨 A SUPERLATIVE NEEDS THE MAXIMUM, NOT THE TOP BAND. Caught by test_nfl_voice on the
        # first run: the "top" band is an 85th percentile, and with four receivers on a slate that
        # is the second-best of them -- so Foxtrot Bell, on 0.35 goal-line looks, was handed "does
        # more inside the ten than any other receiver on the board" while Echo Vance sat on 0.55.
        # That is a quiet lie: the reader cannot check it and it reads like the strongest claim on
        # the card. Band membership still earns the WARM language; only the actual maximum earns
        # the superlative one.

        imps = sorted({round(float(r['imp']), 1) for r in rows if r.get('imp') is not None})
        self.imp_all = imps
        self.imp_max = imps[-1] if imps else None
        self.imp_min = imps[0] if imps else None
        # ⚠️ A ONE-GAME SLATE HAS NO SPREAD. Week one had exactly two implied totals, 23.8 and
        # 20.8, so a percentile put BOTH in the top band and every card claimed its man was in
        # "the highest-implied game on the slate" -- true of one side, false of the other, and
        # said of everybody. The angle now fires only when the slate really spreads, and the
        # superlative only for the side that actually holds the maximum.
        self.imp_spread = (imps[-1] - imps[0]) if len(imps) > 1 else 0.0

    def _band(self, pos, key):
        """Per-position band, falling back to the pooled one when the position is too thin."""
        b = self.by_pos.get((pos or '').upper(), {}).get(key)
        if b and b[0] is not None:
            return b
        return self.band_all.get(key, (None, None))

    # ---------------------------------------------------------------------------------------
    # 🚨 NFLVOICE-2026-09-08c -- THE CARD ALREADY PRINTS THE NUMBERS. STOP READING THEM OUT.
    # ---------------------------------------------------------------------------------------
    # Owner, twice: "i said creative. are you trying to put me to sleep?" then "more variety and
    # there is still no creativity". Both right, and the second time I went and looked at the
    # rendered card instead of the payload. It shows, in a stat strip two inches above the prose:
    #
    #     Touches 16.5 · Inside 10 1.25 · GL share 0.076 · Weather x0.998 · Team total 23.8
    #     +130 · Model 169 · 27.9%
    #
    # Every number the write-up was reciting is ALREADY ON THE SCREEN. So the sentence had no job.
    # No amount of new adjectives fixes that -- "sees 0.4 a game from close range" and "is in the
    # picture when the field runs out" are the same non-contribution in different clothes, which
    # is exactly why the second rewrite read no better than the first.
    #
    # THE JOB IS INTERPRETATION. What does 16.5 touches and 1.25 inside the ten MEAN? It means the
    # offence runs through him and they trust him at the goal line. The chart cannot say that; it
    # is the only thing the sentence can add. A number appears here only when the number IS the
    # point -- a contrast, or a superlative the strip cannot show because it has nothing to
    # compare against.
    #
    # AND SHAPE IS HALF OF VOICE. Every clause was subject-verb-number, joined by "and". Real
    # writing varies LENGTH and STRUCTURE: a four-word fragment against a long clause is what
    # makes rhythm. So each angle now carries a LEAD (a full sentence, names him) and a FRAG (a
    # fragment, no name), and a card is a lead plus one or two fragments -- full stops, not commas.
    #
    # ⚠️ EVERY CLAUSE IS STILL EARNED BY A NUMBER ON THE PAYLOAD, and there are still no matchup
    # claims. "They trust him near the stripe" is what i10pg being top-of-position MEANS. It is
    # not a forecast, not an opinion about a defence, and not a fact the model did not measure.
    def angles(self, p, who, salt='', lead=False):
        """[(key, lead_sentence, fragment)] for one player, best-first."""
        out = []
        k = str(who) + str(salt)
        pos = (p.get('pos') or p.get('bhand') or '').upper()
        touch_word, role = _ROLE.get(pos, ('touches', 'player'))
        i10, tch = p.get('i10pg'), p.get('tchpg')
        shr, imp = p.get('i10_share'), p.get('imp')
        pm, odds = p.get('p_model'), p.get('odds')
        basis, bg = str(p.get('basis') or ''), p.get('basis_games')
        i10_hi, i10_top = self._band(pos, 'i10pg')
        tch_hi, tch_top = self._band(pos, 'tchpg')
        shr_hi, _ = self._band(pos, 'i10_share')
        mx = self.max_by_pos.get(pos, {})

        def is_max(val, key):
            m = mx.get(key)
            return isinstance(val, (int, float)) and isinstance(m, (int, float)) and val >= m - 1e-9

        def hi(v, b):   return isinstance(v, (int, float)) and b is not None and v >= b
        def lo(v, b):   return isinstance(v, (int, float)) and b is not None and v < b
        def pick(o, kk): return _pick(o, kk)

        top_i10, top_tch = is_max(i10, 'i10pg'), is_max(tch, 'tchpg')
        hi_i10, hi_tch = hi(i10, i10_hi), hi(tch, tch_hi)
        lo_i10, lo_tch = lo(i10, i10_hi), lo(tch, tch_hi)
        nolog = basis.startswith('depth') and not bg

        # ---- THE HEADLINE. One of these, and it is the reason he is on the board. -----------
        if nolog:
            out.append(('story',
                pick([f'{who} is a depth chart with a price on it',
                      f'{who} is a projection, not a player — nobody has seen him do this',
                      f'{who} arrives on the board without a game to his name',
                      f'{who} is a slot on a depth chart that the book has put odds on'], k + 'h1'),
                pick(['nobody has seen him do it yet', 'the game log is empty',
                      'a role, not a record', 'all projection, no evidence',
                      'not one snap behind the numbers'], k + 'f1')))
        elif top_tch and top_i10:
            out.append(('story',
                pick([f'the offence runs through {who}, and they trust him when it gets short',
                      f'{who} does the carrying and takes the goal-line work as well',
                      f'{who} is the bell cow here in every sense',
                      f'everything goes through {who}, right down to the last ten yards'], k + 'h2'),
                pick(['the workload and the short field, both his', 'nobody here does more of either',
                      'volume and the goal line in one man', 'he does not share the good part'], k + 'f2')))
        elif top_tch and lo_i10:
            out.append(('story',
                pick([f'{who} does the work and somebody else finishes it',
                      f'{who} moves the chains; the short field belongs to somebody else',
                      f'{who} carries it between the twenties and hands the last ten yards over',
                      f'all that volume for {who}, and almost none of it where it pays'], k + 'h3'),
                pick(['plenty of the ball, none of the good bit', 'a chain-mover, not a finisher',
                      'the work without the reward', 'he gets there and then watches'], k + 'f3')))
        elif top_i10 and lo_tch:
            out.append(('story',
                pick([f'{who} barely plays, and plays where it counts',
                      f'{who} is kept for the short field',
                      f'{who} is a specialist — they bring him on to score',
                      f'{who} does not do much, but what he does is close range'], k + 'h4'),
                pick(['a specialist, not a workhorse', 'kept back for the short field',
                      'he is on for one reason', 'cameo work, scoring work'], k + 'f4')))
        elif top_i10:
            out.append(('story',
                pick([f'when the field runs out, it goes to {who}',
                      f'{who} is the one they trust from a yard',
                      f'nobody in his shirt sees more of the goal line than {who}',
                      f'{who} is first in the queue near the stripe'], k + 'h5'),
                pick(['first in the queue near the stripe', 'the goal-line man',
                      'they trust him from a yard', 'the short field is his'], k + 'f5')))
        elif top_tch:
            out.append(('story',
                pick([f'{who} is not coming off the field',
                      f'the ball finds {who} more than anyone in his shirt',
                      f'{who} is the engine of this offence',
                      f'everything runs through {who}'], k + 'h6'),
                pick(['he never leaves the field', 'the ball keeps finding him',
                      'the engine of it', 'nobody in his shirt sees it more'], k + 'f6')))

        # ---- WHAT KIND OF BET THIS IS. --------------------------------------------------------
        if hi_i10 and not top_i10:
            out.append(('kind',
                pick([f'{who} gets his share of the short field',
                      f'{who} is in the huddle when it gets to goal-to-go',
                      f'{who} does not need a long one'], k + 'k1'),
                pick(['no seventy-yarder required', 'he gets his share of the short field',
                      'goal-to-go is not new to him', 'the cheap kind of touchdown is available'], k + 'k2')))
        elif lo_i10 and not lo_tch:
            out.append(('kind',
                pick([f'{who} is scoring from range or not at all',
                      f'{who} has to go the long way',
                      f'nobody is handing {who} a one-yard gift'], k + 'k3'),
                pick(['it has to be a long one', 'the long way round',
                      'no gimme from a yard', 'distance or nothing'], k + 'k4')))
        elif lo_tch:
            out.append(('kind',
                pick([f'{who} needs the play called for him',
                      f'this is a bet on one snap going {who}\'s way',
                      f'{who} has to make his cameo count'], k + 'k5'),
                pick(['one snap has to go his way', 'the play has to be called for him',
                      'a cameo that has to count', 'he needs the design, not the volume'], k + 'k6')))

        # ---- ROLE, when the share says something the raw count does not. ----------------------
        if hi(shr, shr_hi) and is_max(shr, 'i10_share') and not (top_i10 and lo_tch):
            pct = int(round((shr or 0) * 100))
            out.append(('role',
                pick([f'more of {who}\'s work happens inside the ten than any {role} here',
                      f'{who} is used nearer the stripe than the other {role}s',
                      f'the club saves {who} for the part of the field that scores'], k + 'r1'),
                pick(['used nearer the stripe than the rest', f'the most goal-line-weighted {role} here',
                      'his job is the last ten yards'], k + 'r2')))

        # ---- THE GAME. Only when the slate spreads; only the extremes are worth a clause. -----
        if isinstance(imp, (int, float)) and self.imp_spread >= 1.0:
            if self.imp_max is not None and abs(imp - self.imp_max) < 0.05:
                out.append(('game',
                    pick([f'{who} is in the loudest game on the board',
                          f'nobody is expected to score more than {who}\'s side',
                          f'{who} is in the one everybody expects points from'], k + 'g1'),
                    pick(['in the loudest game on the board', 'points to go round in this one',
                          'the highest-implied side on the card'], k + 'g2')))
            elif self.imp_min is not None and abs(imp - self.imp_min) < 0.05:
                out.append(('game',
                    pick([f'{who} is in the quietest game on the card',
                          f'there may not be many to share out where {who} is playing',
                          f'{who}\'s side is expected to score least of anybody'], k + 'g3'),
                    pick(['the quietest game on the card', 'not many to go round',
                          'the lowest-implied side here'], k + 'g4')))

        # ---- THE MODEL, as a verdict rather than a percentage. --------------------------------
        if isinstance(pm, (int, float)):
            pct = pm * 100
            if pct >= 25:
                out.append(('model',
                    pick([f'the model is not shy about {who}',
                          f'{who} is one of the model\'s favourites tonight',
                          f'the model likes {who} a lot'], k + 'm1'),
                    pick(['the model likes him a lot', 'one of its favourites tonight',
                          'the model is not shy here'], k + 'm2')))
            elif pct < 12:
                out.append(('model',
                    pick([f'the model is cool on {who}',
                          f'{who} is a long shot by the model as well as the book',
                          f'the model does not love {who} either'], k + 'm3'),
                    pick(['the model is cool on him', 'a long shot on both counts',
                          'the numbers do not love him either'], k + 'm4')))

        # ---- PRICE, last, and only when it disagrees with something. --------------------------
        if isinstance(odds, int) and isinstance(pm, (int, float)):
            imp_p = (100.0 / (odds + 100.0)) if odds > 0 else (-odds / (-odds + 100.0))
            if pm - imp_p >= 0.05:
                out.append(('price',
                    pick([f'the book has {who} longer than the model does',
                          f'{who} is priced worse than the model rates him'], k + 'p1'),
                    pick(['longer than the model makes him', 'the book is behind the model here'], k + 'p2')))
            elif imp_p - pm >= 0.05:
                out.append(('price',
                    pick([f'the book is shorter on {who} than the model is',
                          f'{who} is priced better than the model rates him'], k + 'p3'),
                    pick(['shorter than the model makes him', 'the book rates him above the model'], k + 'p4')))

        if not out:
            out.append(('kind', f'{who} is on the card', 'priced and on the card'))
        return out

    # ---------------------------------------------------------------------------------------
    def why(self, p):
        """A lead sentence, then one or two FRAGMENTS. Full stops, not commas.

        Length is deliberately uneven -- some men get one line, some get three -- because a board
        where every card is the same length reads like a form even when the words differ."""
        n = p.get('name') or p.get('nm')
        seq = _rot(self.angles(p, n, lead=True), str(n) + 'card', pin_first=('story',))
        if not seq:
            return ''
        bits = [seq[0][1]]
        want = 1 + (_h(str(n) + 'len') % 3)        # 1, 2 or 3 clauses
        for key, _l, frag in seq[1:]:
            if len(bits) >= want:
                break
            if frag:
                bits.append(frag)
        body = bits[0][0].upper() + bits[0][1:]
        for f in bits[1:]:
            body += '. ' + f[0].upper() + f[1:]
        return body + '.'

    # ---------------------------------------------------------------------------------------
    def ticket_note(self, legs, players, tname=''):
        """One clause per leg, no angle twice, and the shape varies with the slip.

        ⚠️ HOW MANY BEATS EACH MAN GETS IS A FUNCTION OF HOW MANY MEN THERE ARE, and getting that
        wrong silently loses a leg. A first cut gave EVERY man a lead-plus-fragment whenever the
        slip was not a treble, so a two-leg slip built four bits, fell past the `len(bits) == 2`
        frame into the single-clause fallback, and printed `bits[0]` -- one sentence about the
        first man and no mention at all of the second. A note that omits a leg of the slip is
        worse than a dull one: the reader is holding a ticket with a name on it that the write-up
        never acknowledges. Two beats belong to a SINGLE, which would otherwise be a telegram;
        every multi-leg slip gets exactly one beat per man.
        """
        used, bits = set(), []
        three = len(legs) >= 3
        beats = 2 if len(legs) == 1 else 1

        # 🚨 THE SALT IS THE SLIP AND ITS MEN, NOT THE SLIP NAME ALONE. The opener and the frame
        # are picked from a hash of this key so that two slips on one board read with a different
        # pulse. When the key was `tname` on its own, the caller decided whether that worked --
        # and nfl_payload passed the ticket's KIND, which is "builder" for every football slip, so
        # all four hashed identically and the board published "No frills." four times over four
        # different men. Four correct sentences with one opener is the mail-merge read this module
        # exists to kill, reintroduced through the argument rather than the prose.
        # nfl_payload now passes the slip's name, but a module whose output collapses when a
        # caller passes a duplicate label is one bad argument away from that board again. The men
        # ARE what distinguishes two slips that share a label, so they go in the key: the same
        # names in the same order still give the same words every build, which is the property
        # that matters.
        who_key = str(tname) + '|' + '/'.join(
            _surname((players.get(l['name'] if isinstance(l, dict) else l) or {}).get('name')
                     or (l['name'] if isinstance(l, dict) else l)) for l in legs)

        for l in legs:
            nm = l['name'] if isinstance(l, dict) else l
            p = players.get(nm)
            if not p:
                continue
            sur = _surname(p.get('name') or p.get('nm'))
            took = 0
            for key, ldr, frag in _rot(self.angles(p, sur, salt=tname), str(tname) + sur,
                                       pin_first=('story',)):
                if key in used:
                    continue
                used.add(key)
                if three:
                    bits.append(sur + ' — ' + frag)      # one beat per man
                    took += 1
                    break
                # ONE leg: the second beat is a bare FRAGMENT, because the man has already been
                # named a clause ago and "Marsh needs the play called for him and Marsh — the
                # lowest-implied side here" is the mail-merge read this module exists to kill.
                # TWO legs: both men get a LEAD, because the second one is somebody else and a
                # nameless fragment would attach his reason to the first man.
                bits.append(frag if (bits and beats == 2) else ldr)
                took += 1
                if took >= beats:
                    break
        if not bits:
            return ''
        if three:
            # ⚠️ NOT FRAMES_3 HERE. Those insert their own dashes, and a note built of
            # "Surname — fragment" beats then reads "Price — nobody has seen him — Smith-Njigba —
            # in the loudest game", which is unparseable. Semicolons separate the men; the dash
            # belongs to each man's own beat.
            body = _pick(OPENERS_3, who_key + 'o3') + ': ' + '; '.join(bits) + '.'
        elif len(bits) == 2:
            # ONE man's lead + his fragment needs FRAMES_1; TWO men's leads take FRAMES_2. Same
            # bit count, different grammar -- see the FRAMES_1 header.
            frames = FRAMES_2 if len(legs) >= 2 else FRAMES_1
            body = _pick(frames, who_key + 'f2').format(
                a=bits[0], b=bits[1], o=_pick(OPENERS_1, who_key + 'o1'))
        else:
            body = bits[0] + '.'
        body = re.sub(r'(?<=\. )([a-z])', lambda m: m.group(1).upper(), body)
        return body[0].upper() + body[1:]
