"""MONONYM-2026-09-08. Pins match_one()'s containment fallback.

The board printed "—" for the club of a man whose squad row was present: oddschecker priced
"Rayan Vitor", ESPN's Bournemouth sheet says "Rayan", and the surname anchor ("vitor") is not
on the sheet, so the join refused. surname_hits() had known this shape since COMPOUNDSUR-08-30
and match_one() had not been told.

What must stay true:
  * the shorter sheet name joins when it is the ONLY containment candidate,
  * it refuses when two men on the same sheet contain the name (Rayan Aït-Nouri / Rayan Cherki),
  * the anchor pass still wins outright when it can join, so the fallback never overrides it,
  * two men who merely share a given name still do NOT join (FIRSTNAME-2026-08-31).

Run:  python3 test_mononym.py
"""
import sys

from soccer_teamnews import match_one

FAILS = []


def check(label, got, want):
    ok = got == want
    print(('PASS  ' if ok else 'FAIL  ') + label + '   got=' + repr(got) + ' want=' + repr(want))
    if not ok:
        FAILS.append(label)


def sq(*names):
    return [(n, 'sub') for n in names]


# --- the live 2026-09-08 case -------------------------------------------------------------
bmouth = sq('Justin Kluivert', 'Evanilson', 'Rayan', 'Amine Adli', 'Ben Gannon-Doak')
check('Rayan Vitor joins the mononym sheet row',
      match_one('Rayan Vitor', bmouth), ('Rayan', 'sub'))

# --- the refusal that makes the fallback safe ---------------------------------------------
city = sq('Rayan Ait-Nouri', 'Rayan Cherki', 'Erling Haaland')
check('bare Rayan refuses across two Rayans',
      match_one('Rayan', city), None)

# --- the anchor pass must still win ---------------------------------------------------------
check('Rayan Cherki still anchors on the surname',
      match_one('Rayan Cherki', city), ('Rayan Cherki', 'sub'))

# --- COMPOUNDSUR shapes named in surname_hits() ---------------------------------------------
check('Giovane Nascimento -> Giovane',
      match_one('Giovane Nascimento', sq('Giovane', 'Yuri Alberto')), ('Giovane', 'sub'))
check('Gustavo Nunes Gomes -> Gustavo Nunes',
      match_one('Gustavo Nunes Gomes', sq('Gustavo Nunes', 'Pedro')), ('Gustavo Nunes', 'sub'))
check('Jaden Philogene-Bidace -> Jaden Philogene',
      match_one('Jaden Philogene-Bidace', sq('Jaden Philogene', 'Ollie Watkins')),
      ('Jaden Philogene', 'sub'))

# --- FIRSTNAME-2026-08-31 must NOT be reopened ----------------------------------------------
# Gabriel Jesus was not in the squad; Gabriel Magalhaes was starting. Neither name is a subset
# of the other, so containment must not join them.
check('Gabriel Jesus does not join Gabriel Magalhaes',
      match_one('Gabriel Jesus', sq('Gabriel Magalhaes', 'William Saliba')), None)

# --- the reverted substring bug stays reverted ----------------------------------------------
check('Jack Hinshelwood does not join Nicolas Jackson',
      match_one('Jack Hinshelwood', sq('Nicolas Jackson', 'Ollie Watkins')), None)

# --- an anchor-pass TIE stays a refusal -----------------------------------------------------
# UNMATCHED-2026-08-28's own case: the surname anchors on two different men and the token
# overlap is 1 for each, so the anchor pass refuses. Neither sheet name contains the priced
# name, so the fallback must refuse too rather than break the tie.
check('two men sharing a surname stay a refusal',
      match_one('Toni Martinez', sq('Josep Martinez', 'Lautaro Martinez')), None)

print()
if FAILS:
    print('FAILED: ' + ', '.join(FAILS))
    sys.exit(1)
print('all ' + str(9 - len(FAILS)) + ' checks pass')
