#!/usr/bin/env python3
"""nfl_injuries.py -- INJOUT-2026-09-11. A player ESPN lists as OUT cannot be drafted.

Owner, 2026-09-11: "why is bowers in a ticket lmao hes out and theres plenty of time to redraft".
Brock Bowers was Out on the Raiders' injury report two days before kickoff and sat on a live moon
("Money Down"), because the server draft never read an injury report at all. nfl_live.js marks
inactives on the PAGE from 90 minutes out (INACTIVES-2026-09-09), but that is display only -- the
football room has no client re-draft -- and the build, which fresh-drafts every pass until the
slate's games start, drafted him every time.

WHAT IT DOES. Runs between nfl_mock.py and nfl_draft_cli.js. For the slate's date it reads ESPN's
scoreboard, then each game's summary `injuries` block, and sets `out: true` on every scored.json
row whose team lists him with a DEFINITE status. soccer_draft.js already refuses `out` men at every
entry point (buildPool / placeable / pinnable / alive[]), so nothing else has to change; the payload
already carries `out` to the page.

⚠️ DEFINITE ONLY -- the same OUT_STATUS nfl_settle.py and nfl_live.js use: Out, Injured Reserve,
Suspended, Inactive, PUP, Non-Football. QUESTIONABLE and DOUBTFUL are NOT out. A Questionable man
plays more often than not, and the inactives list 90 minutes out is what settles it (nfl_live.js).

⚠️ MATCHED BY TEAM, not name alone. nflverse and ESPN abbreviations differ (LA/LAR, WAS/WSH), and a
name-only match would scratch the wrong man whenever two rosters share a surname-free key.

⚠️ NEVER FATAL, NEVER CLEARS. A network miss leaves scored.json exactly as it was (and says so
loudly); a player is only ever ADDED to out here. The draft simply runs on what it has.

    python3 nfl_injuries.py scored.json fixtures.json
"""
import json, re, sys, unicodedata
import nfl_espn
import datetime
import time

ALIAS = {'LA': 'LAR', 'WAS': 'WSH', 'JAC': 'JAX', 'ARI': 'ARI'}   # nflverse -> ESPN
OUT_STATUS = re.compile(r'^(out|injured reserve|suspension|suspended|inactive|physically unable|non football)', re.I)
_SUF = r'(?:jr|jnr|junior|sr|snr|senior|ii|iii|iv|v)'


def norm(s):
    s = unicodedata.normalize('NFKD', str(s))
    s = ''.join(c for c in s if not unicodedata.combining(c))
    s = re.sub(r'\s+' + _SUF + r'\.?\s*$', '', s.lower())
    return re.sub(r'[^a-z]', '', s)


# CONFLOCK-NFL-2026-10-19 -- the same three tests nfl_live.js's looksLikeInactives() uses (IRLIST-2026-10-18),
# kept byte-for-byte in step: no GAMETIME question left on the list, roster designations ignored, and at least
# MIN_INACTIVE flat Out/Inactive entries, read only once the 90-minute deadline has passed.
PENDING = re.compile(r'^(questionable|doubtful|probable|day.to.day)', re.I)
ROSTER_DESIG = re.compile(r'^(injured reserve|physically unable|non football|suspension|suspended|reserve)', re.I)
MIN_INACTIVE = 3
INACTIVE_DEADLINE_S = 90 * 60


def _status(inj):
    return str(inj.get('status') or ((inj.get('type') or {}).get('description')) or '')


def looks_like_inactives(lst):
    if not lst:
        return False
    flat = 0
    for inj in lst:
        st = _status(inj)
        if PENDING.search(st):
            return False
        if ROSTER_DESIG.search(st):
            continue
        if not OUT_STATUS.search(st):
            return False
        flat += 1
    return flat >= MIN_INACTIVE


def _epoch(iso):
    try:
        return datetime.datetime.strptime(str(iso).replace('Z', '')[:16], '%Y-%m-%dT%H:%M') \
            .replace(tzinfo=datetime.timezone.utc).timestamp()
    except Exception:
        return None


def out_by_team(date, getj=nfl_espn.getj, now=None, published=None):
    """-> {ESPN team abbr: {norm(name): (displayName, status)}} for every game on `date`.
    If `published` is a dict, it is filled with {abbr: True} for every team whose block is the posted
    game-day inactives list (deadline passed + looks_like_inactives), i.e. everyone else is ACTIVE."""
    sb = getj(nfl_espn.ESPN + 'scoreboard?dates=' + date.replace('-', ''))
    now = time.time() if now is None else now
    res = {}
    for ev in sb.get('events') or []:
        s = getj(nfl_espn.ESPN + 'summary?event=' + str(ev.get('id')))
        ko = _epoch(ev.get('date'))
        due = ko is not None and now >= ko - INACTIVE_DEADLINE_S
        for team in s.get('injuries') or []:
            ab = (team.get('team') or {}).get('abbreviation')
            lst = team.get('injuries') or []
            for inj in lst:
                st = _status(inj)
                nm = (inj.get('athlete') or {}).get('displayName')
                if ab and nm and OUT_STATUS.search(st):
                    res.setdefault(ab, {})[norm(nm)] = (nm, st)
            if published is not None and ab and due and looks_like_inactives(lst):
                published[ab] = True
    return res


