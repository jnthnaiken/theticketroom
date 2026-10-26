// THREES-2026-10-25: BettingPros market 162 (player threes made, O/U incl. alternate lines) for every regular-season
// date in [start, end] -> psv:  date|event|home|visitor|bp_pid|name|pos|team|book|line|side|cost|main
//     node pull_bp162.js 2023-10-24 2026-10-25 threes_odds.psv
const fs = require('fs');
const src = fs.readFileSync(__dirname + '/../../fb_fetch.js', 'utf8');
const API = 'https://api.bettingpros.com/v3/';
const PAGE = 'https://www.bettingpros.com/nba/odds/player-props/first-basket/';
const UA = { 'user-agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/129.0 Safari/537.36' };
eval(src.slice(src.indexOf('async function text'), src.indexOf('async function scrape')));
const sleep = ms => new Promise(r => setTimeout(r, ms));
(async () => {
  const [a, b, out] = process.argv.slice(2);
  const k = await key(); const H = { headers: Object.assign({ 'x-api-key': k }, UA) };
  const J = async u => { for (let i = 0; i < 4; i++) { try { const r = await fetch(API + u, H); if (r.ok) return r.json(); } catch (e) {} await sleep(1500 * (i + 1)); } return {}; };
  const w = fs.createWriteStream(out);
  let rows = 0, days = 0;
  for (let d = new Date(a + 'T12:00:00Z'); d <= new Date(b + 'T12:00:00Z'); d = new Date(d.getTime() + 864e5)) {
    const m = d.getUTCMonth() + 1; if (m >= 7 && m <= 9) continue;
    const ds = d.toISOString().slice(0, 10);
    const ev = ((await J('events?sport=NBA&date=' + ds)).events || []).filter(e => e.season_type === 'REG');
    if (!ev.length) continue;
    const E = {}; ev.forEach(e => { E[e.id] = e; });
    const ids = ev.map(e => e.id);
    for (let i = 0; i < ids.length; i += 25) {
      for (let page = 1; ; page++) {
        const o = await J(`offers?sport=NBA&market_id=162&event_id=${ids.slice(i, i + 25).join(':')}&limit=25&page=${page}`);
        for (const off of (o.offers || [])) {
          const e = E[off.event_id] || {};
          const p = (off.participants || [])[0] || {}; const pl = p.player || {};
          for (const s of (off.selections || [])) {
            const side = String(s.selection || s.label || '').toLowerCase().startsWith('o') ? 'O' : 'U';
            for (const bk of (s.books || [])) for (const l of (bk.lines || [])) {
              if (l.is_off || typeof l.cost !== 'number' || l.line == null) continue;
              w.write([ds, off.event_id, e.home, e.visitor, p.id, p.name, pl.position || '', pl.team || '', bk.id, l.line, side, l.cost, l.main ? 1 : 0].join('|') + '\n'); rows++;
            }
          }
        }
        const pg = o._pagination || {};
        if (!pg.total_pages || page >= pg.total_pages) break;
      }
    }
    days++; if (days % 20 === 0) console.log(ds, 'days', days, 'rows', rows);
  }
  w.end(); console.log('done days', days, 'rows', rows);
})();
