#!/usr/bin/env python3
"""TITLENUM-2026-10-17 -- a deep singles card names every slip from the pool, never 'Target Man 11'.

    python3 soccer/test_titlenum.py
"""
import os, re, sys
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import soccer_payload as S

js = open(os.path.join(HERE, 'soccer_draft.js'), encoding='utf-8').read()
m = re.search(r"builder: \[(.*?)\],\n\s*/\* SHAPEREPAIR", js, re.S)
draft = re.findall(r"'([^']+)'", re.sub(r'/\*.*?\*/', '', m.group(1), flags=re.S))
fails = []
def check(c, msg):
    print(('ok   ' if c else 'FAIL ') + msg)
    if not c: fails.append(msg)
check(S.NAMES['builder'] == draft, f"payload builder titles match soccer_draft.js ({len(draft)})")
check(len(set(draft)) == len(draft), 'no title repeats')
check(not any(re.search(r'\d', n) for n in draft), 'no title carries a number')
check(len(draft) >= 40, 'enough titles for a 40-single card')
print(f'\n{len(fails)} failure(s)'); sys.exit(1 if fails else 0)
