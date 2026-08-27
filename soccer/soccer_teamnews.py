#!/usr/bin/env python3
"""soccer_teamnews.py -- join ESPN team sheets to the priced names. 2026-08-25.

WHY. Until today the board said "Team news is NOT yet wired" and every player read `projected`
from publish to full time. ESPN's summary endpoint carries the XI and the bench for every
fixture on this slate:

    site.api.espn.com/apis/site/v2/sports/soccer/<lg>/summary?event=<id>   -> j.rosters[].roster[].starter

Three states, and the difference between them is the whole point:
    XI      -> confirmed. He is playing.
    SUB     -> named on the bench. NOT confirmed: an anytime-goalscorer bet on him is live but
               he may never come on. He is shown, he is priced, he is NOT drafted.
    ABSENT  -> not in the squad at all. He cannot score. Marked `out`, which is what makes the
               ticket carry the 'Out of lineup' warning.

⚠️ ABSENT IS A CLAIM, so the join has to earn it. soccer_results.py's rule stands: an
unresolved name is not a non-appearance. This module therefore refuses to call anyone ABSENT
unless the join placed most of that match's priced names -- if the join is broken for a
fixture, everyone in it stays unclassified rather than being stamped as dropped.
"""
import io, json, sys, re, unicodedata
from collections import defaultdict

# Letters NFKD will not decompose, because they are letters in their own right rather than a
# base plus a combining mark. Without this "Kasper Hogh" never reaches "Kasper Hogh" and a
# STARTING Celtic forward was classified as unplaced. Scandinavian squads make this routine.
XLAT = str.maketrans({'ø': 'o', 'æ': 'ae', 'œ': 'oe', 'ß': 'ss',
                      'đ': 'd', 'ð': 'd', 'þ': 'th', 'ł': 'l',
                      'ı': 'i', 'å': 'a'})


def nrm(s):
    """Accents off, punctuation DELETED (not spaced). 'M'Bina' -> 'mbina', 'Joy-Lance' ->
    'joylance'. The spaced form is also tried, because ESPN writes 'Joy Lance Mickels' where
    oddschecker writes 'Joy-Lance Mickels' -- neither normalisation wins both cases alone."""
    s = unicodedata.normalize('NFKD', s or '')
    s = ''.join(c for c in s if not unicodedata.combining(c))
    s = s.lower().translate(XLAT)
    return re.sub(r'\s+', ' ', s.replace('.', '').replace('-', '').replace("'", '')).strip()


def nrm_sp(s):
    s = unicodedata.normalize('NFKD', s or '')
    s = ''.join(c for c in s if not unicodedata.combining(c))
    s = s.lower().translate(XLAT)
    return re.sub(r'\s+', ' ', re.sub(r"[.\-']", ' ', s)).strip()


def forms(s):
    """Both token sets for one name."""
    return [tuple(x for x in f.split() if len(x) > 2) for f in (nrm(s), nrm_sp(s))]


def match_one(name, squad):
    """squad: [(espn_name, state)]. Returns (espn_name, state) or None.

    Surname-anchored, same guard as the xG puller: the LAST token of the odds name must appear
    in the candidate's tokens. Then the best candidate by shared-token count, and only if that
    best is unique -- a tie is a refusal, not a coin flip."""
    best, bestn, ties = None, 0, 0
    for cand, state in squad:
        for ot in forms(name):
            if not ot:
                continue
            last = ot[-1]
            for ct in forms(cand):
                if last not in ct:
                    continue
                shared = len(set(ot) & set(ct))
                if shared > bestn:
                    best, bestn, ties = (cand, state), shared, 1
                elif shared == bestn and shared and (cand, state) != best:
                    ties += 1
    return best if (best and ties == 1) else None


def build(ags_path, tn_path, out_path):
    priced = defaultdict(list)
    for line in io.open(ags_path, encoding='utf-8'):
        if line.strip():
            m, n, _ = line.strip().split('|')
            priced[m].append(n)

    squads, status, goals, clubs = defaultdict(list), {}, defaultdict(list), {}
    for line in io.open(tn_path, encoding='utf-8'):
        c = line.rstrip('\n').split('|')
        if not c[0]:
            continue
        if c[0] == 'M':
            status[c[1]] = {'espn': c[2], 'ko': c[3],
                            'xi_h': int(c[4]), 'xi_a': int(c[5])}
        elif c[0] == 'R':
            squads[c[1]].append((c[3], c[4]))
            clubs[c[3]] = c[2]
        elif c[0] == 'G':
            goals[c[1]].append((c[2], int(c[3])))

    out = {'xi': {}, 'bench': {}, 'absent': {}, 'unplaced': [], 'status': status,
           'goals': {}, 'trusted': {}, 'club': {}}
    for m, names in priced.items():
        sq = squads.get(m, [])
        placed = {}
        for n in names:
            hit = match_one(n, sq)
            if hit:
                placed[n] = hit[1]
                # the CLUB, straight off the team sheet. Until now `team` came from the
                # understat xG row, which is the club he played for LAST season -- so a man who
                # moved in the summer showed '-' and 45 of 60 cards named no club at all.
                out['club'][n] = clubs.get(hit[0], '')
        # TRUST-2026-08-25. First cut trusted a match when >=60% of its priced names were
        # placed, which is the wrong signal: LASK v Celtic placed only 53% precisely BECAUSE
        # six priced names really are out of the squad, so a correct join looked like a broken
        # one and the board refused to say what it knew. The right test is whether the TEAM
        # SHEET is complete -- eleven starters a side. If ESPN gave a full XI for both teams,
        # a priced name that is not on it is genuinely not on it.
        st = status.get(m, {})
        rate = len(placed) / len(names) if names else 0
        trusted = (st.get('xi_h') == 11 and st.get('xi_a') == 11)
        out['trusted'][m] = trusted
        for n in names:
            st = placed.get(n)
            if st == 'XI':
                out['xi'][n] = m
            elif st == 'SUB':
                out['bench'][n] = m
            elif trusted:
                out['absent'][n] = m
            else:
                out['unplaced'].append(n)
        print(f'  {m:28s} XI {sum(1 for n in names if out["xi"].get(n)==m):2d} · '
              f'bench {sum(1 for n in names if out["bench"].get(n)==m):2d} · '
              f'absent {sum(1 for n in names if out["absent"].get(n)==m):2d} · '
              f'join {rate:.0%}{"" if trusted else "  <-- INCOMPLETE TEAM SHEET, absent not asserted"}')
    # scorers, joined the same way, against the same squads
    for m, gl in goals.items():
        for who, minute in gl:
            hit = match_one(who, [(n, 'X') for n in priced.get(m, [])])
            if hit:
                out['goals'].setdefault(hit[0], []).append(minute)
    json.dump(out, io.open(out_path, 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
    tot = len(out['xi']) + len(out['bench']) + len(out['absent'])
    print(f'  classified {tot} / {sum(len(v) for v in priced.values())}  '
          f'(XI {len(out["xi"])}, bench {len(out["bench"])}, absent {len(out["absent"])}, '
          f'unplaced {len(out["unplaced"])})')
    if out['goals']:
        print('  priced scorers:', {k: v for k, v in out['goals'].items()})


if __name__ == '__main__':
    build(*sys.argv[1:4])
