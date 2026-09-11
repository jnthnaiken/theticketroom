#!/usr/bin/env python3
"""test_nfl_injuries.py -- INJOUT + ESPNFETCH-2026-09-11, offline.

  1. a definite Out/IR man is scratched; Questionable and Doubtful are not
  2. matched by TEAM through the nflverse->ESPN alias (LA->LAR), and suffixes fold (Jr./Sr.)
  3. a same-name man on ANOTHER team is untouched
  4. soccer_draft.js then refuses the scratched man (he makes no ticket)
  5. nfl_espn.getj reads JSON through node from a local server, and raises (not returns) on a 403
  6. nfl_settle routes through nfl_espn (the urllib path that ESPN 403'd is gone)
"""
import http.server, json, os, subprocess, sys, tempfile, threading
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import nfl_injuries, nfl_espn

fail = 0
def chk(label, ok, detail=None):
    global fail
    print(('PASS  ' if ok else 'FAIL  ') + label)
    if not ok:
        fail += 1
        if detail is not None: print('      ', detail)

SB = {'events': [{'id': '1'}, {'id': '2'}]}
SUM = {
  '1': {'injuries': [{'team': {'abbreviation': 'LV'}, 'injuries': [
          {'athlete': {'displayName': 'Brock Bowers'}, 'status': 'Out'},
          {'athlete': {'displayName': "Dont'e Thornton Jr."}, 'status': 'Injured Reserve'},
          {'athlete': {'displayName': 'Some Doubtful'}, 'status': 'Doubtful'}]},
        {'team': {'abbreviation': 'MIA'}, 'injuries': [
          {'athlete': {'displayName': 'Some Questionable'}, 'status': 'Questionable'}]}]},
  '2': {'injuries': [{'team': {'abbreviation': 'LAR'}, 'injuries': [
          {'athlete': {'displayName': 'Deebo Samuel Sr.'}, 'status': 'Out'}]}]},
}
def fake(url):
    if 'scoreboard' in url: return SB
    return SUM[url.split('event=')[1]]

outs = nfl_injuries.out_by_team('2026-09-13', getj=fake)
scored = [
  dict(name='Brock Bowers', team='LV', odds=200, match='m1'),
  dict(name="Dont'e Thornton", team='LV', odds=900, match='m1'),
  dict(name='Some Doubtful', team='LV', odds=400, match='m1'),
  dict(name='Some Questionable', team='MIA', odds=300, match='m1'),
  dict(name='Deebo Samuel', team='LA', odds=250, match='m2'),
  dict(name='Brock Bowers', team='KC', odds=500, match='m3'),
]
hits = nfl_injuries.apply(scored, outs)
by = {(p['name'], p['team']): p for p in scored}
chk('Out: Bowers (LV) scratched', by[('Brock Bowers', 'LV')].get('out') is True)
chk('Injured Reserve + suffix fold: Thornton scratched', by[("Dont'e Thornton", 'LV')].get('out') is True)
chk('Doubtful is NOT out', not by[('Some Doubtful', 'LV')].get('out'))
chk('Questionable is NOT out', not by[('Some Questionable', 'MIA')].get('out'))
chk('nflverse LA -> ESPN LAR, Sr. folds: Samuel scratched', by[('Deebo Samuel', 'LA')].get('out') is True)
chk('same name on another team untouched', not by[('Brock Bowers', 'KC')].get('out'))
chk('exactly three scratches reported', len(hits) == 3, hits)

# 4. the draft refuses him
node = subprocess.run(['node', '-e', """
const D=require(process.argv[1]);
const rows=[]; const M=['a','b','c']; let i=0;
for (const m of M) for (let k=0;k<6;k++) rows.push({name:m+k, match:m, odds:150+k*20, TOTAL:200-(i++), blend:1, gate_z:2, kickoff:780});
rows[0].out=true;
const r=D.draft(rows,{WIN:60,Z_GATE:0.55,GAME_CAP:5},{koOf:()=>780,slateMatches:3});
const names=r.tickets.flatMap(t=>t.legs.map(l=>l.name));
console.log(JSON.stringify({n:r.tickets.length, has:names.includes('a0')}));
""", os.path.join(HERE, '..', 'soccer', 'soccer_draft.js')], capture_output=True, text=True)
res = json.loads(node.stdout or '{}')
chk('an `out` man makes no ticket, and the board still drafts', res.get('n', 0) > 0 and res.get('has') is False, node.stdout + node.stderr)

# 5. transport
class H(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        if 'deny' in self.path:
            self.send_response(403); self.end_headers(); return
        b = json.dumps({'ok': 1}).encode()
        self.send_response(200); self.send_header('content-type', 'application/json'); self.end_headers(); self.wfile.write(b)
    def log_message(self, *a): pass
srv = http.server.HTTPServer(('127.0.0.1', 0), H)
threading.Thread(target=srv.serve_forever, daemon=True).start()
base = f'http://127.0.0.1:{srv.server_address[1]}/'
os.environ.setdefault('NO_PROXY', '127.0.0.1,localhost'); os.environ['no_proxy'] = os.environ['NO_PROXY']
chk('getj reads JSON', nfl_espn.getj(base + 'x') == {'ok': 1})
try:
    nfl_espn.getj(base + 'deny'); chk('a 403 raises', False)
except RuntimeError as e:
    chk('a 403 raises, naming the transports tried', 'node' in str(e) or 'urllib' in str(e), str(e))
srv.shutdown()

# 6. settle is wired through it
src = open(os.path.join(HERE, 'nfl_settle.py')).read()
chk('nfl_settle.py fetches through nfl_espn', 'nfl_espn.getj(url)' in src and "'ticketroom-nfl-settle'" not in src)
wf = open(os.path.join(HERE, '..', '.github', 'workflows', 'nfl-build.yml')).read()
i, j = wf.find('nfl_injuries.py scored.json'), wf.find('node nfl_draft_cli.js scored.json')
chk('nfl-build.yml runs the injury scratch BEFORE the draft', 0 < i < j)

print(f'\n{fail} FAILURE(S)' if fail else '\nall checks pass')
sys.exit(1 if fail else 0)
