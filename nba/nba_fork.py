#!/usr/bin/env python3
"""nba_fork.py -- build nba/index.html from the LIVE index.html by named seam replacement. FIRSTBASKET-2026-10-17.

The basketball room is the football room's fork, one sport over: every baseball->basketball difference
is a NAMED SEAM (an exact string that must appear an exact number of times), so when index.html moves
underneath this file the build FAILS and names the seam instead of publishing a half-baseball page.
Read nfl_fork.py's docstring -- the rules there are the rules here. This file never writes index.html.

    python3 nba_fork.py <index.html> <nba_D.json> <out.html>

WHAT IS DIFFERENT FROM FOOTBALL
  * One product: ⚡ Tip-Off, first-basket singles (kind 'fb', nba_payload.py). They render in the special
    slot (where football shows 🏁 Opening Drive), horizontal, from D.tickets. No Red Zone / builder slips.
  * A first-basket leg is decided the moment anyone makes a field goal, not at the final buzzer. The
    'fb-decided' seam lets gradeTicket() settle a leg whose ftd1 is already FALSE, so a lost pick reads lost
    two minutes into the game instead of pending for two hours.
  * The live loop is nba_live.js (ESPN basketball): first field goal -> ftd1, starters -> confirmed,
    did-not-play -> void.
"""
import json, sys

from nba_live_seams import live_seams, LIVE_SEAM_COUNT, LIVELOOP_NEW

EXPECT_SEAMS = 82 + LIVE_SEAM_COUNT  # ANCHORCARDS-2026-10-24 +2 (anchors-as-builder, lunch-section-off)  # nfl_fork's 70 + fb-decided-push/-fin (FBDECIDED-2026-10-17)   # 60 named + 1 payload + 3 live = 64 (SPECIALKINDS-2026-09-27 +8)  # SPORTEMOJI-2026-10-15 +2 (kemo, howto-tbadge)
                                      # (+2 SNAPSHOTKEY-2026-09-09, +3 NFLLIVE-2026-09-09,
                                      #  +1 INJEXIT-2026-10-11 'out-of-lineup')

RESEARCH = " RS_GROUPS=[['usage','The player'],['arm','The tip'],['mkt','Model & market']];\n RS_VOCAB={unit:'starter',units:'starters',verb:'scores first'};\n RS_P=function(p){return p.p_value!=null?p.p_value:null;};\n RSCOLS=[\n  {k:'_chance',l:'Chance',t:'Our chance he makes the game\\u2019s first field goal (model blended with the market).',g:'mkt',o:1,v:function(p){return p.p_value==null?null:(p.p_value*100).toFixed(1)+'%';},r:function(p){return p.p_value;},hi:1},\n  {k:'odds',l:'FanDuel',t:'FanDuel first-basket price -- the one we post and grade at.',g:'mkt',o:1,v:function(p){return p.odds==null?null:oStr(p.odds);},r:function(p){return p.odds==null?null:rsImp(p.odds);},hi:1},\n  {k:'_fair',l:'Fair',t:'What our chance says the price should be.',g:'mkt',o:1,v:function(p){var f=rsFair(p);return f==null?null:oStr(f);},r:function(p){var f=rsFair(p);return f==null?null:rsImp(f);},hi:1},\n  {k:'_ev',l:'Edge',t:'Our chance against the FanDuel price. A pick needs +30%.',g:'mkt',o:1,hi:1,edge:1},\n  {k:'_mkt',l:'Market',t:'The books\\u2019 consensus chance, margin removed across the ten starters.',g:'mkt',v:function(p){return p.p_mkt==null?null:(p.p_mkt*100).toFixed(1)+'%';},r:function(p){return p.p_mkt;},hi:1},\n  {k:'_model',l:'Model',t:'Our model alone, before the market layer.',g:'mkt',v:function(p){return p.p_model==null?null:(p.p_model*100).toFixed(1)+'%';},r:function(p){return p.p_model;},hi:1},\n  {k:'pb',l:'Tip',t:'Chance his team wins the opening tip -- a jump-ball rating on each side\\u2019s usual jumper.',g:'arm',d:0,hi:1,o:1},\n  {k:'powidx',l:'Team first',t:'Chance his team makes the first field goal: the tip plus how often they score first.',g:'arm',d:0,hi:1,o:1},\n  {k:'_jmp',l:'Jumper',t:'He takes the opening tip for his team.',g:'arm',v:function(p){return p.jumper?'\\u2b55 yes':'';},r:function(p){return p.jumper?1:0;},txt:1},\n  {k:'_share',l:'Share',t:'His share of his team\\u2019s first basket when they score first.',g:'usage',v:function(p){return p.zonev==null?null:Math.round(p.zonev*100)+'%';},r:function(p){return p.zonev;},hi:1},\n  {k:'hh',l:'Early shots',t:'His share of his team\\u2019s shots in the first five minutes (recent starts, weighted).',g:'usage',d:0,hi:1,o:1},\n  {k:'la',l:'First shot',t:'How often he takes his team\\u2019s first shot of the game.',g:'usage',d:0,hi:1,o:1},\n  {k:'_fg',l:'FG%',t:'His field-goal percentage, recent games weighted.',g:'usage',v:function(p){return p.fgp==null?null:(p.fgp*100).toFixed(0)+'%';},r:function(p){return p.fgp;},hi:1},\n  {k:'basis_games',l:'Starts',t:'Career starts behind his numbers.',g:'usage',d:0,hi:1},\n  {k:'bhand',l:'Pos',t:'Position.',g:'usage',txt:1},\n  {k:'_opp',l:'Opponent',t:'Tonight\\u2019s opponent.',g:'arm',o:1,v:function(p){return (p.opp&&p.opp[0])||null;},r:function(p){return (p.opp&&p.opp[0])||'';},txt:1}\n ];"


