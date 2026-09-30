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


def _rot(seq, key, pin_last=('pos', 'model', 'price'), pin_first=()):
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
    # MADDEN-2026-09-30: the tail comes out in pin_last ORDER -- the position picture ("runs like he is
    # late for Thanksgiving dinner") before "we like him" and the price, which are votes, not pictures.
    tail = sorted((a for a in seq if a[0] in pin_last and a[0] not in pin_first),
                  key=lambda a: pin_last.index(a[0]))
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


# ⚠️ `{day}` IS THE SLATE'S OWN WEEKDAY, never a literal. See VOICEDAY-2026-09-14 on Voice.__init__:
# a phrasing that names a day is dropped entirely when the weekday is unknown, rather than guessing.
OPENERS_3 = ['Boom', 'Now here is a ticket', 'Three football players', 'Three tough guys, one {day}',
             'Get the turkey ready', 'Whap, bang, boom', 'This is football', 'Three trips to paydirt',
             'Three guys who get dirty', 'You want touchdowns', 'Look at this bunch', 'Three calls to the house']
OPENERS_1 = ['Boom', 'Now here is a guy', 'Feed him', 'Circle this one', 'Give him the rock',
             'Here is my guy', 'Put six on it', 'Whap']

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
    # NFLSINGLES-2026-09-27: drop a generational suffix first. "Chris Rodriguez Jr." wrote
    # "Jr. is always in the mix" on the 09-27 draft.
    parts = [p for p in str(name).split() if p]
    while len(parts) > 1 and re.fullmatch(r'(?i)(jr|sr|ii|iii|iv|v)\.?', parts[-1]):
        parts.pop()
    return parts[-1] if parts else str(name)


