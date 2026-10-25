/* TRIPPROBE-2026-10-24: owner away 10-28..11-10 with his only computer. What can the GitHub runner reach for
   soccer + football inputs without a browser? Prints a report; the workflow saves it to soccer-data:trip/probe.txt. */
const UA = { 'user-agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/129.0 Safari/537.36',
             'accept': 'text/html,application/json;q=0.9,*/*;q=0.8', 'accept-language': 'en-US,en;q=0.9' };
async function get(u, h) { try { const r = await fetch(u, { headers: Object.assign({}, UA, h || {}) }); const t = await r.text(); return [r.status, t]; } catch (e) { return ['ERR ' + String(e).slice(0, 80), '']; } }
function line(k, s, t, extra) { console.log(`${k.padEnd(34)} ${String(s).padEnd(6)} len=${t.length} ${extra || ''}`); }
const API = 'https://api.bettingpros.com/v3/';
const PAGE = 'https://www.bettingpros.com/nba/odds/player-props/first-basket/';
async function text(u) { const r = await fetch(u, { headers: UA }); if (!r.ok) throw new Error(r.status + ' ' + u); return r.text(); }

async function key_() {
  if (process.env.BP_KEY) return process.env.BP_KEY;
  const html = await text(PAGE);
  const srcs = new Set();
  for (const m of html.matchAll(/(?:src|href)="([^"]+\.m?js[^"]*)"/g)) srcs.add(new URL(m[1], PAGE).href);
  const queue = [...srcs], seen = new Set(), cands = new Set();
  while (queue.length && seen.size < 200) {
    const u = queue.shift(); if (seen.has(u)) continue; seen.add(u);
    let t; try { t = await text(u); } catch (e) { continue; }
    for (const m of t.matchAll(/["'`](\/?[\w\-./]+\.m?js)["'`]/g)) {
      try { const v = new URL(m[1], u).href; if (/bettingpros/.test(v) && !seen.has(v)) queue.push(v); } catch (e) {}
    }
    const re = /x-api-key|apikey|api_key|apiKey/ig; let m;
    while ((m = re.exec(t))) {
      for (const x of (t.slice(Math.max(0, m.index - 400), m.index + 400).match(/[A-Za-z0-9_\-]{24,64}/g) || []))
        if (/[0-9]/.test(x) && /[A-Z]/.test(x) && /[a-z]/.test(x)) cands.add(x);
    }
  }
  for (const c of cands) {
    const r = await fetch(API + 'events?sport=NBA&date=2026-01-15', { headers: Object.assign({ 'x-api-key': c }, UA) });
    if (r.status === 200) return c;
  }
  throw new Error(`no key (${seen.size} scripts, ${cands.size} candidates)`);
}


(async () => {
  let key = null; try { key = await key_(); console.log('BettingPros key: found'); } catch (e) { console.log('key ' + e); }
  const H = { 'x-api-key': key };
  // ---- BettingPros soccer: which leagues, which markets
  for (const [sp, d] of [['SOCCER', '2026-10-25'], ['SOCCER', '2026-10-24'], ['NFL', '2026-10-25']]) {
    const [s, t] = await get(API + 'events?sport=' + sp + '&date=' + d, H);
    try { const j = JSON.parse(t); console.log(`BP ${sp} ${d}: ${j.events.length} events; keys ${Object.keys(j.events[0] || {}).join(',')}`);
      for (const e of j.events.slice(0, 40)) console.log('   ', e.id, e.league || e.league_id || e.competition || '', e.home, 'v', e.visitor, e.scheduled);
    } catch (e) { console.log('BP', sp, s, t.slice(0, 200)); }
  }
  for (const sp of ['SOCCER', 'NFL']) {
    const [s, t] = await get(API + 'markets?sport=' + sp + '&limit=500', H);
    try { const j = JSON.parse(t); const ms = j.markets || j; console.log(`BP markets ${sp}: ${ms.length}; keys ${Object.keys(ms[0] || {}).join(',')}`);
      for (const m of ms) { const s_ = JSON.stringify(m); if (/goal|scor|touchdown|anytime|first|total/i.test(s_)) console.log('   ', s_.slice(0, 220)); }
    } catch (e) { console.log('BP markets', sp, s, t.slice(0, 300)); }
  }
  // ---- FanDuel sbapi: soccer + NFL pages, what market types
  for (const [k, u] of [['FD EPL', 'https://sbapi.nj.sportsbook.fanduel.com/api/content-managed-page?page=CUSTOM&customPageId=epl&_ak=FhMFpcPWXMeyZxOx'],
                         ['FD soccer', 'https://sbapi.nj.sportsbook.fanduel.com/api/content-managed-page?page=SPORT&eventTypeId=1&_ak=FhMFpcPWXMeyZxOx'],
                         ['FD NFL', 'https://sbapi.nj.sportsbook.fanduel.com/api/content-managed-page?page=CUSTOM&customPageId=nfl&_ak=FhMFpcPWXMeyZxOx']]) {
    const [s, t] = await get(u);
    try { const j = JSON.parse(t); const ev = Object.values((j.attachments || {}).events || {}); const mk = Object.values((j.attachments || {}).markets || {});
      const types = {}; mk.forEach(m => types[m.marketType] = (types[m.marketType] || 0) + 1);
      console.log(`${k}: ${s} events=${ev.length} markets=${mk.length} types=${JSON.stringify(types).slice(0, 400)}`);
      console.log('   sample events:', ev.slice(0, 6).map(e => e.eventId + ' ' + e.name + ' ' + (e.competitionId || '')).join(' | '));
      if (ev[0]) { const [s2, t2] = await get(`https://sbapi.nj.sportsbook.fanduel.com/api/event-page?_ak=FhMFpcPWXMeyZxOx&eventId=${ev[0].eventId}&tab=all`);
        try { const j2 = JSON.parse(t2); const mk2 = Object.values((j2.attachments || {}).markets || {}); const ty2 = {}; mk2.forEach(m => ty2[m.marketType + '|' + m.marketName] = 1);
          console.log(`   event-page ${ev[0].name}: ${s2} markets=${mk2.length} :: ${Object.keys(ty2).filter(x => /GOAL|SCOR|TOUCHDOWN|TD|TOTAL|BOTH/i.test(x)).slice(0, 30).join(' ; ')}`); } catch (e) { console.log('   event-page', s2, t2.slice(0, 200)); } }
    } catch (e) { console.log(k, s, t.slice(0, 200)); }
  }
  const [us, ut] = await get('https://understat.com/getLeagueData/EPL/2026', { 'X-Requested-With': 'XMLHttpRequest', referer: 'https://understat.com/league/EPL/2026' });
  let n = '-'; try { n = JSON.parse(ut).players.length; } catch (e) {}
  console.log('understat getLeagueData + XHR header:', us, 'players=' + n);
})();
