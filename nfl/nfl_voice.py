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
  * lead / _depersonalise / brief-vs-full registers
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


def _depersonalise(clause, name):
    """Second and third clauses drop the name: 'Price is on 16.5 touches' -> 'is on 16.5 touches'.

    Only a LEADING name is stripped. The phrase banks include forms where the man is the object
    ('nothing on Price but the price'), and gutting those mid-sentence produces rubbish.
    """
    for form in (name, name.split()[-1]):
        if clause.startswith(form + ' '):
            return clause[len(form) + 1:]
    # ⚠️ AND THE POSSESSIVE, WHEREVER IT SITS. The phrase banks carry forms where the man is
    # neither subject nor object but an owner -- "the market has Price's offence down for 20.8"
    # -- and a leading-name strip cannot see those. Left alone, a card said "Rhamondre
    # Stevenson" three times in one sentence, which is exactly the mail-merge read this module
    # exists to kill. Second and later clauses use "his" instead.
    for form in (name, name.split()[-1]):
        for poss in (form + "'s", form + "\u2019s"):
            if poss in clause:
                return clause.replace(poss, 'his', 1)
    # ⚠️ POSSESSIVES ONLY. A first cut also swapped a bare mid-clause name for "he" and produced
    # "the model puts he in the end zone" -- the name is in OBJECT position there and English
    # wants "him". Rather than guess the case, leave those alone: a repeated surname reads worse
    # than nothing but far better than a grammar error, and the rotation makes it rare.
    return clause


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


OPENERS_3 = ['Three that can all find the end zone', 'Three names, one Sunday',
             'If all three get in', 'Everything has to land', 'The lot has to come off',
             'Three to find paint', 'All three or nothing', 'Nothing here is a formality',
             'Three that fancy the goal line', 'Hold your nerve']
OPENERS_1 = ['One name', 'Straight up', 'Nothing fancy', 'The plain one', 'No frills',
             'Just the one', 'Keep it simple']

FRAMES_3 = ['{a}, {b}, and {c}.', '{o}: {a}, {b}, {c}.', '{a}. {b}, and {c}.',
            '{o} — {a}, {b}, and {c}.', '{a} and {b}. {c}.', '{a}; {b}; {c}.']
