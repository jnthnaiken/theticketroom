/* test_asa.js -- ASAXG-2026-08-31. The MLS xG transform, against a real ASA capture.
 *
 * fixtures/asa-2026-08-31.json is a PINNED slice of the live 2026 ASA season, pulled 2026-08-31
 * and verified byte-exact by sha256 on the way into the container
 * (4eee6c19...da90). Same discipline as fixtures/2026-08-26: a fixture a
 * later pull can overwrite is not a fixture.
 *
 * It is deliberately not a random slice. It carries:
 *   - the Anytime Goalscorer names from a real oddschecker MLS market (Inter Miami v Atlanta),
 *     which is what the join actually has to survive;
 *   - the ten heaviest penalty takers, so the npxG subtraction is exercised rather than assumed;
 *   - accented names (Suárez, Germán, Müller, Nicolás), because norm() has to strip them;
 *   - THREE ZERO-ISH PLAYERS -- Aron John (3 min), Shane Donovan (6 min), Arif Kovac (16 min,
 *     0 shots) -- because per-90 and xG-per-shot both divide, and a NaN in a PSV parses fine and
 *     then contaminates every z-score in the league group.
 */
const fs = require('fs');
const path = require('path');
const SA = require('./soccer_asa.js');

const FX = path.join(__dirname, 'fixtures', 'asa-2026-08-31.json');
const payload = JSON.parse(fs.readFileSync(FX, 'utf8'));

let fail = 0;
const chk = (label, ok, detail) => {
  console.log(`${ok ? 'PASS' : 'FAIL'}  ${label}`);
  if (!ok) { fail++; if (detail !== undefined) console.log('      ' + JSON.stringify(detail)); }
};

const { rows, skipped } = SA.rows(payload);
const by = {};
rows.forEach(r => { by[r.name] = r; });

console.log(`=== ${rows.length} rows from ${payload.all.length} ASA records `
          + `(${payload.pen.length} with penalties), ${skipped.length} skipped\n`);

/* ---- shape ------------------------------------------------------------------------- */
chk('every ASA record with a name became a row', rows.length === payload.all.length, rows.length);
chk('nothing was skipped on this fixture', skipped.length === 0, skipped);
chk('18 columns, in soccer_mock.py\'s order', SA.COLS.length === 18, SA.COLS.length);

const psv = SA.toPSV(rows);
const lines = psv.trim().split('\n');
chk('PSV has one line per row', lines.length === rows.length, lines.length);
chk('every PSV line has 18 fields', lines.every(l => l.split('|').length === 18),
  lines.map(l => l.split('|').length).filter(n => n !== 18));
chk('no header line (soccer_mock reads by position)', !/^league\|/.test(psv));

/* ---- 🚨 the npxG subtraction, which is the whole point of the file ------------------- */
/* Messi: xgoals 15.6821 all, 1.567 from 2 penalties -> npxG 14.1151 on 110 non-penalty shots. */
const messi = by['Lionel Messi'];
chk('Messi npxG = xgoals(all) - xgoals(Penalty)', messi.npxg === 14.1151, messi.npxg);
chk('...and his shots exclude the penalties (112 - 2)', messi.shots === 110, messi.shots);
chk('...and his npg excludes the penalty he scored (17 - 1)', messi.npg === 16, messi.npg);
chk('...goals stays the TOTAL, penalties included', messi.goals === 17, messi.goals);

/* A player with no penalty row must be untouched, not zeroed. */
const silvetti = by['Mateo Silvetti'];
chk('a player with no penalties keeps his full xG', silvetti.npxg === 2.1023, silvetti.npxg);
chk('...and all his shots', silvetti.shots === 27, silvetti.shots);

/* ⚠️ Nobody may end up with more npxG than xG, or negative anything. */
chk('no npxG exceeds the raw xgoals', rows.every(r => {
  const src = payload.all.find(a => (payload.players.find(p => p.player_id === a.player_id) || {}).player_name === r.name);
  return r.npxg <= (src.xgoals || 0) + 1e-9;
}), null);
chk('no negative npxG / npg / shots', rows.every(r => r.npxg >= 0 && r.npg >= 0 && r.shots >= 0),
  rows.filter(r => r.npxg < 0 || r.npg < 0 || r.shots < 0).map(r => r.name));

/* ---- 🚨 the divide-by-zero players --------------------------------------------------- */
const john = by['Aron John'];          // 3 minutes, 0 shots
const kovac = by['Arif Kovac'];        // 16 minutes, 0 shots
chk('a 3-minute player yields finite per-90s', Number.isFinite(john.npxg90) && Number.isFinite(john.xa90),
  { npxg90: john.npxg90, xa90: john.xa90 });
chk('a 0-shot player yields xGperShot 0, not NaN/Infinity', kovac.xgpershot === 0, kovac.xgpershot);
chk('NO NaN OR Infinity ANYWHERE IN THE PSV', !/NaN|Infinity/.test(psv),
  lines.filter(l => /NaN|Infinity/.test(l)));

/* ---- per-90 arithmetic --------------------------------------------------------------- */
chk('npxg90 = npxG / minutes * 90', Math.abs(messi.npxg90 - (14.1151 * 90 / 1887)) < 1e-3,
  { got: messi.npxg90, want: 14.1151 * 90 / 1887 });
