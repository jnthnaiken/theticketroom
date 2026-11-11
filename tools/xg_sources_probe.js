// XGALT-2026-11-11 step 2: what FotMob's league stats carry (understat down since 11-02 for everyone)
'use strict';
const UA = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0 Safari/537.36';
const get = async (u) => { try { const r = await fetch(u, { headers: { 'user-agent': UA, accept: 'application/json' } }); const t = await r.text(); return { s: r.status, t }; } catch (e) { return { s: 'ERR ' + e.message, t: '' }; } };
(async () => {
  const r = await get('https://www.fotmob.com/api/data/leagues?id=47&ccode3=USA'); const j = JSON.parse(r.t);
  console.log('top keys', Object.keys(j)); const st = j.stats || {};
  console.log('stats keys', Object.keys(st));
  for (const k of Object.keys(st)) { const v = st[k]; console.log(' ', k, Array.isArray(v) ? `array(${v.length}) ` + JSON.stringify(v[0]).slice(0, 400) : JSON.stringify(v).slice(0, 400)); }
  const pl = st.players || [];
  console.log('player stat lists:', pl.map(x => x.name || x.header).join(' | '));
  for (const want of ['expected_goals', 'goals', 'expected_assists', 'mins_played', 'total_scoring_att', 'expected_goals_per_90', 'ontarget_scoring_att']) {
    const x = pl.find(p => (p.fetchAllUrl || '').includes('/' + want + '.json')); if (!x) { console.log('no list', want); continue; }
    const q = await get(x.fetchAllUrl); let L; try { L = JSON.parse(q.t); } catch (e) { console.log(want, q.s, 'unparsable'); continue; }
    const rows = (((L.TopLists || [])[0] || {}).StatList) || []; console.log(`LIST ${want}: ${q.s} ${x.fetchAllUrl} rows=${rows.length}`, JSON.stringify(rows.slice(0, 2)).slice(0, 700));
  }
  // seasons list ids for 2025/26
  console.log('seasons', JSON.stringify((st.seasonStatLinks || []).slice(0, 3)).slice(0, 500));
  // a finished match: team xG
  const m = ((j.fixtures || {}).allMatches || []).filter(x => x.status && x.status.finished).slice(-1)[0];
  if (m) { const d = await get(`https://www.fotmob.com/api/data/matchDetails?matchId=${m.id}`); console.log('matchDetails', d.s, d.t.length);
    try { const D = JSON.parse(d.t); const ts = (((D.content || {}).stats || {}).Periods || {}).All; console.log(' xG row', JSON.stringify(((ts || {}).stats || []).map(g => (g.stats || []).filter(s => /expected_goals/.test(s.key || ''))).flat().slice(0, 3)).slice(0, 500)); } catch (e) { console.log(' md parse', e.message); } }
})().catch(e => console.log('ERR', e));
