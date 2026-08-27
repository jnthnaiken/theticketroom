#!/usr/bin/env python3
"""soccer_fork.py -- build soccer.html from the LIVE index.html by named seam replacement.

WHY A TRANSFORMER AND NOT A COPY. The soccer room must look exactly like the baseball room,
and index.html is ~1 MB of which only ~280 KB is application (46 KB CSS / 14 KB shell /
210 KB engine / 9 KB tail) -- the rest is one night's `const D`. Copying that file once and
hand-editing it means the two rooms drift the moment index.html changes, silently, and nobody
notices until a card renders wrong in one room and right in the other.

So every baseball->soccer difference is declared below as a NAMED SEAM: an exact string that
must appear EXACTLY ONCE in index.html. If a seam matches zero times or twice, this script
FAILS and prints which one -- which is the signal that index.html moved underneath the fork
and the seam needs re-cutting. That is the whole safety property. Do not "fix" a failing seam
by loosening it to a regex; go read what changed.

    python3 soccer_fork.py <index.html> <soccer_D.json> <out.html>

⚠️ THIS SCRIPT NEVER WRITES index.html. It reads it. The MLB board is not a build artifact of
the soccer board and must never become one.

SEAM COUNT is asserted at the end: if you add a seam, bump EXPECT_SEAMS. That stops a seam
being silently dropped during an edit.
"""
import json, sys, io

from soccer_live_seams import live_seams, LIVE_SEAM_COUNT, LIVELOOP_NEW, REFETCH_NEW

EXPECT_SEAMS = 86 + LIVE_SEAM_COUNT          # 86 base + 5 live = 91

OPLOG_OLD = '<div class="adminlog"><h4>Operator log</h4>\n  <div class="entry"><span class="d">Jun 12 · weight + UI</span>Trimmed the <b>suppress-park penalty</b> slightly — park-multiplier slope 0.30 → 0.25 below ×1.00, boost side unchanged — after Jun 11 showed two suppress-park bats (Lowe at PNC, Torres at Comerica) homering against the lean. Suppress marker on ticket weather summaries changed from the blue square to ❄️. Form weight left as-is; revisit in ~2 weeks with more sample.</div>\n  <div class="entry"><span class="d">Jun 12 · lineup-timing rule</span>Adopted the <b>&gt;180-min lineup-timing flag</b> after the Jun 11 <b>Four Corners</b> salami. It bridged a 2:10 PM anchor (Jung) to 7:05–7:40 PM legs whose lineups weren\'t posted at lock. <b>Wisdom</b> (7:05) was scratched after lock and voided; the 7:40 ATL@CWS game was cancelled, voiding <b>Vargas</b>. The 4-leg ticket collapsed to two live legs (Jung, Muncy) — both cold — so only the lone all-live combo graded as a loss; the rest was refunded. Takeaway: don\'t bridge afternoon → night on one parlay. Any leg more than 180 min after the earliest leg now carries the flag.</div>\n </div>'

OPLOG_NEW = (
    '<div class="adminlog"><h4>Operator log</h4>\n'
    '  <div class="entry"><span class="d">Aug 26 · live results</span>The board now <b>re-reads the '
    'results feed every three minutes</b>. Goals, goal minutes, red cards and full time settle '
    'themselves on the card, and the tickets tab grades tonight as they land. What it deliberately '
    'does <b>not</b> do: it does not re-draft (the draft engine is still Python-side), it does not '
    'run a second grader, and it never infers full time from a clock — only the feed writes a '
    'final. Anything it cannot match to a board name is left alone rather than guessed at.</div>\n'
    '  <div class="entry"><span class="d">Aug 26 · team news</span><b>Confirmed line-ups are wired.</b> '
    'The draft now runs off the published XI, so a name on a slip started the match. Today’s slate '
    'was thin enough that four anchors would not fit the pool, so it drafted the largest count that '
    'did — one — rather than padding the card with names the gate rejected.</div>\n'
    '  <div class="entry"><span class="d">Aug 24 · fork</span>The soccer room is a <b>seam-for-seam '
    'fork of the baseball board</b>, not a rewrite — same layout, same card anatomy, same draft '
    'engine. What is not carried over is said so out loud: the Builder’s letter grade is <b>off</b> '
    'until there are graded soccer nights to fit it on.</div>\n'
    ' </div>'
)

# --------------------------------------------------------------------------------------
# The seams. (label, old, new). Order does not matter; each must match exactly once.
# Grouped by what they are, because "which of these is cosmetic" is a question that WILL be
# asked later and the grouping is the answer.
# --------------------------------------------------------------------------------------

