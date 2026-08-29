"""
WAYBACK-2026-08-29 -- take "The Way Back Machine" back off the 2026-08-28 board and out of the
ledger. It was removed by the ban at 23:12Z and my own bug put it back after the games were over.

THE FACTS, from the archive:

    23:12Z  Junior Caminero drifts into the top-4 ban. CHALKOFF removes the slip he is on --
            "The Way Back Machine" (Munetaka Murakami + Junior Caminero + Max Muncy). Board 14 -> 12.
            That is CHALKOFF-2026-08-26 working: "ANY LEG, not just the anchor", locked included.
    00:44Z  CHALKLOCK-2026-08-29 ships. It judged a locked slip on its ANCHOR only, so the slip was
            re-admitted -- with Caminero still on it, and hours after every game on the slate was
            final. Board -> 14.
    05:27Z  grade_night folds 2026-08-28 with it on the board.
    05:42Z  CHALKLOCK reverted (ae546a5b). Fifteen minutes too late; `graded_nights` blocks a re-fold
            and the engine no longer re-drafts a graded night, so nothing self-corrects.

CHALKLOCK was mine and it contradicted three written rules -- CHALKOFF-2026-08-26 ("exemption was
the wrong direction. Removal is the rule."), the Dingers pull ("i dont care if they are locked") and
lock-latch-2026-08-17 ("do not conflate 'a locked ticket is never re-derived' with 'a locked ticket
survives anything'"). This puts the board and the ledger back to what those rules produced at 23:12Z.

⚠️ THIS IS NOT THE SAME AS THE SOCCER LEFTOVERS. Those three singles were PUBLISHED, live and
bettable for hours, and graded correctly -- the ledger records what the board showed, so they stay
(see the 2026-08-29 revert of LEFTOVERBACKOUT). This slip is the opposite case: the board had
already correctly removed it DURING the slate, and it only reappeared afterwards because of a code
change. Nobody could have placed it off that reappearance; every game was final.

THE NUMBERS, and they are not asserted -- they are reproduced.

`grade_night.grade_ticket()` itself was re-run over the archived board, with `homered` and `played`
rebuilt from calibration.jsonl's 265 rows for the night (29 homered). That reproduces the recorded
figure EXACTLY before anything is touched -- the same standard the Dingers back-out was held to:

    as graded   14 tickets  -22.00u   == season.json's own history step (515.67 -> 508.67 -> 486.67)
    corrected   13 tickets  -20.00u
    delta                   +2.00u

The slip is a moon round robin, risk 2.0, and all three legs are hr=0 in calibration -- so it is a
clean -2.00u loss with no void legs and no partial return. Removing it is a pure +2.00u.

    cats.moon   335 / 45 won / +489.82u on 670.0   ->   334 / 45 / +491.82u on 668.0
    history     ... 486.67                          ->   ... 488.67

`won` is unchanged because the slip lost. `graded_nights` is unchanged: 2026-08-28 WAS graded, and
saying otherwise would invite a re-fold.

WHAT ELSE THIS TOUCHES: nothing. calibration.jsonl is a per-BAT log of whether a man homered; that
is unaffected by which slips existed, and all three bats remain on the board anyway (Murakami on
"Climbing the Ladder" and "Drop the Hook"). The other 13 slips are byte-identical.
"""
import io, json, os, sys

SEASON = 'season.json'
BOARD  = 'D_2026-08-28.json'
SLIP   = 'The Way Back Machine'
DATE   = '2026-08-28'

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import grade_night as G

# ---------------------------------------------------------------- reproduce the recorded night
cal = [json.loads(l) for l in io.open('calibration.jsonl', encoding='utf-8')
       if l.strip() and f'"{DATE}"' in l]
if not cal:
    sys.exit(f'ABORT: no calibration rows for {DATE} -- cannot reproduce the night, refusing to edit')
homered = {G.norm(r['name']) for r in cal if r.get('hr') == 1}
played  = {G.norm(r['name']) for r in cal}

D = json.load(io.open(BOARD, encoding='utf-8'))
if (D.get('meta') or {}).get('date') != DATE:
    sys.exit(f"ABORT: {BOARD} is {(D.get('meta') or {}).get('date')}, not {DATE}")

total, target = 0.0, None
for t in D['tickets']:
    g = G.grade_ticket(t, homered, played, set(), 1.0)
    if not g:
        continue
    total += g['net']
    if t['name'] == SLIP:
        target = (t, g)
if target is None:
    sys.exit(f'ABORT: "{SLIP}" is not on {BOARD} -- already corrected, or the wrong board')

S = json.load(io.open(SEASON, encoding='utf-8'))
if DATE not in S.get('graded_nights', []):
    sys.exit(f'ABORT: {DATE} is not in graded_nights -- it was never folded, nothing to correct')
if len(S.get('history', [])) < 2:
    sys.exit('ABORT: history too short to read the night step')
