#!/usr/bin/env python3
"""nfl_injexit.py -- INJEXIT-2026-10-11. A man RULED OUT DURING HIS OWN GAME voids his leg.

WHAT HAPPENED. 2026-10-11, Week 5. The board carried TreVeyon Henderson (+165, "Inside the Ten")
and T.J. Hockenson (+300, "Audible") as 1u anytime-TD singles. Both took the field, both were
ruled out mid-game, and both slips graded as LOSSES -- 🚩 SOLD on the live board. Owner:
"hockenson and treyveon were both void due to injuries. we need to set that up to update on its
own correctly and not count the tickets as sold."

WHY EVERY EXISTING RULE MISSED IT, measured on that night's feed:

  * nfl_injuries.py (INJOUT-2026-09-11) runs BEFORE the draft. Both men were Questionable at
    build time and legitimately drafted. Nothing it does applies after kickoff.
  * nfl_live.js's inactives pass runs `if (!live && !fin)` -- pre-kickoff only, by design.
  * nfl_settle.py voids a leg only when ESPN's injury block says Out/IR AND the man is absent
    from the box score. BOTH halves fail here: ESPN's per-game injury block still read
    "T. Henderson Questionable" and "T.J. Hockenson Questionable" hours after the final whistle
    -- it carries the PRE-GAME designation and is never updated -- and both men are in the box
    score, because they played (Henderson 4 car/22 yds + 1 rec/16; Hockenson 1 rec/7).

    ⚠️ That second rule is NOT broken and must not be "fixed" into this one. The same feed
    correctly carried `B. Morton Out`, `A. O'Connell Out`, `O. Beckham Jr. Out` for men who were
    genuinely inactive. Out-and-absent still means inactive. This file covers the other shape:
    PRESENT in the box score, and ruled out anyway.

THE SIGNAL. ESPN's v3 athlete record carries a dated, per-player injury row that the per-game
block does not. On the night, with `status` STILL reading "Questionable" on both:

    Henderson  2026-10-11T19:12Z  "The Patriots ruled out Henderson (ankle) for the remainder of
                                   Sunday's game against the Raiders..."
    Hockenson  2026-10-11T17:42Z  "The Vikings downgraded Hockenson to out for Sunday's game
                                   against the Saints due to a concussion."

So the COMMENT is read and `status` is ignored -- status is the stale field that caused this.
Note the two phrasings: one says "ruled out", the other never does. A pattern fitted to one of
them catches one of two, which is a fix the owner would watch fail a second time.

THE RULE, deliberately narrow:
  a leg is voided when, for a game that is LIVE or FINAL, the man
    1. is on a TICKET (nothing else can cost money, and it bounds the fetch count),
    2. appears in that game's box score (so we have his ESPN id, and so this never overlaps the
       out-and-absent rule above),
    3. did NOT score -- a scorer is never voided, which is doctrine from nfl_settle.py's header
       and is the one way this rule could take money off a winning slip, and
    4. has an ESPN injury row dated inside his own game's window whose comment says he was ruled
       out, and does not say the opposite.

WHAT IT TOUCHES. `p['out'] = True` and nothing else. Every consumer of that flag already does the
right thing and none of them is changed: index.html's gradeTicket pushes a 'v' leg and refunds
(VOIDSHOW-2026-09-27 renders it "↩ VOID · refunded" instead of dropping it), nfl_settle.py's
marking loop leaves a pre-set `out` alone, and soccer_grade.fold() books the refund. If this file
is ever wrong about a man who then scores, BOTH the page and the settler clear `out` on a scorer,
so the mistake self-heals into the right answer.

WHERE IT RUNS. nfl-build.yml, between nfl_payload.py and nfl_fork.py, so the flag is baked into
the page and into the archived board the ledger grades. It is NOT a second live loop: the page
needs no change, because a board that arrives already carrying `out` renders the refund.

    python3 nfl_injexit.py <board.json> [--date YYYY-MM-DD]
Exit 0 always. A network miss leaves the flag unset and the next build tries again.
"""
import io
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)
import nfl_espn                                   # ESPNFETCH-2026-09-11: node fetch, not urllib
from nfl_settle import ESPN, ALIAS, box, norm     # ONE box-score reader, ONE name normaliser

