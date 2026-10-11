#!/usr/bin/env python3
"""test_jkmargin.py -- JKMARGIN-2026-10-11. A sitting Jackpot is not churned off by noise.

WHAT HAPPENED. 2026-10-10, a one-game postseason slate (CWS@CLE). The Long Ball Jackpot posted
Munetaka Murakami at +382, the owner placed the bet, and at 20:01:22Z the next build moved the
slip to Jose Ramirez at +619. Nothing had gone wrong with Murakami: the cards had posted, every
bat re-scored, and Ramirez came out 0.0833 of a z ahead on the park-tail + TOTAL blend. Ramirez
then hit the only home run of the night. Owner: "why did it just switch murakami to jose? kami
was green check".

WHY A MARGIN AND NOT A PIN. SPECIALS-2026-09-24 deliberately REMOVED incumbent-prepending from
the two specials, and was right at the time: a special drafted by a buggy build would be
re-selected forever, and free plays "have no stake to protect". JACKPOTSINGLE-2026-09-29 then
made the Jackpot a real 1u single with committed exposure, which is exactly the premise that
reasoning rested on. A margin satisfies both halves: a placed bet is not churned off by noise,
and a wrong pick is still dislodged by anything bigger than noise.

WHERE 0.25 COMES FROM. Every archived board replayed build by build -- 12,857 commits across 105
boards, 2,458 of them carrying a Jackpot. The pick changed FOUR times:

    09-24 16:41  Goodman -> Walker    gap 0.0000   not a crossing: the incumbent was still
                                                   cand[0] and the shared-bat pass moved the seat
    09-24 17:01  Walker -> Goodman    gap 0.1212   flipped straight back
    10-10 20:01  Murakami -> Ramirez  gap 0.0833   the bet above
    10-10 21:09  Ramirez -> Murakami  --           the owner reposting BY HAND, not the engine

Three engine changes, two oscillations, largest crossing 0.1212. 0.25 blocks all of them with
room and leaves a bat who genuinely pulls clear free to take the seat. Those gaps are the
ENGINE's own numbers, printed out of jackpotCand() on the replay, not a Python paraphrase of it.

THE FIXTURE IS THE REAL BOARD. fixtures/2026-10-10/mlb_D_jackpot_flip.json is the exact input
the 20:01:22Z build saw: `players`/`meta` as that build committed them, `tickets` as the 20:00:40Z
build left them (Murakami sitting). Replayed through the UNFIXED engine it returns Ramirez, so
this suite fails without the fix rather than passing vacuously -- scenario 3 is that control, run
through the live engine with the margin switched off rather than against an archived copy of it.

Run: python3 test_jkmargin.py        (from the repo root; needs node for client_assemble.js)
"""
import importlib.util
import json
import os
import re
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
FIX = os.path.join(HERE, 'fixtures', '2026-10-10', 'mlb_D_jackpot_flip.json')
ASOF = '2026-10-10T20:01:22Z'
INCUMBENT = 'Munetaka Murakami'
RIVAL = 'José Ramírez'
FAILS = []


def check(ok, label, detail=''):
    print(('  ok   ' if ok else '  FAIL ') + label + (('   ' + str(detail)) if detail and not ok else ''))
    if not ok:
        FAILS.append(label)


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, os.path.join(HERE, path))
    m = importlib.util.module_from_spec(spec)
    sys.modules[name] = m
    spec.loader.exec_module(m)
    return m


def draft(mutate=None):
    """Run index.html's own engine over the fixture and return the Jackpot pick."""
    D = json.load(open(FIX, encoding='utf-8'))
    if mutate:
        mutate(D)
    with tempfile.NamedTemporaryFile('w', suffix='.json', delete=False, encoding='utf-8') as tf:
        json.dump(D, tf, ensure_ascii=False)
        tmp = tf.name
    try:
        env = dict(os.environ, ASOF=ASOF)
        r = subprocess.run(['node', 'client_assemble.js', tmp, 'index.html'],
                           capture_output=True, text=True, cwd=HERE, env=env)
        if r.returncode != 0:
            print('     client_assemble.js exited %d\n%s' % (r.returncode, (r.stderr or '')[-800:]))
            return None
        out = json.load(open(tmp, encoding='utf-8'))
    finally:
        os.unlink(tmp)
    jk = next((t for t in (out.get('tickets') or []) if t.get('kind') == 'jackpot'), None)
    return ((jk.get('players') or [{}])[0] or {}).get('name') if jk else None


print(__doc__.split('\n')[0] + '\n')

# ---- 1. the knob exists in both places and they agree ------------------------------------
cfg_json = json.load(open(os.path.join(HERE, 'board_config.json')))
boardcfg = load('boardcfg', 'boardcfg.py')
M = cfg_json.get('JACKPOT_MARGIN')

check(M is not None, 'board_config.json declares JACKPOT_MARGIN', '= %r' % (M,))
check(boardcfg.DEFAULTS.get('JACKPOT_MARGIN') == M,
      'boardcfg.DEFAULTS agrees with board_config.json',
      'DEFAULTS=%r config=%r' % (boardcfg.DEFAULTS.get('JACKPOT_MARGIN'), M))
check(isinstance(M, float) and 0 < M <= 1, 'the margin is a fraction of a z, not a price', repr(M))

# ⚠️ THE ONE THAT WOULD BE SILENT. boardcfg coerces its _INT keys with int(), and int(0.25) is 0 --
# which is this knob's OFF switch. A margin listed there would disable itself and nothing would be
# red: the board would just quietly go back to re-picking on every crossing.
check('JACKPOT_MARGIN' not in boardcfg._INT,
      'JACKPOT_MARGIN is NOT in boardcfg._INT -- int(0.25)==0 would silently switch it off')

