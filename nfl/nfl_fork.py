#!/usr/bin/env python3
"""nfl_fork.py -- build nfl/index.html from the LIVE index.html by named seam replacement.

⚠️ THE FOOTBALL ROOM IS NOT A DESIGN. It is the baseball room with football words in it. Owner,
2026-08-24, on the soccer fork and restated 2026-09-03 on this one: "it should look just like the
other 2". A hand-built page -- however nice -- diverges from index.html the moment index.html
changes, silently, and nobody notices until one room renders a card wrong and the other renders it
right. So every baseball->football difference is declared below as a NAMED SEAM: an exact string
that must appear an exact number of times. Zero or an unexpected count FAILS the build and names
the seam, which is the signal that index.html moved underneath the fork. That is the whole safety
property. Do not "fix" a failing seam by loosening it to a regex -- go read what changed.

    python3 nfl_fork.py <index.html> <nfl_D.json> <out.html>

⚠️ THIS SCRIPT NEVER WRITES index.html. It reads it. The MLB board is not a build artifact of the
football board and must never become one.

WHY THIS FORK IS SMALLER THAN THE SOCCER ONE (90 seams). Soccer had to REPLACE the weather lane
with a rotation-risk lane, restate the whole how-to tab, and add odds-on price handling. Football
KEEPS the weather lane -- wind is a measured term here (-1.6pp above 11mph, within usage strata)
and Open-Meteo is already wired -- so seam group 4 does not exist at all. What is left is
vocabulary, the five chips, the MLB-fitted calibration, and the game clock.
"""
import json, sys

EXPECT_SEAMS = 45     # 44 named + 1 payload (6 added on a SECOND pass, from grepping the OUTPUT)

