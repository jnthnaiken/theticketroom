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
 *        [--teamnews teamnews.json] [--now <UTC minutes past midnight>]
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

const now = flag('--now') != null ? Number(flag('--now')) : null;
if (now == null || !isFinite(now)) { console.error('!! --now is required (UTC minutes past midnight)'); process.exit(2); }
const koOf = g => { const v = (D.meta.ko || {})[String(g)]; return v == null ? null : Number(v); };

let repriced = 0, frozenPrice = 0;
Object.keys(D.players).forEach(n => {
  const p = D.players[n], s = byName[n];
  if (!s) return;
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
  /* XIPARTIAL-2026-08-28. soccer_teamnews.py already records, per match, whether the sheet is
     COMPLETE (`trusted`: eleven starters a side) and maps every classified player to his match.
     Both facts were being thrown away here: the XI collapsed to a flat name set and was applied
     to the whole slate, so one unpublished sheet meant either wait (the old workflow's rc=20) or
     delete that match from the board. Neither is right. Scope the filter to the matches that
     HAVE published, and leave the rest alone. */
  const TRUST = tn.trusted || {};
  const slugOf = n => XI[n] || BENCH[n] || ABSENT[n] || null;
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
  xi = SD.nameSet(Object.keys(XI));
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

const out = r.tickets.map(t => ({
  kind: t.kind,
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