# the validator has to actually reject nonsense, or the range comment is decoration.
# _validate() RAISES, and it wants a loaded (coerced) config -- RR_UNIT's keys are ints by then,
# so handing it the raw json would fail on unrelated rules and prove nothing about this one.
def refuses(val):
    try:
        boardcfg._validate(dict(boardcfg.CFG, JACKPOT_MARGIN=val))
        return ''
    except ValueError as e:
        return str(e) if 'JACKPOT_MARGIN' in str(e) else ''

check(bool(refuses(4)), 'boardcfg._validate refuses a margin above 1')
check(bool(refuses(-0.1)), 'boardcfg._validate refuses a negative margin')
check(not refuses(M), 'the shipped margin passes its own validator')
check(not refuses(0), 'and 0 is legal -- it is the documented OFF switch')

# ---- 2. the client reads it, and reads it the way state.py --check expects ----------------
html = open(os.path.join(HERE, 'index.html'), encoding='utf-8').read()
m = re.search(r"""cfg\(\s*['"]JACKPOT_MARGIN['"]\s*,\s*([0-9.]+)\s*\)""", html)
check(bool(m), 'index.html reads JACKPOT_MARGIN through cfg()')
check(bool(m) and float(m.group(1)) == M,
      "index.html's fallback literal equals board_config.json (archived boards render the same)",
      'html=%s config=%r' % (m.group(1) if m else None, M))

# the score has to be EXPOSED, not recomputed beside the sort -- a second copy of the z formula is
# how the two drafters drifted in the first place (BOARDCFG-2026-09-13).
i_jc = html.find('function jackpotCand(pool){')
body = html[i_jc:html.find('\n    }', i_jc)] if i_jc > 0 else ''
check(i_jc > 0, 'jackpotCand() found in index.html')
check('_JKZ={};' in body, 'jackpotCand() rebuilds _JKZ on every call (no stale scores)')
check(body.count('_PTAIL[_parkOf(n)]-tl[0]') == 1,
      'the z blend is written ONCE -- the guard reads _JKZ instead of recomputing it')

i_g = html.find('JKMARGIN-2026-10-11 -- THE INCUMBENT')
check(i_g > 0, 'the guard carries its rule tag')
guard = html[i_g:i_g + 4200]
check("kind==='jackpot'" in html[max(0, i_g - 400):i_g],
      'the guard sits inside the jackpot branch of the re-pick, not in the shared path')
check('_JKZ[cand[0]]-_JKZ[_inc]' in guard and "cfg('JACKPOT_MARGIN'" in guard,
      'the guard compares the LEAD to the margin')
check('cand.indexOf(_inc)>0' in guard,
      'a dead or scratched incumbent cannot pin the seat (indexOf fails, the leader stands)')
# the other free play is deliberately NOT guarded: it has no stake, so SPECIALS-2026-09-24's
# reasoning still holds for it in full.
i_d = html.find("else if(kind==='dinger')")
dinger = html[i_d:html.find('else', i_d + 10)] if i_d > 0 else ''
check(i_d > 0 and 'JACKPOT_MARGIN' not in dinger and '_JKZ' not in dinger,
      'the Daily Dinger branch is untouched -- it carries no stake, so it has nothing to protect',
      dinger[:120])

# and nobody mirrors it into the fresh drafter, which has no incumbent to protect
atpy = open(os.path.join(HERE, 'assemble_tickets.py'), encoding='utf-8').read()
check('JKMARGIN-2026-10-11 IS NOT MIRRORED HERE' in atpy,
      'assemble_tickets.py says WHY it has no margin (it is handed no prior board)')
check('_CFG.JACKPOT_MARGIN' not in atpy and "'JACKPOT_MARGIN'" not in atpy,
      'assemble_tickets.py never READS the margin -- it drafts fresh, so it has no incumbent')

# ---- 3. behaviour, on the real board that lost the bet ------------------------------------
print()
pick = draft()
check(pick == INCUMBENT,
      'THE BET HOLDS: replaying 2026-10-10 20:01Z keeps Murakami on the Jackpot', pick)

pick = draft(lambda D: D['meta'].setdefault('cfg', {}).update(JACKPOT_MARGIN=M))
check(pick == INCUMBENT,
      "the same, with the margin arriving through the board's own meta.cfg (the live path)", pick)

# THE CONTROL. Margin off is the pre-2026-10-11 engine, and it must reproduce the loss.
pick = draft(lambda D: D['meta'].setdefault('cfg', {}).update(JACKPOT_MARGIN=0))
check(pick == RIVAL,
      'CONTROL: with the margin at 0 the same input still swaps to Ramirez (so this suite is not vacuous)',
      pick)

# ---- 4. the margin stops noise, not news -------------------------------------------------
def kill_incumbent(D):
    D['players'][INCUMBENT]['out'] = True

pick = draft(kill_incumbent)
check(pick == RIVAL, 'a scratched incumbent does NOT hold the seat', pick)

def pull_clear(D):
    D['players'][INCUMBENT]['TOTAL'] = 100.0      # a real move, far past 0.25 of a z

pick = draft(pull_clear)
check(pick == RIVAL, 'a rival who genuinely pulls clear still takes the seat', pick)

print()
if FAILS:
    print('%d FAILED:' % len(FAILS))
    for f in FAILS:
        print('   ' + f)
    sys.exit(1)
print('all JKMARGIN checks pass')
