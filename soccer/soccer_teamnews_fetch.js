#!/usr/bin/env node
/* soccer_teamnews_fetch.js -- ESPN team sheets -> teamnews.psv, on a runner.
 *
 * WHY. PIPELINE open item 2: the team-news pull was hand-driven through the browser, which meant
 * the board could only pick up an XI when a person was sitting there to fetch it. Everything else
 * about soccer is browser-only because the runner cannot reach understat or oddschecker -- but it
 * CAN reach ESPN, which is how soccer_settle.js has been settling nights unattended since 08-26.
 * So the one input that changes DURING the day is the one input a workflow can fetch itself.
 *
 * ⚠️ IT REUSES soccer_live.js's PARSER, on purpose. squadOf() and goalsOf() already encode the
 * things that are easy to get wrong and were got wrong once: "Penalty - Scored" is a goal and
 * contains no "goal", "Own Goal" is not this player's goal, a shootout kick settles nothing, and
 * a roster is only trustworthy when BOTH sides published a non-empty one. Writing a second parser
 * here is the assemble_tickets.py mistake in miniature -- two implementations of one rule set,
 * drifting, disagreeing about whether a man started.
 *
 *   node soccer_teamnews_fetch.js <fixtures.json> <out teamnews.psv> [out squads.psv]
 *
 * Output is the M/R/G format soccer_teamnews.py consumes:
 *   M|match|espn_status|kickoff_iso|xi_home_count|xi_away_count
 *   R|match|club|player|XI|SUB
 *   G|match|scorer|minute
 *
 * EXIT CODES, so a workflow can tell the difference between "not yet" and "broken":
 *   0  every fixture returned a COMPLETE team sheet (both sides, non-empty)
 *   20 reached ESPN, but at least one sheet is not published yet -- come back later
 *   30 could not reach ESPN at all, or every call failed. Nothing written.
 *
 * ===================================================================================
 * SQUADAUTO-2026-09-25 -- THE THIRD ARGUMENT, AND WHY THE SQUAD PULL LIVES HERE
 * ===================================================================================
 * PIPELINE.md has carried this as a follow-up since SQUADCLUB-2026-08-28: *"the runner CAN
 * reach ESPN, so this belongs in soccer_teamnews_fetch.js alongside the XI pull rather than
 * being hand-scraped into the slate directory. Then the club label maintains itself and
 * squads.psv stops being a manual input."* It came due on 2026-09-25, the first international
 * card, where the club chip read "--" on every leg: there are no national-team sheets, so the
 * only surviving source for the label was the player's UNDERSTAT row -- his club -- and
 * `_side()` rightly refuses to place Real Madrid on a side of Türkiye v France.
 *
 * `squads.psv` is `match|team|player`, and for an international the squad roster IS the
 * national team. Same endpoint SQUADCLUB documented:
 *     .../soccer/<league>/teams/<id>/roster
 * with the two team ids taken from the summary this file already fetches.
 *
 * ⚠️ NOT THE SUMMARY'S rosters[]. That array is present and EMPTY until the sheets drop --
 * measured 0/0 on all nine fixtures nineteen hours out -- so a squad scraper built on it
 * writes a zero-row file and looks like a format change. The M/R/G rows above come from
 * rosters[] because they ARE the team sheet; the squad does not.
 *
 * 🚨 BOTH SIDES, OR NEITHER -- because squads.psv has a SECOND READER. soccer_mock's
 * WRONGCLUB-2026-08-30 drops any priced player who is in NEITHER squad (it shipped Nicolas
 * Jackson as an anchor of a game his club was not in). That gate is armed by the mere presence
 * of rows for a fixture, so a HALF-pulled fixture would read as "every man on the missing side
 * is not in the squad" and take them all off the board. So a fixture contributes rows only when
 * both sides answered with a plausible squad, and contributes NOTHING otherwise -- which leaves
 * WRONGCLUB disarmed for it, exactly as a missing file does today. Same standard squadOf()
 * already applies to the XI: both sides, non-empty.
 *
 * 🚨 AND IT NEVER WRITES AN EMPTY FILE. The workflow copies the committed slate squads.psv into
 * .work BEFORE this runs, so an empty write would CLOBBER a good file with one that disarms the
 * label and the gate. No rows means the file is left exactly as it was found -- the `_XI is
 * None` trap, same shape, third time.
 *
 * It is also CACHED, and that is not an optimisation. A 22-fixture slate rebuilding every four
 * minutes would be 44 extra ESPN calls a pass, all day, for a list that changes when a manager
 * names a squad. If squads.psv already covers every fixture on the slate, this does not call at
 * all. A squad that gains a late call-up is not a problem worth that traffic: once the sheet
 * publishes, the XI supersedes the squad label anyway (team sheet > squad roster > understat).
 */
