# FBL-REBUILD (2026-10-24)

The owner asked: "i want to redo our model from the ground up using that site [firstbasketland.com]. do the same backtest over as many years as possible to find the most succesful layer of data points."

Scripts run in order: `build3.py` (PBP extras) → `feat3.py` (FBL feature families) → `search.py` (ground-up selection) → `gbm.py` (boosted trees) → `probs.py` (walk-forward probabilities) → `bt.py` (market blend + shipped-board backtest) → `layers.py` / `layers2.py` / `layer_board.py` (filters on the value pool).

**Data:** nbastatsv3 play-by-play 2014–25 (14,436 games) and BettingPros/FanDuel prices 2021–25.

**Result:** nothing beats production. See `claude/nba-fblrebuild-2026-10-24.md` in the project.