def seams(payload_js):
    S = []
    def add(label, old, new, n=1):
        """n = how many times this string is expected (see nfl_fork.py)."""
        S.append((label, old, new, n))

    add('payload', '__PAYLOAD__', payload_js)
    # Every seam below carries nfl_fork.py's label and source string; only the replacement is basketball.
    # Comments on WHY each seam exists live in nfl_fork.py under the same label.
    add('dinger-idle', ' const closed=\'<div class="closed">\'+(D.tickets.some(t=>t.kind===\'dinger\'&&t.final)?\'⚾ This one’s already rounded the bases. Fresh swing tomorrow.\':\'⚾ The Dinger’s still in the dugout — nobody’s called its name yet. Check back before first pitch.\')+\'</div>\';', ' const closed=\'<div class="closed">\'+(D.tickets.some(t=>t.kind===\'fb\')?\'⚡ Tonight’s first baskets are in the books. New picks tomorrow.\':\'⚡ No first-basket pick yet — it posts once the first-basket prices and the starting fives are up. Check back before tip.\')+\'</div>\';')
    add('title', '<title>The Baseball Room</title>', '<title>The Basketball Room</title>')
    add('eyebrow', 'eyebrow">Home-Run Props · ', 'eyebrow">First Basket · ')
    add('eyebrow-tail', ' · Kasper blend + matchup</div>', ' · tip-off model + market</div>')
    add('tagline', '“Every strike brings me closer to the next home run.”<span class="cite">— Babe Ruth</span>', '“The strength of the team is each individual member. The strength of each member is the team.”<span class="cite">— Phil Jackson</span>')
    add('chips', "const chips=[['Pitcher',(p.phr9!=null?Math.max(0,Math.min(100,Math.round((p.phr9-0.70)/0.60*100))):'—')],['POWER',(p.powidx!=null?p.powidx:'—')],['Model',p.TOTAL!=null?Math.round(p.TOTAL):'—'],['Zone',fmt(p.zonev)],['Park','×'+p.wf],['Hit rate',hitPct(p.TOTAL)],['House',houseOdds(p.TOTAL)]];", "const chips=[['Model',p.khr!=null?p.khr.toFixed(1)+'%':'—'],['Tip',(p.pb!=null?p.pb+'%':'—')],['Team first',(p.powidx!=null?p.powidx+'%':'—')],['Share',(p.zonev!=null?Math.round(p.zonev*100)+'%':'—')],['Early shots',(p.hh!=null?p.hh+'%':'—')],['First shot',(p.la!=null?p.la+'%':'—')]];")
    add('homered', '⚾ homered', '🏀 scored first', 3)
    add('nohomer', '❌ no homer', '❌ not first', 2)
    add('out-of-lineup', ' — will not hit as built', ' — did not play')
    add('podds', "${p.odds?('HR '+oddsStr(p.odds)):'HR TBD'}", "${p.odds?('FB '+oddsStr(p.odds)):'FB TBD'}")
    add('sort-odds', '<option value="odds">HR odds · shortest first</option>', '<option value="odds">First-basket odds · shortest first</option>')
    add('sort-power', '<option value="power">Power · highest first</option>', '<option value="power">Team scores first · most likely</option>')
    add('sort-hr9', '<option value="hr9">Opp SP HR/9 · most homer-prone</option>', '<option value="hr9">Early shots · biggest share</option>')
    add('sort-lift', '<option value="lift">Park/weather lift · biggest</option>', '<option value="lift">Model chance · highest</option>')
    add('tonight-count', "+kc.moon+' 🥎'", "+kc.moon+' 🚀'+(kc.temple?' \\u00b7 '+kc.temple+' 🏛️':'')")   # FAVANCHOR: moons are the only bets   # BBDRAFT-2026-10-23
    add('tracker-moon', "['moon','🥎','Moonshots']", "['temple','🏛️','Garrett\u2019s Temple'],['moon','🚀','Moonshots']")   # TEMPLE-2026-10-24
    add('client-moon-badge', "kind:'moon',badge:'🚀'", "kind:'moon',badge:'🚀'", 2)
    add('mkparlay-badge', "mkParlay('moon','🚀'", "mkParlay('moon','🚀'")
    # NOTECLAMP-2026-10-24, owner: "writeups are cut off ... this should be standard by now". Baseball clamps a slip's
    # write-up to two lines; the basketball calls run a line per player, so every write-up shows in full here.
    add('tnote-unclamp', "#v-h .tnote{-webkit-line-clamp:none;overflow:visible;min-height:0}",
        "#v-h .tnote{-webkit-line-clamp:none;overflow:visible;min-height:0}\n.tnote{-webkit-line-clamp:none;line-clamp:none;overflow:visible;display:block}")
    add('sec-moonshots', "sec('lot','Moonshots',moon)", "sec('big','Garrett\u2019s Temple',D.tickets.filter(t=>t.kind==='temple').filter(match))+sec('lot','Moonshots',moon)")   # TEMPLE-2026-10-24
    add('special-count-lunch', "if(k==='dinger')return !t.final&&singleAlive(t);", "if(k==='fb')return !t.final&&singleAlive(t);")
    add('special-count-late', "if(k==='jackpot')return !t.final&&singleAlive(t);", "if(k==='late')return !t.final&&singleAlive(t);")
    add('special-sec-lunch', "const dingerLive=D.tickets.filter(t=>t.kind==='dinger'&&!t.final)", "const dingerLive=D.tickets.filter(t=>t.kind==='fb'&&!t.final)")
    add('special-sec-late', 'var L=D.tickets.filter(t=>t.kind===\'jackpot\'&&!t.final).filter(singleAlive);el.innerHTML=L.length?L.map(ticketCard).join(\'\'):\'<div class="closed">\\ud83c\\udfdf\\ufe0f No jackpot pick posted right now.</div>\';', "var L=[];el.innerHTML='';")
    add('special-css-lunch', "${t.kind==='dinger'?' lunchwide':''}", "${t.kind==='temple'?' lunchwide bigtop':''}")   # TEMPLE-2026-10-24: owner "needs to be horizontal"   # ANCHORCARDS-2026-10-24: anchors are regular cards, not the wide strip
    add('special-css-late', "${t.kind==='jackpot'?' lunchwide nightcap':''}", "${t.kind==='late'?' lunchwide nightcap':''}")
    add('special-tile-kc', 'var kc={dinger:0,jackpot:0,builder:0,moon:0,family:0};', 'var kc={fb:0,late:0,builder:0,moon:0,family:0,temple:0};')
    add('special-tile-cnt', "var cnt=kc.dinger+' ⚾ \\u00b7 '+kc.jackpot+' 🏟️ \\u00b7 '", "var cnt=''")   # FAVANCHOR: no anchor singles to count
    add('leg-hr-icon', "${fp.hr?'⚾':fp.void?", "${fp.hr?'🏀':fp.void?")
    add('stat-poolbats', "['Pool bats',D.meta.pool]", "['Starters',D.meta.pool]")
    add('pcount-bats-a', "+' priced bats'):", "+' priced starters'):")
    add('pcount-bats-b', "+' priced bats · '+pool.size", "+' priced starters · '+pool.size")
    add('legend-brick', '<span>🧱 base score</span>', '<span>🎯 model chance</span>')
    add('bbadge', '<span class="bbadge">🧱 ${p.khr!=null?p.khr.toFixed(1):\'—\'} ${lift}</span>', '<span class="bbadge">🎯 ${p.khr!=null?p.khr.toFixed(1)+\'%\':\'—\'} ${lift}</span>')
    add('legend-soft', '⚠</b> soft starter · ', '⚠</b> starter not confirmed · ')
    add('howto-order', 'Read it top to bottom: ⚾ Daily Dinger, 🏟️ Long Ball Jackpot, 🧢 Anchors, 🥎 Moonshots.', 'Read it top to bottom: ⚡ Tip-Off.')
    add('odds-allbats', '<option value="all">All bats</option>', '<option value="all">All starters</option>')
    add('odds-hint', 'Type a number per bat —', 'Type a number per starter —')
    add('kind-anchors', '<span class="ke">🧢</span><div><b>Anchors</b><span>The four bats the moons are built around, each also sold as a straight single.</span>', '<span class="ke">⚡</span><div><b>Tip-Off</b><span>First basket: the first made field goal of the game (free throws do not count). Every starter whose chance beats his FanDuel price by 30% or more, one per game, up to three a night, 1u each. If nobody clears that bar, the single best edge on the slate. No parlays.</span>')
    add('howto-tbadge', 'class="tbadge">🥎</span>', 'class="tbadge">⚡</span>')
    add('kemo', "var KEMO={dinger:'⚾',jackpot:'🏟️',builder:'🧢',moon:'🥎'};", "var KEMO={fb:'⚡',builder:'⚡',moon:'🚀',temple:'🏛️'};")
    add('tracker-builder', "['builder','🧢','Anchors']", '')
    add('sec-anchors', "sec('sug','Anchors',builder)", "sec('sug','Anchors',builder)")
    # ANCHORCARDS-2026-10-24. Owner: "can we do the anchors as smaller tickets like we do on baseball" -> "the size of
    # it. not horizontal". The ⚡ anchors leave the full-width Daily Dinger strip and render as ordinary slips in
    # baseball's own Anchors section (sec 'sug'), one card per anchor in the ticket grid. Display only: kind stays 'fb'.
    add('anchors-as-builder', "const builder=D.tickets.filter(t=>t.kind==='builder'&&!t.braced)", "const builder=D.tickets.filter(t=>t.kind==='fb'&&!t.braced)")
    add('lunch-section-off', "if(ty==='all'&&(dingerLive.length||!q)){html+=", "if(false&&ty==='all'&&(dingerLive.length||!q)){html+=")
    add('tonight-builder', "+kc.builder+' 🧢 \\u00b7 '", '')
    add('step-builder', 'Every scored bat is one row:', 'Every starter is one row:')
    add('step-players', 'Every bat that cleared the pool gate, one card each.', 'Every starter on the slate, one card each.')
    add('footer-wind', 'always verify odds, lineups, and wind before you wager.', 'always verify odds and starting lineups before you wager.')
    add('live-btn', '\\u21bb Update from MLB', '\\u21bb Update from ESPN')
    add('gcal', 'var GCAL={mu:98.398,sd:32.179,a:-2.16143,b:0.34215};', 'var GCAL=null; /* NBA: MLB-fitted calibration does not transfer. */')
    add('likely-ended', 'return g!=null&&nowETMin()>=g+240;}', 'return g!=null&&nowETMin()>=g+165;}')
    add('odds-sign', "oddsStr=o=>o?'+'+comma(o):'TBD'", "oddsStr=o=>o?((o>0?'+':'')+comma(o)):'TBD'")
    add('odds-sign-header', "(t.parlay_am?('+'+comma(t.parlay_am)):'n/a')", "(t.parlay_am?((t.parlay_am>0?'+':'')+comma(t.parlay_am)):'n/a')")
    add('live-ledger-key', "localStorage.setItem('hr_live_ledger'", "localStorage.setItem('nba_live_ledger'")
    add('odds-key', "ODDS_KEY='hr_ticket_odds'", "ODDS_KEY='nba_ticket_odds'")
    add('lock-key', "'hr_lock_'", "'nba_lock_'", 2)
    add('liveloop', 'liveUpdate(); setInterval(liveUpdate, 6*60*1000)', LIVELOOP_NEW)
    add('footer-sources', 'Sources: Kasper matchup cards, Baseball Savant (Statcast), MLB StatsAPI (schedules · HR/9 · live results), RotoWire (projected lineups), Open-Meteo (park weather), and multi-book consensus HR odds.', 'Sources: NBA play-by-play 2014-26 (the jump ball, the starters and every first field goal of 14,439 games), ESPN (starters, the opening tip and live results), and BettingPros first-basket prices — FanDuel for the price we post, the multi-book consensus as the market layer.')
    add('lg-hd-homers', '<span>conviction</span><span>homers</span>', '<span>conviction</span><span>first</span>')
    add('odds-homered', 'title="${p.hr?\'homered \\u2014 click to undo\':\'mark homered\'}">${p.hr?\'\\u26be\':\'\'}', 'title="${p.hr?\'scored first \\u2014 click to undo\':\'mark scored first\'}">${p.hr?\'\\ud83c\\udfc0\':\'\'}')
    add('kind-moonshots', '<div class="kind"><span class="ke">🥎</span><div><b>Moonshots</b><span>Two three-leg round robins per anchor, eight a night. This is the one diagrammed above.</span></div></div>', '<div class="kind"><span class="ke">🚀</span><div><b>Moonshots</b><span>Two per anchor: the anchor plus three more first-basket picks, four different games, every two-, three- and four-way combination at 0.10u (11 bets, 1.10u). An anchor\'s two moons differ by at least two legs.</span></div></div>')
    add('cal-11-base', "t:'Base score', d:'Kasper’s khr score, the base of the model.'", "t:'Model chance', d:'Our chance he makes the game’s first field goal, the books blended in.'")
    add('howto-n1', '>Babe Ruth</span>', '>Phil Jackson</span>')
    add('sec-lunch', '<div class="tsec lunch"><span class="tsech">Daily Dinger</span>', '<div class="tsec lunch"><span class="tsech">Anchors</span>')
    add('sec-nightcap', 'html+=\'<details class="pool"><summary><span class="tag">Free play</span> Long Ball Jackpot<span class="chev">&#9662;</span></summary><div class="poolbody" id="pool"></div></details>\';', "html+='';")
    add('tracker-restated', "'u risked \\u00b7 since '+esc(sn.since||'\\u2014')+'", "'u risked \\u00b7 '+(sn.restated?'restated ':'')+'since '+esc(sn.since||'\\u2014')+'")
    # LEDGERNOANCHOR-2026-10-24, owner: "remove anchors from ledger" -- anchors are no longer bets (FAVANCHOR); the
    # season box shows Moonshots only. The empty slot is a hole that tracker-holes filters out.
    add('tracker-lunch', "['dinger','⚾','Daily Dinger'],['jackpot','🏟️','Jackpot']", "")
    add('kind-lunch', '<span class="ke">⚾</span><div><b>Daily Dinger</b><span>Free play. FanDuel publishes a short list of bats each day and you pick one — this is the best model score on their list. Not a bet we place.</span>', '<span class="ke">⚡</span><div><b>Tip-Off</b><span>First basket. Our chance each starter makes his game’s first field goal: who wins the opening tip (a jump-ball rating on each team’s center), how often his team scores first, and his share of the early shots, the first shot and the makes, with the books’ prices as one more layer. We post the starters the price undersells, 1u each.</span>')
    add('kind-nightcap', '<div class="kind"><span class="ke">🏟️</span><div><b>Long Ball Jackpot</b><span>Free play. Fanatics splits a pot among everyone who picks the man who hits the <i>longest</i> homer that day — we rank park carry plus model score. Not a bet we place.</span></div></div>', '')
    add('research-cols', 'var RS_ROOM=null;', RESEARCH)
    add('slip-key', "SLIP_KEY='hr_slip'", "SLIP_KEY='nba_slip'")

    # TIPEMOJI-2026-10-17, owner: "lets do a different emoji than a basketball for the ticket emojis. keep it for
    # when they score first". ⚡ marks the Tip-Off slips (⛹️ first, owner: "thats too kiddish" -- ⚡, his pick) (badge, tracker row, tile, idle line, How To); 🏀 now means
    # only one thing on this board: he scored the first basket (homered / leg-hr-icon / odds-homered).
    # ---- NBA ONLY ------------------------------------------------------------------------
    # NBACHROME-2026-10-17, found by rendering the first build: the leg card's two badges were weather
    # (🏀 150.4 -- the score times an indoor weather factor) and baseball's 🧱 base score, the legend carried
    # rain / hot park / FORM rows that cannot happen indoors, the season box claimed a backtested record the
    # basketball ledger does not have, and the banner promised weather updates.
    add('leg-wbadge', '<span class="wbadge">${wx.emoji} ${_lt.toFixed(1)}</span>',
        "<span class=\"wbadge\">⭕ tip ${(D.players[p.name]||{}).pb!=null?(D.players[p.name]||{}).pb+'%':'—'}</span>")
    add('leg-bbadge', "<span class=\"bbadge\">🧱 ${(D.players[p.name]||{}).khr!=null?(D.players[p.name]||{}).khr.toFixed(1):'—'}</span>",
        "<span class=\"bbadge\">🎯 ${(D.players[p.name]||{}).khr!=null?(D.players[p.name]||{}).khr.toFixed(1)+'%':'—'}</span>")
    add('legend-wx', '<span>🌧️ rain · ☀️ heat · 💨 wind · 🥶 cold · 🏟 dome · ⛅ mild</span>', '')
    add('legend-park', '<span>🔥 hot park · ❄️ suppressed park</span>', '')
    add('legend-form', '<span>FORM ↑ rising · → steady · ↓ cooling</span>', '')
    add('banner-weather', 'Vegas odds move and the weather updates', 'the prices move')
    # TRACKERHOLES-2026-10-17: 'tracker-builder' empties the Anchors row, which leaves a HOLE in the defs
    # array, and drawTracker indexes defs[i][0] -- one hole threw and blanked the season box. Football never
    # had a hole (its emptied row was the last one). Drop holes before the loop.
    add('tracker-holes', "var tg=0,tw=0,tu=0,ts=0,rows='';for(var i=0;i<defs.length;i++)",
        "defs=defs.filter(Boolean);var tg=0,tw=0,tu=0,ts=0,rows='';for(var i=0;i<defs.length;i++)")
    # RECORDLINE-2026-10-17, owner: "the disclaimer on the ledger should be the same as the other boards" -- the
    # 'record-line' seam is gone; the ledger keeps index.html's own line, as football and soccer do.
    # FBDECIDED-2026-10-17: a first-basket leg is LOST the moment someone else makes a field goal
    # (nba_live.js writes ftd1=false on every other man in the game), not at the final buzzer.
    # gradeTicket() kept such a leg "not final" until isFinal(game), so a dead pick sat pending for
    # two hours. The leg now carries `dn` (decided-not) and counts as final. ftdView() has already
    # copied ftd1 into the leg's view, so _p.ftd1 is the live value. Server side, soccer_grade grades
    # only once the whole board is final, so the ledger is unaffected.
    add('fb-decided-push', "kept.push({odds:_l.odds,game:_l.game,hr:_hr});",
        "kept.push({odds:_l.odds,game:_l.game,hr:_hr,dn:(!!_l.ftd&&_p.ftd1===false)});")
    add('fb-decided-fin', "var fin=kept.every(function(x){return x.hr||isFinal(x.game);});",
        "var fin=kept.every(function(x){return x.hr||x.dn||isFinal(x.game);});")

    S.extend(live_seams())
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

    # HOWTOROOMS-2026-10-17: the How To tab body and its callout table become this room's (nba_howto.py);
    # the narrower seams that edited pieces of them drop out. Done after the count check on purpose:
    # EXPECT_SEAMS still counts the seams this file declares.
    from nba_howto import howto_seams
    S, _dropped = howto_seams(S, src)
    print(f'  how-to: replaced; superseded seams: {", ".join(_dropped) or "none"}')

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
        sys.exit('usage: nba_fork.py <index.html> <nba_D.json> <out.html>')
    build(sys.argv[1], sys.argv[2], sys.argv[3])
