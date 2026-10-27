// FDCUP-2026-10-27 probe v2: per-competition listing endpoints
'use strict';
const AK = 'FhMFpcPWXMeyZxOx', UA = { 'user-agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/129.0 Safari/537.36' };
const base = 'https://sbapi.nj.sportsbook.fanduel.com/api/', q = `&_ak=${AK}&timezone=America%2FNew_York`;
const get = async u => { const r = await fetch(base + u + q, { headers: UA }); return r.ok ? r.json() : { status: r.status }; };
const show = (lab, j) => { const ev = Object.values((j.attachments || {}).events || {}).filter(e => / v /.test(e.name)); console.log(lab, j.status || 'ok', 'events', ev.length, ev.slice(0, 12).map(e => e.name + ' ' + e.openDate.slice(5, 16)).join(' | ')); };
(async () => {
  const C = { pokal: 11458113, rey: 12801, efl: 2134 };
  for (const [k, id] of Object.entries(C)) {
    for (const u of [`competition-page?competitionId=${id}&eventTypeId=1`, `content-managed-page?page=COMPETITION&competitionId=${id}`,
                     `content-managed-page?page=SPORT&eventTypeId=1&competitionId=${id}`, `content-managed-page?page=CUSTOM&customPageId=${k}`])
      show(k + ' ' + u.split('?')[0] + ' ' + u.split('?')[1].slice(0, 45), await get(u));
  }
  for (const slug of ['german-dfb-pokal', 'spanish-copa-del-rey', 'english-football-league-cup', 'carabao-cup', 'efl-cup', 'soccer-cups', 'soccer-today', 'soccer-live'])
    show('slug ' + slug, await get(`content-managed-page?page=CUSTOM&customPageId=${slug}`));
  const sp = await get('content-managed-page?page=SPORT&eventTypeId=1');
  console.log('SPORT layout keys', Object.keys(sp.layout || {}), JSON.stringify(Object.values((sp.layout || {}).coupons || {}).slice(0, 3)).slice(0, 800));
  console.log('SPORT tabs', JSON.stringify(Object.values((sp.layout || {}).tabs || {}).map(t => t.title + '=' + t.id)).slice(0, 800));
})().catch(e => console.log('ERR', e));