chk('xGperShot = npxG / non-penalty shots', Math.abs(messi.xgpershot - (14.1151 / 110)) < 1e-3,
  messi.xgpershot);

/* ---- names, teams, and the unused columns -------------------------------------------- */
chk('accents survive the transform', !!by['Luis Suárez'] && !!by['Germán Berterame'],
  Object.keys(by).filter(n => /rez|Berter/.test(n)));
chk('team ids resolved to names', by['Lionel Messi'].team === 'Inter Miami CF', by['Lionel Messi'].team);
chk('games is 0 (ASA has none; soccer_mock never reads it)', rows.every(r => r.games === 0));
chk('xgchain is 0 (same)', rows.every(r => r.xgchain === 0));
chk('league/season stamped on every row',
  rows.every(r => r.league === 'MLS' && r.season === '2026'));

/* a row with no name must be dropped, not shipped with an unjoinable id */
const orphan = JSON.parse(JSON.stringify(payload));
orphan.all.push({ player_id: 'GHOST', team_id: 'zeQZkL1MKw', general_position: 'ST',
                  minutes_played: 900, shots: 30, goals: 9, xgoals: 8, key_passes: 5, xassists: 2 });
const o = SA.rows(orphan);
chk('a player ASA prices but cannot name is DROPPED, not shipped', o.rows.length === rows.length,
  { rows: o.rows.length, skipped: o.skipped });
chk('...and reported, not swallowed', o.skipped.length === 1 && o.skipped[0] === 'GHOST', o.skipped);

/* ---- 🚨 THE JOIN. soccer_mock.lookup()'s exact rule, against a real odds market ------- */
/* These are the Anytime Goalscorer names oddschecker showed for Inter Miami v Atlanta United on
   2026-08-31. This is the assertion that actually matters: an xG file that will not join is an
   xG file that does nothing. */
const AGS = ['Lionel Messi', 'Luis Suarez', 'German Berterame', 'Mateo Silvetti', 'Diego Rey',
             'Lovends Delinois', 'Daniel Pinter', 'Cayman Togashi', 'Arif Kovac', 'Breel Embolo',
             'Aleksey Miranchuk', 'Preston Plambeck', 'Enzo Dovlo', 'Luke Brennan', 'Sergio Santos'];

const norm = s => s.normalize('NFD').replace(/[̀-ͯ]/g, '').toLowerCase()
                   .replace(/[^a-z ]/g, ' ').replace(/\s+/g, ' ').trim();
const exact = {}, tokIx = {};
rows.forEach(r => {
  const n = norm(r.name);
  (exact[n] = exact[n] || []).push(r.name);
  const k = n.split(' ').sort().join(' ');
  (tokIx[k] = tokIx[k] || []).push(r.name);
});
function lookup(name) {
  const k = norm(name);
  if (exact[k]) return ['exact', exact[k][0]];
  const w = new Set(k.split(' '));
  const sur = k.split(' ').slice(-1)[0];
  const hits = [];
  for (const t in tokIx) {
    const ct = new Set(t.split(' '));
    if (!ct.has(sur)) continue;
    if ([...ct].every(x => w.has(x)) || [...w].every(x => ct.has(x))) hits.push(tokIx[t][0]);
  }
  return hits.length === 1 ? ['token', hits[0]] : ['MISS', null];
}
const joined = AGS.map(n => [n, ...lookup(n)]);
const hit = joined.filter(j => j[1] !== 'MISS');
console.log('\n  join: ' + hit.length + '/' + AGS.length + '  '
  + joined.filter(j => j[1] === 'MISS').map(j => 'MISS ' + j[0]).join(' · '));

chk('the accented pair joins through norm() (Suarez, German)',
  lookup('Luis Suarez')[1] === 'Luis Suárez' && lookup('German Berterame')[1] === 'Germán Berterame');
chk('at least 12 of the 15 priced names join', hit.length >= 12, hit.length);

/* ⚠️ THE THREE MISSES ARE PINNED ON PURPOSE, so a later "improvement" to the join has to say
   out loud that it changed them.
   - Diego Rey and Breel Embolo are genuinely not in ASA's 805-player 2026 season: no recorded
     MLS minutes. ANY source misses them.
   - Lovends Delinois is a real near-miss -- ASA spells him LOVENS, one letter apart in the FIRST
     name. The surname anchors, but neither token set contains the other, so lookup() refuses.
     That is UNMATCHED-2026-08-28's shape ("Toni Martinez" / "Antonio Martinez").
   All three fail in the SAFE direction: has_xg=False, and the player still prices off the market
   term. A miss never produces a WRONG-player join, which is the only failure that would matter. */
chk('Delinois is a near-miss, not a wrong-player join', lookup('Lovends Delinois')[1] === null,
  lookup('Lovends Delinois'));
chk('a name ASA has never heard of misses cleanly', lookup('Breel Embolo')[1] === null);

console.log('');
console.log(fail ? `${fail} FAILURE(S)` : 'ALL GREEN -- ASA rows are npxG-correct, NaN-free and joinable');
process.exit(fail ? 1 : 0);
