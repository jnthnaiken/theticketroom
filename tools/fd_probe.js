// FDCUP-2026-10-27 probe: where does FanDuel list cup ties (DFB-Pokal, Copa del Rey, EFL Cup)?
'use strict';
const AK = 'FhMFpcPWXMeyZxOx', UA = { 'user-agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/129.0 Safari/537.36' };
const base = 'https://sbapi.nj.sportsbook.fanduel.com/api/', q = `&_ak=${AK}&timezone=America%2FNew_York`;
const get = async u => { const r = await fetch(base + u + q, { headers: UA }); return r.ok ? r.json() : { status: r.status }; };
const want = /arsenal|dortmund|frankfurt|leipzig|augsburg|bochum|gladbach|union|darmstadt|elche|espanyol|villarreal|rayo|malaga/i;
(async () => {
  const sp = await get('content-managed-page?page=SPORT&eventTypeId=1');
  const comps = Object.values((sp.attachments || {}).competitions || {});
  console.log('SPORT page events', Object.keys((sp.attachments || {}).events || {}).length, 'comps', comps.length);
  console.log('cup-like comps', comps.filter(c => /cup|pokal|copa|rey|trophy|coupe|coppa/i.test(c.name)).map(c => c.competitionId + ':' + c.name).join(', '));
  const hits = Object.values((sp.attachments || {}).events || {}).filter(e => want.test(e.name));
  console.log('SPORT hits', hits.map(e => e.eventId + ' ' + e.name + ' ' + e.openDate + ' c' + e.competitionId).join(' | '));
  for (const c of comps.filter(c => /pokal|rey|league cup|efl|carabao|football league cup|german|spanish|copa/i.test(c.name))) {
    for (const u of [`content-managed-page?page=COMPETITION&competitionId=${c.competitionId}&eventTypeId=1`, `content-managed-page?page=CUSTOM&customPageId=soccer&competitionId=${c.competitionId}`]) {
      const j = await get(u); const ev = Object.values((j.attachments || {}).events || {});
      console.log(c.name, u.split('?')[1].slice(0, 40), j.status || '', 'events', ev.length, ev.filter(e => / v /.test(e.name)).slice(0, 10).map(e => e.eventId + ' ' + e.name + ' ' + e.openDate).join(' | '));
    }
  }
  // search endpoint
  for (const t of ['Arsenal', 'Dortmund', 'Elche']) {
    const j = await get(`search?searchTerm=${t}`); console.log('search', t, j.status || '', JSON.stringify(j).slice(0, 400));
  }
})().catch(e => console.log('ERR', e));