class Voice:
    """Writes the prose. Holds the SLATE's own distribution, so 'heavy' means heavy this week.

    A fixed threshold would call 1.0 goal-line looks a lot in week one and a lot in week
    seventeen, which is how every player ends up described as dangerous.

    Two registers, as on the soccer board. A CARD has room for a full sentence; a TICKET note is
    clamped to two lines and may carry three legs, so it gets the same fact in a shorter form.
    Same angle, same number, different length -- never a different claim.
    """

    def __init__(self, scored, weekday=None):
        rows = [s for s in (scored or []) if s.get('odds') is not None]
        self.n = len(rows)

        # 🚨 VOICEDAY-2026-09-14. Three phrasings named SUNDAY as a literal, so the 2026-09-14
        # Monday-night board shipped "Wiley steps into the spotlight this Sunday" -- the board
        # telling the reader the wrong day for their own slate. That breaks this module's one
        # rule (every clause restates something that is ON the payload) in the cheapest possible
        # place: the weekday is the easiest fact on the page to check.
        #
        # `fixtures.json` has carried "weekday" since the format was set, so no scrape changes --
        # the voice simply never read it. Phrasings now carry `{day}` and go through _dayfmt().
        #
        # ⚠️ WHEN THE WEEKDAY IS UNKNOWN THE PHRASING IS DROPPED, NOT DEFAULTED. Defaulting to
        # Sunday is the bug wearing a fallback's clothes. Dropping leaves a shorter bank, which
        # the pickers already handle, and asserts nothing.
        self.day = (str(weekday).strip() if weekday else '') or None

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

        # 📣 BROADCAST-2026-09-11 -- ONE BOOTH, NO CATCHPHRASE TWICE. The first broadcaster cut
        # printed "throw it up and let him go get it" twice inside ONE note and opened two slips
        # with "Three trips to paydirt". A phrase bank picked by hash collides; a broadcaster who
        # repeats his line in the same segment sounds like a recording. The Voice remembers what
        # it has already said on this board and reaches for another phrasing of the SAME angle
        # (same claim, different words). Deterministic: the board is written in the same order
        # every build, so the same slate still reads identically.
        self._said_card, self._said_note, self._said_open = set(), set(), set()

    def _fresh(self, p, who, salt, key, idx, said):
        """Another phrasing of angle `key` (idx 1 = lead, 2 = fragment) not yet said on this board."""
        first = None
        for j in range(48):   # enough re-salts to walk every phrasing of a 3-6 option bank
            for a in self.angles(p, who, salt=salt if j == 0 else '%s#%d' % (salt, j)):
                if a[0] != key:
                    continue
                txt = a[idx]
                sig = txt.replace(str(who), '{}').lower()
                if first is None:
                    first = (txt, sig)
                if sig not in said:
                    said.add(sig)
                    return txt
        if first:
            said.add(first[1])
            return first[0]
        return ''

    def _dayfmt(self, options):
        """Substitute the slate's weekday into any phrasing carrying `{day}`, and DROP the
        phrasing when the weekday is unknown (VOICEDAY-2026-09-14).

        ⚠️ When the day IS known this returns the same options in the same order, so every
        pick index is unchanged and a Sunday board is byte-identical to the pre-fix output.
        That is the regression test in test_nfl_voice, not a hope.
        """
        out = [o.format(day=self.day) if '{day}' in o else o
               for o in options if self.day or '{day}' not in o]
        return out or [o for o in options if '{day}' not in o] or list(options)

    def _open(self, bank, key):
        start = _h(key) % len(bank)
        for j in range(len(bank)):
            o = bank[(start + j) % len(bank)]
            if o not in self._said_open:
                self._said_open.add(o)
                return o
        return bank[start]

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
    # ---------------------------------------------------------------------------------------
    # 📣 BROADCAST-2026-09-11 -- SELL THE PLAY. THE BOOTH, NOT THE SPREADSHEET.
    # ---------------------------------------------------------------------------------------
    # Owner, 2026-09-11: "the writeups on the football tickets are god awful. im looking for
    # persuasive broadcaster terminology." The live 9/13 board read like a bookie hedging:
    #
    #     Money Down | Three men, three end zones: Wilson — the model is cool on him; Lane — a role,
    #                  not a record; Moore — goal-to-go is not new to him.
    #     The Pylon  | Three shouts at it: Ayomanor — ...; Dotson — the numbers do not love him either.
    #
    # Three failures in two notes: it ARGUES AGAINST ITS OWN TICKET ("cool on him", "do not love
    # him", "a role, not a record", "the quietest game", "the work without the reward"), it talks
    # like a British tipster ("shouts", "favourites", "offence", "in his shirt"), and it narrates
    # the model instead of the game.
    #
    # THE RULES NOW:
    #   1. EVERY ANGLE SELLS. An angle whose honest reading is a knock (model < 12%, the lowest
    #      team total, the book shorter than the model) is DROPPED, not softened. Silence is the
    #      broadcaster's move; nobody in the booth says "the model is cool on him".
    #   2. A weakness is re-read as the upside it actually is. Low goal-line work with real volume
    #      is a big-play threat. A low-snap man is the wrinkle the coordinator dials up. A man with
    #      no game log is a fresh face stepping into a role.
    #   3. Booth vocabulary, American: paydirt, six, red zone, goal-to-go, bell cow, moves the
    #      sticks, house call, dial up, the money snaps.
    #   4. UNCHANGED, AND STILL LOAD-BEARING: no digits (the stat strip prints them), no fragment
    #      carries a name, superlatives only for the real position leader / real top team total,
    #      and NO MATCHUP CLAIMS -- there is still no defensive term on this board.
    #   5. Every man always has at least one angle: the POSITION angle ("one catch from six") is
    #      the floor, pinned last with price, so dropping the negatives can never leave a leg of a
    #      slip unmentioned.
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
        back = pos == 'RB'

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

        # 🏈 MADDEN-2026-09-30. Owner, the morning after the first Madden cut: "football still sounds
        # terrible. soccer is good". Put side by side, the difference was SHAPE, not vocabulary:
        #   soccer:   "Martinez is a surgeon with a scalpel dipped in honey! He fires away like a pirate
        #              ship with a hold full of cannonballs."            -- pictures, and real sentences
        #   football: "This offense runs through Warren, and everybody in the building knows it. The
        #              numbers love him. A red-zone regular."           -- a lead, then two stat labels
        # So the fragments are now whole "he ..." sentences that paint a PICTURE (mud, grass stains,
        # Thanksgiving, a truck with no brakes), the lead is shouted when more follows, and "the model
        # / the numbers / Vegas" talk is gone from the prose -- that is a spreadsheet, not a colour man.
        # Every angle still fires only when the payload earns it; leader-only claims stay leader-only.
        # Fragments are lower-case "he ..." so why() can capitalise them and a three-leg note can drop
        # the "he" after the man's name ("Warren — runs like he is late for Thanksgiving dinner").
        # ---- THE HEADLINE. One of these, and it is the reason he is on the board. -----------
        if nolog:
            out.append(('story',
                pick(self._dayfmt([f'{who} is the new guy, and the new guy always wants to show you something',
                      f'here comes {who}, fresh legs and a brand-new job',
                      f'{who} gets his shot this {{day}}, and a young guy with a shot plays like his hair is on fire',
                      f'{who} is a new face in this huddle, and I love a new face']), k + 'h1'),
                pick(self._dayfmt(['he plays like his hair is on fire', 'he has been waiting his whole life for this {day}',
                      'he has fresh legs, big eyes, and he wants that football',
                      'he is out there to prove something, and guys like that make plays']), k + 'f1')))
        elif top_tch and top_i10:
            out.append(('story',
                pick([f'{who} is the bell cow, and when you get down close, you give it to the bell cow',
                      f'{who} carries them down the field and then carries them right into the end zone',
                      f'this whole offense runs through {who}, start to finish',
                      f'{who} is the workhorse, and you ride the workhorse all the way to the goal line']
                     if back else
                     [f'{who} is the top target here, and at the goal line you throw it to your top guy',
                      f'this offense runs through {who} from the first snap to the goal line',
                      f'{who} is the focal point, and when it gets close the quarterback looks for him first',
                      f'{who} is the guy they go to all day, and they go to him at the goal line too'], k + 'h2'),
                pick(['he gets it between the twenties and he gets it at the goal line',
                      'nobody at his position gets more of either',
                      'every down, every goal-line snap, it is his football',
                      'he is the whole drive, start to finish'], k + 'f2')))
        elif top_tch and lo_i10:
            out.append(('story',
                pick([f'{who} moves the sticks all day long, and you give a guy the ball that much, one of them goes',
                      f'{who} piles up touches like a guy piling up a Thanksgiving plate',
                      f'the ball keeps finding {who}, and I love a guy the ball keeps finding',
                      f'{who} is the volume play, and volume is how you get into the end zone'], k + 'h3'),
                pick(['he gets touches on touches, and one of them is gonna pop',
                      'he keeps the chains moving like a guy pushing a stalled car up a hill',
                      'feed him enough and whap, one of them breaks',
                      'he goes back for seconds and thirds, and nobody stops him'], k + 'f3')))
        elif top_i10 and lo_tch:
            out.append(('story',
                pick([f'{who} is the goal-line hammer, and when they get close, bang, in comes the hammer',
                      f'when they get down there close, they call {who}\'s number',
                      f'{who} is a red-zone specialist, and a specialist has one job, and his job is six',
                      f'{who} comes on the field for one reason, and that reason is the end zone'], k + 'h4'),
                pick(['he is the hammer they bring out when they see a nail',
                      'they save him for the money snaps',
                      'he has one job, and that job is six points',
                      'he trots on, he scores, he trots off'], k + 'f4')))
        elif top_i10:
            out.append(('story',
                pick([f'when they get inside the ten, the ball goes to {who}',
                      f'{who} is the first call at the goal line, and he has got mud all over that jersey',
                      f'{who} is the go-to guy once the field gets short',
                      f'nobody at his position sees more goal-line work than {who}'], k + 'h5'),
                pick(['he is the first call at the goal line, and he loves it down there',
                      'the goal line is his office, and he never takes a day off',
                      'he gets dirty down there, and dirty guys score touchdowns',
                      'nobody at his position gets more looks near the stripe'], k + 'f5')))
        elif top_tch:
            out.append(('story',
                pick([f'{who} never leaves the field, and that is the kind of guy you want',
                      f'the ball finds {who} more than anyone at his position',
                      f'{who} is the engine of this offense, and you have to feed the engine',
                      f'this offense runs through {who}, and everybody in the building knows it'], k + 'h6'),
                pick(['he never leaves the field, not even for a sip of water',
                      'he is the engine, and you feed the engine',
                      'nobody at his position touches it more',
                      'feed him and good things happen, it is that simple'], k + 'f6')))

        # ---- WHAT KIND OF PLAY THIS IS. Every branch reads as upside. -------------------------
        if hi_i10 and not top_i10:
            out.append(('kind',
                pick([f'{who} is right there in the huddle at goal-to-go, and that is where touchdowns live',
                      f'{who} gets real work in the red zone, where it gets tight and nasty',
                      f'{who} is always in the pile at the goal line, and he comes out of it with grass in his helmet',
                      f'{who} lives in the red zone, and that is my kind of neighborhood'], k + 'k1'),
                pick(['he lives down in the red zone, where it gets tight and nasty',
                      'he comes out of the pile with grass in his helmet',
                      'goal-to-go is his neighborhood, and he knows every house on the street',
                      'he is right there when they smell the end zone',
                      'he loves it down in the mud inside the twenty'], k + 'k2')))
        elif lo_i10 and not lo_tch:
            out.append(('kind',
                pick([f'{who} is a home-run hitter, and he can take it to the house from anywhere',
                      f'{who} makes one guy miss and whoosh, he is gone',
                      f'{who} does not need a short field, he brings his own'], k + 'k3'),
                pick(['he makes one guy miss and whoosh, he is gone',
                      'he can take it the distance from anywhere on the field',
                      'one cut and it is a footrace, and he wins footraces'], k + 'k4')))
        elif lo_tch:
            out.append(('kind',
                pick([f'{who} is the wrinkle, and you know the coordinator has something drawn up just for him',
                      f'one well-drawn play and {who} is standing in the end zone',
                      f'{who} is the surprise, and nobody ever sees the surprise coming'], k + 'k5'),
                pick(['he is the trick play they have been saving all week',
                      'one play call and he is standing in the end zone',
                      'nobody sees him coming, and then boom',
                      'he is the play they drew up on the back of a napkin'], k + 'k6')))

        # ---- ROLE, when the share says something the raw count does not. ----------------------
        if hi(shr, shr_hi) and is_max(shr, 'i10_share') and not (top_i10 and lo_tch):
            out.append(('role',
                pick([f'{who}\'s whole game is built around the end zone, and I love it',
                      f'no {role} on the board lives closer to the goal line than {who}',
                      f'the team saves {who} for the part of the field that pays'], k + 'r1'),
                pick(['his whole game lives near the goal line',
                      f'he is the most end-zone-heavy {role} on the board',
                      'he is built for the last ten yards'], k + 'r2')))

        # ---- THE GAME. Only the top team total; the bottom one is not a selling point. -------
        if isinstance(imp, (int, float)) and self.imp_spread >= 1.0:
            if self.imp_max is not None and abs(imp - self.imp_max) < 0.05:
                out.append(('game',
                    pick([f'{who} plays for the offense expected to put up the most points, so bring the gravy',
                          f'{who} is in the highest-scoring spot on the board, and that is a good spot to be',
                          f'{who}\'s offense carries the biggest team total on the board'], k + 'g1'),
                    pick(['his offense has the biggest team total on the board',
                          'points are on the menu, so pass the turkey',
                          'his offense is expected to light up the scoreboard like a pinball machine'], k + 'g2')))

        # ---- OUR PICK, only when it is a vote FOR him. -----------------------------------------
        if isinstance(pm, (int, float)) and pm * 100 >= 25:
            out.append(('model',
                pick([f'everything we have points right at {who}',
                      f'{who} is one of our favorite plays on the whole board',
                      f'we like {who} a whole bunch, and I will tell you why, the guy finds the end zone'], k + 'm1'),
                pick(['everything we have points right at him',
                      'he is one of our favorites on the whole board',
                      'we like him a whole bunch'], k + 'm2')))

        # ---- PRICE, only when the number is on OUR side. ---------------------------------------
        if isinstance(odds, int) and isinstance(pm, (int, float)):
            imp_p = (100.0 / (odds + 100.0)) if odds > 0 else (-odds / (-odds + 100.0))
            if pm - imp_p >= 0.05:
                out.append(('price',
                    pick([f'the price on {who} is a gift, like finding a drumstick in the couch cushions',
                          f'{who} is priced like an afterthought, and he is no afterthought',
                          f'somebody set the number on {who} way too generous'], k + 'p1'),
                    pick(['the price is a gift, like finding a drumstick in the couch cushions',
                          'he is priced like an afterthought, and he is no afterthought',
                          'somebody set that number way too generous'], k + 'p2')))

        # ---- THE FLOOR. Every man is live for six; this is what guarantees he gets a beat. ------
        floor = {
            'RB': ([f'{who} runs like he is late for Thanksgiving dinner',
                    f'{who} is a downhill runner, and downhill runners go through you, not around you',
                    f'{who} lowers that shoulder, and somebody is going backwards',
                    f'give {who} the rock and get out of the way',
                    f'{who} runs angry once he smells the goal line'],
                   ['he runs like he is late for Thanksgiving dinner',
                    'he lowers the shoulder, and somebody goes backwards',
                    'he goes through you, not around you',
                    'he has grass stains on his grass stains',
                    'he runs angry once he smells the goal line',
                    'he has a nose for the end zone like a bloodhound',
                    'hand it to him and get out of the way']),
            'WR': ([f'{who} goes up and takes the ball away from you',
                    f'throw it up to {who} and let him go get it',
                    f'{who} can turn a little slant into six, whoosh',
                    f'{who} is one catch away from the highlight reel',
                    f'{who} has hands like buckets',
                    f'{who} is a threat to score on every single snap'],
                   ['he goes up and takes it away from you',
                    'throw it up and let him go get it',
                    'he turns a little slant into six, whoosh',
                    'he has hands like buckets',
                    'he is one catch from the highlight reel',
                    'he gets open when it matters',
                    'he is a threat on every single snap',
                    'he catches everything, even the ugly ones']),
            'TE': ([f'{who} is a big ol\' target, and at the goal line you throw it to the big ol\' target',
                    f'{who} boxes out like a power forward',
                    f'nobody wants to tackle {who} at the goal line',
                    f'{who} is the quarterback\'s security blanket'],
                   ['he boxes out like a power forward',
                    'nobody wants to tackle him at the goal line',
                    'he is a big ol\' target when the field gets short',
                    'he rumbles in like a truck with no brakes',
                    'he is the security blanket every quarterback needs']),
            'QB': ([f'{who} will tuck it and go, and I love a quarterback who sticks his nose in there',
                    f'{who} can punch it in himself'],
                   ['he will tuck it and go', 'he sticks his nose right in there']),
        }.get(pos, ([f'{who} is live for six'], ['he is live for six, and that is all you need']))
        out.append(('pos', pick(floor[0], k + 'x1'), pick(floor[1], k + 'x2')))
        return out

    # ---------------------------------------------------------------------------------------
    # 🏈 MADDEN-2026-09-29 -- THE FIRST-TOUCHDOWN SLIP. Owner: "what the fuck does 'the football says
    # its 13%'? that sounds retarded ... i want john madden language". The note used to print the
    # model's P(first TD) as a percentage. It is gone: the pick is already the board's best first-TD
    # chance, which is the whole reason the slip exists, and a small honest number reads like an
    # apology. What the FTDSTATS model actually rewards is a big share of the touches, work near the
    # goal line and an offence that scores early -- so that is what the colour man talks about, by
    # position, with no digits and no promise that he WILL score.
    FTD_BANK = {
        'RB': ['First drive of the game, you want to run the football, and when they get down close they hand it to the big guy. That is {who}. Boom!',
               'They script that opening drive for {who}. Hand it to him, he lowers the shoulder, somebody goes backwards, six!',
               '{who} gets the ball early and he gets it often, and a guy who touches it that much on the first drive, whap, he is in there!',
               'Out of the tunnel, the first thing this offense wants to do is run it right at you with {who}. Grass stains by the first quarter. That is football!'],
        'WR': ['You script those first plays for your best guy, and {who} is their best guy. Throw it up and let him go get it. Boom!',
               'First drive, the quarterback is looking for his favorite target, and that is {who}. He gets open, he catches it, whoosh, six!',
               '{who} is the first read, and on the first drive you go to your first read. It is that simple, and I love simple!',
               'That opening script is drawn up with {who} in mind, and when they get close, the ball is coming his way. Hands like buckets!'],
        'TE': ['First drive, they get down there close, and the quarterback looks for the big guy. That is {who}. Nobody wants to tackle him at the goal line!',
               '{who} is a big ol\' target, and on that first trip into the red zone you throw it to the big ol\' target. Boom!',
               'When the field gets short on the opening drive, {who} boxes out like a power forward and rumbles in like a truck with no brakes!'],
        'QB': ['{who} can take it in himself on that first drive, tuck it and go, and I love a quarterback who sticks his nose in there!'],
    }

    def ftd_line(self, s, salt=''):
        """One Madden sentence for the first-touchdown pick. No digits, no forecast of the result."""
        pos = (s.get('pos') or s.get('bhand') or '').upper()
        who = _surname(s.get('name') or s.get('nm'))
        bank = self.FTD_BANK.get(pos) or ['{who} is our guy to get in there first, and that is all you need to know. Boom.']
        return _pick(bank, str(who) + str(salt) + 'ftd').format(who=who)

    # ---------------------------------------------------------------------------------------
    def why(self, p):
        """A lead sentence, then one or two FRAGMENTS. Full stops, not commas.

        Length is deliberately uneven -- some men get one line, some get three -- because a board
        where every card is the same length reads like a form even when the words differ."""
        n = p.get('name') or p.get('nm')
        seq = _rot(self.angles(p, n, lead=True), str(n) + 'card', pin_first=('story',))
        if not seq:
            return ''
        bits = [self._fresh(p, n, '', seq[0][0], 1, self._said_card)]
        want = 2 + (_h(str(n) + 'len') % 2)        # 2 or 3 (MADDEN-2026-09-30: a lone lead read flat)
        for key, _l, frag in seq[1:]:
            if len(bits) >= want:
                break
            if frag:
                bits.append(self._fresh(p, n, '', key, 2, self._said_card))
        # MADDEN-2026-09-30: the lead is SHOUTED when more follows, like the soccer cards.
        body = bits[0][0].upper() + bits[0][1:]
        for i, f in enumerate(bits[1:]):
            body += ('! ' if i == 0 else '. ') + f[0].upper() + f[1:]
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
                frag = self._fresh(p, sur, tname, key, 2, self._said_note)
                ldr = self._fresh(p, sur, tname, key, 1, self._said_note) if not (bits and beats == 2) else ldr
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
            # 📣 BROADCAST-2026-09-11: angles are consumed once per slip, and dropping the
            # negative angles left some men with only one or two. A man whose every angle was
            # already spent by a teammate still gets his POSITION floor -- a leg of the slip is
            # never left out of the write-up.
            if took == 0:
                key = self.angles(p, sur, salt=tname)[-1][0]
                bits.append(sur + ' — ' + self._fresh(p, sur, tname, key, 2, self._said_note) if three
                            else self._fresh(p, sur, tname, key, 1, self._said_note))
        if not bits:
            return ''
        if three:
            # ⚠️ NOT FRAMES_3 HERE. Those insert their own dashes, and a note built of
            # "Surname — fragment" beats then reads "Price — nobody has seen him — Smith-Njigba —
            # in the loudest game", which is unparseable. Semicolons separate the men; the dash
            # belongs to each man's own beat.
            body = self._open(self._dayfmt(OPENERS_3), who_key + 'o3') + ': ' + '; '.join(bits) + '.'
        elif len(bits) == 2:
            # ONE man's lead + his fragment needs FRAMES_1; TWO men's leads take FRAMES_2. Same
            # bit count, different grammar -- see the FRAMES_1 header.
            frames = FRAMES_2 if len(legs) >= 2 else FRAMES_1
            fr = _pick(frames, who_key + 'f2')
            body = fr.format(a=bits[0], b=bits[1],
                             o=self._open(OPENERS_1, who_key + 'o1') if '{o}' in fr else '')
        else:
            body = bits[0] + '.'
        body = re.sub(r'(?<=\. )([a-z])', lambda m: m.group(1).upper(), body)
        return body[0].upper() + body[1:]
