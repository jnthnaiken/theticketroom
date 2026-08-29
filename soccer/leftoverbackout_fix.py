"""
LEFTOVERBACKOUT-2026-08-29 -- take the three leftover singles out of the soccer ledger.

UNLEFTOVER-2026-08-28 stopped the MINTING but deliberately did not reach back:

    "TONIGHT'S BOARD IS NOT TOUCHED. ... This change stops the MINTING; it does not reach back and
     delete slips that shipped. Whether those three should be backed out of the ledger the way the
     MLB family nights were is the owner's call, not a side effect of a code change."

Owner's call, made. They come out.

WHAT THEY WERE. The 2026-08-28 soccer board was six slips. Two moons and a builder, all anchored by
Haaland, are the board. The other three anchor nothing -- they are the retired leftover section:

    builder  Back Post   Antonio Martinez  +200
    builder  Near Post   Lucas Boye        +200
    builder  The Nine    Luis Diaz         +120

⚠️ AND THE BACKOUT COSTS MONEY. Graded by soccer_grade.grade_ticket() itself -- not by hand:

    Back Post   Martinez did not score   -1.0u
    Near Post   Boye scored              +2.0u
    The Nine    Diaz scored              +1.2u
    ------------------------------------------
    3 graded, 2 won, +2.2u on 3.0u staked

So this removes a WINNING line. That is the point: the section was retired on 12 nights and 91 units
of evidence (MLB `family`: 11-80, -33.34u, -36.6% ROI), and three tickets is not evidence of
anything. Keeping them because they happened to win is exactly the reasoning the retirement exists
to overrule. The ledger should say what the board's rules produce, not what one lucky night did.

⚠️ ANTONIO MARTINEZ WAS NEVER CONFIRMED. His status on the settled board is `projected` -- a single
shipped on a man who never got a confirmed start. That is the same defect OUTSQUAD-2026-08-29 fixed
on the lock side, and it is a second reason this slip should not be in a ledger.

WHAT CHANGES

1. soccer_season.json -- subtract the three from `cats.builder` and unwind the night's history step
   by the same 2.2u, so the season figure and the Overall line agree. Following the exact precedent
   the file already records for the family retirement in `backout_note`, which is APPENDED TO, never
   overwritten: that note is the record of the earlier decision and must survive this one.

       cats.builder   11 / 6 won / +1.7524u / 11.0 staked
                  ->   8 / 4 won / -0.4476u /  8.0 staked
       history     ... 8.615238095238094  ->  6.415238095238094

   Cross-checked independently rather than trusted: the pre-08-28 builder line was 7 / 3 / -1.4 /
   7.0, and adding back ONLY The Poacher (Haaland's real anchor builder, won, +0.952381u on 1u)
   reproduces the post-backout figures to within 1e-9. If it does not, this script aborts.

2. soccer/boards/2026-08-28.json -- the three slips are FLAGGED, not deleted. They shipped and were
   visible for hours; the archive is the record of what the room actually showed, and rewriting it
   would be lying about the night. `backedout` carries the reason with it.

3. soccer_grade.py -- honour the flag in fold(). Today this is belt-and-braces, because fold()
   already refuses a date in `graded_nights` and 2026-08-28 is in it. It matters the day someone
   re-grades from the archive or force-folds: without it the flag is a comment, and a backed-out
   slip walks straight back into the ledger. A marker nothing enforces is how a correction gets
   quietly undone six weeks later.

WHAT IS NOT TOUCHED. The three moons/builder that ARE the board. The family backout note. Any other
night. `graded_nights` -- 2026-08-28 stays folded, because it was.
"""
import io, json, os, sys

SEASON = 'soccer_season.json'
BOARD  = 'boards/2026-08-28.json'
GRADER = 'soccer_grade.py'
LEFTOVERS = {'Back Post', 'Near Post', 'The Nine'}
REASON = ('LEFTOVERBACKOUT-2026-08-29: leftover single (anchors nothing), section retired by '
          'UNLEFTOVER-2026-08-28 and backed out of the ledger')

# ---------------------------------------------------------------- grade them with the REAL grader
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import soccer_grade as G

B = json.load(io.open(BOARD, encoding='utf-8'))
S = json.load(io.open(SEASON, encoding='utf-8'))
finals = set(B['meta'].get('finals') or [])
if not finals:
    sys.exit('ABORT: the archived board has no finals -- nothing was settled, do not touch the ledger')

removed = {'graded': 0, 'won': 0, 'units': 0.0, 'staked': 0.0}
keeper = None
seen = set()
for t in B['tickets']:
    g = G.grade_ticket(t, B['players'], finals)
    if t['name'] in LEFTOVERS:
        seen.add(t['name'])
        if (t.get('players') or []) and len(t['players']) != 1:
            sys.exit(f"ABORT: \"{t['name']}\" is not a one-leg single -- refusing to back out a parlay")
        if not g:
            sys.exit(f"ABORT: \"{t['name']}\" did not grade -- it was never in the ledger to remove")
        removed['graded'] += 1
        removed['won'] += 1 if g['won'] else 0
        removed['units'] += g['net']
        removed['staked'] += g['stake']
    elif t['kind'] == 'builder' and g:
        keeper = g                       # The Poacher -- the only builder that stays

if seen != LEFTOVERS:
    sys.exit(f'ABORT: expected all of {sorted(LEFTOVERS)} on the board, found {sorted(seen)}')
if keeper is None:
    sys.exit('ABORT: no surviving builder found -- the board is not the shape this backout assumes')
print(f"  graded by soccer_grade: {removed['graded']} slips, {removed['won']} won, "
      f"{removed['units']:+.4f}u on {removed['staked']:.1f}u")

