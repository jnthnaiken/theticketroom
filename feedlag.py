#!/usr/bin/env python3
"""FEEDLAG-2026-09-24 -- tell a lagging feed apart from a lineup that is genuinely not out.

THE COMPLAINT THAT PRODUCED THIS, TWICE
    2026-09-22, owner: "i feel like some teams arent confirming at all now. the rangers start in
    an hour and their lineup isnt out yet?"
    2026-09-23, owner: "the houston lineup is out. why is it still projected on the tickets?"

    The first was answered with a different bug (a card flickering on and off) and the underlying
    report was dropped. The second is the same report, and this time it cost a slip: Daulton
    Varsho sat on a locked 7:40 slip because Houston's 10:10 card never reached the board, and
    Houston sat him.

WHAT IS ACTUALLY HAPPENING
    The board has exactly ONE live source for "is this man in the lineup": MLB's StatsAPI, via
    slate_auto. The RotoWire scrape behind lineups_<date>.json is taken once and never updates.
    So when StatsAPI is slow to publish a club, nothing in the pipeline can see the card, and
    every bat on that side stays `projected` however long the lineup has actually been out.

    Verified 2026-09-23 at 00:28Z, 95 minutes before HOU@SEA: schedule?hydrate=lineups,
    /game/{pk}/boxscore and /game/{pk}/feed/live ALL returned Seattle 9, Houston 0, while
    RotoWire had shown Houston as "Confirmed Lineup" for some time. ESPN's summary endpoint
    carried the same hole, because it syndicates the same feed. It is not our parsing and there
    is no second machine-readable source to fall back on.

THE SIGNAL
    Clubs do not post an hour and a half apart. When MLB has one half of a game confirmed with a
    full nine and the other half at zero, that is the FEED lagging a specific club, not a manager
    withholding a card. That asymmetry is the thing the board could not previously tell apart
    from "no lineup yet", and it is what this module detects.

MEASURED OVER THE PULL HISTORY (every 3rd committed slate_auto revision)
    2026-09-22   NYM 12 of 44 pre-game pulls, closest 77 min to first pitch
                 HOU 6/51, MIA 5/41, CWS 5/41, ARI 5/46, MIN 3/51, SD 3/53, TB 2/52
    2026-09-23   HOU 10 of 42, closest 98 min to first pitch
                 ARI 9/42, STL 7/33, TB 6/35, MIL 5/33, CWS 3/38, NYM 2/40, BOS 2/36

    Eight clubs a night, both nights. This is routine, not an incident.

WHAT THIS MODULE DOES AND DOES NOT DO
    It reports. It does not change a draft, a lock, or a player's status -- those are the two
    changes that broke the live board on 2026-09-23 and they are not being made from a detector.
    A lagging side is surfaced so the build log says so and the payload carries it, which is the
    difference between a board that is quietly wrong and one that says which club it cannot see.
"""

MIN_POSTED = 9          # a real card is nine bats; fewer means the pull caught it mid-flight


def _posted(half):
    """True when MLB has published this half of a game: confirmed AND a full nine."""
    if not isinstance(half, dict):
        return False
    lu = half.get('lineup')
    n = lu if isinstance(lu, int) else len(lu or [])
    return bool(half.get('confirmed') and n >= MIN_POSTED)


def lagging(game, side):
    """True when THIS side is unpublished while the OTHER side of the same game is published.

    `game` is a slate_auto game record, `side` is 'away' or 'home'. Returns False when the game
    record is missing or when both halves are in the same state -- two empty halves are simply an
    early pull, and that is not a lag, it is a lineup nobody has posted yet.
    """
    if not isinstance(game, dict) or side not in ('away', 'home'):
        return False
    other = 'home' if side == 'away' else 'away'
    return _posted(game.get(other)) and not _posted(game.get(side))


def scan(slate):
    """Every lagging side in a slate_auto pull, as [(matchup, side, abbrev)], skipping live/final.

    Only pre-game states are considered: once a game is under way the lineup question is settled
    by the box score, and a half that never posted is a feed that has stopped mattering.
    """
    out = []
    for g in (slate or {}).get('games', []) or []:
        if str(g.get('status') or '') not in ('Scheduled', 'Pre-Game', 'Warmup'):
            continue
        for side in ('away', 'home'):
            if lagging(g, side):
                out.append((g.get('matchup') or '?', side,
                            ((g.get(side) or {}).get('abbrev') or '?')))
    return out


if __name__ == '__main__':
    import json
    import sys
    for path in sys.argv[1:]:
        hits = scan(json.load(open(path)))
        print('%s: %s' % (path, ', '.join('%s %s (%s)' % (m, s, a) for m, s, a in hits) or 'none'))
