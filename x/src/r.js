const { chromium } = require('/tmp/claude-0/node_modules/playwright');
(async()=>{const b=await chromium.launch({executablePath:'/opt/pw-browsers/chromium'});
for(const n of ['nba']){const p=await b.newPage({viewport:{width:1600,height:900}});
await p.goto('file:///home/claude/xpost/'+n+'.html');await p.waitForTimeout(800);await p.screenshot({path:'/home/claude/xpost/nba-opens.png'});}
await b.close();})();