def seams(payload_js):
    S = []
    def add(label, old, new, n=1):
        """n = how many times this string is expected to occur. Defaults to 1 (the safe case).
        A seam with n>1 is one where the SAME phrase appears in several render paths and every
        one of them means the same thing -- e.g. the 'homered' badge, which the legend, the
        carry-over strip and the player card each emit. Setting n>1 is a claim that you checked
        all of them; it is not a way to silence a surprise."""
        S.append((label, old, new, n))

    # ---- 1. THE PAYLOAD -------------------------------------------------------------
    # Everything after `const D=` up to `,WX=D.meta.wx;` is one night's slate. Replaced
    # wholesale. The tail assignment is kept so the rest of the engine binds identically.
    add('payload', '__PAYLOAD__', payload_js)   # handled specially, see build()

    # ---- 2. IDENTITY / COPY ---------------------------------------------------------
    add('title',
        '<title>HR Prop Ticket Room</title>',
        '<title>The Soccer Room</title>')
    add('eyebrow',
        'eyebrow">Home-Run Props · ',
        'eyebrow">Anytime Goalscorer · ')
    add('eyebrow-tail',
        ' · Kasper blend + matchup</div>',
        ' · xG blend + matchup</div>')
    # ⚠️ ATTRIBUTION UNVERIFIED -- this line is widely attributed to Gerd Müller but the
    # provenance was not checked. Swap it for anything; it is one string and touches nothing.
    add('tagline',
        '“Every strike brings me closer to the next home run.”<span class="cite">— Babe Ruth</span>',
        '“If you think before you shoot, you’ve already missed.”<span class="cite">— Gerd Müller</span>')

    # ---- 3. THE FIVE CHIPS ----------------------------------------------------------
    # Owner's call 2026-08-24: direct one-for-one analogues of the MLB five, so the card
    # anatomy and the eye-path are identical.
    #   Pitcher -> Defense    (opponent xGA/90, scaled 0-100 the same way phr9 is)
    #   POWER   -> xG90       (non-penalty xG per 90)
    #   Model   -> Model      (unchanged -- it is TOTAL in both sports)
    #   Zone    -> Shot Qual  (xG per shot)
    #   Park    -> Mins       (minutes played; soccer's availability read)
    add('chips',
        "const chips=[['Pitcher',(p.phr9!=null?Math.max(0,Math.min(100,Math.round((p.phr9-0.70)/0.60*100))):'—')],"
        "['POWER',(p.powidx!=null?p.powidx:'—')],['Model',p.TOTAL!=null?Math.round(p.TOTAL):'—'],"
        "['Zone',fmt(p.zonev)],['Park','×'+p.wf],['Hit rate',hitPct(p.TOTAL)],['House',houseOdds(p.TOTAL)]];",
        # HITRATE-2026-08-27: the two MLB chips are dropped here, not translated. Their bands
        # are the MLB calibration curve; showing them against a soccer TOTAL would be a
        # different sport's hit rate wearing this board's numbers. Soccer gets its own when
        # soccer_season.json has enough graded nights to cut bands from.
        "const chips=[['Defense',(p.oppxga!=null?Math.max(0,Math.min(100,Math.round((p.oppxga-0.80)/1.00*100))):'—')],"
        "['xG90',(p.npxg90!=null?p.npxg90.toFixed(2):'—')],['Model',p.TOTAL!=null?Math.round(p.TOTAL):'—'],"
        "['Shot Qual',(p.xgshot!=null?String(p.xgshot.toFixed(3)).slice(1):'—')],"
        "['Mins',(p.minutes!=null?p.minutes:'—')]];")

    # ---- 4. THE SUBSTITUTE LANE (replaces the weather lane) --------------------------
    # ⚠️ COSMETIC ONLY, owner's explicit instruction 2026-08-24: "just make the substitute
    # part cosmetic. dont complicate it." It does NOT move TOTAL, it is NOT in the scorer,
    # and grade_night settles on the NAMED player exactly like a book does. It answers one
    # question on the card -- "if he goes off, who am I left with?" -- and nothing else.
    # It occupies the weather lane because soccer has no park factor and the lane is
    # load-bearing in the layout; leaving it empty makes the soccer card visibly sparser.
    #
    # wxOf() is re-pointed from the GAME to the PLAYER, because a successor is per-player
    # where weather is per-venue. The five keys keep their meaning positionally:
    #   emoji -> 🔄        park -> successor surname (the bold token)
    #   cond  -> his xG90  rain -> typical minute he comes on
    #   lean  -> cover tier, the badge that sits beside the score
    add('wxOf',
        "const wxOf=g=>WX[String(g)],liftCls=",
        "const wxOf=p=>((p&&p.sub)||{emoji:'🔄',park:'—',cond:'no cover',lean:'none'}),liftCls=")
    add('pcard-wxcall',
        "const p=D.players[name],tier=tierOf(confOf(p)),wx=wxOf(p.game),c=isConf(p.status),av=avail(p);",
        "const p=D.players[name],tier=tierOf(confOf(p)),wx=wxOf(p),c=isConf(p.status),av=avail(p);")
    add('legrow-wxcall',
        "tier=tierOf(confOf(fp)),w=Math.max(5,_lt/maxT*100),wx=wxOf(p.game),",
        "tier=tierOf(confOf(fp)),w=Math.max(5,_lt/maxT*100),wx=wxOf(fp),")
    # The brick badge was Kasper's HR projection + the weather lift. Soccer: expected goals
    # in THIS match (xG90 scaled by expected minutes). The lift is dropped -- there is no
    # multiplier to report, and printing "+0%" forever is a lie with a decimal point on it.
    add('bbadge',
        '<span class="bbadge">🧱 ${p.khr!=null?p.khr.toFixed(1):\'—\'} ${lift}</span>',
        '<span class="bbadge">🎯 ${p.xgmatch!=null?p.xgmatch.toFixed(2):\'—\'}</span>')

    # ---- 5. SPORT NOUNS -------------------------------------------------------------
    add('homered', '⚾ homered', '<span class="bal">⚽</span> scored', 3)   # legend + carry-over strip + player card
    add('nohomer', '❌ no homer', '❌ no goal', 2)
    add('podds',
        "${p.odds?('HR '+oddsStr(p.odds)):'HR TBD'}",
        "${p.odds?('GOAL '+oddsStr(p.odds)):'GOAL TBD'}")
    add('psub-opp',
        '· vs ${p.opp[0]} (${p.opp[1]}) ·',
        '· vs ${p.opp[0]} ${p.opp[1]} ·')
    add('sort-odds',
        '<option value="odds">HR odds · shortest first</option>',
        '<option value="odds">Goal odds · shortest first</option>')
    add('sort-power',
        '<option value="power">Power · highest first</option>',
        '<option value="power">xG90 · highest first</option>')
    add('sort-hr9',
        '<option value="hr9">Opp SP HR/9 · most homer-prone</option>',
        '<option value="hr9">Opp defence · leakiest first</option>')
    add('sort-lift',
        '<option value="lift">Park/weather lift · biggest</option>',
        '<option value="lift">Minutes · most played</option>')
    # ---- 5b. SCREAMERS ---------------------------------------------------------------
    # SCREAMERS-2026-08-26, owner's call. The three-leg round robin is a MOONSHOT on the
    # baseball board and a SCREAMER here -- the spectacular strike, same register.
    #
    # ⚠️ It renames the MOON section, not the leftover section. An earlier cut of these seams
    # pointed at kind 'family' (Dingers) because that was the closest analogue on 2026-08-24;
    # by 2026-08-25 the owner retired Dingers on the baseball board outright (retiredKind()),
    # so those strings no longer exist upstream and the fork's seam guard caught all four in
    # one build. The fork inherits the retirement for free -- soccer_mock.py mints no 'family'
    # ticket, and nothing here re-admits one.
    #
    # ⚠️ Every string below still says 'moon'. That is the LEDGER KIND KEY, not a name:
    # soccer_season.json and the grader reconcile on it, exactly as DINGERS-2026-08-18 kept
    # 'family' when the section became Dingers. It is a database column. It is never the word
    # for the section, on screen or in prose.
    add('chip-screamers', 'data-type="moon">🚀 Moonshots', 'data-type="moon">💥 Screamers')
    # The tracker has TWO places that name the kind: the `defs` row list and the "Tonight"
    # counter, which carries its own literal. Seaming only defs left the counter reading
    # "2 \U0001F680" under a row labelled Screamers -- the same one-of-three-render-paths
    # miss that seam group 10 records.
    add('tonight-count', "+kc.moon+' 🚀'", "+kc.moon+' 💥'")
    add('tracker-screamers',
        "['moon','🚀','Moonshots']",
        "['moon','💥','Screamers']")
    # The CLIENT re-derivation mints its own moons (__assembleClient runs on every render for
    # the live builder pass) and stamps the badge itself, so the baked payload's 💥 is not the
    # only source. Three sites: the fill loop's seed, mkParlay(), and the direct out.push().
    # Miss them and a client-minted screamer renders with a 🚀 next to a section titled
    # Screamers -- render-path drift, the exact failure seam group 10 exists to record.
    add('client-moon-badge', "kind:'moon',badge:'🚀'", "kind:'moon',badge:'💥'", 2)
    add('mkparlay-badge', "mkParlay('moon','🚀'", "mkParlay('moon','💥'")
    # The RETIRED kind's ledger row. index.html re-adds it the moment cats.family carries P&L,
    # which on the soccer board it does: the 2026-08-24 slate minted three family slips before
    # the kind was retired, and they graded 1-2 +0.8u. That row is real money and must keep
    # showing -- but "💣 Dingers" is a baseball word for a section this board never had. Renamed
    # to what it actually is now: a retired kind still carrying its season P&L. The KEY stays
    # 'family' (see the SCREAMERS note above) so soccer_season.json keeps reconciling.
    add('tracker-retired',
        "defs.push(['family','💣','Dingers'])",
        "defs.push(['family','🗄','Retired'])")
    add('legend',
        '🌧️ rain · ☀️ heat · 💨 wind · 🥶 cold · 🏟 dome · ⛅ m',
        '🔄 cover · 🟢 strong sub · 🟡 thin · 🔴 none · ⛅ m')

    # ---- 6. THINGS THAT ARE MLB-FITTED AND MUST NOT SILENTLY CARRY OVER --------------
    # GCAL turns a TOTAL into P(homers) for the Builder tab's grade. It was fitted on MLB
    # slates. Neutered rather than re-fitted: hrP() returns null, which the grader already
    # handles, so the Builder tab degrades to "no grade" instead of printing a confident
    # letter grade computed from baseball. Re-fit it when soccer has graded nights.
    add('gcal',
        'var GCAL={mu:98.398,sd:32.179,a:-2.16143,b:0.34215};',
        'var GCAL=null;   /* SOCCER: MLB-fitted calibration deliberately NOT carried over. '
        'hrP() returns null until a soccer fit exists -- see soccer_fork.py seam "gcal". */')
    add('hrP',
        'function hrP(t){ if(t==null||!isFinite(t))return null; return 1/(1+Math.exp(-(GCAL.a+GCAL.b*(t-GCAL.mu)/GCAL.sd))); ',
        'function hrP(t){ if(GCAL==null)return null; if(t==null||!isFinite(t))return null; return 1/(1+Math.exp(-(GCAL.a+GCAL.b*(t-GCAL.mu)/GCAL.sd))); ')
    # The MLB live loop fetches D_<date>.json, Open-Meteo and MLB StatsAPI, then RE-DRAFTS with
    # MLB rules (GAME_CAP, CHALK_N, WIN=120, precipOf). Pointed at a soccer board it would
    # re-draft the tickets against baseball constants. It stays dead. What replaces it is the
    # SOCCER loop -- see soccer_live_seams.py, which supplies LIVELOOP_NEW and injects
    # soccer_live.js. That module reads ESPN, writes finals/results/hr/goalmins/status, and
    # calls refreshAll(); it does not draft, does not grade, and does not adopt a newer file.
    # LIVELOOP-BOOT-2026-08-25: this seam used to match only the setInterval, which left the
    # BOOT call `liveUpdate()` one statement to its left still firing once on load. Rendering
    # the fork under Playwright showed a live request to statsapi.mlb.com from the soccer
    # board -- blocked by the artifact CSP, and wrong even where it is not. Killing the timer
    # and leaving the boot call is exactly the "verified one surface" mistake seam group 10
    # records. Both go, in one seam, so they cannot drift apart.
    add('liveloop',
        'liveUpdate(); setInterval(liveUpdate, 6*60*1000)',
        LIVELOOP_NEW)
    # ---- 7. SECOND PASS: leftovers the first render exposed --------------------------
    # Every one of these was found by RENDERING the board and reading it, not by grep.
    # Recording that, because it is the lesson: the seam list you can derive statically is
    # not the seam list. Build it, screenshot it, and read the page.
    add('sec-screamers', "sec('lot','Moonshots',moon)", "sec('lot','Screamers',moon)")
    add('stat-poolbats', "['Pool bats',D.meta.pool]", "['Pool players',D.meta.pool]")
    # NB: index.html carries the JS escape ↻ literally (six characters), not the glyph.
    add('live-btn', '\\u21bb Update from MLB', '\\u21bb Update from ESPN')
    add('legend-park', '<span>🔥 hot park · ❄️ suppressed park</span>', '')
    add('legend-soft', '⚠</b> soft starter · ', '⚠</b> rotation risk · ')
    add('howto-order',
        'Read it top to bottom: 🍱 Lunch Special, 🌃 Nightcap, ⚓️ Anchors, 🚀 Moonshots.',
        'Read it top to bottom: 🍱 Lunch Special, 🌃 Nightcap, ⚓️ Anchors, 💥 Screamers.')
    # the leg row carries its OWN copy of the brick badge; pCard's seam does not reach it
    add('leg-bbadge',
        """<span class="bbadge">🧱 ${(D.players[p.name]||{}).khr!=null?(D.players[p.name]||{}).khr.toFixed(1):'—'}</span>""",
        """<span class="bbadge">🎯 ${(D.players[p.name]||{}).xgmatch!=null?(D.players[p.name]||{}).xgmatch.toFixed(2):'—'}</span>""")
    add('legrow-wbadge',
        '<span class="wbadge">${wx.emoji} ${_lt.toFixed(1)}</span>',
        '<span class="wbadge">📊 ${_lt.toFixed(1)}</span>')
    add('leg-hr-icon', "${fp.hr?'⚾':fp.void?", "${fp.hr?'⚽':fp.void?")
    add('footer-sources',
        'Sources: Kasper matchup cards, Baseball Savant (Statcast), MLB StatsAPI (schedules · HR/9 · live results), '
        'RotoWire (projected lineups), Open-Meteo (park weather), and multi-book consensus HR odds.',
        'Sources: Understat (player xG, five top leagues), published team news for the confirmed XI, '
        'ESPN (fixtures · live results · goal minutes), and Oddschecker best-available '
        'anytime-goalscorer prices — best of book, not a consensus median. A player with no '
        'top-five xG history scores on the market term alone and shows — on the xG chips.')
    # Two call sites, and " priced bats" also appears in three CODE COMMENTS -- so seam the
    # call sites with enough context to exclude the prose. The guard caught this (5 != 2).
    add('pcount-bats-a', "+' priced bats'):", "+' priced players'):")
    add('pcount-bats-b', "+' priced bats · '+pool.size", "+' priced players · '+pool.size")
    add('legend-brick', '<span>🧱 base score</span>', '<span>🎯 xG this match</span>')
    # ---- 8. GAME DURATION -----------------------------------------------------------
    # likelyEnded() suppresses the "🚧 in progress" claim once the clock says a game is
    # surely over. +240 is FOUR HOURS PAST FIRST PITCH -- a baseball number. A football match
    # is 45+15+45 plus stoppage, ~115 minutes wall-clock. Left at 240, a 12:30 PM kickoff kept
    # claiming "in progress" until 4:30 PM ET, which is over two hours of the board asserting
    # something false. 125 = ~115 plus a small buffer; it is a bound, not a measurement.
    #
    # ⚠️ This does NOT make a match FINAL. Nothing on this board infers finality from a clock,
    # by deliberate design on the baseball side -- isFinal() reads D.meta.finals and only a real
    # results feed writes it. Suppressing a wrong claim and asserting a right one are different
    # jobs and this seam only does the first.
    add('likely-ended',
        'return g!=null&&nowETMin()>=g+240;}   // ~4h past first pitch: no longer claim "in progress" on the clock alone',
        'return g!=null&&nowETMin()>=g+125;}   // SOCCER: ~115min match (45+15+45+stoppage) + buffer, not baseball\'s 4h')
    # ---- 9. NEVER ASSERT A RESULT FOR A PLAYER THE JOIN COULD NOT PLACE -------------
    # isFinal() is per-GAME, so once a match is final the card prints "❌ no goal" for every
    # player in it -- including one the roster join could not resolve. That is the board
    # asserting he did not score when all we actually know is that we could not find him.
    # It also renders absurdly, next to "⏳ projected", which is what exposed it.
    # `unres` is set by soccer_payload for a priced man absent from a FINAL match's squad sheet.
    # NB: this runs AFTER the 'nohomer' seam, so it matches the already-soccerised text.
    # `unres` is a MESSAGE string set by soccer_payload. When it is non-empty the card prints
    # it ALONE and suppresses the confirmed/projected chip -- because for those players every
    # available chip would be a false claim. Two cases reach it:
    #   * priced man absent from a settled match's squad sheet  -> "not found on the squad sheet"
    #   * match ENDED but the feed has not published players     -> "FT 4-0 · scorers not published"
    # The second is what left Malen reading "projected" 25 minutes after full time.
    # ONE helper, three render paths. Injected ahead of pCard so legRow and ticketCard can
    # share it. Returns '' for normal rendering, or a message the card must show ALONE.
    #
    # Two situations where every ordinary chip would be a false claim:
    #   * `unres`  -- data-driven (soccer_payload): the man is not on a settled match's squad
    #                 sheet, or the match ended and the feed has not published players.
    #   * past full time with nothing in -- CLOCK-driven, and deliberately kept at render time
    #     rather than baked, because a baked flag is stale the moment the page sits open.
    #     Saying "the scheduled finish has passed and no result has arrived" is a statement
    #     about OUR DATA, not a claim about the match, so it does not violate the rule that
    #     nothing infers finality from a clock.
    add('sstate-helper',
        'function pCard(name){',
        "function sState(p){ if(!p) return '';\n"
        " if(p.unres) return p.unres;\n"
        " if(!isFinal(p.game) && !isLive(p.game) && likelyEnded(p.gtime)) return '⏱ past full time · result not in yet';\n"
        " return ''; }\n"
        'function pCard(name){')
    add('unresolved-badge',
        """<span class="st ${c?'conf':'proj'}">${c?'✓ confirmed':'⏳ '+p.status}</span>${isFinal(p.game)?'<span class="st dead">❌ no goal</span>':av==='started'""",
        """${sState(p)?'':'<span class="st '+(c?'conf':'proj')+'">'+(c?'✓ confirmed':'⏳ '+p.status)+'</span>'}${sState(p)?'<span class="st haz">'+sState(p)+'</span>':isFinal(p.game)?'<span class="st dead">❌ no goal</span>':av==='started'""")
    # ---- 10. THE TICKETS TAB HAS ITS OWN STATE LOGIC ---------------------------------
    # Seam 9 fixed pCard. pCard is the PLAYERS tab. The default view is TICKETS, which renders
    # through legRow() and ticketCard() -- each with its own independent status chain that
    # seam 9 never touched. So the board still showed "⏳ Donyell Malen" and a "projected"
    # ticket badge for a match that had finished, on the first screen you land on.
    #
    # Verifying one surface and calling the feature done is the mistake this pair of seams
    # exists to record. THREE render paths carry player state: pCard, legRow, ticketCard.
    add('legrow-unres',
        """${fp.hr?'⚽':fp.void?'↩':fp.out?'🪑':fp.pending?'↻':isFinal(p.game)?'❌'""",
        """${sState(fp)?'⏱':fp.hr?'⚽':fp.void?'↩':fp.out?'🪑':fp.pending?'↻':isFinal(p.game)?'❌'""")
    # A slip whose every leg sits in an ended-but-unpublished match is not "projected" --
    # nothing about it is still a projection. t.unres is the count of such legs (soccer_payload).
    # The badge must count legs through sState too, not a baked field -- otherwise a slip whose
    # legs are unsettled only by the CLOCK (no data has arrived) still reads "projected".
    # That is the same bug one level up, and it is why this is counted live per render.
    add('ticket-badge-count',
        """const lk=(t.locked||(t.confleg===t.nlegs&&t.nlegs))?""",
        """const _sp=(t.players||[]).filter(function(l){return sState(D.players[l.name]||l);}).length;"""
        """const lk=_sp&&_sp===t.nlegs?'<span class="badge">⏱ result pending</span>':_sp?"""
        """'<span class="badge">'+(t.nlegs-_sp)+'/'+t.nlegs+' settled</span>':"""
        """(t.locked||(t.confleg===t.nlegs&&t.nlegs))?""")
    # ---- 11. SHOW THE GOAL MINUTES ---------------------------------------------------
    # "just like they do in the box score" applies to the goal itself, not only the
    # substitution. Malen scored three times; "⚽ scored" alone throws two of them away.
    add('scored-minutes',
        """${p.hr?'<span class="st hit"><span class="bal">⚽</span> scored</span>':p.void?""",
        """${p.hr?'<span class="st hit"><span class="bal">⚽</span> scored'+((p.goalmins&&p.goalmins.length)?' '+p.goalmins.map(function(m){return m+String.fromCharCode(8242);}).join(', '):'')+'</span>':p.void?""")

    # ---- 12. THE HOW-TO TAB IS STILL BASEBALL ---------------------------------------
    # Found the same way seam group 7 was found: by RENDERING the page and reading it. The
    # Tickets and Players tabs were soccerised by the seams above; the How To tab was not
    # touched at all, so a board about anytime goalscorers explained itself with Babe Ruth,
    # Reggie Jackson and Ken Griffey Jr., a park-and-weather callout, and a 💣 Dingers legend
    # that contradicted the 💥 Screamers section three tabs to the left.
    #
    # The worked example keeps its ODDS and PAYOUT untouched (+277 / +350 / +379, max +136u).
    # Those numbers are internally consistent with each other and with the round-robin maths
    # the diagram explains; re-rolling them to "look like soccer prices" would mean inventing a
    # payout I cannot derive. Retired greats stand in for the names, exactly as the baseball
    # board uses Ruth and Griffey, and the card still carries its "Example only" pill.
    add('howto-wxsum',
        '<span class="wxsum" data-cal="2">🔥1 🏟 2</span>',
        '<span class="wxsum" data-cal="2">🟢2 🟡1</span>')
    add('howto-lock', '<span>Lock 6:35 PM ET</span>', '<span>Lock 10:00 AM ET</span>')
    add('howto-tnote',
        'Ruth is launching rockets (65% hard-hit), Jackson stays in the launch\n'
        '              zone (23°), and Griffey packs elite raw power, a 100/100 grade.',
        'Henry is getting the best looks on the card (0.18 xG a shot), van Basten has\n'
        '              played nearly every minute (2,640), and Baggio draws the leakiest defence on the slate.')
    add('howto-n1', '>Babe Ruth</span>', '>Thierry Henry</span>')
    add('howto-n2', '>Reggie Jackson</span>', '>Marco van Basten</span>')
    add('howto-n3', '>Ken Griffey Jr.</span>', '>Roberto Baggio</span>')
    # wbadge = model score behind a lane emoji; on the soccer card that lane is the substitute
    # cover (see seam group 4), so ☀️/🏟 become 🔄. bbadge = the base score, which this fork
    # re-points to xG in the match (seams 'bbadge' / 'leg-bbadge' / 'legend-brick').
    add('howto-l1-badges',
        '<span class="wbadge">☀️ 174.6</span>\n                <span class="bbadge">🧱 68</span>',
        '<span class="wbadge">📊 174.6</span>\n                <span class="bbadge">🎯 0.68</span>')
    add('howto-l2-badges',
        '<span class="wbadge">🏟 152.2</span><span class="bbadge">🧱 73</span>',
        '<span class="wbadge">📊 152.2</span><span class="bbadge">🎯 0.73</span>')
    add('howto-l3-badges',
        '<span class="wbadge" data-cal="10">🏟 148.3</span><span class="bbadge" data-cal="11">🧱 49</span>',
        '<span class="wbadge" data-cal="10">📊 148.3</span><span class="bbadge" data-cal="11">🎯 0.49</span>')
    add('howto-w1',
        '<span class="lwhere" data-cal="6">Yankees · NYY@BAL · 6:35</span>',
        '<span class="lwhere" data-cal="6">Arsenal · ARS v CHE · 10:00</span>')
    add('howto-w2',
        '<span class="lwhere">Angels · LAA@HOU · 8:10</span>',
        '<span class="lwhere">Milan · MIL v INT · 12:00</span>')
    add('howto-w3',
        '<span class="lwhere">Mariners · SEA@MIL · 7:40</span>',
        '<span class="lwhere">Juventus · JUV v ROM · 2:45</span>')
    # The twelve numbered callouts around the diagram. Five of them describe baseball.
    add('cal-2',
        "t:'Park & weather', d:'Legs getting help: 🔥 hot park, 🏟 dome, 🌧️ rain, 💨 wind. Updates live.'",
        "t:'Substitute cover', d:'Who you inherit if he goes off: 🟢 strong, 🟡 thin, 🔴 none. Display only — the price does not move.'")
    add('cal-5', 'Frozen at that bat’s own first pitch.', 'Frozen at that player’s own kickoff.')
    add('cal-6',
        "t:'Team · game · time', d:'No slip carries two bats from one game, and every leg fits a 120-minute window.'",
        "t:'Club · match · kickoff', d:'No slip carries two players from one match, and every leg fits one window.'")
    add('cal-9', '⚠ = unranked opposing starter.', '⚠ = rotation risk.')
    add('cal-11',
        "t:'Base score', d:'Kasper’s khr score, the base of the model.'",
        "t:'xG this match', d:'Non-penalty xG per 90 scaled by his expected minutes — goal expectancy in this match.'")
    # The five numbered steps, and the kind legend under them.
    add('step-players',
        'Every bat that cleared the pool gate, one card each.',
        'Every player who cleared the pool gate, one card each.')
    add('step-builder',
        'tick the bats you like, then hit 🔨 Build.',
        'tick the players you like, then hit 🔨 Build.')
    add('step-notes',
        'breaks out every bat with its price, a conviction bar and its own chance of going deep.',
        'breaks out every player with his price, a conviction bar and his own chance of scoring.')
    add('step-livebats', 'tonight&rsquo;s live bats', 'tonight&rsquo;s live players')
    add('kind-lunch',
        '<b>Lunch Special</b><span>One bat, best model score in an afternoon game.',
        '<b>Lunch Special</b><span>One player, best model score in an early kickoff.')
    add('kind-anchors',
        '<b>Anchors</b><span>The four bats the moons are built around,',
        '<b>Anchors</b><span>The players the screamers are built around,')
    # "eight a night" is a BASEBALL count (ANCH_PER_GAME 2 x MOONS_PER_ANC 2 x 4 anchors, on a
    # fifteen-game slate). The soccer draft scales its anchor count to the pool, so on a thin
    # five-match slate it mints two. Printing a fixed eight would be a promise the board breaks
    # most nights.
    add('kind-screamers',
        '<span class="ke">🚀</span><div><b>Moonshots</b><span>Two three-leg round robins per '
        'anchor, eight a night. This is the one diagrammed above.</span>',
        '<span class="ke">💥</span><div><b>Screamers</b><span>Two three-leg round robins per '
        'anchor. This is the one diagrammed above.</span>')
    add('howto-lede',
        'This is a moonshot — the\n      three-leg parlay that carries most of the season.',
        'This is a screamer — the\n      three-leg parlay that carries most of the season.')
    add('howto-tbadge', 'class="tbadge">🚀</span>', 'class="tbadge">💥</span>')
    # Three call sites, same sentence, same meaning (checked all three).
    add('builder-hint', 'Pick bats on the left, then Build.', 'Pick players on the left, then Build.', 3)
    add('odds-allbats', '<option value="all">All bats</option>', '<option value="all">All players</option>')
    add('odds-hint', 'Type a number per bat —', 'Type a number per player —')
    add('footer-wind',
        'always verify odds, lineups, and wind before you wager.',
        'always verify odds and team news before you wager.')
    # The operator log is a baseball changelog: park multipliers, PNC, Comerica, a 4-leg salami.
    # None of it happened on this board. Replaced with the things a reader of THIS page needs
    # to know: what the live loop does and does not do, that team news is wired, and what the
    # fork deliberately did not carry over.
    add('step-refetch',
        'can change as lineups post — the board re-fetches itself every few minutes\n'
        '        and adopts the newer draft.',
        REFETCH_NEW)
    # LUNCH-EMPTY-2026-08-25: the baseball board's empty lunch tray says today's meal "already
    # got served and cleared". On the soccer board that sentence is false every single day --
    # soccer_mock.py mints moon / builder / family only, so a lunch special is never drafted and
    # nothing was ever served. The board is not allowed to assert something that did not happen;
    # the nightcap's own empty state ("no late play posted right now") is already fine as-is.
    add('lunch-empty',
        '🍽️ The cafeteria ladies are on break — today’s meal already got served and cleared. '
        'Fresh tray tomorrow morning.',
        '🍽️ No lunch special on the soccer board yet — the scorer drafts anchors and '
        'screamers only.')
    # ---- 13. COUNTERS AND THE TIMING WARNING ARE BASEBALL-SHAPED --------------------
    # TEAMNEWS-2026-08-25, all three found by freezing the page clock at 1:30 PM ET (one
    # fixture underway, three not) and reading the board, which is the only way any of this
    # shows up -- at build time every counter looks fine.
    #
    # (a) THE 'Confirmed' KPI IS NO LONGER SEAMED, and that is a deliberate removal.
    #     TEAMNEWS-2026-08-25 replaced it with a "Kicked off" tile because with team news
    #     unwired every player was 'projected' from publish to full time, so "Confirmed 0/60"
    #     was a dead counter in a five-slot KPI row -- which reads as a broken feed, worse than
    #     no counter. TEAMNEWS-2026-08-26 wired the published XI into the draft, so the tile now
    #     reports something real and moving (today: 25/75). A seam that exists to route around a
    #     fixed bug has to come out when the bug does, or it quietly hides the fix.
    # (b) The lineup-timing warning never fired. 155 minutes is a BASEBALL number: it is tuned
    #     to how long before first pitch a card posts. Football XIs are published ONE HOUR
    #     before kickoff, so the moment two legs are more than 60 minutes apart the earlier one
    #     is already underway while the later one's team sheet is still unpublished. The wording
    #     follows: "lineups post" is not what a football reader calls it, and the hour is the
    #     whole point, so it says the hour.
    add('twarn',
        'const twarn=_span>155?\'<div class="owarn twarn">\\u23f1 Lineup-timing risk \\u2014 '
        'earliest leg starts before the later legs\\u2019 lineups post, so they can\\u2019t be '
        'confirmed at bet time</div>\':\'\'',
        'const twarn=_span>60?\'<div class="owarn twarn">\\u23f1 Team-news risk \\u2014 the first '
        'leg kicks off before the later legs\\u2019 line-ups are published (an hour before '
        'kickoff), so they cannot be confirmed at bet time</div>\':\'\'')
    add('oplog', OPLOG_OLD, OPLOG_NEW)


    add('ball-css',
        '.st{font-size:11px;border-radius:8px;padding:4px 10px;font-weight:700;letter-spacing:.04em}',
        '.st{font-size:11px;border-radius:8px;padding:4px 10px;font-weight:700;letter-spacing:.04em}'
        # .bal wraps the glyph only, so the chip's 11px text is untouched and the badge
        # does not grow. .lst.hit is the LEG ROW glyph, whose span contains nothing but
        # the ball -- no template change needed there, which also avoids re-cutting
        # 'leg-hr-icon' and 'legrow-unres', whose old-strings are chained through each other.
        '.bal{font-size:1.22em;line-height:1;vertical-align:-.09em}'
        '.lst.hit{font-size:15.5px}')

    # ---- 15. ODDS SIGNS -- THE BOARD HAD NEVER SEEN AN ODDS-ON PRICE ------------------
    # ODDSSIGN-2026-08-26, owner: "mbappes odds read +-250. it should just be -250."
    #
    # Three separate places glue a literal '+' onto a price. On the baseball board that is
    # correct by accident: a home-run prop is never odds-on -- the shortest ever drafted is
    # around +150 -- so `'+'+odds` has been right for every price the board has ever rendered.
    # Anytime goalscorer is a different market. A favourite striker is routinely odds-on, and
    # Kylian Mbappe at -250 is the FIRST negative price this codebase has ever had to print.
    # All three sites produced "+-250".
    #
    # Found by grepping for every "'+'+" in the built file rather than fixing the one the owner
    # could see -- the ticket header and the card-note generator were both wrong too, and the
    # note one ("at a fair +-250") sits in prose where it reads worst.
    #
    # ⚠️ index.html HAS THE SAME BUG and is deliberately NOT patched here: this script never
    # writes the MLB board. It is latent there, not harmless -- type a negative price into the
    # operator console and it renders "+-150" -- so it is worth fixing on that side separately.
    add('odds-sign',
        "oddsStr=o=>o?'+'+comma(o):'TBD'",
        "oddsStr=o=>o?((o>0?'+':'')+comma(o)):'TBD'")
    # The ticket HEADER price, for a slip with no round robin -- i.e. every anchor single.
    # The rr branch beside it already gets this right ((_mp>=0?'+':'')), which is what made the
    # single-leg branch's bare '+' easy to miss.
    add('odds-sign-header',
        "(t.parlay_am?('+'+comma(t.parlay_am)):'n/a')",
        "(t.parlay_am?((t.parlay_am>0?'+':'')+comma(t.parlay_am)):'n/a')")
    # The seven card-note phrasings, each with the sign baked into the sentence.
    add('odds-sign-note',
        '''var od=p.odds; if(od)o.push([1.4,'price',['at a fair +'+od,'priced at +'+od,"you're getting +"+od+' on it','the +'+od+' tag plays','+'+od+' is a number worth taking','+'+od+' carries value','a tidy +'+od+' price']]);''',
        '''var od=p.odds, _so=(od>0?'+':'')+od; if(od)o.push([1.4,'price',['at a fair '+_so,'priced at '+_so,"you're getting "+_so+' on it','the '+_so+' tag plays',_so+' is a number worth taking',_so+' carries value','a tidy '+_so+' price']]);''')

    # ---- 16. THE LIVE-LEDGER HAND-OFF ------------------------------------------------
    # LIVELEDGER-2026-08-26. index.html now stashes its computed season figure under
    # 'hr_live_ledger' so the cover page can show a number that moves during a night instead of
    # the deploy-time ledger.json, which cannot. Both boards share an origin, so the soccer
    # board must NOT write the baseball key -- same collision the ODDS_KEY / LOCK_KEY seams
    # exist to prevent, and here it would put soccer P&L on the baseball door.
    add('live-ledger-key', "localStorage.setItem('hr_live_ledger'", "localStorage.setItem('sr_live_ledger'")

    # ---- 14. THE LIVE LOOP -- MUST BE LAST ------------------------------------------
    # ⚠️ ORDER MATTERS. Every seam is counted against the progressively-replaced text, so
    # injecting ~250 lines of soccer_live.js before the other seams run would let the injected
    # code change another seam's match count and fail the build for a reason that has nothing to
    # do with index.html moving. Injected last, nothing is counted after it.
    S.extend(live_seams())
    return S


