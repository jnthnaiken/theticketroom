// USPROBE-2026-11-07: what does understat serve a runner now? (getLeagueData returns the HTML shell since 11-06 ~22:30Z)
'use strict';
const UA = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0 Safari/537.36';
(async () => {
  const jar = {};
  const get = async (u, h = {}) => {
    const r = await fetch(u, { headers: Object.assign({ 'user-agent': UA, cookie: Object.entries(jar).map(([k, v]) => k + '=' + v).join('; ') }, h), redirect: 'follow' });
    for (const c of r.headers.getSetCookie ? r.headers.getSetCookie() : []) { const [kv] = c.split(';'); const i = kv.indexOf('='); jar[kv.slice(0, i)] = kv.slice(i + 1); }
    const t = await r.text(); return { s: r.status, t, ct: r.headers.get('content-type'), url: r.url };
  };
  const p = await get('https://understat.com/league/EPL/2026');
  console.log('league page', p.s, p.t.length, p.ct, 'cookies', Object.keys(jar));
  console.log('--- head of page ---\n' + p.t.slice(0, 2500));
  const scripts = [...p.t.matchAll(/<script[^>]*src="([^"]+)"/g)].map(m => m[1]); console.log('scripts', scripts);
  console.log('inline vars', [...p.t.matchAll(/var\s+(\w+)\s*=\s*JSON\.parse/g)].map(m => m[1]));
  for (const s of scripts) {
    const u = new URL(s, 'https://understat.com/').href; const r = await get(u);
    const hits = [...r.t.matchAll(/["'`](\/?(?:get|api)[A-Za-z]*[\w/{}$.-]*)["'`]/g)].map(m => m[1]);
    console.log('script', u, r.s, r.t.length, 'endpoints', [...new Set(hits)].slice(0, 40));
    for (const m of r.t.matchAll(/(getLeagueData|getPlayerData|getTeamData|getMatchData)[^\n]{0,200}/g)) console.log('  ctx:', m[0].slice(0, 220));
  }
  for (const path of ['/getLeagueData/EPL/2026', '/getLeagueData/EPL/2025', '/api/league/EPL/2026', '/getLeagueData?league=EPL&season=2026']) {
    const r = await get('https://understat.com' + path, { 'X-Requested-With': 'XMLHttpRequest', referer: 'https://understat.com/league/EPL/2026', accept: 'application/json, text/javascript, */*; q=0.01' });
    console.log('TRY', path, r.s, r.ct, r.t.length, JSON.stringify(r.t.slice(0, 160)));
  }
  const pl = await get('https://understat.com/player/8260'); console.log('player page', pl.s, pl.t.length, [...pl.t.matchAll(/var\s+(\w+)\s*=\s*JSON\.parse/g)].map(m => m[1]));
})().catch(e => console.log('ERR', e));
