// FDSOCCER-2026-10-26 probe: what does FanDuel's sbapi give a GitHub runner for soccer goalscorers?
'use strict';
const AK = 'FhMFpcPWXMeyZxOx', UA = { 'user-agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/129.0 Safari/537.36' };
const want = (process.argv[2] || 'lyon').toLowerCase();
(async () => {
  for (const st of ['nj', 'ny', 'pa']) {
    const base = `https://sbapi.${st}.sportsbook.fanduel.com/api/`;
    for (const q of ['content-managed-page?page=SPORT&eventTypeId=1', 'content-managed-page?page=CUSTOM&customPageId=soccer']) {
      try {
        const r = await fetch(`${base}${q}&_ak=${AK}&timezone=America%2FNew_York`, { headers: UA });
        console.log(st, q, r.status);
        if (!r.ok) continue;
        const j = await r.json(), evs = Object.values((j.attachments || {}).events || {});
        console.log('  events', evs.length, evs.slice(0, 8).map(e => e.name + ' ' + e.openDate + ' c' + e.competitionId).join(' ; '));
        const comps = Object.values((j.attachments || {}).competitions || {}); console.log('  comps', comps.slice(0, 40).map(c => c.competitionId + ':' + c.name).join(', '));
        const ev = evs.find(e => e.name.toLowerCase().includes(want));
        if (!ev) continue;
        console.log('  HIT', JSON.stringify(ev).slice(0, 300));
        for (const tab of ['', 'goalscorers', 'goal-scorer', 'player-props', 'popular']) {
          const r2 = await fetch(`${base}event-page?eventId=${ev.eventId}${tab ? '&tab=' + tab : ''}&_ak=${AK}&timezone=America%2FNew_York`, { headers: UA });
          console.log('  event-page tab=' + tab, r2.status); if (!r2.ok) continue;
          const j2 = await r2.json(), mk = Object.values((j2.attachments || {}).markets || {});
          console.log('   tabs', JSON.stringify(((j2.layout || {}).tabs) ? Object.values(j2.layout.tabs).map(t => t.title + '=' + t.id) : []).slice(0, 600));
          console.log('   markets', mk.map(m => m.marketType + '/' + m.marketName + '(' + (m.runners || []).length + ')').join(' ; ').slice(0, 3000));
          const g = mk.find(m => /goal ?scorer|to score/i.test(m.marketName));
          if (g) console.log('   SAMPLE', JSON.stringify(g.runners.slice(0, 3)).slice(0, 1500));
        }
        return;
      } catch (e) { console.log(st, q, 'ERR', String(e).slice(0, 200)); }
    }
  }
})();
