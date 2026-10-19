"""TNAMNESIA-2026-10-19: a pass with no team news must not undo what an earlier pass learned."""
import io, json, os, shutil, sys, tempfile, contextlib
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import soccer_payload as SP

FX = os.path.join(HERE, 'fixtures', '2026-08-26')
DATE = '2026-08-26'
fails = 0
def check(ok, what):
    global fails
    print(('PASS  ' if ok else 'FAIL  ') + what); fails += (not ok)

root = tempfile.mkdtemp()
XG = os.path.join(root, 'xg.psv'); open(XG, 'w').close()   # minutes only feed the prose; not under test
work = os.path.join(root, 'work'); os.makedirs(work); os.makedirs(os.path.join(root, 'boards'))
tn = json.load(open(os.path.join(FX, 'teamnews.json')))
xi_name = next(iter(tn['xi'])); out_name = next(iter(tn['absent']))
quiet = lambda: contextlib.redirect_stdout(io.StringIO())

# pass 1: team news present
with quiet():
    SP.build(os.path.join(FX, 'scored.json'), os.path.join(FX, 'tickets.json'), XG,
             os.path.join(work, 'd1.json'), DATE, teamnews_path=os.path.join(FX, 'teamnews.json'))
d1 = json.load(open(os.path.join(work, 'd1.json')))
p1 = d1['players']
check(p1[xi_name]['status'] == 'confirmed', 'pass 1 confirms an XI man')
check(p1[out_name]['out'] is True, 'pass 1 marks a man out of the squad')
# a goal the first pass saw
gm = next(n for n in p1 if n not in (xi_name, out_name))
p1[gm]['hr'] = True; p1[gm]['goalmins'] = ['37']
json.dump(d1, open(os.path.join(root, 'boards', DATE + '.json'), 'w'))   # the archive the next build reads

# pass 2: NO team news (ESPN down / empty XI)
with quiet():
    SP.build(os.path.join(FX, 'scored.json'), os.path.join(FX, 'tickets.json'), XG,
             os.path.join(work, 'd2.json'), DATE)
p2 = json.load(open(os.path.join(work, 'd2.json')))['players']
check(p2[xi_name]['status'] == 'confirmed', 'a confirmed man stays confirmed when a pass has no team news')
check(p2[out_name]['out'] is True, 'an out man stays out when a pass has no team news')
check(p2[gm]['hr'] is True and p2[gm]['goalmins'] == ['37'], 'a goal already seen is not unseen')

# pass 3: no prior board -> nothing invented
os.remove(os.path.join(root, 'boards', DATE + '.json'))
with quiet():
    SP.build(os.path.join(FX, 'scored.json'), os.path.join(FX, 'tickets.json'), XG,
             os.path.join(work, 'd3.json'), DATE)
p3 = json.load(open(os.path.join(work, 'd3.json')))['players']
check(p3[xi_name]['status'] == 'projected' and not p3[out_name]['out'], 'no archive: the pass reads as before')
shutil.rmtree(root, ignore_errors=True)
print('ALL GREEN -- team news is not forgotten between passes' if not fails else f'{fails} FAILURE(S)')
sys.exit(1 if fails else 0)