def confirm(scored, published):
    """CONFLOCK-NFL: every priced man on a team whose inactives list is posted, and who is not on it, is ACTIVE --
    the football analogue of a name on a published XI. status -> 'confirmed', which is what CONFLOCK locks on."""
    hits = []
    for p in scored:
        ab = ALIAS.get(p.get('team'), p.get('team'))
        if published.get(ab) and not p.get('out') and not p.get('void') and p.get('status') != 'confirmed':
            p['status'] = 'confirmed'
            hits.append(p['name'])
    return hits


def apply(scored, outs):
    hits = []
    for p in scored:
        ab = ALIAS.get(p.get('team'), p.get('team'))
        hit = (outs.get(ab) or {}).get(norm(p.get('name')))
        if hit and not p.get('out'):
            p['out'] = True
            p['out_why'] = hit[1]
            hits.append((p['name'], p.get('team'), hit[1], p.get('odds')))
    return hits


# 🚨 STICKYOUT-2026-10-19. Owner: "croskey merritt is out tonight. you had already removed him from the board.
# why is he back?" Because an `out` lived only as long as ESPN kept printing it. Every build re-reads the
# summary's `injuries` block, and ~90 minutes before kickoff ESPN REPLACES the week's injury report there with
# the game-day inactives list. Croskey-Merritt (groin, ruled out on the Saturday) was Out on the report and
# off the board 20:16Z-22:40Z, then simply absent from the inactives list (reserve-list moves are not
# "inactives"), so at 23:00Z nothing said out, and the 23:02Z build drafted him straight back onto
# "Red Zone Target". "NEVER CLEARS" above held within one run and nowhere else.
#
# So an out is now INSERT-ONLY FOR THE SLATE, the same shape as PRICELEDGER: anyone the slate's archived
# board (boards/<date>.json, the prior build) already carries as `out` stays out. ESPN can add names; it can
# never take one back. Runs before the network call, so it holds even when ESPN is unreachable.
def carry_prior_outs(scored, date, board_paths=None, seed_paths=None):
    paths = board_paths or ['../boards/%s.json' % date, 'boards/%s.json' % date]
    prior = None
    for pth in paths:
        try:
            prior = json.load(open(pth, encoding='utf-8'))
            break
        except Exception:
            continue
    pp = (prior or {}).get('players') or {}
    # the payload keeps the nflverse code in `code` (`team` is the display name, e.g. "Commanders")
    was = {(norm(n), ALIAS.get(p.get('code'), p.get('code'))): (p.get('out_why') or 'out on an earlier build')
           for n, p in (pp.items() if isinstance(pp, dict) else []) if p.get('out')}
    # Hand-seeded outs for the slate: slates/<date>/outs.json = {"outs": [{"name": ..., "team": <nflverse code>,
    # "why": ...}]}. For a man the feeds never list (or the night the chain already broke, as on 10-19).
    for pth in (seed_paths or ['../slates/%s/outs.json' % date, 'slates/%s/outs.json' % date]):
        try:
            for o in json.load(open(pth, encoding='utf-8')).get('outs') or []:
                was[(norm(o['name']), ALIAS.get(o.get('team'), o.get('team')))] = o.get('why') or 'ruled out'
            break
        except Exception:
            continue
    # CONFLOCK-NFL-2026-10-19: `confirmed` is insert-only for the slate too. Once a posted inactives list has
    # named a man active, a later build that cannot see the list (ESPN down, block reshuffled) must not hand him
    # back `projected` and unpin his slip. An out (above) still beats it.
    conf = {(norm(n), ALIAS.get(p.get('code'), p.get('code')))
            for n, p in (pp.items() if isinstance(pp, dict) else []) if p.get('status') == 'confirmed' and not p.get('out')}
    hits = []
    for r in scored:
        k = (norm(r.get('name')), ALIAS.get(r.get('team'), r.get('team')))
        if k in conf and k not in was and not r.get('void'):
            r['status'] = 'confirmed'
        if k in was and not r.get('out'):
            r['out'] = True
            r['out_why'] = was[k]
            hits.append(r['name'])
    return hits


if __name__ == '__main__':
    if len(sys.argv) < 3:
        print('usage: nfl_injuries.py scored.json fixtures.json'); sys.exit(2)
    sp, fp = sys.argv[1], sys.argv[2]
    scored = json.load(open(sp, encoding='utf-8'))
    date = json.load(open(fp, encoding='utf-8')).get('date')
    kept = carry_prior_outs(scored, date)
    json.dump(scored, open(sp, 'w', encoding='utf-8'), indent=1)
    print(f'nfl_injuries {date}: STICKYOUT carried {len(kept)} prior out(s): {", ".join(kept) or "-"}')
    pub = {}
    try:
        outs = out_by_team(date, published=pub)
    except Exception as e:
        print(f'::warning::nfl_injuries: ESPN injury report unreachable ({str(e)[:120]}) -- drafting without it')
        sys.exit(0)
    hits = apply(scored, outs)
    conf = confirm(scored, pub)
    json.dump(scored, open(sp, 'w', encoding='utf-8'), indent=1)
    n = sum(len(v) for v in outs.values())
    print(f'nfl_injuries {date}: {n} definite-out listings across {len(outs)} teams; '
          f'{len(hits)} priced player(s) scratched; inactives posted for {sorted(pub) or "-"} '
          f'-> {len(conf)} confirmed active (CONFLOCK-NFL)')
    for nm, tm, st, od in hits:
        print(f'  OUT  {nm} ({tm}) {st}  {od:+d}' if isinstance(od, int) else f'  OUT  {nm} ({tm}) {st}')
