# Agora: a prediction-market forecast of the 2026 US House and Senate elections

Entry in the Yale PLSC 2219 2026 Election Forecast contest. Every race's Democratic two-party vote share is
forecast from Polymarket and Kalshi prices snapshotted on 2 November 2026, with past results used only to
calibrate the map from prices to vote shares.

## Results (final contest scores, 13 November 2026)

| Measure | Score | Rank among 37 ranked entries |
|---|---|---|
| Mean absolute error, 452 races | 2.76 pts | 2nd |
| Senate mean absolute error | 2.71 pts | 1st (Senate Prize) |
| Toss-up mean absolute error | 2.26 pts | 1st |
| Races called correctly | 426 of 452 | 3rd |
| Average rank across categories entered | 1.5 | 1st |

The entry beat the class model (3.17) and the professional benchmarks Split Ticket (3.15) and ElectIt (3.35).

## Layout

- `forecast.csv`: the submitted forecast (predicted Democratic two-party share per race).
- `forecast_guard05.csv`, `forecast_guard15.csv`, `forecast_prev_pull.csv`: variants from the final evening.
- `market_model/`: the pipeline, raw market snapshots, calibration set and diagnostics.
  See [`market_model/README.md`](market_model/README.md) for the method and how to reproduce it.

## Course data not included

The scripts read the course's race list, PVI and past-results files from `data (1)/` next to `market_model/`.
Those files belong to the course and are not in this repository.
