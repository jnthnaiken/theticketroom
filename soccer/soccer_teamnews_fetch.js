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
 *   node soccer_teamnews_fetch.js <fixtures.json> <out teamnews.psv>
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
 */
const fs = require('fs');
const path = require('path');
const L = require(path.join(__dirname, 'soccer_live.js'));

const ESPN = 'https://site.api.espn.com/apis/site/v2/sports/soccer/';
const [, , FIX, OUT] = process.argv;
if (!FIX || !OUT) {
  console.error('usage: soccer_teamnews_fetch.js <fixtures.json> <teamnews.psv>');
  process.exit(2);
}

const fx = JSON.parse(fs.readFileSync(FIX, 'utf8'));
const matches = Object.entries(fx.matches || {});
if (!matches.length) { console.error('!! fixtures.json has no matches'); process.exit(2); }

/* Node 18+ has global fetch on every GitHub runner image in use. */
async function getJSON(url) {
  const r = await fetch(url, { headers: { 'user-agent': 'ticketroom-teamnews' } });
  if (!r.ok) throw new Error('http ' + r.status);
  return r.json();
}

(async () => {
  const lines = [];
  let reached = 0, complete = 0;

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
  }

  if (!reached) {
    console.error('!! could not reach ESPN for any fixture -- writing nothing');
    process.exit(30);
  }

  fs.writeFileSync(OUT, lines.join('\n') + '\n');
  console.log(`wrote ${OUT}: ${lines.length} rows, ${complete}/${matches.length} sheets complete`);

  /* ⚠️ 20 IS NOT AN ERROR. Football XIs publish about an hour before kickoff, and a slate with
     staggered kickoffs is PARTIALLY published for the whole gap between them. The draft must not
     run on that -- an XI filter applied while one sheet is missing deletes that match from the
     board entirely. The caller comes back. */
  process.exit(complete === matches.length ? 0 : 20);
})().catch(e => {
  console.error('!! ' + (e && e.message ? e.message : String(e)));
  process.exit(30);
});
