# Market-only forecast (Yale 2026 Election Prediction Competition)

Every race with a tradeable margin-of-victory market (330 of 452 scored races, including nearly all competitive
ones) is forecast from market prices alone. The 121 races whose only market is a win-probability market use the
win price plus the district or state PVI, because a 98% price says who wins but not by how much. No polls,
fundamentals or past results enter the forecast; past results are used only to *calibrate* the map from market
prices to vote shares.

## Data (snapshot)
- Polymarket (Gamma API), fetched 20261102T000829Z: per-race "Election Winner" events (470/470 races) and
  "Margin of Victory" bucket events (439/470; 330 had a tradeable book, the rest were empty order books
  quoting ~0.45 on every bucket and were discarded).
- Kalshi vote-percentage ladders (series KXVOTEGENERAL, 1,043 events): for each candidate, "at least X%" markets at
  1-2 point steps. A normal distribution is fitted to each ladder's survival curve; the D two-party share is
  mu_D / (mu_D + mu_R). Usable for 439 races (Louisiana jungle races and first-round ladders in ranked-choice
  races excluded; final-round ladders used for AK/ME). Combined with the other estimate by traded volume
  (median ladder volume ~$1.8k vs ~$25k for Polymarket margin books), so they matter most in the races that
  lack a margin market. They agreed with the pre-existing forecast to 0.9 pts (margin races) and 1.5 pts
  (win-price+PVI races) on average.
- Kalshi (public trade API), fetched 20261102T000829Z: KXHOUSERACE + per-district House series (434 districts),
  SENATE{ST}-26 events (35 races).
- Calibration set (114 resolved markets, 79 distinct races): Polymarket 2024 Senate (31 states), 2024 House
  (19 districts), 2024 DE/VT and 2025 VA/NJ governor, 2025 FL-1, FL-6 and Wisconsin Supreme Court, plus Kalshi's
  settled 2024 Senate (19), 2024 House (23), 2024 governor (9) and 2025 special/governor (6) markets from the public
  `/historical/markets` and `/historical/markets/{ticker}/candlesticks` endpoints (no API key needed). Price taken
  2 days before each election, matching this snapshot's horizon. Results from the course results file (2024) or
  public returns (2025 and governors). PredictIt was tried: its metadata API answers for closed IDs but the chart
  endpoint is empty for pre-2024 markets, so it contributed nothing. Polymarket 2022 markets have no price history.

## Method
1. Win probability p = volume-weighted blend of Polymarket and Kalshi D-side probabilities (independents
   who are the D-side candidate, e.g. Osborn, Achilles, Bengs, Hill, are matched by name; Montana uses
   Bankhead + Bodnar).
2. Results-trained map: a cubic in logit(p) fitted by least absolute deviations on the 114 markets. Chosen by a
   leave-one-race-out comparison (compare_models.py; grouped so a race priced on both exchanges cannot see its
   twin): cubic LAD 2.01 pts, kNN 2.2, linear LAD 2.24, probit with longshot correction 2.53, constant 0.5 5.85.
   On the 63 competitive markets (p between 0.15 and 0.85) cubic LAD scores 1.25 vs 1.75 for a constant 0.5, so
   win prices carry only modest margin information in close races; most of the map's value is in the tails.
3. Margin markets: bucket prices -> normal distribution over the D margin (least squares) -> expected
   margin -> two-party share (3% other-vote allowance). Where a usable margin book exists this path is used
   alone: on the five resolved 2025 races that had both market types before the election, margin-only scored
   2.60 pts MAE vs 2.66 for an 85/15 blend and 3.05 for win probabilities alone, and blending in the win path
   mainly dragged safe seats toward 0.5 (a 99% price cannot express a 35-point margin). Guard: if the margin
   book's implied win probability disagrees with the winner market by more than 15 points, the margin path is
   down-weighted to 0.3 * vol/(vol + 5000) and the win path fills the rest (no race triggered it on Nov 1).
4. Races with no usable margin market (121): share = cubic(logit p) + beta * PVI, fitted by least absolute
   deviations on the 330 races that have both a win market and a usable margin market tonight (target: the
   margin-implied share). Beta = 0.88 share points per PVI point; 10-fold CV error 1.28 pts, against 3.77 pts for
   the same map without PVI. PVI is the only non-market input and is used only on this path. Evidence from 2024
   resolved markets points the same way: adding PVI to the price-to-share map cut grouped-LOO error from 1.72 to
   1.55 pts, all of it in safe seats (2.80 -> 2.19), while competitive races were unchanged or slightly worse.
4b. Kalshi vote-share ladders (above) are blended into both paths by volume; 394 races received a ladder
   adjustment, mean absolute change 0.18 pts, largest about 5 pts (CA-24, ID Senate).
5. Fixed races (18) take the race file's fixed_prediction; Montana p_dem_win = 0 per the rules; the Montana
   margin market prices Alme vs the runner-up, so only the win-probability path is used there.
6. Win probabilities, intervals and 10,000 seat simulations are kept in forecast_detail.csv and
   market_model/seat_sims.csv for reference; the submitted forecast.csv carries only pred_dem_share.

## Reproduce
```
python3 fetch_polymarket.py      # raw/polymarket_2026.json, raw/polymarket_hist.json
python3 fetch_kalshi.py          # raw/kalshi_2026.json + raw/kalshi_votegeneral_2026.json (vote-share ladders)
python3 fetch_kalshi_hist.py     # raw/kalshi_hist.json (settled 2024-25 markets + candlesticks)
python3 build_training.py && python3 build_kalshi_hist.py && python3 fit_calibration.py
python3 compare_models.py        # optional: model comparison table
python3 make_forecast.py         # ../forecast.csv (template columns A-F, only E filled), seat_sims.csv, forecast_detail.csv
python3 export_site.py           # site files: ../plsc2219-forecast-template-main/{forecast.csv,seat_sims.csv}
Rscript -e 'source("data (1)/check_forecast.R"); check_forecast("forecast.csv",stage="prelim",data_dir="data (1)")'
```

## Known limits
- Louisiana jungle races: markets price the eventual seat winner, not the Nov 3 combined D share.
- Open-ended top margin buckets ("30% or more") cap how far the margin path can go in very safe seats.
- The calibration set is two cycles deep at most (2024 and 2025); the map is flat in the middle because 2024
  markets were over-confident (a 75% favourite averaged a ~50.5% share).

## Variants kept for comparison
- `forecast_market_only.csv`: the pure market-only version (121 no-margin races from the win price alone).
  Differs from the submitted file by 1.0 pt per race on average, all in those 121 races.
- `make_forecast_pvi.py` / `forecast_with_pvi.csv`: the experiment that led to the hybrid; now identical to the
  main output. A PVI-only uniform-swing baseline using the market's D+10 national margin differs from the market
  forecast by 6.8 pts per race and would imply 309 D seats, which no market believes.
