// XGFOTMOB-2026-11-11 step 3: layout of FotMob matchDetails player stats + the league fixtures list
'use strict';
const UA = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0 Safari/537.36';
const get = async (u) => JSON.parse(await (await fetch(u, { headers: { 'user-agent': UA, accept: 'application/json' } })).text());
(async () => {
  const L = await get('https://www.fotmob.com/api/data/leagues?id=47&ccode3=USA');
  const all = (L.fixtures || {}).allMatches || []; console.log('fixtures', all.length, JSON.stringify(all.find(m => m.status && m.status.finished)).slice(0, 600));
  const m = all.filter(x => x.status && x.status.finished).slice(-1)[0];
  const D = await get(`https://www.fotmob.com/api/data/matchDetails?matchId=${m.id}`);
  console.log('top', Object.keys(D), 'content', Object.keys(D.content || {}));
  console.log('header teams', JSON.stringify((D.header || {}).teams).slice(0, 400));
  console.log('general', JSON.stringify(D.general).slice(0, 500));
  const ps = (D.content || {}).playerStats || {}; const ids = Object.keys(ps); console.log('playerStats n', ids.length);
  const one = Object.values(ps).find(x => (x.stats || []).length && !x.isGoalkeeper); console.log('one player', JSON.stringify(one).slice(0, 3500));
  const sh = (D.content || {}).shotmap || {}; console.log('shotmap keys', Object.keys(sh), JSON.stringify((sh.shots || [])[0]).slice(0, 600));
  const lu = (D.content || {}).lineup || {}; console.log('starter', JSON.stringify(((lu.homeTeam || {}).starters || [])[3]).slice(0, 900)); console.log('sub', JSON.stringify(((lu.homeTeam || {}).subs || [])[0]).slice(0, 700)); console.log('situations', [...new Set((sh.shots || []).map(x => x.situation))]);
})().catch(e => console.log('ERR', e));
