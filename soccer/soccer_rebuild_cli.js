#!/usr/bin/env node
/* soccer_rebuild_cli.js -- a SAME-SLATE rebuild that cannot re-draft a placed bet.
 *
 * WHY THIS EXISTS, and it is the single most important thing about running the soccer board on a
 * cron. regen15.py's rule, in its own words: "a same-slate rebuild ALWAYS preserves the prior
 * draft ... so a live, confirmed board is never re-drafted out from under a placed bet." That
 * rule exists because the baseball board once force-re-drafted a confirmed 07-09 board and
 * swapped a bet leg. Soccer has had no equivalent because soccer has had no scheduled build --
 * every board was hand-forked once and left alone.
 *
 * The moment a workflow rebuilds every few minutes, a fresh `draft()` each pass is exactly that
 * bug: prices drift all afternoon, so the draft moves, and a slip someone backed at 14:00 is
 * quietly gone at 14:05.
 *
 * So a rebuild does NOT re-draft. It takes the PRIOR board, refreshes what is knowable (prices,
 * scores, team news), and runs SoccerDraft.redraft() -- the same function the browser runs --
 * which freezes anything CONFLOCK has locked, mints nothing past its own kickoff, and repairs
 * open slips leg by leg.
 *
 *   node soccer_rebuild_cli.js <prior board.json> <scored.json> <out tickets.json> \
 *        [--teamnews teamnews.json] [--now <minutes past midnight UTC OF THE SLATE DATE>]
 *
 * ⚠️ SLATECLOCK-2026-08-31 -- `--now` IS SLATE-RELATIVE, NOT WALL-CLOCK, and may exceed 1440.
 * It is on the same basis as `kickoff` in fixtures.json, which soccer_payload's et_dt() defines
 * as minutes past midnight UTC OF THE SLATE DATE. MLS kicks off at 00:30Z = 1470. Omit the flag
 * and this file computes it from the real clock and the prior board's own meta.date, which is
 * what the workflow now does; pass it only from a test or a hand run, where it has always meant
 * this.
 *
 * There is no first-build path here on purpose: with no prior board there is nothing to preserve,
 * and soccer_draft_cli.js is the right tool. The workflow picks between them.
 */
const fs = require('fs');
const path = require('path');
const SD = require(path.join(__dirname, 'soccer_draft.js'));

const args = process.argv.slice(2);
const flag = (n) => { const i = args.indexOf(n); return i >= 0 ? args[i + 1] : null; };
const pos = args.filter((a, i) => !a.startsWith('--') && !(i > 0 && String(args[i - 1]).startsWith('--')));
const [PRIOR, SCORED, OUT] = pos;
if (!PRIOR || !SCORED || !OUT) {
  console.error('usage: soccer_rebuild_cli.js <prior.json> <scored.json> <tickets.json> [--teamnews f] [--now m]');
  process.exit(2);
}

const D = JSON.parse(fs.readFileSync(PRIOR, 'utf8'));
const scored = JSON.parse(fs.readFileSync(SCORED, 'utf8'));
const tnPath = flag('--teamnews');
const tn = tnPath && fs.existsSync(tnPath) ? JSON.parse(fs.readFileSync(tnPath, 'utf8')) : null;

if (!D.meta || !D.meta.ko || !Object.keys(D.meta.ko).length) {
  console.error('!! prior board carries no meta.ko -- it predates STAGE2 and cannot be re-drafted safely');
  process.exit(4);
}

/* ---- refresh what is knowable -----------------------------------------------------------
 * PRICES move all afternoon and the model rides them, so odds / TOTAL / blend / gate_z are
 * taken from the fresh scoring pass. Everything else about a player -- his club, his match, his
 * kickoff -- is a property of the slate and is already right on the prior board.
 *
 * ⚠️ A player who has KICKED OFF keeps his baked price. That is the baseball price freeze
 * (PRICEFREEZE-2026-08-17): once his match is underway the number he was bet at is the number
 * that grades, and repricing him would rewrite history on the card. */
const byName = {};
scored.forEach(p => { byName[p.name] = p; });

/* 🚨 SLATECLOCK-2026-08-31 -- THE CLOCK MUST BE ON THE SLATE'S BASIS, NOT THE WALL'S.
   `kickoff` is minutes past midnight UTC OF THE SLATE DATE (soccer_payload.et_dt builds it that
   way), so it legally exceeds 1440 -- MLS kicks off 00:30Z = 1470. `now` used to be wall-clock
   UTC 0..1439, straight out of the workflow's `date -u`, and MINTGUARD compares the two
   directly (`if (ko == null || now >= ko) return false`).
   Measured: with ko 1470, a slip minted identically at now=1400 (70 min BEFORE kickoff) and at
   now=60 (30 min INTO the match) -- past 1440 the guard cannot tell one from the other, ever.
   The same arithmetic the other way is a hole that was already live on the European board: after
   midnight the clock wraps and the slate does not, so at now=15 the 2026-08-31 board minted SIX
   slips into matches that had finished hours earlier. Only the graded-night skip was covering
   it, which depends on settling beating the first post-midnight build.
   soccer_draft.js is fine and is not touched -- it takes `nowUTCmin` opaquely and every test
   already passes it slate-relative. The bug was this caller manufacturing a wall-clock number. */