FRAMES_2 = ['{a} and {b}.', '{o}: {a}, {b}.', '{a}, and {b}.', '{o} — {a}, and {b}.']

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
    def angles(self, p, who, salt='', lead=False):
        """[(key, brief, full)] for one player, best-first. `who` is how to name him.

        Every entry restates a number that is on the payload. Nothing here predicts anything.
        """
        out = []
        k = str(who) + str(salt)
        pos = (p.get('pos') or p.get('bhand') or '').upper()
        touch_word, role = _ROLE.get(pos, ('touches', 'player'))
        i10 = p.get('i10pg')
        tch = p.get('tchpg')
        shr = p.get('i10_share')
        imp = p.get('imp')
        pm = p.get('p_model')
        odds = p.get('odds')
        basis = str(p.get('basis') or '')
        bg = p.get('basis_games')
        i10_hi, i10_top = self._band(pos, 'i10pg')
        tch_hi, tch_top = self._band(pos, 'tchpg')
        shr_hi, _shr_top = self._band(pos, 'i10_share')
        mx = self.max_by_pos.get((pos or '').upper(), {})

        def is_max(val, key):
            m = mx.get(key)
            return isinstance(val, (int, float)) and isinstance(m, (int, float)) and val >= m - 1e-9

        def say(opts, kk):
            """Prefer a phrasing where he is the SUBJECT when this clause leads the sentence."""
            if lead:
                subj = [o for o in opts if o.startswith(str(who) + ' ')]
                if subj:
                    return _pick(subj, kk)
            return _pick(opts, kk)

        # --- THE GOAL LINE. The one number that is actually about scoring a touchdown. --------
        if isinstance(i10, (int, float)) and i10 > 0:
            if is_max(i10, 'i10pg') and i10_top is not None and i10 >= i10_top:
                out.append(('goalline',
                            say([f'{who} tops the {role}s for goal-line work — {i10:.1f} a game inside the ten',
                                 f'no {role} here sees more inside the ten than {who}',
                                 f'{i10:.1f} looks a game inside the ten for {who}',
                                 f'{who} gets {i10:.1f} cracks at it from close range',
                                 f'{who} is on the field when it gets tight — {i10:.1f} inside the ten'], k + 'g'),
                            say([f'{who} sees {i10:.1f} looks a game inside the ten, more goal-line work than any {role} on the card',
                                 f'{who} does more inside the ten than any other {role} on the board, {i10:.1f} a game',
                                 f'{who} gets {i10:.1f} cracks a game from inside the ten, which is where this bet is won',
                                 f'{who} is on the field when the field gets short: {i10:.1f} looks a game inside the ten'], k + 'G')))
            elif i10_hi is not None and i10 >= i10_hi:
                out.append(('goalline',
                            say([f'{who} sees {i10:.1f} a game inside the ten',
                                 f'{i10:.1f} goal-line looks a game for {who}',
                                 f'{who} is around it near the stripe, {i10:.1f} a game',
                                 f'{who} gets {i10:.1f} close-range looks'], k + 'g'),
                            say([f'{who} takes {i10:.1f} touches a game inside the ten',
                                 f'{who} is in the picture near the stripe — {i10:.1f} looks a game inside the ten',
                                 f'{who} sees {i10:.1f} a game from close range'], k + 'G')))
            else:
                out.append(('goalline',
                            say([f'{who} only {i10:.1f} a game inside the ten',
                                 f'{i10:.1f} goal-line looks for {who}, and that is the worry',
                                 f'{who} is light near the stripe — {i10:.1f} a game'], k + 'g'),
                            say([f'{who} sees only {i10:.1f} touches a game inside the ten, so this is a drive-length bet rather than a goal-line one',
                                 f'{who} is light near the stripe at {i10:.1f} a game — he needs the long one',
                                 f'{who} gets {i10:.1f} a game inside the ten, so he is scoring from distance or not at all'], k + 'G')))
        elif i10 == 0:
            out.append(('goalline',
                        say([f'{who} has no goal-line work at all',
                             f'nothing inside the ten for {who}',
                             f'{who} is not a short-yardage answer'], k + 'g'),
                        say([f'{who} has not taken a touch inside the ten, so every yard of this has to come from distance',
                             f'nothing at all inside the ten for {who} — he scores the long way or not at all'], k + 'G')))

        # --- SHARE. Of his own work, how much of it happens where the points are. ------------
        if (isinstance(shr, (int, float)) and shr > 0 and shr_hi is not None and shr >= shr_hi
                and is_max(shr, 'i10_share')):
            pct = int(round(shr * 100))
            out.append(('share',
                        say([f'{pct}% of {who}\'s work is inside the ten',
                             f'{who} works nearer the stripe than the other {role}s — {pct}% of his touches',
                             f'{pct}% of what {who} gets is close range'], k + 's'),
                        say([f'{pct}% of {who}\'s touches come inside the ten, a bigger share than the other {role}s here',
                             f'{who} is used where it counts — {pct}% of his work is inside the ten',
                             f'{pct}% of {who}\'s touches happen inside the ten'], k + 'S')))

        # --- VOLUME, said in the language of the position. ------------------------------------
        if isinstance(tch, (int, float)) and tch > 0:
            if is_max(tch, 'tchpg') and tch_top is not None and tch >= tch_top:
                out.append(('volume',
                            say([f'{who} is the workhorse at {tch:.1f} a game',
                                 f'{tch:.1f} {touch_word} a game for {who}',
                                 f'{who} carries the load — {tch:.1f} a game',
                                 f'no {role} on this card sees it more than {who}'], k + 'v'),
                            say([f'{who} is the workhorse here, {tch:.1f} {touch_word} a game',
                                 f'{who} gets {tch:.1f} {touch_word} a game, as much as any {role} on the card',
                                 f'the ball goes through {who} — {tch:.1f} {touch_word} a game'], k + 'V')))
            elif tch_hi is not None and tch >= tch_hi:
                out.append(('volume',
                            say([f'{who} on {tch:.1f} {touch_word} a game',
                                 f'{tch:.1f} a game through {who}',
                                 f'{who} sees the ball {tch:.1f} times a game'], k + 'v'),
                            say([f'{who} is on {tch:.1f} {touch_word} a game',
                                 f'{who} sees the ball {tch:.1f} times a game as the {role}'], k + 'V')))
            else:
                out.append(('volume',
                            say([f'{who} on a thin {tch:.1f} a game',
                                 f'only {tch:.1f} {touch_word} a game for {who}',
                                 f'{who} is a bit-part at {tch:.1f} a game'], k + 'v'),
                            say([f'{who} is on only {tch:.1f} {touch_word} a game, so he needs the one he gets to count',
                                 f'{who} is a bit-part {role} at {tch:.1f} {touch_word} a game'], k + 'V')))

        # --- ENVIRONMENT. The implied total is the board's only game-level term. --------------
        # ⚠️ ONLY WHEN THE SLATE ACTUALLY SPREADS, and the superlative only for the side that
        # holds the maximum. See the note in __init__: a two-game slate put both totals in the
        # "top" band and every card claimed the highest-implied game on the slate.
        if isinstance(imp, (int, float)) and self.imp_spread >= 1.0:
            top = self.imp_max is not None and abs(imp - self.imp_max) < 0.05
            bot = self.imp_min is not None and abs(imp - self.imp_min) < 0.05
            if top:
                out.append(('game',
                            say([f'{who} is in the highest-implied game on the board',
                                 f'{who}\'s side is implied for {imp:.1f}, the most on the slate',
                                 f'nobody is expected to score more than {who}\'s offence',
                                 f'{imp:.1f} implied for {who}\'s side, top of the card'], k + 'e'),
                            say([f'{who} is in the highest-implied game on the board — {imp:.1f} for his side',
                                 f'{who}\'s offence is down for {imp:.1f}, more than anybody else today',
                                 f'no offence on this slate is implied for more than {who}\'s {imp:.1f}'], k + 'E')))
            elif bot:
                out.append(('game',
                            say([f'{who}\'s side is implied for only {imp:.1f}',
                                 f'just {imp:.1f} implied for {who}\'s offence',
                                 f'{who} is in the quietest game on the board'], k + 'e'),
                            say([f'{who}\'s side is implied for only {imp:.1f}, the lowest on the card, so there may not be many to share out',
                                 f'the market gives {who}\'s offence just {imp:.1f} — this is a bet on one of a small number'], k + 'E')))
            else:
                out.append(('game',
                            say([f'{who}\'s side is implied for {imp:.1f}',
                                 f'{imp:.1f} implied for {who}\'s offence'], k + 'e'),
                            say([f'{who}\'s side is implied for {imp:.1f}',
                                 f'the market has {who}\'s offence down for {imp:.1f}'], k + 'E')))

        # --- THE MODEL'S OWN NUMBER. ----------------------------------------------------------
        if isinstance(pm, (int, float)):
            pct = pm * 100
            out.append(('model',
                        say([f'the model has {who} at {pct:.0f}%',
                             f'{who} scores {pct:.0f}% of the time by the model',
                             f'{pct:.0f}% on the model for {who}'], k + 'm'),
                        say([f'the model puts {who} in the end zone {pct:.0f}% of the time',
                             f'{who} comes out at {pct:.0f}% to find it'], k + 'M')))

        # --- WHAT THE NUMBERS REST ON. A caveat, and it goes last. ----------------------------
        if basis.startswith('depth') and (bg == 0 or bg is None):
            out.append(('basis',
                        say([f'{who} has no game log at all — this is the depth chart',
                             f'nothing but a depth chart behind {who}',
                             f'{who} is projected off his slot, not off snaps'], k + 'b'),
                        say([f'{who} has no game log behind him at all: every number here comes off the depth chart, not off anything he has done',
                             f'nothing but a depth chart behind {who} — treat the numbers as a role, not a record'], k + 'B')))
        elif isinstance(bg, int) and 0 < bg <= 5:
            out.append(('basis',
                        say([f'{who} on {bg} games of evidence',
                             f'only {bg} games behind {who}'], k + 'b'),
                        say([f'{who} has only {bg} games behind these numbers, so read them lightly',
                             f'{bg} games is all the evidence there is on {who}'], k + 'B')))

        # --- PRICE. Pinned last by _rot. -------------------------------------------------------
        if isinstance(odds, int):
            out.append(('price',
                        say([f'{who} at {odds:+d}', f'{odds:+d} for {who}', f'{who} is {odds:+d}'], k + 'p'),
                        say([f'{who} is priced {odds:+d}', f'the book has {who} at {odds:+d}'], k + 'P')))

        if not out:
            out.append(('rate', f'{who} is on the card', f'{who} is priced and on the card'))
        return out

    # ---------------------------------------------------------------------------------------
    def why(self, p):
        """Two or three clauses on one card: full name first, then the name drops away."""
        n = p.get('name') or p.get('nm')
        keep, used = [], set()
        # ⚠️ SUBJECT-FIRST FOR EVERY CLAUSE, not just the leading one. soccer's why() picks the
        # non-lead clauses from the whole bank for variety, and on this board that put an
        # OBJECT-position phrasing in clause three -- "the model puts Echo Wide in the end zone
        # 28% of the time" -- which _depersonalise deliberately will not touch, so the card said
        # his name twice. Asking for the subject form means the leading strip always bites.
        # Variety is not lost: it comes from _rot choosing a different ANGLE per player, which
        # was always where it came from.
        lead_of = {a[0]: a for a in self.angles(p, n, lead=True)}
        # A man with NO game log at all is a caveat that cannot be allowed to rotate off the
        # end of a three-clause card. Everything else competes for the remaining seats.
        must = ('basis',) if (str(p.get('basis') or '').startswith('depth')
                              and not p.get('basis_games')) else ()
        for key, _brief, _full in _rot(self.angles(p, n), str(n) + 'card', pin_first=must):
            if key in used:
                continue
            used.add(key)
            full = lead_of.get(key, (0, 0, _full))[2]
            keep.append(_depersonalise(full, n) if keep else full)
            if len(keep) == 3:
                break
        return _sentence(keep)

    # ---------------------------------------------------------------------------------------
    def ticket_note(self, legs, players, tname=''):
        """One sentence naming what each leg is FOR, in slip order, no angle used twice.

        A three-leg slip gets one clause per leg or the note overruns the two-line clamp; a
        single has the room for two and reads like a telegram with one.
        """
        per = 1 if len(legs) >= 3 else 2
        used, bits = set(), []
        for l in legs:
            p = players.get(l['name'] if isinstance(l, dict) else l)
            if not p:
                continue
            sur = _surname(p.get('name') or p.get('nm'))
            lead_of = {a[0]: a for a in self.angles(p, sur, salt=tname, lead=True)}
            cands = _rot(self.angles(p, sur, salt=tname), str(tname) + sur)
            took = 0
            for key, brief, full in cands:
                if key in used:
                    continue
                used.add(key)
                if took == 0:
                    _k, brief, full = lead_of.get(key, (key, brief, full))
                    bits.append(brief if per == 1 else full)
                else:
                    bits.append(_depersonalise(brief if per == 1 else full, sur))
                took += 1
                if took == per:
                    break
            if not took and cands:
                bits.append(cands[0][1] if per == 1 else cands[0][2])
        if not bits:
            return ''
        if len(bits) >= 3:
            body = _pick(FRAMES_3, str(tname) + 'f3').format(
                a=bits[0], b=bits[1], c=', '.join(bits[2:]), o=_pick(OPENERS_3, str(tname) + 'o3'))
        elif len(bits) == 2:
            body = _pick(FRAMES_2, str(tname) + 'f2').format(
                a=bits[0], b=bits[1], o=_pick(OPENERS_1, str(tname) + 'o1'))
        else:
            body = bits[0] + '.'
        body = re.sub(r'(?<=\. )([a-z])', lambda m: m.group(1).upper(), body)
        return body[0].upper() + body[1:]
