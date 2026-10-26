// FDLADDER-2026-10-26 probe: FanDuel NBA threes markets (main + alternate "X+ made threes" ladders)
'use strict';
const AK = 'FhMFpcPWXMeyZxOx', UA = { 'user-agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/129.0 Safari/537.36' };
(async () => {
  const base = 'https://sbapi.nj.sportsbook.fanduel.com/api/', q = `&_ak=${AK}&timezone=America%2FNew_York`;
  const j = await (await fetch(`${base}content-managed-page?page=CUSTOM&customPageId=nba${q}`, { headers: UA })).json();
  const evs = Object.values((j.attachments || {}).events || {}).filter(e => / @ /.test(e.name));
  console.log('events', evs.length, evs.slice(0, 12).map(e => e.eventId + ' ' + e.name + ' ' + e.openDate).join(' | '));
  const ev = evs.find(e => Date.parse(e.openDate) > Date.now()) || evs[0];
  for (const tab of ['', 'player-threes', 'player-points', 'threes', 'popular']) {
    const r = await fetch(`${base}event-page?eventId=${ev.eventId}${tab ? '&tab=' + tab : ''}${q}`, { headers: UA });
    if (!r.ok) { console.log('tab', tab, r.status); continue; }
    const k = await r.json(), mk = Object.values((k.attachments || {}).markets || {});
    if (tab === '') console.log('TABS', JSON.stringify(Object.values((k.layout || {}).tabs || {}).map(t => t.title + '=' + (t.seoIdentifier || t.id))));
    const th = mk.filter(m => /three/i.test(m.marketName + m.marketType));
    console.log('tab', tab, 'markets', mk.length, 'threes', th.length, th.slice(0, 40).map(m => m.marketType + '/' + m.marketName + '(' + (m.runners || []).length + ')').join(' ; ').slice(0, 2500));
    if (th.length) console.log('  SAMPLE', JSON.stringify(th.slice(0, 2).map(m => ({ t: m.marketType, n: m.marketName, r: (m.runners || []).slice(0, 4).map(r => [r.runnerName, r.handicap, ((r.winRunnerOdds || {}).americanDisplayOdds || {}).americanOddsInt]) }))));
  }
})().catch(e => console.log('ERR', e));
