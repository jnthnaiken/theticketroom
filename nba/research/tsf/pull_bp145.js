// TSF-2026-11-11: BettingPros market 145 "team to score first" for every regular-season date in [start, end] -> psv:
//   date|event|home|visitor|selection|participant_id|participant_name|book|cost
// Owner: "bro team to score first is the same thing, come on" -- Winter's "first team basket" is this market, and its
// price history lets the idea (bet the team NOT expected to win the tip) be backtested now.
//     node pull_bp145.js 2020-12-22 2026-11-10 tsf_odds.psv
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
  let rows = 0, days = 0, dumped = false;
  for (let d = new Date(a + 'T12:00:00Z'); d <= new Date(b + 'T12:00:00Z'); d = new Date(d.getTime() + 864e5)) {
    const m = d.getUTCMonth() + 1; if (m >= 7 && m <= 9) continue;
    const ds = d.toISOString().slice(0, 10);
    const ev = ((await J('events?sport=NBA&date=' + ds)).events || []).filter(e => e.season_type === 'REG');
    if (!ev.length) continue;
    const E = {}; ev.forEach(e => { E[e.id] = e; });
    const ids = ev.map(e => e.id);
    for (let i = 0; i < ids.length; i += 25) {
      for (let page = 1; ; page++) {
        const o = await J(`offers?sport=NBA&market_id=145&event_id=${ids.slice(i, i + 25).join(':')}&limit=25&page=${page}`);
        for (const off of (o.offers || [])) {
          if (!dumped) { console.log('SAMPLE', JSON.stringify(off).slice(0, 1500)); console.log('EVENT', JSON.stringify(E[off.event_id]).slice(0, 600)); dumped = true; }
          const e = E[off.event_id] || {}; const P = {}; (off.participants || []).forEach(p => { P[p.id] = p.name || (p.team || {}).name || ''; });
          for (const s of (off.selections || [])) {
            for (const bk of (s.books || [])) for (const l of (bk.lines || [])) {
              if (l.is_off || typeof l.cost !== 'number') continue;
              w.write([ds, off.event_id, e.home, e.visitor, s.selection || s.label || '', s.participant || '', P[s.participant] || s.label || '', bk.id, l.cost].join('|') + '\n'); rows++;
            }
          }
        }
        const pg = o._pagination || {};
        if (!pg.total_pages || page >= pg.total_pages) break;
      }
    }
    days++; if (days % 50 === 0) console.log(ds, 'days', days, 'rows', rows);
  }
  w.end(); console.log('done days', days, 'rows', rows);
})();
