#!/usr/bin/env python3
"""kasper_rows.py -- the Kasper pipe-row payload -> cards.json / extras.json / pitch.json.

WHY THIS FILE EXISTS
    The daily build scrapes Kasper in the browser into one pipe-delimited text payload (the
    `@@S@@...@@E@@` transfer channel), then has to turn it into the three intermediates
    `slate_assemble.py` reads. Until 2026-09-24 that last step was retyped from memory every
    morning. That is precisely the failure `slate_assemble.py`'s own header was written about
    ("Keep this in the repo so it is NEVER rebuilt from memory again"), and the column order
    below is not guessable -- `cards.test` and `extras.bip` are THE SAME column, and the
    roster table's last column (`Likely`) is scraped but used by nothing.

    Verified on 2026-09-24 by replaying the 2026-09-23 payload: Harry Ford, Kyle Schwarber,
    Luis Arraez and Framber Valdez all reproduce the committed `cards_2026-09-23.json`,
    `kasper_extras_2026-09-23.json` and `pitchers_2026-09-23.json` entries exactly.

THE PAYLOAD
    One row per line, pipe-delimited, two kinds:

    B | matchup | team | name | form_pct | form_arrow | <16 roster values>
    P | name | hand | <12 "All" values> | <12 "vs RHH" values> | <12 "vs LHH" values>

    A pitcher with no split rows emits empty strings for those 12-value groups.

THE ROSTER COLUMN ORDER (Kasper's hitter table, 0-indexed, as it renders since 2026-08-05)
    0 Hitter Name  1 Match  2 Ceil  3 Zone  4 kHR  5 Form  6 Pit  7 BIP  8 ISO  9 xwOBA
    10 xwOBAc  11 SwS%  12 PBrl%  13 Brl%  14 SwSp%  15 FB%  16 HH%  17 LA  18 Likely

    The scraper reorders those into the 16 payload values, so the payload's own order is what
    ROSTER names below, NOT the table's.

WHAT EACH OUTPUT GETS
    cards   name, form_pct, form_arrow, pb, hh, la, zone, test
    extras  khr, xwobacon, xwoba, fb, sweet, brl_bip, swstr, bip, pitch, ceiling, iso, team
            `team` is the DROPSCOPE-2026-09-05 tag; `slate_assemble` strips it after using it
            to resolve name collisions. Emitting extras without it is a hard error there.
    pitch   pit, bip, xwoba, cs, csw, swstr, ball, pbrl, brl, fb, hh, la, hand, vR{...}, vL{...}

    `Likely` (payload index 20) is deliberately dropped -- nothing downstream reads it.

Run: python3 kasper_rows.py <payload.txt> --dir <outdir>
"""
import json
import os
import sys

# payload value slots 6..21, in payload order
ROSTER = ['pb', 'hh', 'la', 'zone', 'khr', 'xwobacon', 'xwoba', 'fb', 'sweet',
          'brl_bip', 'swstr', 'bip', 'pitch', 'ceiling', 'likely', 'iso']
CARD_KEYS = ['pb', 'hh', 'la', 'zone']          # plus `test`, which IS `bip`
EXTRA_KEYS = ['khr', 'xwobacon', 'xwoba', 'fb', 'sweet', 'brl_bip', 'swstr', 'bip',
              'pitch', 'ceiling', 'iso']
ARM = ['pit', 'bip', 'xwoba', 'cs', 'csw', 'swstr', 'ball', 'pbrl', 'brl', 'fb', 'hh', 'la']


def num(s):
    """Kasper prints '-' and '' for a stat it has no sample for. Those must become null, not
    0.0 -- build15 tests `is None` to fall back, and a zero would score as a real reading."""
    s = (s or '').strip()
    if s in ('', '-', '--'):
        return None
    try:
        return float(s)
    except ValueError:
        return None


def parse(text):
    cards, extras, pitch = {}, {}, {}
    bats = arms = 0
    for ln in (text or '').split('\n'):
        f = ln.rstrip('\r').split('|')
        if f[0] == 'B':
            if len(f) < 22:
                raise SystemExit('!! short B row (%d fields): %s' % (len(f), ln[:80]))
            mk, team, name = f[1], f[2], f[3]
            v = dict(zip(ROSTER, [num(x) for x in f[6:22]]))
            card = {'name': name, 'form_pct': num(f[4]),
                    'form_arrow': f[5] or 'flat'}
            for k in CARD_KEYS:
                card[k] = v[k]
            card['test'] = v['bip']          # same column; see this file's header
            cards.setdefault(mk, {}).setdefault(team, []).append(card)
            e = {k: v[k] for k in EXTRA_KEYS}
            e['team'] = team                 # DROPSCOPE tag, stripped by slate_assemble
            extras[name] = e
            bats += 1
        elif f[0] == 'P':
            if len(f) < 39:
                raise SystemExit('!! short P row (%d fields): %s' % (len(f), ln[:80]))
            name, hand = f[1], f[2]
            p = dict(zip(ARM, [num(x) for x in f[3:15]]))
            p['hand'] = hand
            for key, off in (('vR', 15), ('vL', 27)):
                chunk = f[off:off + 12]
                if any(c != '' for c in chunk):
                    p[key] = dict(zip(ARM, [num(x) for x in chunk]))
            pitch[name] = p
            arms += 1
        elif ln.strip():
            raise SystemExit('!! unrecognised row: %s' % ln[:80])
    return cards, extras, pitch, bats, arms


def main():
    args = [a for a in sys.argv[1:] if not a.startswith('--')]
    if not args:
        print('usage: kasper_rows.py <payload.txt> [--dir DIR]')
        return 2
    out = sys.argv[sys.argv.index('--dir') + 1] if '--dir' in sys.argv else '.'
    cards, extras, pitch, bats, arms = parse(open(args[0], encoding='utf-8').read())

    # A name carded twice is the MUNCYCOLLIDE shape: extras and pitch are name-keyed and
    # last-write-wins, so the survivor is decided by scrape order. Say so rather than ship it.
    seen = {}
    for mk, teams in cards.items():
        for tm, arr in teams.items():
            for b in arr:
                seen.setdefault(b['name'], []).append('%s %s' % (mk, tm))
    dupes = {n: w for n, w in seen.items() if len(w) > 1}
    for n, w in sorted(dupes.items()):
        print('!! DUPLICATE carded name %r in %s -- extras/odds cannot tell them apart' % (n, w))

    for fn, obj in (('cards.json', cards), ('extras.json', extras), ('pitch.json', pitch)):
        with open(os.path.join(out, fn), 'w', encoding='utf-8') as fh:
            json.dump(obj, fh, ensure_ascii=False)
    print('cards   %d matchups / %d bats' % (len(cards), bats))
    print('extras  %d keys%s' % (len(extras), '' if not dupes else '  (%d lost to dupes)' % len(dupes)))
    print('pitch   %d arms, %d with vR/vL splits'
          % (arms, sum(1 for p in pitch.values() if 'vR' in p and 'vL' in p)))
    return 1 if dupes else 0


if __name__ == '__main__':
    sys.exit(main())
