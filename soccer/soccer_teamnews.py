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
# CURLYQUOTE-2026-08-31. ESPN writes `Konan N’Dri` with U+2019 RIGHT SINGLE QUOTATION MARK,
# not the ASCII apostrophe both nrm() and nrm_sp() strip. His tokens came out as `n’dri` where
# the priced `Konan NDri` gives `ndri`, so match_one never joined him and he sat in `unmatched`
# all night while he was on Lecce's bench. Folded to the plain apostrophe HERE so both
# normalisers get it for free -- the same reason ø is in this table rather than in nrm().
# Caught only because FIRSTNAME below made absence assertable for him, which turned a silent
# non-join into a live false absence. U+02BC (ʼ) is the same character class and is included.
XLAT = str.maketrans({'ø': 'o', 'æ': 'ae', 'œ': 'oe', 'ß': 'ss',
                      'đ': 'd', 'ð': 'd', 'þ': 'th', 'ł': 'l',
                      'ı': 'i', 'å': 'a',
                      '’': "'", 'ʼ': "'", '‘': "'"})


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


def surname_hits(name, squad):
    """How many squad members share this player's SURNAME token.

    UNMATCHED-2026-08-28. match_one() returning None conflates two facts the board must not
    treat alike: "he is nowhere on the team sheet" and "he IS on the sheet but the join refused".
    The second is common -- oddschecker priced "Antonio Martinez", ESPN's sheet says
    "Toni Martínez", the surname anchors but the token overlap is 1 and any second Martínez ties
    it, so match_one refuses. He was then asserted ABSENT and his single was killed while he was
    starting (2026-08-28, "Back Post"). Same shape as the 08-17 Jr./Sr. suffix bug and the
    Paris Saint-Germain hyphen: a name that fails to join looks exactly like a player who is not
    playing, and it fails in the direction that silently removes a live bet.

    A surname hit means the sheet plausibly contains him, so absence must NOT be asserted.

    COMPOUNDSUR-2026-08-30. The surname-token test alone misses two shapes the two feeds
    disagree on constantly, and BOTH make a real squad member read as absent:

        compound surname   oddschecker "Jaden Philogene-Bidace"  ESPN "Jaden Philogene"
        extra surname      oddschecker "Giovane Nascimento"      ESPN "Giovane"
                           oddschecker "Emersonn Silva"          ESPN "Emersonn"
                           oddschecker "Kevin Macedo"            ESPN "Kevin"
                           oddschecker "Gustavo Nunes Gomes"     ESPN "Gustavo Nunes"

    Anchoring on the LAST token cannot see any of them -- `bidace`, `nascimento`, `silva`,
    `macedo`, `gomes` are simply not on the sheet, though the men are. So for the ABSENCE test
    the anchor is dropped: ANY token in common is a hit. `forms()` already yields the SPACED
    form, so a hyphenated surname is split and `philogene` is an exact token on both sides --
    no substring test is needed and none is used.

    ⚠️ SUBSTRING CONTAINMENT WAS TRIED AND REVERTED THE SAME HOUR. `jack` is inside `jackson`,
    so Brighton's Jack Hinshelwood gave Nicolas Jackson a hit and the gate stopped seeing the
    one player it was built to catch. Exact tokens only.

    ⚠️ THIS IS DELIBERATELY LOOSE AND IT ONLY EVER ADDS HITS. It cannot create a false join --
    match_one() still does the joining and is untouched. All it can do is make absence HARDER
    to assert, which is the only safe direction: a missed hit kills a live bet, a spurious hit
    merely declines to kill one. Same reasoning as the docstring above, one level down.

        🚨 FIRSTNAME-2026-08-31. "ANY token in common" is too loose in ONE direction that matters:
    a shared GIVEN name between two different men. 2026-08-31, Villa v Arsenal, sheet fully
    published 11+9 both sides: `Gabriel Jesus` was priced, was NOT in the XI and NOT on the
    bench -- he was not in the squad at all -- and `gabriel` hit `Gabriel Magalhaes`, who was
    starting. One shared first name, so absence was never asserted and a man who was not at the
    ground rode a live screamer to its lock. That is the WRONGCLUB-2026-08-30 harm arriving
    through the other door.

    The discriminator is NOT "ignore first names" -- three of COMPOUNDSUR's five cases are
    first-name-only matches (`Giovane`, `Emersonn`, `Kevin`). What separates them is CONTAINMENT:
    the sheet name is a token SUBSET of the priced name (or vice versa). Two different men who
    merely share a given name are a subset of neither.

        Jaden Philogene-Bidace / Jaden Philogene   {jaden,philogene} <= {jaden,philogene,bidace}   hit
        Giovane Nascimento     / Giovane           {giovane}         <= {giovane,nascimento}       hit
        Gustavo Nunes Gomes    / Gustavo Nunes     {gustavo,nunes}   <= {gustavo,nunes,gomes}      hit
        Gabriel Jesus          / Gabriel Magalhaes neither is a subset of the other            NO hit

    Subset ALONE is not enough: it would break the case this gate was built for.
    `Antonio Martinez` / `Toni Martinez` is a subset of neither, but they ARE the same man and
    UNMATCHED-2026-08-28 exists because asserting his absence killed a live single. So a shared
    SURNAME token still counts on its own -- the last token of either name appearing in the
    other's tokens.

    ⚠️ Still exact tokens, so the reverted substring bug stays reverted: `jack` (Hinshelwood)
    neither equals nor is a subset involving `jackson`, and the gate keeps catching Nicolas
    Jackson, which is the one player it was built for.
    """
    n = 0
    for cand, _ in squad:
        hit = False
        for ot in forms(name):
            if not ot:
                continue
            os_ = set(ot)
            for ct in forms(cand):
                cs = set(ct)
                if not cs:
                    continue
                if os_ <= cs or cs <= os_:          # containment either direction
                    hit = True
                elif ot[-1] in cs or ct[-1] in os_:  # shared surname token
                    hit = True
                if hit:
                    break
            if hit:
                break
        if hit:
            n += 1
    return n


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
            # STOPPAGE-2026-08-28. ESPN writes an added-time goal's minute as '90+2', and the
            # int() this used to do raised ValueError and killed the whole join -- so the FIRST
            # stoppage-time goal of any slate failed every subsequent build (31 consecutive
            # failures from 20:41Z on 08-28, and the last green pass before it wiped the team
            # news off the live board). The minute is only ever concatenated with a prime for
            # display, and soccer_live.js already carries ESPN's clock as a STRING, so keep the
            # string here too: '90+2' renders as 90+2' and says exactly what happened.
            goals[c[1]].append((c[2], c[3].strip()))

    out = {'xi': {}, 'bench': {}, 'absent': {}, 'unplaced': [], 'status': status,
           'goals': {}, 'trusted': {}, 'club': {}, 'unmatched': {}}
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
            elif trusted and not surname_hits(n, sq):
                out['absent'][n] = m          # complete sheet, nobody of that surname -> really out
            elif trusted:
                # UNMATCHED-2026-08-28: the sheet HAS someone of that surname and the join
                # refused. Unknown, not absent -- he stays draftable and this shouts about it.
                out['unmatched'][n] = m
                print(f'  ::warning::{m}: "{n}" did not join a complete team sheet '
                      f'but the surname is on it -- left draftable, NOT marked out')
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
