#!/usr/bin/env python3
"""test_longname.py -- LONGNAME-2026-09-18. The long-name fallback in soccer_mock.lookup().

Same shape as test_jrjoin.py, and for the same reason: a pinned xg.psv rather than a slate, so
it pins the MECHANISM and cannot rot when a slate is re-scraped.

    THE MISS. lookup() anchors on the LAST token of the ODDS name. Where a book prints a double
    surname and the xG source prints one -- Spanish and Brazilian naming, most of a first MLS
    card -- that anchor is a token no candidate can contain, so the match fails 100% of the
    time. Not a near-miss; the same guaranteed miss JRJOIN documented for `Jr`.

        oddschecker "Nicolas Fernandez Mercau"  anchor "mercau"
        ASA / ESPN  "Nicolás Fernández"         -> no candidate has `mercau`

    AND IT IS NOT COSMETIC. An unjoined man scores on the market term with edge_z = 0, which
    reads as AVERAGE rather than UNKNOWN, so the shortest price in his game floats up the board
    on a model number he does not have.

⚠️ EQUALITY, NOT CONTAINMENT, AND >= 3 TOKENS. The candidate's token set must EQUAL the odds
tokens minus the final one. Containment is the bug the surname anchor exists to stop (`Pablo
Garcia` -> Arsenal's `Pablo`), and a two-token odds name reduces to a lone given name, which is
that same bug. Both halves are asserted below.

⚠️ IT RUNS LAST, so it can only ever turn a MISS into a hit.

    python3 test_longname.py
"""
import importlib.util, io, contextlib, os, sys, tempfile

HERE = os.path.dirname(os.path.abspath(__file__))

XG = """\
MLS|2026|Nicolás Fernández|New York City FC|ST|0|2355|15|11|5.2446|0.2004|58|2.2166|0.0904|6.2983|0.2407|45|0
MLS|2026|Luighi Hanri|New York City FC|ST|0|479|4|3|3.562|0.6693|16|3.0063|0.2226|0.2821|0.053|3|0
EPL|2026|Pablo|Arsenal|M|3|270|0|0|0.10|0.03|2|0.67|0.0500|0.10|0.03|2|0.40
EPL|2026|Marcus Thuram|Inter|F|3|270|2|2|1.50|0.50|9|3.00|0.1666|0.20|0.07|4|1.60
La_liga|2026|Carlos Ruiz|Getafe|F|3|270|1|1|0.50|0.17|4|1.33|0.1250|0.10|0.03|1|0.50
La_liga|2025|Carlos Ruiz|Valencia|M|3|270|0|0|0.10|0.03|2|0.67|0.0500|0.10|0.03|2|0.40
"""

AGS = "m|Nicolas Fernandez Mercau|5/4\n"
FIX = '{"date":"2026-01-01","matches":{"m":{"home":"A","away":"B","kickoff":1000,' \
      '"league":"MLS","espn":["usa.1","1"]}}}\n'


def load_mock(tmp):
    for n, body in (('xg.psv', XG), ('ags.psv', AGS), ('fixtures.json', FIX)):
        open(os.path.join(tmp, n), 'w', encoding='utf-8').write(body)
    old = os.getcwd()
    os.chdir(tmp)
    spec = importlib.util.spec_from_file_location('sm', os.path.join(HERE, 'soccer_mock.py'))
    m = importlib.util.module_from_spec(spec)
    buf = io.StringIO()
    try:
        with contextlib.redirect_stdout(buf), contextlib.redirect_stderr(buf):
            try:
                spec.loader.exec_module(m)
            except BaseException:
                # soccer_mock is a SCRIPT -- see test_jrjoin.load_mock for why the tail is
                # allowed to fail. lookup() is bound long before it.
                pass
    finally:
        os.chdir(old)
    if not hasattr(m, 'lookup'):
        raise SystemExit('soccer_mock did not get as far as defining lookup() -- test is invalid')
    return m


def main():
    with tempfile.TemporaryDirectory() as tmp:
        m = load_mock(tmp)
        fails = []

        def check(label, got, want):
            if got != want:
                fails.append(f'{label}: got {got!r}, want {want!r}')

        # THE BUG. The book's trailing surname is the one the stats source drops.
        recs, how = m.lookup('Nicolas Fernandez Mercau')
        check('Fernandez Mercau resolves', how, 'longname')
        check('...to the right player', recs and recs[0]['name'], 'Nicolás Fernández')

        # ⚠️ TWO TOKENS IS NOT ENOUGH. `Luighi Sousa` and `Luighi Hanri` are the same man on the
        # 2026-09-18 card and this rule still must NOT join them: dropping the surname leaves a
        # lone given name, which is precisely the `Pablo Garcia` failure. A miss is the correct
        # answer here, and it is pinned so nobody "fixes" it by loosening the rule.
        check('Luighi Sousa stays a miss', m.lookup('Luighi Sousa'), (None, None))

        # ⚠️ THE ANCHOR STILL DOES ITS JOB, by the same token.
        check('Pablo Garcia is not Pablo', m.lookup('Pablo Garcia'), (None, None))

        # ⚠️ AMBIGUITY IS A REFUSAL, NOT A COIN FLIP (UNMATCHED-2026-08-28). Two seasons of ONE
        # man is not ambiguity -- two rows, one distinct name, so this must still resolve.
        check('two seasons of one man still joins', m.lookup('Carlos Ruiz Alvarez')[1], 'longname')
        check('...and carries both seasons', len(m.lookup('Carlos Ruiz Alvarez')[0]), 2)

        # An ordinary name is untouched by any of this.
        check('exact still exact', m.lookup('Marcus Thuram')[1], 'exact')
        check('genuine miss stays missing', m.lookup('Nobody Here At All'), (None, None))

        if fails:
            print('FAIL')
            for f in fails:
                print('  ' + f)
            sys.exit(1)
        print('PASS  long-name fallback joins a dropped trailing surname, refuses a two-token '
              'name, and keeps the surname anchor honest')


if __name__ == '__main__':
    main()
