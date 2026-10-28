// POSDEF-2026-10-28: Basketball-Reference season totals -> player|team|season|pos (PG/SG/SF/PF/C) for 2016-17 .. 2026-27.
'use strict';
const fs = require('fs'); const out = []; const sleep = ms => new Promise(r => setTimeout(r, ms));
(async () => {
  for (let y = 2017; y <= 2027; y++) {
    let html = null;
    for (let t = 0; t < 4 && !html; t++) {
      const r = await fetch(`https://www.basketball-reference.com/leagues/NBA_${y}_totals.html`, { headers: { 'user-agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/129.0 Safari/537.36' } });
      console.log(y, r.status); if (r.ok) { html = await r.text(); console.log('  len', html.length, (html.match(/data-stat="pos"/g) || []).length, 'pos cells'); } else await sleep(20000);
    }
    if (!html) continue; let n = 0;
    for (const tr of html.split('<tr').slice(1)) {
      const g = k => { const m = new RegExp(`data-stat="${k}"[^>]*>(?:<a[^>]*>)?([^<]*)`).exec(tr); return m ? m[1].trim() : null; };
      const name = g('name_display') || g('player'), team = g('team_name_abbr') || g('team_id'), pos = g('pos');
      if (name && pos && team) { out.push([name, team, y - 1, pos].join('|')); n++; }
    }
    console.log(y, 'rows', n); await sleep(5000);
  }
  fs.writeFileSync('br_pos.psv', out.join('\n') + '\n');
})();