def seams(payload_js):
    S = []
    def add(label, old, new, n=1):
        """n = how many times this string is expected. n>1 is a CLAIM THAT YOU CHECKED ALL OF
        THEM -- e.g. '⚾ homered' is emitted by the legend, the carry-over strip and the player
        card and all three mean the same thing. It is not a way to silence a surprise."""
        S.append((label, old, new, n))

    # ---- 1. THE PAYLOAD ---------------------------------------------------------------
    add('payload', '__PAYLOAD__', payload_js)

    # ---- 2. IDENTITY / COPY -----------------------------------------------------------
    add('title', '<title>HR Prop Ticket Room</title>', '<title>The Football Room</title>')
    add('eyebrow', 'eyebrow">Home-Run Props · ', 'eyebrow">Anytime Touchdown · ')
    add('eyebrow-tail', ' · Kasper blend + matchup</div>', ' · usage blend + game total</div>')
    add('tagline',
        '“Every strike brings me closer to the next home run.”<span class="cite">— Babe Ruth</span>',
        '“Today I will do what others won’t, so tomorrow I can accomplish what others can’t.”'
        '<span class="cite">— Jerry Rice</span>')

    # ---- 3. THE FIVE CHIPS ------------------------------------------------------------
    # ⚠️ 'Pitcher' is the OPPOSING-MATCHUP chip and it is GONE, not re-pointed. Its football
    # analogue measured +0.8pp (opp red-zone trips allowed) and -0.2pp (opp TD rate allowed
    # inside the 10) with usage AND price held -- dead on both instruments. Hit rate / House
    # go with GCAL below: both derive from an MLB-fitted curve and there are no graded football
    # nights to refit on. Five chips, every one a term that measured.
    add('chips',
        "const chips=[['Pitcher',(p.phr9!=null?Math.max(0,Math.min(100,Math.round((p.phr9-0.70)/0.60*100))):'—')],"
        "['POWER',(p.powidx!=null?p.powidx:'—')],['Model',p.TOTAL!=null?Math.round(p.TOTAL):'—'],"
        "['Zone',fmt(p.zonev)],['Park','×'+p.wf],['Hit rate',hitPct(p.TOTAL)],['House',houseOdds(p.TOTAL)]];",
        "const chips=[['Touches',(p.hh!=null?p.hh:'—')],['Inside 10',(p.la!=null?p.la:'—')],"
        "['Model',p.TOTAL!=null?Math.round(p.TOTAL):'—'],['GL share',fmt(p.zonev)],"
        "['Weather','×'+p.wf],['Team total',(p.powidx!=null?p.powidx:'—')]];")

    # ---- 4. SPORT NOUNS ---------------------------------------------------------------
    add('homered', '⚾ homered', '🏈 scored', 3)      # legend + carry-over strip + player card
    add('nohomer', '❌ no homer', '❌ no TD', 2)
    add('podds', "${p.odds?('HR '+oddsStr(p.odds)):'HR TBD'}",
                 "${p.odds?('TD '+oddsStr(p.odds)):'TD TBD'}")
    add('sort-odds', '<option value="odds">HR odds · shortest first</option>',
                     '<option value="odds">TD odds · shortest first</option>')
    add('sort-power', '<option value="power">Power · highest first</option>',
                      '<option value="power">Touches · most per game</option>')
    add('sort-hr9', '<option value="hr9">Opp SP HR/9 · most homer-prone</option>',
                    '<option value="hr9">Inside-10 share · biggest</option>')
    add('sort-lift', '<option value="lift">Park/weather lift · biggest</option>',
                     '<option value="lift">Weather lift · biggest</option>')
    add('tonight-count', "+kc.moon+' 🚀'", "+kc.moon+' 🏈'")
    add('tracker-moon', "['moon','🚀','Moonshots']", "['moon','🏈','Paydirt']")
    add('client-moon-badge', "kind:'moon',badge:'🚀'", "kind:'moon',badge:'🏈'", 2)
    add('mkparlay-badge', "mkParlay('moon','🚀'", "mkParlay('moon','🏈'")
    add('sec-moonshots', "sec('lot','Moonshots',moon)", "sec('lot','Paydirt',moon)")
    add('leg-hr-icon', "${fp.hr?'⚾':fp.void?", "${fp.hr?'🏈':fp.void?")
    add('stat-poolbats', "['Pool bats',D.meta.pool]", "['Pool players',D.meta.pool]")
    add('pcount-bats-a', "+' priced bats'):", "+' priced players'):")
    add('pcount-bats-b', "+' priced bats · '+pool.size", "+' priced players · '+pool.size")
    add('legend-brick', '<span>🧱 base score</span>', '<span>🎯 model chance</span>')
    add('bbadge', '<span class="bbadge">🧱 ${p.khr!=null?p.khr.toFixed(1):\'—\'} ${lift}</span>',
                  '<span class="bbadge">🎯 ${p.khr!=null?p.khr.toFixed(1)+\'%\':\'—\'} ${lift}</span>')
    add('legend-soft', '⚠</b> soft starter · ', '⚠</b> inactive risk · ')
    add('howto-order', 'Read it top to bottom: 🍱 Lunch Special, 🌃 Nightcap, ⚓️ Anchors, 🚀 Moonshots.',
                       'Read it top to bottom: 🍱 Early Window, 🌃 Sunday Night, ⚓️ Anchors, 🏈 Paydirt.')
    add('builder-hint', 'Pick bats on the left, then Build.', 'Pick players on the left, then Build.', 3)
    add('odds-allbats', '<option value="all">All bats</option>', '<option value="all">All players</option>')
    add('odds-hint', 'Type a number per bat —', 'Type a number per player —')
    add('kind-anchors', '<b>Anchors</b><span>The four bats the moons are built around,',
                        '<b>Anchors</b><span>The four players the parlays are built around,')
    add('step-players', 'Every bat that cleared the pool gate, one card each.',
                        'Every player who cleared the pool gate, one card each.')
    add('footer-wind', 'always verify odds, lineups, and wind before you wager.',
                       'always verify odds, inactives, and wind before you wager.')
    add('live-btn', '\\u21bb Update from MLB', '\\u21bb Update from ESPN')

    # ---- 5. THINGS THAT ARE MLB-FITTED AND MUST NOT SILENTLY CARRY OVER ---------------
    # GCAL maps a TOTAL to a hit rate and was fitted on baseball nights (mu 98.4, sd 32.2).
    # Football TOTALs sit on the same 100+30*blend scale but the CURVE is not the same, and
    # there are no graded football nights to fit one on. Null it and let the chips that used
    # it disappear, exactly as the soccer room did -- a borrowed calibration is a wrong number
    # wearing a right number's clothes.
    add('gcal', 'var GCAL={mu:98.398,sd:32.179,a:-2.16143,b:0.34215};',
                'var GCAL=null; /* NFL: MLB-fitted calibration does not transfer; no graded '
                'football nights yet. Hit rate / House chips are removed by the chips seam. */')
    # A football game is ~3h10, not ~4h. The "still in progress" claim must expire on the
    # right clock or a finished 1:00 game reads as live through the 4:25 wave.
    add('likely-ended', 'return g!=null&&nowETMin()>=g+240;}', 'return g!=null&&nowETMin()>=g+200;}')

    # ---- 6. ODDS SIGNS -- THE BOARD HAD NEVER SEEN AN ODDS-ON PRICE -------------------
    # Baseball HR prices are always +. Anytime-TD is routinely odds-ON (Gibbs -260, Henry -200,
    # Bijan -150 on 2026-09-13), and the unsigned formatter would render -260 as "+-260".
    # Soccer hit the identical seam on 2026-08-27.
    add('odds-sign', "oddsStr=o=>o?'+'+comma(o):'TBD'", "oddsStr=o=>o?((o>0?'+':'')+comma(o)):'TBD'")
    add('odds-sign-header', "(t.parlay_am?('+'+comma(t.parlay_am)):'n/a')",
                            "(t.parlay_am?((t.parlay_am>0?'+':'')+comma(t.parlay_am)):'n/a')")

    # ---- 7. THE LIVE LEDGER HAND-OFF --------------------------------------------------
    # Three rooms, three localStorage keys, or one room's ledger overwrites another's.
    add('live-ledger-key', "localStorage.setItem('hr_live_ledger'",
                           "localStorage.setItem('nfl_live_ledger'")

    # ---- 8. THE LIVE LOOP -- MUST BE LAST ---------------------------------------------
    # LIVELOOP-BOOT-2026-08-25: this seam must kill BOTH the interval and the boot call. The
    # soccer fork matched only the setInterval and left `liveUpdate()` one statement to its
    # left still firing once on load -- which showed up as a live request to statsapi.mlb.com
    # from the soccer board. Both go, in one seam, so they cannot drift apart.
    add('liveloop', 'liveUpdate(); setInterval(liveUpdate, 6*60*1000)',
        "/* NFL: the MLB live loop is not wired here yet. */")

    # ---- 9. SECOND PASS: leftovers the FIRST RENDER exposed ---------------------------
    # ⚠️ THE STATIC SEAM LIST IS NOT THE SEAM LIST. Everything above was derived by reading the
    # source. Every seam below was found by BUILDING the file and grepping the OUTPUT for
    # baseball words -- the same lesson soccer_fork.py records ("build it, screenshot it, and
    # read the page"). Residual 'homer' ran to 17 occurrences in the first build; most are code
    # comments or prose branches that are dormant at football magnitudes (the hr9 branch cannot
    # fire with phr9 null, and the launch-angle branch gates on la>=18 where football's inside-10
    # figure tops out near 3), and these six are the ones that actually render.
    add('footer-sources',
        'Sources: Kasper matchup cards, Baseball Savant (Statcast), MLB StatsAPI '
        '(schedules \u00b7 HR/9 \u00b7 live results), RotoWire (projected lineups), Open-Meteo '
        '(park weather), and multi-book consensus HR odds.',
        'Sources: nflverse (play-by-play, weekly rosters, depth charts), the closing spread and '
        'total for each game\u2019s implied team total, Open-Meteo (stadium weather), and '
        'oddschecker best-available anytime-touchdown prices \u2014 best of book, not a consensus '
        'median. A player with no 2026 snaps is scored from last season blended with his depth '
        'slot, and the card says so.')
    add('lg-hd-homers', '<span>conviction</span><span>homers</span>',
                        '<span>conviction</span><span>TDs</span>')
    add('odds-homered',
        "title=\"${p.hr?'homered \\u2014 click to undo':'mark homered'}\">${p.hr?'\\u26be':''}",
        "title=\"${p.hr?'scored \\u2014 click to undo':'mark scored'}\">${p.hr?'\\ud83c\\udfc8':''}")
    add('kind-moonshots',
        '<b>Moonshots</b><span>Two three-leg round robins per anchor, eight a night.',
        '<b>Paydirt</b><span>Two three-leg round robins per anchor, eight a Sunday.')
    add('cal-11-base', "t:'Base score', d:'Kasper\u2019s khr score, the base of the model.'",
                       "t:'Model chance', d:'The model\u2019s own probability that he finds the "
                       "end zone, before the price.'")
    add('howto-n1', '>Babe Ruth</span>', '>Jerry Rice</span>')
    return S


