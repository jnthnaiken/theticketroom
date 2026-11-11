// FTBPROBE-2026-11-11: where FanDuel keeps "first team basket" (each team's first scorer) on an NBA event page
'use strict';
const AK = 'FhMFpcPWXMeyZxOx', UA = { 'user-agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/130.0 Safari/537.36' };
const base = 'https://sbapi.nj.sportsbook.fanduel.com/api/', q = `&_ak=${AK}&timezone=America%2FNew_York`;
const get = async u => { const r = await fetch(base + u + q, { headers: UA }); if (!r.ok) throw new Error(r.status + ' ' + u); return r.json(); };
(async () => {
  const page = await get('content-managed-page?page=CUSTOM&customPageId=nba');
  const evs = Object.values((page.attachments || {}).events || {}).filter(e => / @ /.test(e.name) && !/\(/.test(e.name));
  console.log('events', evs.length, evs.slice(0, 3).map(e => e.name + ' ' + e.openDate));
  const e = evs[0]; const first = await get(`event-page?eventId=${e.eventId}`);
  const tabs = ((first.layout || {}).tabs) || {}; console.log('tabs', JSON.stringify(Object.values(tabs).map(t => t.title + '=' + (t.seoIdentifier || t.id))).slice(0, 1500));
  const types = new Set();
  for (const m of Object.values((first.attachments || {}).markets || {})) if (/BASKET|FIRST|SCORE/.test(m.marketType || '')) console.log('default ::', m.marketType, '::', m.marketName);
  for (const t of Object.values(tabs)) {
    const slug = t.seoIdentifier || String(t.title || '').toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/(^-|-$)/g, ''); if (!slug) continue;
    try { const k = await get(`event-page?eventId=${e.eventId}&tab=${slug}`);
      for (const m of Object.values((k.attachments || {}).markets || {})) if (/BASKET|FIRST|SCORE_FIRST|TEAM_TO/.test(m.marketType || '')) { const key = slug + ' :: ' + m.marketType + ' :: ' + m.marketName; if (!types.has(key)) { types.add(key); console.log(key, '|', (m.runners || []).slice(0, 4).map(r => r.runnerName + ' ' + (((r.winRunnerOdds || {}).americanDisplayOdds || {}).americanOddsInt)).join(', ')); } }
    } catch (err) { console.log('tab', slug, String(err).slice(0, 80)); }
  }
})().catch(e => console.log('ERR', e));