const fs = require('fs');
const path = require('path');
const L = require(path.join(__dirname, 'soccer_live.js'));

const ESPN = 'https://site.api.espn.com/apis/site/v2/sports/soccer/';
const [, , FIX, OUT, SQOUT] = process.argv;
if (!FIX || !OUT) {
  console.error('usage: soccer_teamnews_fetch.js <fixtures.json> <teamnews.psv> [squads.psv]');
  process.exit(2);
}

/* A senior squad is twenty-odd men. This floor is what stops a stub, a placeholder or a
   half-filled response from arming WRONGCLUB: eleven is the smallest number that can field a
   side, so anything under it is not a squad whatever ESPN called it. */
const SQUAD_MIN = 11;

const fx = JSON.parse(fs.readFileSync(FIX, 'utf8'));
const matches = Object.entries(fx.matches || {});
if (!matches.length) { console.error('!! fixtures.json has no matches'); process.exit(2); }

/* Node 18+ has global fetch on every GitHub runner image in use. */
async function getJSON(url) {
  const r = await fetch(url, { headers: { 'user-agent': 'ticketroom-teamnews' } });
  if (!r.ok) throw new Error('http ' + r.status);
  return r.json();
}

/* ESPN ships a team roster as a FLAT `athletes` array for soccer and as position GROUPS
   (`athletes:[{position, items:[...]}]`) for the American sports. Read both rather than assume
   the flat one: the grouped shape would silently yield zero names, which under the both-sides
   rule above turns into "no squad rows" and a board that quietly loses its club labels again. */
function rosterNames(j) {
  const a = (j && j.athletes) || [];
  const flat = (a.length && a[0] && Array.isArray(a[0].items))
    ? a.reduce((acc, g) => acc.concat(g.items || []), [])
    : a;
  return flat.map(x => (x && (x.displayName || x.fullName)) || '').filter(Boolean);
}

/* THE CACHE, read before anything is fetched -- and it asks the SAME question the writer does,
   which is the point. "Has this fixture got rows?" is not good enough:
 *
 * 🚨 MEASURED 2026-09-25 across the 11 committed slates that carry a squads.psv. The files from
 * 2026-08-28 and 2026-08-29 have BOTH sides for every fixture and as few as TWO, THREE or FIVE
 * names on the smaller one -- team-sheet fragments, not squads. 20 fixtures like that, and
 * between them they flagged 31 priced players as "in neither squad", which is WRONGCLUB taking
 * a man off the board because a five-name list did not mention him. Alexander Sorloth, Andrea
 * Pinamonti, Giovanni Fabbian, Riccardo Sottil and Fabio Miretti are all on that list.
 *
 * Split by completeness: under a both-sides, >= SQUAD_MIN squad the flag rate is 6.28%, and it
 * is the academy and trialist names the gate exists for. Under a partial one it is 7.38% and it
 * is first-teamers. So a cache test that accepted a partial file would keep one forever, and the
 * fixtures most in need of a real squad are exactly the ones that would never get re-pulled.
 * Same predicate, both ends: a file only counts as covering a fixture if it would have been
 * written for it. */
function squadIsComplete(rows) {
  const per = new Map();
  rows.forEach(([, team]) => per.set(team, (per.get(team) || 0) + 1));
  return per.size === 2 && [...per.values()].every(n => n >= SQUAD_MIN);
}

function squadsAlreadyCover(pathname, slugs) {
  if (!pathname || !fs.existsSync(pathname)) return false;
  const byFix = new Map();
  try {
    fs.readFileSync(pathname, 'utf8').split('\n').forEach(l => {
      const c = l.split('|');
      if (c.length >= 3 && c[0]) {
        if (!byFix.has(c[0])) byFix.set(c[0], []);
        byFix.get(c[0]).push(c);
      }
    });
  } catch (e) { return false; }
  return slugs.every(s => byFix.has(s) && squadIsComplete(byFix.get(s)));
}