function slateRelativeNow(slateDate) {
  var d = new Date();
  var wall = d.getUTCHours() * 60 + d.getUTCMinutes();
  var m = /^(\d{4})-(\d{2})-(\d{2})$/.exec(String(slateDate || ''));
  if (!m) return wall;                       /* no usable slate date -> old behaviour, loudly */
  var slate = Date.UTC(+m[1], +m[2] - 1, +m[3]);
  var today = Date.UTC(d.getUTCFullYear(), d.getUTCMonth(), d.getUTCDate());
  var offDays = Math.round((today - slate) / 86400000);
  return wall + 1440 * offDays;
}
var now;
if (flag('--now') != null) {
  /* taken VERBATIM: `--now` has always meant slate-relative minutes and every test passes it
     that way (nowUTCmin: KO - 120). Do not "correct" it here or they all shift. */
  now = Number(flag('--now'));
  if (!isFinite(now)) { console.error('!! --now must be a number (minutes past slate midnight UTC)'); process.exit(2); }
} else {
  if (!D.meta || !D.meta.date) {
    console.error('!! no --now and the prior board carries no meta.date -- cannot place the clock');
    process.exit(2);
  }
  now = slateRelativeNow(D.meta.date);
  var _off = Math.round((now - (new Date().getUTCHours() * 60 + new Date().getUTCMinutes())) / 1440);
  console.log(`  clock: slate ${D.meta.date}, now ${now} min past slate midnight UTC`
              + (_off ? `  (+${_off}d past the slate date)` : ''));
}
const koOf = g => { const v = (D.meta.ko || {})[String(g)]; return v == null ? null : Number(v); };

let repriced = 0, frozenPrice = 0;
Object.keys(D.players).forEach(n => {
  const p = D.players[n], s = byName[n];
  if (!s) return;
  /* WRONGCLUB-2026-08-30. `out` is carried across BEFORE the price freeze and it only ever
     goes false->true. "Is he in this fixture's squad at all" is not a price and not a property
     of the prior board -- it is a fact the scoring pass newly learned from squads.psv, exactly
     like team news below. Without this the flag died here: soccer_mock marked Nicolas Jackson
     out, the fresh draft dropped him, and then the same-slate rebuild read `out` off the PRIOR
     payload -- where it was false -- and put an Aston Villa forward straight back on a
     Chelsea v Brighton screamer. Never cleared, so team news and OUTSQUAD keep the last word. */
  if (s.out) p.out = true;
  const ko = koOf(p.game);
  if (ko != null && now >= ko) { frozenPrice++; return; }      // his match is underway
  if (p.odds !== s.odds || p.TOTAL !== Math.round(s.TOTAL * 10) / 10) repriced++;
  p.odds = s.odds;
  p.TOTAL = Math.round(s.TOTAL * 10) / 10;
  p.baseTotal = p.TOTAL;
  p.blend = s.blend;
  p.gate_z = s.gate_z;
});

/* ---- team news ---------------------------------------------------------------------------
 * Same contract as everywhere else: absent means "no team news", and the whole priced field is
 * eligible. An EMPTY xi is a different fact and must never be treated as the first. */
let xi = null, xiMatches = null;
if (tn) {
  const XI = tn.xi || {}, BENCH = tn.bench || {}, ABSENT = tn.absent || {};
  if (!Object.keys(XI).length) {
    console.error('!! teamnews.json carries an EMPTY xi -- refusing to gate the pool to nothing');
    process.exit(3);
  }
  /* UNMATCHED-2026-08-28. A priced name that could not be joined to a published sheet is
     UNKNOWN, not benched -- soccer_teamnews.py now keeps those out of `absent` and lists them
     here. Treat them as eligible: refusing to draft a man because two spellings disagree is the
     worse error, and it already cost "Back Post" (Toni Martinez, starting) on 2026-08-28. */
  const UNM = tn.unmatched || {};

  /* XIPARTIAL-2026-08-28. soccer_teamnews.py already records, per match, whether the sheet is
     COMPLETE (`trusted`: eleven starters a side) and maps every classified player to his match.
     Both facts were being thrown away here: the XI collapsed to a flat name set and was applied
     to the whole slate, so one unpublished sheet meant either wait (the old workflow's rc=20) or
     delete that match from the board. Neither is right. Scope the filter to the matches that
     HAVE published, and leave the rest alone. */
  const TRUST = tn.trusted || {};
  const slugOf = n => XI[n] || BENCH[n] || ABSENT[n] || UNM[n] || null;
  xiMatches = {};
  Object.keys(D.players).forEach(n => {
    const sl = slugOf(n);
    if (sl && TRUST[sl] !== false) xiMatches[String(D.players[n].game)] = true;
  });
  Object.keys(D.players).forEach(n => {
    const p = D.players[n];
    if (!xiMatches[String(p.game)]) return;      /* sheet not out -> he stays 'projected' */
    p.status = XI[n] ? 'confirmed' : BENCH[n] ? 'benched' : p.status;
    if (ABSENT[n]) p.out = true;
  });
  xi = SD.nameSet(Object.keys(XI).concat(Object.keys(UNM)));
  if (Object.keys(UNM).length) console.log('  unmatched but kept draftable: ' + Object.keys(UNM).join(', '));
  console.log(`  team news: ${Object.keys(XI).length} confirmed XI, ` +
              `${Object.keys(BENCH).length} benched, ${Object.keys(ABSENT).length} out of squad` +
              `  (sheets published for ${Object.keys(xiMatches).length} match(es))`);
} else {
  console.log('  team news: none supplied -- the prior draft stands on the whole priced field');
}