V3 = 'https://site.web.api.espn.com/apis/common/v3/sports/football/nfl/athletes/'

# ⚠️ FITTED TO BOTH PHRASINGS ON THE NIGHT, NOT ONE. "ruled out" alone catches Henderson and
# misses Hockenson, whose row says "downgraded Hockenson to out" -- the player's own name sits
# between the verb and the word, which is why the gap is matched rather than a fixed phrase.
OUT_RE = re.compile(r'ruled out'
                    r'|downgraded[^.]{0,40}\bto out\b'
                    r'|declared out'
                    r'|will not (?:play|return)'
                    r"|won[^a-z]?t (?:play|return)"
                    r'|out for the (?:rest|remainder)'
                    r'|(?:is|was) out for', re.I)
# and the readings that LOOK like an out and are not. "questionable to return" is the common one:
# it is what ESPN writes while a man is being evaluated, i.e. exactly when a panicking rule would
# fire early and void a leg that is about to come back and score.
NOT_RE = re.compile(r'not (?:been )?ruled out'
                    r'|questionable to return'
                    r'|doubtful to return'
                    r'|expected to return'
                    r'|cleared to return'
                    r'|returned to the game', re.I)

# The window the row has to fall in, around THIS game's kickoff. 72 hours before covers a Friday
# "ruled out for Sunday" (a genuine inactive, which this rule may also catch, harmlessly -- it
# agrees with the out-and-absent rule rather than contradicting it); 8 hours after covers a row
# published once the game is over. Last week's row for last week's game falls outside both.
BEFORE_H, AFTER_H = 72, 8


def ruled_out(comment):
    """Does this ESPN injury comment say the man was ruled out? Read the COMMENT, never `status`
    -- `status` still read 'Questionable' for both men on 2026-10-11 and is what caused this."""
    c = str(comment or '')
    return bool(OUT_RE.search(c)) and not NOT_RE.search(c)


def _ts(s):
    """ESPN hands back both '...Z' and '...+00:00'. -> epoch seconds, or None."""
    s = str(s or '').strip().replace('Z', '+00:00')
    try:
        import datetime
        return datetime.datetime.fromisoformat(s).timestamp()
    except Exception:
        return None


def in_window(stamp, kickoff):
    d, k = _ts(stamp), _ts(kickoff)
    if d is None or k is None:
        return False
    return (k - BEFORE_H * 3600) <= d <= (k + AFTER_H * 3600)


def box_ids(summary):
    """-> {norm(name): espn athlete id} for everyone in one box score. The id is the whole reason
    this rule is limited to men who appear: it is the key the v3 record is addressed by, and the
    box score is the only place the build already has it."""
    ids = {}
    for tp in ((summary.get('boxscore') or {}).get('players') or []):
        for g in tp.get('statistics') or []:
            for a in g.get('athletes') or []:
                ath = a.get('athlete') or {}
                nm, aid = ath.get('displayName'), ath.get('id')
                if nm and aid:
                    ids.setdefault(norm(nm), str(aid))
    return ids


def latest_injury(aid, getj):
    """The athlete's most recent injury row, or None. Only the latest is read: an older row is
    about an older injury, and the window check below would reject it anyway."""
    j = getj(V3 + str(aid))
    a = j.get('athlete') or j
    rows = a.get('injuries') or []
    return rows[0] if rows else None


def bet_names(D):
    """Every name that is actually ON a slip -- the only names that can cost money, and the bound
    on how many athlete records a build asks ESPN for (18 on the night this was written)."""
    out = []
    for t in (D.get('tickets') or []):
        for l in (t.get('players') or []):
            out.append(l.get('name'))
    ft = (D.get('meta') or {}).get('ftd') or {}
    for t in [ft] + list(ft.get('alts') or []):
        for l in (t.get('players') or []):
            out.append(l.get('name'))
    return [n for n in dict.fromkeys(out) if n]


