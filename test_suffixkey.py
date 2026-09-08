"""SUFFIXKEY-2026-09-08. The generational suffix, on either side of every name join.

Measured on the live 2026-09-08 board before the fix: every Jr. among the 420 bats had
chase/whiff/xwcon = None, and every one of them still had his Kasper khr/iso -- because KEXTRA
was the one map already keyed under both norms (KEXTRAKEY-2026-09-04). The fix generalises that
map's patch to all of them.

    Bobby Witt Jr.        chase=None   khr=61     Elly De La Cruz  chase=26.1   (control)
    Fernando Tatis Jr.    chase=None   khr=54     Junior Caminero  chase=29.8   (control)
    Jazz Chisholm Jr.     chase=None   khr=50
    Lourdes Gurriel Jr.   chase=None   khr=54
    Vladimir Guerrero Jr. chase=None   khr=66

Run:  python3 test_suffixkey.py
"""
import re
import sys
import unicodedata

# The three definitions under test, lifted verbatim from build15.py. Kept as a copy on purpose:
# build15 runs a whole slate on import and cannot be imported for a unit test.
norm = lambda s: ''.join(c for c in unicodedata.normalize('NFKD', s)
                         if not unicodedata.combining(c)).lower().replace('.', '').strip()
_SUF = r'(?:jr|jnr|junior|sr|snr|senior|ii|iii|iv|v)'
lunorm = lambda s: re.sub(r'\s+' + _SUF + r'$', '', norm(s))


def pnorm(x):
    x = ''.join(c for c in unicodedata.normalize('NFD', x or '') if not unicodedata.combining(c)).lower()
    return re.sub(r'[^a-z ]', '', x).strip()


plunorm = lambda s: re.sub(r'\s+' + _SUF + r'$', '', pnorm(s))


def nput(d, name, val):
    d[norm(name)] = val
    d[lunorm(name)] = val
    return d


def nget(d, name, default=None):
    for k in (norm(name), lunorm(name)):
        if k in d:
            return d[k]
    return default


FAILS = []


def check(label, got, want):
    ok = got == want
    print(('PASS  ' if ok else 'FAIL  ') + label + '   got=' + repr(got))
    if not ok:
        FAILS.append(label)


# --- the measured regression: Savant spells the suffix, the card does not -------------------
# Savant's custom leaderboard writes "Bobby Witt Jr."; the Kasper card writes "Bobby Witt", and
# no board name on 2026-09-08 carried a suffix at all (0 of 420).
SAV = {}
for n, v in [('Bobby Witt Jr.', 'witt'), ('Fernando Tatis Jr.', 'tatis'),
             ('Jazz Chisholm Jr.', 'chisholm'), ('Lourdes Gurriel Jr.', 'gurriel'),
             ('Vladimir Guerrero Jr.', 'guerrero'), ('Elly De La Cruz', 'elly'),
             ('Junior Caminero', 'caminero')]:
    nput(SAV, n, v)

for card, want in [('Bobby Witt', 'witt'), ('Fernando Tatis', 'tatis'),
                   ('Jazz Chisholm', 'chisholm'), ('Lourdes Gurriel', 'gurriel'),
                   ('Vladimir Guerrero', 'guerrero')]:
    check('board "%s" reaches the suffixed Savant row' % card, nget(SAV, card), want)

# --- the controls that must not move ---------------------------------------------------------
check('Elly De La Cruz (no suffix) still joins', nget(SAV, 'Elly De La Cruz'), 'elly')
check('Junior Caminero: a LEADING Junior is a given name, not a suffix',
      nget(SAV, 'Junior Caminero'), 'caminero')
check('the leading Junior survives normalisation', lunorm('Junior Caminero'), 'junior caminero')

# --- the suffix may be on EITHER side ---------------------------------------------------------
CARD = {}
nput(CARD, 'Bobby Witt', 61)
check('suffixed board name reaches a suffix-less map', nget(CARD, 'Bobby Witt Jr.'), 61)

# --- spelled-out forms, which is what JRJOIN was about ---------------------------------------
check('"Junior" as a trailing suffix folds like "Jr"', lunorm('Vinicius Junior'), 'vinicius')
check('"Jr" and "Junior" reach the same key',
      lunorm('Vinicius Jr') == lunorm('Vinicius Junior'), True)
check('"Senior" folds like "Sr"', lunorm('Someone Senior'), 'someone')
check('III still folds', lunorm('Efton Chism III'), 'efton chism')

# --- it must not eat a real name --------------------------------------------------------------
check('a surname is never mistaken for a suffix', lunorm('Ronald Acuna'), 'ronald acuna')
check('a name that IS the suffix is left alone (no empty key)', lunorm('Jr'), 'jr')
check('accents still fold', norm('Ronald Acuña Jr.'), 'ronald acuna jr')
check('accents fold under lunorm too', lunorm('Ronald Acuña Jr.'), 'ronald acuna')

# --- the pitcher pair behaves the same ---------------------------------------------------------
check('pnorm strips punctuation', pnorm('Luis L. Ortiz'), 'luis l ortiz')
check('plunorm strips a trailing suffix', plunorm('Some Pitcher Jr.'), 'some pitcher')

# ==============================================================================================
# THE ANTI-DRIFT CHECK. This is the one that matters most.
# ==============================================================================================
# Both of 2026-09-08's incidents were the SAME defect in DIFFERENT COPIES of one rule: the soccer
# browser join said "Jr" and not "Junior" while the server said both, and build15 said "Jr" while
# Savant's feed said "Jr." spelled out. Nobody will remember to update four files by hand. So the
# test reads the vocabulary out of each of them and refuses to pass unless they are identical.
#
# If you are here because this failed: do not edit the list in one file. Edit all four.
import os

SOURCES = {
    'build15.py':          r"_SUF\s*=\s*r'\(\?:([^)]+)\)'",
    'index.html':          r"replace\(/ \(([a-z|]+)\)\$/",
    'nfl/nfl_mock.py':     r"_SUF\s*=\s*r'\(\?:([^)]+)\)'",
    'soccer/soccer_live.js': r"var NAMESUF\s*=\s*\{([^}]+)\}",
}
HERE = os.path.dirname(os.path.abspath(__file__))
found, absent = {}, []
for rel, rx in SOURCES.items():
    path = os.path.join(HERE, rel)
    if not os.path.exists(path):
        absent.append(rel)
        continue
    txt = open(path, encoding='utf-8', errors='replace').read()
    m = re.search(rx, txt)
    if not m:
        found[rel] = None
        continue
    raw = m.group(1)
    # the JS one is an object literal (`jr: 1, junior: 1, ...`), the rest are alternations
    toks = re.findall(r'[a-z]+', raw)
    toks = [t for t in toks if t != 'r']
    found[rel] = frozenset(toks)

for rel in absent:
    print('SKIP  ' + rel + ' not present next to this test')
for rel, v in found.items():
    if v is None:
        check('the suffix list is findable in ' + rel, 'NOT FOUND', 'a list')

sets = {k: v for k, v in found.items() if v}
if len(sets) > 1:
    ref_name, ref = sorted(sets.items())[0]
    for name, v in sorted(sets.items()):
        check('%s carries the same suffix vocabulary as %s' % (name, ref_name),
              sorted(v), sorted(ref))
    print('      vocabulary: ' + ', '.join(sorted(ref)))

print()
if FAILS:
    print('FAILED: ' + ', '.join(FAILS))
    sys.exit(1)
print('all checks pass')