const before = (D.tickets || []).map(t => t.kind + ':' + t.players.map(l => l.name).join('+')).sort();
const r = SD.redraft(D, { nowUTCmin: now, xi, xiMatches });

console.log(`  reprice: ${repriced} moved, ${frozenPrice} frozen (match underway)`);
console.log(`  redraft: ${r.locked} locked · ${r.repaired} repaired · ${r.minted} new` +
            (r.demoted && r.demoted.length ? ` · ${r.demoted.length} demoted` : '') +
            `  -> ${r.changed ? 'CHANGED' : 'unchanged'}`);
(r.demoted || []).forEach(d => console.log(`    demoted ${d.anchor}: ${d.why}`));
/* UNORPHAN-2026-08-31 replaced the reseat with a mint, so this says the new thing out loud.
   The line here used to read "A single that loses its screamers moves to the lunch/nightcap
   section instead of standing there looking like a fifth anchor" -- that rule is gone, on the
   owner's call that it was never a baseball rule. A moonless single is a builder and renders
   under Anchors, exactly as index.html:1006 says. `r.reseated` is still returned and is now
   always empty; a log line describing a deleted rule is how the next reader loses an hour.
   SHAPEREPAIR-2026-08-31 is what fills the specials now, minting one single from the FIELD into
   any empty section -- baseball's SHAPE REPAIR (index.html:2755). Worth a line because it is a
   NEW BET appearing on the board, which is exactly what the demoted/repaired lines above are
   for. */
(r.shaped || []).forEach(x => console.log(`    shape repair: no ${x.kind} on the board -> minted ${x.name}`));

/* NAMECARRY-2026-08-29 -- THE TITLE MUST TRAVEL. soccer_draft.js does REDRAFT-2026-08-18
   properly: a surviving slip keeps its own title, a repaired slip keeps it via `priorName`, and a
   dead slip's name is SPENT for the night. All of that was thrown away right here -- this object
   never carried `name`, so soccer_payload.shape_ticket re-derived every title from the ticket's
   ARRAY INDEX and titles were reassigned by POSITION on every build.
   Measured 2026-08-29: "Top Corner" was Guirassy + Edouard + Awoniyi at 11:47Z and Schick +
   Awoniyi + Tietz at 17:26Z; "Runs the Channel" moved from Guirassy's single to David's; "The
   Poacher" from David's to Boga's. That is REDRAFT-2026-08-18's own words -- "the board showed
   one ticket that had been two bets" -- with the engine's fix intact and discarded at the file
   boundary. */
const out = r.tickets.map(t => ({
  kind: t.kind,
  name: t.name,
  /* LOCKCARRY-2026-08-30. NAMECARRY's failure, one field over, and this one drops PLACED BETS.
     soccer_draft.js sets `t.locked = true` the moment CONFLOCK freezes a slip -- and it died
     right here, because this object never carried it. soccer_payload then hardcoded
     'locked': False, so every build read the board back with NO slip locked, recomputed the
     freeze from scratch, and a slip that had frozen an hour earlier was open again.
     `ticketIsLocked` opens with `if (t.locked) return true;` and calls it "a latch ... so a
     placed bet is never unwound". There was no latch. The one line that would have made it one
     was missing, so OUTSQUAD's `!p.out` clause -- correct on a slip that has NEVER locked --
     reached slips that had, and team news dropping a single leg unfroze the whole bet and
     redrafted it. Measured 2026-08-30: `locked` was 0 on all 14 builds of the day while slips
     came and went underneath live matches. */
  locked: !!t.locked,
  risk: (t.rr && t.rr.risk) || (t.kind === 'moon' ? SD.DEFAULTS.MOON_RISK : SD.DEFAULTS.SINGLE_STAKE),
  legs: t.players.map(l => ({
    name: l.name, odds: l.odds,
    match: (D.players[l.name] || {}).gmatch || String(l.game),
    TOTAL: l.total
  }))
}));
fs.writeFileSync(OUT, JSON.stringify(out, null, 1));

const after = out.map(t => t.kind + ':' + t.legs.map(l => l.name).join('+')).sort();
console.log(`  ${out.length} tickets written to ${OUT}`);
/* exit 10 = nothing moved, so the caller can skip the rest of the build and commit nothing.
   This is soccer's commit_gate: a board that did not change must not churn a commit. */
process.exit(JSON.stringify(before) === JSON.stringify(after) ? 10 : 0);
