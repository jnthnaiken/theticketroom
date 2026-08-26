const {chromium}=require('playwright');
const AT   = process.argv[2] || '2026-08-26T18:40:00Z';   // 2:40 PM ET, 20 min to kickoff
const FILE = process.argv[3] || '/home/claude/soccer/soccer.html';
const SHOT = process.argv[4] || 'clock.png';
(async()=>{
 const b=await chromium.launch();
 const ctx=await b.newContext({viewport:{width:1440,height:1400},deviceScaleFactor:2});
 await ctx.addInitScript(`(()=>{const F=new Date('${AT}').getTime(), R=Date;
   class D extends R{constructor(...a){ if(!a.length) super(F); else super(...a);} static now(){return F;}}
   window.Date=D;})();`);
 const p=await ctx.newPage();
 const errs=[];p.on('pageerror',e=>errs.push(String(e).slice(0,200)));
 const net=[];p.on('request',r=>{const u=r.url(); if(!u.startsWith('file:')) net.push(u.slice(0,110));});
 await p.goto('file://'+FILE,{waitUntil:'load'});
 await p.waitForTimeout(2500);
 const r=await p.evaluate(()=>{
  const cl=s=>(s||'').replace(/\s+/g,' ').trim();
  const kpi=[...document.querySelectorAll('#stats .kpi')].map(k=>cl(k.textContent));
  const secs=[...document.querySelectorAll('.tsech')].map(h=>cl(h.textContent));
  const chips=[...document.querySelectorAll('#ttype .tbtn')].map(h=>cl(h.textContent));
  const cards=[...document.querySelectorAll('.slip')].map(c=>({
    n:cl((c.querySelector('.tname')||{}).textContent),
    badge:cl((c.querySelector('.tbadge')||{}).textContent),
    warn:cl((c.querySelector('.owarn')||{}).textContent),
    legs:[...c.querySelectorAll('.leg')].map(l=>cl((l.querySelector('.nm')||{}).textContent)+' | '+cl((l.querySelector('.lwhere')||{}).textContent))
  }));
  return {clock:new Date().toString().slice(0,24), kpi, secs, chips, cards,
          tracker:cl((document.querySelector('#tracker')||{}).textContent).slice(0,300)};
 });
 console.log('CLOCK:', r.clock);
 console.log('ERRORS:', JSON.stringify(errs));
 console.log('NETWORK:', JSON.stringify([...new Set(net)]));
 console.log('KPI:', JSON.stringify(r.kpi));
 console.log('CHIPS:', JSON.stringify(r.chips));
 console.log('SECTIONS:', JSON.stringify(r.secs));
 console.log('TRACKER:', r.tracker);
 r.cards.forEach(c=>{console.log('\n▸',c.badge,c.n, c.warn?('\n   WARN: '+c.warn):''); c.legs.forEach(l=>console.log('   ',l));});
 await p.screenshot({path:SHOT,fullPage:false});
 await b.close();
})();