def build(index_path, payload_path, out_path):
    src = io.open(index_path, encoding='utf-8').read()
    D = json.load(io.open(payload_path, encoding='utf-8'))
    payload_js = json.dumps(D, ensure_ascii=False, separators=(',', ':'))

    S = seams(payload_js)
    assert len(S) == EXPECT_SEAMS, f'seam count changed: {len(S)} != {EXPECT_SEAMS} (bump EXPECT_SEAMS deliberately)'

    # the payload seam is positional, not a string match: replace everything between
    # `const D=` and the `,WX=D.meta.wx;` tail that binds it.
    a = src.index('const D=') + len('const D=')
    b = src.index(',WX=D.meta.wx;', a)
    out = src[:a] + payload_js + src[b:]

    fails = []
    for label, old, new, want in S:
        if label == 'payload':
            continue
        got = out.count(old)
        if got != want:
            fails.append(f'  seam {label!r}: matched {got} times, expected {want}')
            continue
        out = out.replace(old, new)

    if fails:
        sys.exit('SEAM FAILURE -- index.html moved under the fork. Re-cut these:\n' + '\n'.join(fails))

    io.open(out_path, 'w', encoding='utf-8').write(out)
    print(f'ok  {out_path}  {len(out):,} chars  ({len(S)-1} seams applied, payload {len(payload_js):,})')


if __name__ == '__main__':
    if len(sys.argv) != 4:
        sys.exit('usage: soccer_fork.py <index.html> <soccer_D.json> <out.html>')
    build(*sys.argv[1:])
