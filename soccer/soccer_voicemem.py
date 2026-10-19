"""soccer_voicemem.py -- VOICEMEM-2026-10-19. A memory for the write-ups, so the board stops repeating itself.

Owner, 2026-10-19: "soccer and football tickets are way too repetitive" ... "the write ups".

WHAT WAS REPEATING, MEASURED ON THE LIVE BOARDS BEFORE THIS CHANGE
  * Within one board: the 10-20 card used "is a firecracker, not a candle" on two of five slips,
    "Mamma mia" as the opener on two, and "the box belongs to him" on two. Every phrase was picked
    by hashing (surname + slip title) with no memory of what the rest of the board had said.
  * Across nights: the pick key held no date, and the slip titles come round in the same order
    every night (Target Man, The Poacher, Six-Yard Box ...), so the same man on the same title got
    the same sentence night after night. Football had the in-board memory already
    (BROADCAST-2026-09-11) but not the cross-night one: "grass stains on his grass stains",
    "where it's tight, and it's nasty", "the team that scores the most points usually wins" all
    shipped on two or three of the last five football boards.
  * The Goal Line write-ups have two or three phrasings per situation, so "only need one, and
    they have been creating enough to get it" printed twice on the 10-19 card.

WHAT THIS DOES -- AND WHAT IT DELIBERATELY DOES NOT
  1. The slate DATE joins every pick key, so a different night reads differently.
  2. A phrase already said on THIS board is skipped while another phrasing of the same angle is
     left (same claim, different words -- the angle, the band that earned it and the voice rules
     are untouched).
  3. A phrase printed on any of the previous RECENT_NIGHTS archived boards is skipped the same way.
  4. When every phrasing is spent it falls back to the plain pick -- a repeat beats a missing leg.

  Deterministic: same slate + same prior boards + same slip order => same words, every build,
  which is the property the old comment on _h() was protecting.

HOW A PHRASE IS RECOGNISED
  The "core" of a phrasing is its longest stretch of text between occurrences of the player's
  name -- e.g. "is a firecracker, not a candle" -- lowercased. A core shorter than MIN_CORE
  characters is too generic to police ("is box office" would block every other "box office").
"""
import glob
import json
import os
import re

RECENT_NIGHTS = 3
MIN_CORE = 14
_STRIP = ' ,.;:!?—-–\'"'


def _fnv(key):
    h = 2166136261
    for ch in key:
        h = ((h ^ ord(ch)) * 16777619) & 0xFFFFFFFF
    return h


def core(text, names=(), min_len=MIN_CORE):
    t = text
    for n in names:
        if n:
            t = t.replace(n, '\x00')
    t = t.replace('{who}', '\x00')
    best = max((p.strip(_STRIP) for p in t.split('\x00')), key=len, default='')
    best = best.lower()
    return best if len(best) >= min_len else None


def recent_notes(boards_dir, date, n=RECENT_NIGHTS):
    """Every write-up printed on the last `n` archived boards strictly before `date`, as one lowercase string."""
    if not boards_dir or not os.path.isdir(boards_dir):
        return ''
    files = sorted(f for f in glob.glob(os.path.join(boards_dir, '*.json'))
                   if re.match(r'\d{4}-\d{2}-\d{2}$', os.path.basename(f)[:-5])
                   and os.path.basename(f)[:-5] < str(date))[-n:]
    out = []
    for f in files:
        try:
            d = json.load(open(f, encoding='utf-8'))
        except Exception:
            continue
        for t in d.get('tickets') or []:
            if t.get('note'):
                out.append(t['note'])
        m = d.get('meta') or {}
        for k in ('ftd', 'tot', 'longtd'):
            v = m.get(k)
            if isinstance(v, dict):
                if v.get('note'):
                    out.append(v['note'])
                for l in v.get('tlegs') or []:
                    if l.get('why'):
                        out.append(l['why'])
    return '\n'.join(out).lower()


def boards_dir_near(*starts):
    """The archived boards for this room: ../boards from a .work dir, or ./boards from the room dir."""
    for s in starts:
        if not s:
            continue
        for c in (os.path.join(s, '..', 'boards'), os.path.join(s, 'boards')):
            if os.path.isdir(c):
                return os.path.normpath(c)
    return None


class Mem:
    def __init__(self, day='', recent=''):
        self.day = str(day or '')
        self.recent = recent or ''
        self.said = set()
        self.seen = set()

    def stale(self, c):
        # a said SHORT form also spends its long form ("is a firecracker, not a candle" inside
        # "is a firecracker, not a candle, every minute a fireworks show"), so test containment.
        return bool(c) and (c in self.recent or any(s in c or c in s for s in self.said))

    def pick(self, opts, key, names=(), min_len=MIN_CORE):
        """The first phrasing, walking from the dated hash, not said tonight nor on recent boards."""
        if not opts:
            return ''
        n = len(opts)
        start = _fnv(str(key) + '|' + self.day) % n
        # Tier 2, when every phrasing is spent: never one said TONIGHT, and of the rest the one whose
        # last appearance is OLDEST (recent_notes() is oldest board first, so a smaller rfind = longer ago).
        spare, spare_at = None, None
        for j in range(n):
            o = opts[(start + j) % n]
            c = core(o, names, min_len)
            if c:
                self.seen.add(c)
            if not self.stale(c):
                return o
            if not (c and any(s in c or c in s for s in self.said)):
                at = self.recent.rfind(c) if c else -1
                if spare is None or at < spare_at:
                    spare, spare_at = o, at
        return spare if spare is not None else opts[start]

    def commit(self, body):
        """Mark every phrase core that actually made it into a published note as said."""
        low = (body or '').lower()
        for c in list(self.seen):
            if c in low:
                self.said.add(c)