(async () => {
  const lines = [];
  let reached = 0, complete = 0;

  const sqLines = [];
  let sqFix = 0, sqShort = 0;
  const wantSquads = !!SQOUT && !squadsAlreadyCover(SQOUT, matches.map(([s]) => s));
  if (SQOUT && !wantSquads) {
    console.log(`  squads: ${SQOUT} already covers all ${matches.length} fixture(s) -- not re-pulling`);
  }

  for (const [slug, m] of matches) {
    const [lg, ev] = m.espn || [];
    if (!lg || !ev) { console.log(`  ${slug}: no espn id in fixtures.json -- skipped`); continue; }

    let sum = null, sb = null;
    try {
      sum = await getJSON(`${ESPN}${lg}/summary?event=${ev}`);
      reached++;
    } catch (e) {
      console.log(`  ${slug}: summary unreachable (${e.message})`);
      continue;
    }
    try {
      const ymd = String(fx.date || '').replace(/-/g, '');
      sb = await getJSON(`${ESPN}${lg}/scoreboard?dates=${ymd}`);
    } catch (e) { /* status is a nice-to-have; the roster is the point */ }

    const evRow = ((sb && sb.events) || []).find(e => String(e.id) === String(ev));
    const status = (((evRow || {}).status || {}).type || {}).name || 'STATUS_SCHEDULED';
    const ko = (evRow || {}).date || '';

    /* THE SHARED PARSER. squadOf() decides `complete` -- both sides, non-empty -- and that is
       the same standard soccer_teamnews.py uses to decide whether ABSENT may be asserted. */
    const sq = L.squadOf(sum);
    const rosters = (sum && sum.rosters) || [];
    let xiH = 0, xiA = 0;
    rosters.forEach((r, i) => {
      const n = ((r.roster) || []).filter(p => p.starter).length;
      if (i === 0) xiH = n; else if (i === 1) xiA = n;
    });

    lines.push(['M', slug, status, ko, xiH, xiA].join('|'));

    rosters.forEach(r => {
      const club = ((r.team || {}).displayName) || ((r.team || {}).abbreviation) || '';
      ((r.roster) || []).forEach(p => {
        const nm = (p.athlete || {}).displayName;
        if (!nm) return;
        lines.push(['R', slug, club, nm, p.starter ? 'XI' : 'SUB'].join('|'));
      });
    });

    L.goalsOf(sum).forEach(g => {
      lines.push(['G', slug, g.name, g.min].join('|'));
    });

    if (sq.complete) complete++;
    console.log(`  ${slug}: ${status}  XI ${xiH}+${xiA}  squad ${Object.keys(sq.all).length}` +
                `  goals ${L.goalsOf(sum).length}${sq.complete ? '' : '   <-- SHEET NOT PUBLISHED'}`);

    /* SQUADAUTO-2026-09-25 -- see the header. The ids come out of the summary already fetched
       above, so this costs two calls per fixture and only on a slate whose squads are not
       already on disk. A roster failure NEVER changes this script's exit code: the squad is the
       club label, the exit code is about the team SHEET, and conflating them would turn a
       cosmetic miss into a build failure. */
    if (wantSquads) {
      const comps = (((sum || {}).header || {}).competitions || [])[0] || {};
      const ids = (comps.competitors || []).map(c => ((c || {}).team || {}).id).filter(Boolean);
      const sides = [];
      for (const id of ids) {
        try {
          const j = await getJSON(`${ESPN}${lg}/teams/${id}/roster`);
          sides.push({ team: ((j.team || {}).displayName) || '', names: rosterNames(j) });
        } catch (e) { sides.push(null); }
      }
      const ok = ids.length === 2 && sides.length === 2 &&
                 sides.every(s => s && s.team && s.names.length >= SQUAD_MIN);
      if (ok) {
        sides.forEach(s => s.names.forEach(n => sqLines.push([slug, s.team, n].join('|'))));
        sqFix++;
      } else {
        sqShort++;
        console.log(`    squad roster incomplete (${sides.map(s => (s ? s.names.length : 'x')).join('+') || 'no ids'})` +
                    ` -- no squad rows for this fixture, so WRONGCLUB stays disarmed on it`);
      }
    }
  }

  if (!reached) {
    console.error('!! could not reach ESPN for any fixture -- writing nothing');
    process.exit(30);
  }

  fs.writeFileSync(OUT, lines.join('\n') + '\n');
  console.log(`wrote ${OUT}: ${lines.length} rows, ${complete}/${matches.length} sheets complete`);

  /* ⚠️ NEVER AN EMPTY SQUAD FILE. The workflow has already copied the committed slate squads.psv
     into place, so writing zero rows here would replace a good file with one that disarms both
     the club label and WRONGCLUB. Nothing learned means nothing written. */
  if (wantSquads) {
    if (sqLines.length) {
      fs.writeFileSync(SQOUT, sqLines.join('\n') + '\n');
      console.log(`wrote ${SQOUT}: ${sqLines.length} roster names across ${sqFix} fixture(s)` +
                  (sqShort ? `, ${sqShort} skipped for an incomplete roster` : ''));
    } else {
      console.log(`  squads: nothing usable pulled -- ${SQOUT} left as it was found`);
    }
  }

  /* ⚠️ 20 IS NOT AN ERROR. Football XIs publish about an hour before kickoff, and a slate with
     staggered kickoffs is PARTIALLY published for the whole gap between them. The draft must not
     run on that -- an XI filter applied while one sheet is missing deletes that match from the
     board entirely. The caller comes back. */
  process.exit(complete === matches.length ? 0 : 20);
})().catch(e => {
  console.error('!! ' + (e && e.message ? e.message : String(e)));
  process.exit(30);
});
