#!/usr/bin/env bash
# Full NFL backtest (NFLBT-2026-09-15). ~10 min on 2 cores. See RESULTS-2026-09-15.md.
set -euo pipefail
cd "$(dirname "$0")"
python3 prep.py 2021 2022 2023 2024 2025          # weekly tables + outcomes (nflverse, no prices)
python3 book.py 0.1                               # four synthetic books
for s in 2025 2024; do for b in weak same rich sharp; do
  BT_VIG=1.15 BT_SEASONS=$s BT_BOOKS=$b BT_OUT=res_${s}_${b}.pkl python3 run.py > log_${s}_${b}.txt 2>&1 &
done; done; wait
python3 report.py
