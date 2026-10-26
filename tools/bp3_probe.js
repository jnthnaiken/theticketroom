// THREES-2026-10-25 probe: BettingPros NBA three-pointer markets, and whether past dates carry prices.
const fs = require('fs');
const src = fs.readFileSync('nba/fb_fetch.js', 'utf8');
const API = 'https://api.bettingpros.com/v3/';
const UA = { 'user-agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/129.0 Safari/537.36' };
eval(src.slice(src.indexOf('async function text'), src.indexOf('async function scrape')));
(async () => {
  const k = await key(); const H = { headers: Object.assign({ 'x-api-key': k }, UA) };
  const J = async u => (await fetch(API + u, H)).json();
  const mk = await J('markets?sport=NBA&limit=500'); const ms = mk.markets || mk;
  const th = ms.filter(m => /three|3pt|3-p/i.test(m.slug + ' ' + (m.stat || '')));
  console.log('three markets:', th.map(m => `${m.id}:${m.slug}:${m.category}:${m.period}`).join(' | '));
  for (const d of ['2026-10-25', '2025-03-12', '2024-01-10', '2022-12-01']) {
    const ev = ((await J('events?sport=NBA&date=' + d)).events || []).filter(e => e.season_type === 'REG');
    for (const m of th.slice(0, 4)) {
      const o = await J(`offers?sport=NBA&market_id=${m.id}&event_id=${ev.slice(0, 25).map(e => e.id).join(':')}&limit=25&page=1`);
      const offs = o.offers || [];
      const sel = offs.flatMap(x => x.selections || []);
      const ex = offs[0] ? JSON.stringify(offs[0]).slice(0, 700) : '';
      console.log(`${d} m${m.id} ${m.slug}: events ${ev.length}, offers ${offs.length} (pages ${(o._pagination || {}).total_pages}), selections ${sel.length}`);
      if (d === '2026-10-25' || d === '2024-01-10') console.log('   sample', ex);
    }
  }
})().catch(e => console.log('ERR', e));
