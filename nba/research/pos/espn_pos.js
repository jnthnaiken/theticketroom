// POSDEF-2026-10-28: every NBA game's starters with ESPN's listed position (PG/SG/SF/PF/C), for the
// "position the opponent gives up the first basket to" test. node espn_pos.js 2016-10-20 2026-10-27 out.jsonl
'use strict';
const fs = require('fs');
const B = 'https://site.api.espn.com/apis/site/v2/sports/basketball/nba/';
const sleep = ms => new Promise(r => setTimeout(r, ms));
async function get(u, tries = 4) {
  for (let i = 0; i < tries; i++) {
    try { const r = await fetch(u); if (r.ok) return await r.json(); } catch (e) {}
    await sleep(800 * (i + 1));
  }
  return null;
}
(async () => {
  const [a, b, out] = process.argv.slice(2);
  const done = new Set();
  try { for (const l of fs.readFileSync(out, 'utf8').split('\n')) if (l) done.add(JSON.parse(l).id); } catch (e) {}
  const days = []; for (let d = new Date(a + 'T12:00:00Z'); d <= new Date(b + 'T12:00:00Z'); d = new Date(+d + 864e5)) days.push(d.toISOString().slice(0, 10));
  const evs = [];
  for (let i = 0; i < days.length; i += 12) {
    const res = await Promise.all(days.slice(i, i + 12).map(async d => [d, await get(B + `scoreboard?dates=${d.replace(/-/g, '')}&limit=50`)]));
    for (const [d, j] of res) for (const e of (j && j.events) || []) {
      const st = (((e.status || {}).type) || {}).completed; const sea = (e.season || {}).type;
      if (st && (sea === 2 || sea === 3)) evs.push([d, e.id]);
    }
  }
  console.log('games', evs.length, 'already', done.size);
  const todo = evs.filter(x => !done.has(x[1])); let n = 0;
  for (let i = 0; i < todo.length; i += 10) {
    const res = await Promise.all(todo.slice(i, i + 10).map(async ([d, id]) => [d, id, await get(B + `summary?event=${id}`)]));
    const lines = [];
    for (const [d, id, j] of res) {
      if (!j) continue;
      const teams = {}, comp = ((j.header || {}).competitions || [])[0] || {};
      for (const c of comp.competitors || []) teams[c.homeAway] = (c.team || {}).abbreviation;
      const st = {};
      for (const tp of ((j.boxscore || {}).players) || []) {
        const ab = (tp.team || {}).abbreviation; st[ab] = [];
        for (const s of tp.statistics || []) for (const at of s.athletes || []) if (at.starter)
          st[ab].push([(at.athlete || {}).displayName, (((at.athlete || {}).position) || {}).abbreviation || '', (at.athlete || {}).id]);
      }
      lines.push(JSON.stringify({ id, date: d, home: teams.home, away: teams.away, starters: st })); n++;
    }
    if (lines.length) fs.appendFileSync(out, lines.join('\n') + '\n');
    if (i % 500 === 0) console.log(i, '/', todo.length);
  }
  console.log('wrote', n);
})();