# ---------------------------------------------------------------- 1. the ledger
c = S['cats']['builder']
before = dict(c)
after = {'graded': c['graded'] - removed['graded'],
         'won':    c['won']    - removed['won'],
         'units':  c['units']  - removed['units'],
         'staked': c['staked'] - removed['staked']}

# INDEPENDENT RECONSTRUCTION. Do not trust the subtraction: rebuild the same line from the other
# direction -- what the builder row was BEFORE this night, plus the one builder that stays.
prior = {'graded': before['graded'] - 4, 'won': before['won'] - 3,
         'units': before['units'] - (keeper['net'] + removed['units']),
         'staked': before['staked'] - 4.0}
rebuilt = {'graded': prior['graded'] + 1, 'won': prior['won'] + (1 if keeper['won'] else 0),
           'units': prior['units'] + keeper['net'], 'staked': prior['staked'] + keeper['stake']}
for k in after:
    if abs(after[k] - rebuilt[k]) > 1e-9:
        sys.exit(f'ABORT: {k} disagrees -- subtraction says {after[k]}, reconstruction says '
                 f'{rebuilt[k]}. Do not write a ledger you cannot derive twice.')
print(f"  cats.builder {before['graded']}/{before['won']} {before['units']:+.4f}u on {before['staked']:.1f}"
      f"  ->  {after['graded']}/{after['won']} {after['units']:+.4f}u on {after['staked']:.1f}  (agrees both ways)")
S['cats']['builder'] = after

if not S.get('history'):
    sys.exit('ABORT: no history to unwind')
S['history'][-1] = S['history'][-1] - removed['units']
print(f"  history tail unwound by {removed['units']:+.4f}u -> {S['history'][-1]}")

if '2026-08-28' not in S.get('graded_nights', []):
    sys.exit('ABORT: 2026-08-28 is not in graded_nights -- it was never folded, nothing to back out')

note = S.get('backout_note', '')
S['backout_note'] = (note.rstrip() + '\n\n' if note else '') + (
    'LEFTOVERBACKOUT-2026-08-29: the three LEFTOVER SINGLES on 2026-08-28 -- Back Post '
    '(Antonio Martinez +200), Near Post (Lucas Boye +200), The Nine (Luis Diaz +120) -- backed out '
    'of the ledger, owner\'s call. They anchored nothing; the section was retired by '
    'UNLEFTOVER-2026-08-28 as the MLB `family` retirement in a different coat. 3 graded / 2 won / '
    '+2.20u on 3.0u staked, so this REMOVES a winning line -- deliberately: the retirement rests on '
    '12 nights and 91 units (family went 11-80, -33.34u, -36.6% ROI) and three tickets is not '
    'evidence against it. Antonio Martinez was still `projected` on the settled board, a single on a '
    'man who never got a confirmed start (the lock-side half of that is OUTSQUAD-2026-08-29). '
    'cats.builder 11/6 +1.7524u on 11.0 -> 8/4 -0.4476u on 8.0; history tail 8.6152 -> 6.4152. '
    'The slips are FLAGGED `backedout` in boards/2026-08-28.json rather than deleted -- they '
    'shipped, and the archive is the record of what the room showed. 2026-08-28 stays in '
    'graded_nights because it was graded.')

# ---------------------------------------------------------------- 2. flag, do not delete
n = 0
for t in B['tickets']:
    if t['name'] in LEFTOVERS:
        t['backedout'] = REASON
        n += 1
if n != 3:
    sys.exit(f'ABORT: flagged {n} slips, expected 3')
print(f'  flagged {n} slips in {BOARD} (kept on the board, excluded from the ledger)')

# ---------------------------------------------------------------- 3. make the flag load-bearing
gsrc = io.open(GRADER, encoding='utf-8').read()
OLD_G = """    for t in D['tickets']:
        g = grade_ticket(t, players, finals)
        if not g:
            rows.append((t['kind'], t['name'], 'not settled / void', 0.0))
            continue"""
NEW_G = """    for t in D['tickets']:
        # LEFTOVERBACKOUT-2026-08-29: a slip explicitly BACKED OUT of the ledger is never folded.
        # Today this cannot fire -- fold() already refuses a date in graded_nights and 2026-08-28
        # is in it -- but it is what makes the flag mean something the day someone re-grades from
        # the archive or --force folds. A marker nothing enforces is how a correction gets quietly
        # undone six weeks later. The slip stays ON the board: it shipped, and the archive is the
        # record of what the room actually showed.
        if t.get('backedout'):
            rows.append((t['kind'], t['name'], 'backed out', 0.0))
            continue
        g = grade_ticket(t, players, finals)
        if not g:
            rows.append((t['kind'], t['name'], 'not settled / void', 0.0))
            continue"""
if gsrc.count(OLD_G) != 1:
    sys.exit(f'ABORT: expected exactly 1 fold() ticket loop in {GRADER}, found {gsrc.count(OLD_G)}')
gsrc = gsrc.replace(OLD_G, NEW_G, 1)

# ---------------------------------------------------------------- write
json.dump(S, io.open(SEASON, 'w', encoding='utf-8'), indent=1, ensure_ascii=False)
json.dump(B, io.open(BOARD, 'w', encoding='utf-8'), indent=1, ensure_ascii=False)
io.open(GRADER, 'w', encoding='utf-8').write(gsrc)
tot = sum(x['units'] for x in S['cats'].values())
st = sum(x['staked'] for x in S['cats'].values())
gr = sum(x['graded'] for x in S['cats'].values())
wn = sum(x['won'] for x in S['cats'].values())
print(f'wrote {SEASON}, {BOARD}, {GRADER}')
print(f'  season now {wn}-{gr - wn}  {tot:+.2f}u on {st:.1f}u staked')
