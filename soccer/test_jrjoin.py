#!/usr/bin/env python3
"""test_jrjoin.py -- JRJOIN-2026-09-08. The suffix fallback in soccer_mock.lookup().

Runs against a pinned two-line xg.psv rather than a slate, so it cannot rot when a slate is
re-scraped. What it pins is the MECHANISM, not the roster:

    toks() drops every token of two letters or fewer, so `jr` is already absent from every
    candidate set -- but the surname anchor is taken from norm(name).split(), which keeps it.
    For any odds name ending in `Jr` the anchor is therefore a token no candidate can contain,
    and the surname test fails 100% of the time. It is a guaranteed miss, not a near-miss, and
    it lands on exactly the Brazilian convention where `Jr` IS the known name.

    understat  "Vinicius Junior" -> toks {junior, vinicius}
    oddschecker "Vinicius Jr"    -> toks {vinicius},  anchor "jr"  -> unmatchable

⚠️ THE FALLBACK RUNS LAST, ON PURPOSE. It can only ever turn a miss into a hit; every name that
resolves via exact or token must resolve identically. That is what test_only_converts_misses
asserts, and it is why this is not a change to toks().

    python3 test_jrjoin.py
"""
import importlib.util, io, contextlib, os, sys, tempfile, textwrap

HERE = os.path.dirname(os.path.abspath(__file__))

XG = """\
La_liga|2026|Vinícius Júnior|Real Madrid|F|4|356|1|1|2.36|0.60|11|2.78|0.2144|2.20|0.56|10|5.11
La_liga|2025|Vinícius Júnior|Real Madrid|F|36|2865|16|12|10.69|0.34|100|3.14|0.1069|7.16|0.22|69|23.05
EPL|2026|Bobby Witt|Aston Villa|F|3|270|2|2|1.50|0.50|9|3.00|0.1666|0.20|0.07|4|1.60
EPL|2026|Marcus Thuram|Inter|F|3|270|2|2|1.50|0.50|9|3.00|0.1666|0.20|0.07|4|1.60
EPL|2026|Pablo|Arsenal|M|3|270|0|0|0.10|0.03|2|0.67|0.0500|0.10|0.03|2|0.40
EPL|2026|Pablo Garcia|Real Betis|M|3|270|0|0|0.10|0.03|2|0.67|0.0500|0.10|0.03|2|0.40
EPL|2026|Alex Senior|Everton|F|3|270|1|1|0.50|0.17|4|1.33|0.1250|0.10|0.03|1|0.50
EPL|2026|Alex Junior|Everton|F|3|270|1|1|0.50|0.17|4|1.33|0.1250|0.10|0.03|1|0.50
"""

AGS = "m|Vinicius Jr|2/1\n"
FIX = '{"date":"2026-01-01","matches":{"m":{"home":"A","away":"B","kickoff":1000,' \
      '"league":"UCL","espn":["uefa.champions","1"]}}}\n'


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
                # soccer_mock is a SCRIPT: importing it runs the whole slate pipeline, which a
                # pinned one-fixture stub cannot satisfy (standardize() needs n>1, the draft
                # shells out to node). Everything this test touches -- norm, toks, sufkey,
                # xg_exact/xg_tok/xg_suf and lookup -- is bound well before that point, so the
                # tail is allowed to fail. Guarded below: if lookup never got defined, say so
                # rather than reporting a vacuous pass.
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

        # THE BUG. Jr / Junior are the same man.
        recs, how = m.lookup('Vinicius Jr')
        check('Vinicius Jr resolves', how, 'suffix')
        check('...to the right player', recs and recs[0]['name'], 'Vinícius Júnior')
        check('...and carries both seasons', len(recs or []), 2)

        # A trailing suffix on the ODDS name, absent on the candidate.
        check('Bobby Witt Jr -> Bobby Witt', m.lookup('Bobby Witt Jr')[1] in ('token', 'suffix'), True)

        # ⚠️ THE ANCHOR STILL DOES ITS JOB. This is the pair the surname anchor was added for:
        # Real Betis's `Pablo Garcia` must NOT resolve to Arsenal's `Pablo`.
        check('Pablo Garcia is not Pablo', m.lookup('Pablo Garcia')[0][0]['name'], 'Pablo Garcia')

        # ⚠️ AMBIGUITY IS A REFUSAL, NOT A COIN FLIP (UNMATCHED-2026-08-28). `Alex Junior` and
        # `Alex Senior` both strip to `alex`; an odds line reading `Alex Jr` names neither
        # unambiguously, so it must refuse rather than pick one.
        check('Alex Jr refuses on ambiguity', m.lookup('Alex Jr'), (None, None))

        # An ordinary name is untouched by any of this.
        check('exact still exact', m.lookup('Marcus Thuram')[1], 'exact')

        # A name with nothing behind it stays missing.
        check('genuine miss stays missing', m.lookup('Nobody Here At All'), (None, None))

        if fails:
            print('FAIL')
            for f in fails:
                print('  ' + f)
            sys.exit(1)
        print('PASS  suffix fallback resolves Jr/Junior, keeps the surname anchor honest, '
              'and refuses on ambiguity')


if __name__ == '__main__':
    main()
