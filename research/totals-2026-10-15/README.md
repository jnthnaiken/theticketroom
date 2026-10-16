# TOTALS research 2026-10-15

Owner: "design another algorithm that figures out the correct layer of data points ... the most successful way to predict game totals and team totals for goals in a game. one parlay a day."

Data: soccer-data branch history/2014-2026-limit0 (understat team + player xG), history/market (merged football-data), history/fd_raw (full football-data CSVs incl. Max/MaxC, pulled by .github/workflows/soccer-fdraw.yml).
Paths in the scripts are the session's /home/claude/tot/{data,src}. Order: join.py -> feats.py -> addmax.py -> teamtot.py (implied.pkl) -> sim/parlay/holdout/boot; lineup.py -> lineup_test.py; other.py.

Findings: see the project doc claude/totals-research-2026-10-15.md.