def mark(D, getj=None, log=print):
    """Set p['out'] on every betted man ruled out during his own game. -> list of (name, why)."""
    getj = getj or nfl_espn.getj
    date = (D.get('meta') or {}).get('date')
    if not date:
        log('  injexit: board has no meta.date'); return []
    names = bet_names(D)
    if not names:
        return []

    # game index -> "AWAY@HOME", for the games the slips actually sit on
    games = {}
    for n in names:
        p = (D.get('players') or {}).get(n) or {}
        if p.get('game') is not None and p.get('gmatch'):
            games[p['game']] = p['gmatch']
    if not games:
        return []

    sb = getj(ESPN + 'scoreboard?dates=' + date.replace('-', ''))
    events = {}
    for ev in (sb.get('events') or []):
        comp = (ev.get('competitions') or [{}])[0]
        side = {c.get('homeAway'): ((c.get('team') or {}).get('abbreviation'))
                for c in (comp.get('competitors') or [])}
        st = ((comp.get('status') or ev.get('status') or {}).get('type')) or {}
        events[(side.get('away'), side.get('home'))] = (
            ev.get('id'), str(st.get('state') or ''), str(st.get('name') or ''), ev.get('date'))

    hits = []
    for gi, gm in sorted(games.items()):
        away, home = gm.split('@')
        hit = events.get((ALIAS.get(away, away), ALIAS.get(home, home)))
        if not hit:
            continue
        eid, state, stname, kickoff = hit
        # pre-kickoff is nfl_injuries.py's half of the job; a postponement voids the whole game
        # elsewhere. This rule only speaks about a game that is being, or has been, played.
        if state not in ('in', 'post') or re.search(r'POSTPONED|CANCELED|CANCELLED', stname, re.I):
            continue
        try:
            sumry = getj(ESPN + 'summary?event=' + str(eid))
        except Exception as e:
            log(f'  injexit: summary {eid} unreachable ({str(e)[:70]})'); continue
        scored, seen, _ = box(sumry)
        ids = box_ids(sumry)

        for n in names:
            p = (D.get('players') or {}).get(n) or {}
            if p.get('game') != gi or p.get('out'):
                continue
            k = norm(n)
            if k in scored or p.get('hr'):
                continue                      # A SCORER IS NEVER VOIDED
            if k not in seen:
                continue                      # absent from the box: the out-and-absent rule's case
            aid = ids.get(k)
            if not aid:
                continue
            try:
                inj = latest_injury(aid, getj)
            except Exception as e:
                log(f'  injexit: athlete {aid} unreachable ({str(e)[:70]})'); continue
            if not inj:
                continue
            txt = str(inj.get('shortComment') or '') or str(inj.get('longComment') or '')
            if in_window(inj.get('date'), kickoff) and ruled_out(txt):
                p['out'] = True
                hits.append((n, txt[:110]))
                log(f'  injexit: {n} ({gm}) ruled out -- {txt[:90]}')
    return hits


def main():
    args = [a for a in sys.argv[1:] if not a.startswith('--')]
    if not args:
        print('usage: nfl_injexit.py <board.json>'); return 2
    path = args[0]
    D = json.load(io.open(path, encoding='utf-8'))
    try:
        hits = mark(D)
    except Exception as e:
        print(f'::warning::nfl_injexit: {str(e)[:150]} -- board left as drafted')
        return 0
    if hits:
        json.dump(D, io.open(path, 'w', encoding='utf-8'),
                  ensure_ascii=False, separators=(', ', ': '))   # nfl_payload.py's shape
    print(f'nfl_injexit {(D.get("meta") or {}).get("date")}: {len(hits)} leg(s) voided'
          + (' -- ' + ', '.join(n for n, _ in hits) if hits else ''))
    return 0


if __name__ == '__main__':
    sys.exit(main())
