# RULESEARCH-2026-10-23 -- first-basket ticket-rule search (reproducible)

Owner: "all possibilities shouldve been tested". Rebuilds the 2014-26 walk-forward backtest and searches ticket rules.

1. Data: shufinskiy/nba_data `datasets/nbastatsv3_YYYY.tar.xz` + `shotdetail_YYYY.tar.xz` (2014-2025) unpacked to
   `pbp/` and `sd/`; prices `soccer-data:nba/raw/fb_odds.psv` -> `fb_odds.psv`.
2. `python3 build_games.py` -> games.json (14,436 games; tip team scores first 63.4%)
3. `python3 replay.py` -> rows.json (nba_fb.State replay; team + share refit per season on earlier seasons only)
4. `python3 join.py` -> bets.json (BettingPros join; market blend refit per season on earlier priced seasons)
5. `python3 grid.py`, `grid2.py`, `split.py` (rules; split = choose on 2021-23, test on 2024-25)
Findings: claude/nba-rulesearch-2026-10-23.md
