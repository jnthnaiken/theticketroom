// XGALT-2026-11-11: which free xG sources answer a GitHub runner, and with what? (understat down since 11-02 for everyone)
'use strict';
const UA = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0 Safari/537.36';
const get = async (u, h = {}) => { try { const r = await fetch(u, { headers: Object.assign({ 'user-agent': UA, accept: 'application/json, text/html;q=0.9, */*;q=0.8' }, h) }); const t = await r.text(); return { s: r.status, t, ct: r.headers.get('content-type') }; } catch (e) { return { s: 'ERR ' + e.message, t: '', ct: '' }; } };
const show = (lab, r, n = 300) => console.log(`${lab}: ${r.s} ${r.ct} ${r.t.length}B :: ${JSON.stringify(r.t.slice(0, n))}`);
(async () => {
  console.log('=== FotMob');
  let r = await get('https://www.fotmob.com/api/leagues?id=47&ccode3=USA'); show('leagues 47', r, 200);
  try { const j = JSON.parse(r.t); const st = j.stats || {}; console.log(' stats keys', Object.keys(st)); console.log(' seasonStatLinks', JSON.stringify((st.seasonStatLinks || []).slice(0, 2)).slice(0, 400));
    const pl = (st.players || []).slice(0, 8).map(x => [x.header, x.fetchAllUrl]); console.log(' player stats', JSON.stringify(pl).slice(0, 900));
    const xgu = (st.players || []).find(x => /expected_goals/.test(x.fetchAllUrl || '')); if (xgu) { const q = await get(xgu.fetchAllUrl); show(' xg list', q, 900); }
  } catch (e) { console.log(' parse', e.message); }
  r = await get('https://www.fotmob.com/api/data/leagues?id=47&ccode3=USA'); show('data/leagues 47', r, 200);
  console.log('=== Sofascore');
  r = await get('https://api.sofascore.com/api/v1/unique-tournament/17/seasons'); show('seasons', r, 300);
  r = await get('https://www.sofascore.com/api/v1/unique-tournament/17/seasons'); show('www seasons', r, 300);
  try { const sid = JSON.parse(r.t).seasons[0].id;
    const q = await get(`https://www.sofascore.com/api/v1/unique-tournament/17/season/${sid}/statistics?limit=5&order=-expectedGoals&accumulation=total&fields=expectedGoals,goals,minutesPlayed,appearances,totalShots`); show(' player xg', q, 900); } catch (e) { console.log(' sofa parse', e.message); }
  console.log('=== FBref');
  r = await get('https://fbref.com/en/comps/9/shooting/Premier-League-Stats', { accept: 'text/html' }); show('shooting', r, 200);
  console.log('  xG column present:', /data-stat="xg"|data-stat="npxg"/.test(r.t), ' rows:', (r.t.match(/data-stat="player"/g) || []).length);
  console.log('=== xgstat');
  r = await get('https://www.xgstat.com/', { accept: 'text/html' }); show('home', r, 300);
  console.log('=== understat (still?)');
  r = await get('https://understat.com/league/EPL/2026', { accept: 'text/html' }); show('understat', r, 120);
})();