step = round(S['history'][-1] - S['history'][-2], 2)
if abs(step - round(total, 2)) > 0.011:
    sys.exit(f'ABORT: reconstruction {round(total,2):+.2f}u does not match the recorded step '
             f'{step:+.2f}u -- do not edit a ledger you cannot reproduce')
print(f'  reproduced the recorded night exactly: {step:+.2f}u over {len(D["tickets"])} tickets')

t, g = target
ch = (D['meta'].get('chalk') or [])
banned = [l['name'] for l in t['players'] if l['name'] in ch]
if not banned:
    sys.exit(f'ABORT: "{SLIP}" carries no banned bat -- it is not a CHALKOFF removal, leave it alone')
print(f'  "{SLIP}" carries banned bat(s): {banned}; graded {g["net"]:+.2f}u on {g["stake"]}')

# ---------------------------------------------------------------- 1. the board
before = [x['name'] for x in D['tickets']]
D['tickets'] = [x for x in D['tickets'] if x['name'] != SLIP]
after = [x['name'] for x in D['tickets']]
if after != [n for n in before if n != SLIP] or len(after) != len(before) - 1:
    sys.exit('ABORT: removing the slip changed more than one ticket')
D.setdefault('meta', {})['tickets'] = len(D['tickets'])
still = [x['name'] for x in D['tickets'] if any(l['name'] in ch for l in x.get('players', []))]
if still:
    sys.exit(f'ABORT: a banned bat is still on {still}')
print(f'  board {len(before)} -> {len(after)} tickets, no banned bat left on it')

# ---------------------------------------------------------------- 2. the ledger
k = g['kind']
c = S['cats'][k]
was = dict(c)
c['graded'] -= 1
c['won']    -= 1 if g['won'] else 0
c['units']  = round(c['units'] - g['net'], 2)
c['staked'] = round(c['staked'] - g['stake'], 2)
S['history'][-1] = round(S['history'][-1] - g['net'], 2)

# derive it a second way: the corrected board, graded from scratch, must equal the new step
corrected = sum(x['net'] for x in
                (G.grade_ticket(y, homered, played, set(), 1.0) for y in D['tickets']) if x)
new_step = round(S['history'][-1] - S['history'][-2], 2)
if abs(new_step - round(corrected, 2)) > 0.011:
    sys.exit(f'ABORT: new step {new_step:+.2f}u disagrees with re-grading the corrected board '
             f'({round(corrected,2):+.2f}u)')
tot = round(sum(x['units'] for x in S['cats'].values()), 2)
if abs(tot - S['history'][-1]) > 0.011:
    sys.exit(f'ABORT: cats sum {tot} != history tail {S["history"][-1]}')
print(f"  cats.{k} {was['graded']}/{was['won']} {was['units']:+.2f}u on {was['staked']}"
      f"  ->  {c['graded']}/{c['won']} {c['units']:+.2f}u on {c['staked']}")
print(f"  history {step:+.2f}u -> {new_step:+.2f}u for the night; season {tot:+.2f}u (cats == history)")

note = S.get('correction_note', '')
S['correction_note'] = (note.rstrip() + '\n\n' if note else '') + (
    f'WAYBACK-2026-08-29: "{SLIP}" (Murakami + Junior Caminero + Max Muncy) was removed from the '
    f'{DATE} board at 23:12Z by CHALKOFF when Caminero drifted into the top-4 ban -- correct, "ANY '
    f'LEG, locked included". CHALKLOCK-2026-08-29 shipped at 00:44Z, judged a locked slip on its '
    f'ANCHOR only, and re-admitted it hours after every game was final; grade_night folded the '
    f'night at 05:27Z with it on, and the revert (ae546a5b) landed at 05:42Z, too late. The slip '
    f'is a 2u moon round robin, all three legs 0 HR, so it graded a clean -2.00u. Backed out of '
    f'both the board and the ledger: cats.moon {was["graded"]}/{was["won"]} {was["units"]:+.2f}u on '
    f'{was["staked"]} -> {c["graded"]}/{c["won"]} {c["units"]:+.2f}u on {c["staked"]}; the night '
    f'{step:+.2f}u -> {new_step:+.2f}u; season history tail -> {S["history"][-1]}. Verified by '
    f're-running grade_night.grade_ticket() with homered/played rebuilt from calibration.jsonl, '
    f'which reproduced the recorded {step:+.2f}u exactly before anything was changed. '
    f'{DATE} stays in graded_nights -- it was graded. This is NOT the soccer-leftover case: those '
    f'slips were published and bettable and stay in the ledger; this one had already been removed '
    f'during the slate and only reappeared because of a code change.')

json.dump(S, io.open(SEASON, 'w', encoding='utf-8'), indent=1)
json.dump(D, io.open(BOARD, 'w', encoding='utf-8'), indent=1)
print(f'wrote {SEASON}, {BOARD}')