def build(index_path, d_path, out_path):
    src = open(index_path, encoding='utf-8').read()
    D = json.load(open(d_path, encoding='utf-8'))
    payload = json.dumps(D, ensure_ascii=False, separators=(', ', ': '))

    i = src.find('const D=')
    if i < 0: sys.exit('!! no `const D=` in index.html')
    j = i + len('const D=')
    depth, k = 0, j
    while True:
        c = src[k]
        if c == '{': depth += 1
        elif c == '}':
            depth -= 1
            if depth == 0: k += 1; break
        k += 1
    src = src[:j] + '__PAYLOAD__' + src[k:]

    S = seams(payload)
    if len(S) != EXPECT_SEAMS:
        sys.exit(f'!! seam count {len(S)} != EXPECT_SEAMS {EXPECT_SEAMS} -- a seam was added or '
                 f'dropped without bumping the constant')

    fails = []
    for label, old, new, n in S:
        c = src.count(old)
        if c != n:
            fails.append(f'  seam {label!r} matched {c}, expected {n}')
    if fails:
        print('!! SEAM MISMATCH -- index.html moved underneath the fork:', file=sys.stderr)
        print('\n'.join(fails), file=sys.stderr)
        sys.exit(4)

    for label, old, new, n in S:
        src = src.replace(old, new)

    open(out_path, 'w', encoding='utf-8').write(src)
    print(f'{out_path}: {len(src)} B, {len(S)} seams applied '
          f'({len(D["players"])} players, {len(D["tickets"])} tickets)')


if __name__ == '__main__':
    if len(sys.argv) != 4:
        sys.exit('usage: nfl_fork.py <index.html> <nfl_D.json> <out.html>')
    build(sys.argv[1], sys.argv[2], sys.argv[3])
