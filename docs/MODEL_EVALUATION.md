# Forecast Evaluation

**Evaluation date:** 2026-10-16
**Verdict:** **PROMISING BUT NOT YET VALIDATED**

This evaluation measures next-day prediction of the repository’s processed `daily_cash_flow` field. It is not yet evidence of production ATM withdrawal-demand accuracy because the field is signed cash flow rather than a verified nonnegative withdrawal amount.

## Data evidence

The evaluator used an explicitly selected local history file. The private source file is excluded from this publishing snapshot and is not required at application startup; deployed forecasts use approved history uploaded into PostgreSQL.

| Property | Measured value |
| --- | ---: |
| Rows | 8,461 ATM-day observations |
| ATM identifiers | 20 |
| Date range | 2017-06-09 through 2018-09-30 |
| Unique dates | 479 |
| Duplicate ATM/date rows | 0 |
| Flagged missing observations | 109 |
| Zero-flow rows | 112 |
| Negative-flow rows | 1,591 |
| `daily_cash_flow` range | -1,925.30 to 3,711.27 |

The omitted processed file was derived from the public Tinkoff ATM Competition/Kaggle data according to the repository documentation. It was not live bank or ATM operational data. The publishing snapshot contains a separate synthetic development dataset, but it was not used for that historical evaluation.

### External source documentation

The official [Tinkoff ATM Competition data page](https://www.kaggle.com/competitions/tinkoffatm/data) identifies these upstream files: `train_kaggle.csv`, `test_kaggle.csv`, and `kaggle_partners_2015_2016.csv`. It lists raw fields including `atm_id`, `datetime`, `operation_type`, `client_id`, `operation_value`, `trxn_date`, `trxn_amt_rub`, and `trxn_cnt`, and describes the competition target as the sum of operation values for each ATM-day. Access to download is subject to the competition rules.

That external description establishes the target formula and candidate raw fields, but does not state a verified sign convention for `operation_value` or prove that `daily_cash_flow` is in rubles. Prior authorized local evidence from `train_kaggle.csv` reproduced the raw-backed signed-flow rows in the omitted processed CSV. `test_file.csv` has only `datetime` and `atm_id`, so it cannot derive a target. Neither file is included in this publishing snapshot.

The remaining provenance gaps are the download/version and terms-acceptance record, monetary unit, official operation-type/sign mapping, approved ATM identity mapping beyond the existing IDs, and the original process that created the 109 flagged rows. A record-level reconciliation can now be produced for signed flow, but withdrawal-demand derivation remains blocked.

## Target provenance and raw-data semantics

The repository does **not** contain the raw operation-level source file, a raw-data download/import script, or a committed transformation that derives `daily_cash_flow`. Git history shows the processed CSV being added directly as `data/processed/atm_daily_history.csv`; the explicit local evaluator can read that file when supplied, but it is not included or required by the deployed database-backed runtime. Therefore the exact source formula, currency/unit, transaction sign convention, and meaning of each negative value cannot be verified from this repository.

The evidence that can be reproduced from the current files is:

- The processed schema contains only `atm_id`, `datetime`, `daily_cash_flow`, `operation_count`, and `is_missing_observation`; there is no withdrawal/deposit type, amount-by-operation, cash balance, capacity, replenishment, or cash-out field.
- `backend/app/data/tinkoff_history.py` parses the existing `daily_cash_flow` as numeric, drops rows with malformed required fields, sorts by ATM/date, and keeps the last duplicate ATM/date. It does not calculate cash flow or convert it to demand.
- The production feature path uses the prior values of this same field for `lag_1`, `lag_7`, `lag_14`, and rolling features. The target is `cash_flow.shift(-1)`, named `next_day_cash_flow`, in `backend/app/services/model_evaluation_service.py` and `experiments/evaluate_production_forecast.py`.
- There is no scaling, log transform, clipping, or inverse transformation. Predictions and metrics are in the raw numeric units of `daily_cash_flow`; those units are not specified by the repository.
- Field lineage is only partially observable: `atm_id` and `datetime` are already present in the processed file; `daily_cash_flow`, `operation_count`, and `is_missing_observation` have no local raw-source derivation. The uploaded-history path creates `operation_count=1` per accepted operation, sums amounts by UTC calendar day, and sets `is_missing_observation=0`, but this is separate from the historical CSV pipeline.
- All 109 `is_missing_observation=1` rows have `daily_cash_flow=0` and `operation_count=0`. There are also non-missing zero-flow rows with positive operation counts, so a zero is not automatically treated as missing. The data-quality service defines flagged rows as internally imputed observations, but the absent raw records and imputation rule are not available for audit.
- Representative processed rows include a flagged `(74, 2017-08-17, 0.0, 0.0, 1)`, a non-missing zero `(87, 2017-08-16, 0.0, 4.0, 0)`, and a negative `(74, 2017-08-20, -12.2379214088, 12.0, 0)`. The 8,352 raw-backed ATM-days are now traceable to the supplied operation file; the flagged rows remain traceable only to the processed missing-observation policy because no underlying operations exist for them.

Accordingly, negative values are verified signed-flow observations, not verified withdrawals or “bad” values. They may represent net deposits/withdrawals, balance movement, reversals, or another source convention; the column name alone is insufficient to choose among those interpretations. They must not be clipped to zero. The 109 flagged rows are explicit zero placeholders in the processed file, while 1,119 ATM/date pairs are absent across the overall date range; neither case supplies a reliable withdrawal-demand label.

The separate onboarding path accepts operation-level `withdrawal`, `cash_withdrawal`, `deposit`, and `cash_deposit` records and aggregates their signed `amount` values by ATM/date. That is an application upload contract, not evidence of how the historical processed CSV was produced, and it currently does not establish a governed sign convention or a nonnegative withdrawal target. The current model therefore forecasts **next-day signed net cash flow**, not ATM withdrawal demand.

The upload validator currently requires nonnegative `amount` values and stores the amount without applying an operation-type sign mapping. This is suitable only as an ingestion contract for separately governed records; it is not a verified historical cash-flow derivation and must not be used to infer withdrawal demand.

The application CSV upload intentionally accepts only the operational schema
`atm_id`, `datetime`, `operation_type`, and nonnegative `amount`. It explicitly
rejects raw Kaggle operation files containing `operation_value`, two-column
prediction inputs containing only `datetime` and `atm_id`, unsupported extra
columns, empty files, and malformed CSV. Raw Kaggle training files must use the
separate signed-flow reconstruction path in
`backend/app/data/tinkoff_history.py`; duplicate raw transactions are retained
when calculating the daily `operation_value` sum and are not converted into
operational withdrawal records.

### Target decision

No separate nonnegative demand target was implemented. A reliable withdrawal-demand field cannot be derived from the available processed data without inventing a sign convention or converting net flow by clipping, which would be scientifically invalid. The platform should remain characterized as a net-cash-flow forecasting prototype until an approved source snapshot supplies at least withdrawal amount/count, deposit amount/count, ATM cash balance, capacity, replenishment events/amounts, service availability, and cash-out/shortage outcomes with stable ATM identity and units.

## Target and forecast horizon

- Target: the observed `daily_cash_flow` on exactly the next calendar date, configured as `next_day_cash_flow`. Each ATM is independently reindexed to a calendar grid for feature/target alignment; a candidate is excluded if that next date has no record or is flagged `is_missing_observation=1`. Flagged placeholders are excluded from both targets and feature values rather than treated as zero flow.
- Horizon evaluated: one day ahead only.
- The production artifact uses a 50/50 Linear Regression + Random Forest ensemble.
- Features use per-ATM lagged values, rolling values shifted before the target, calendar fields, operation counts, and missing-observation flags.
- No learned preprocessing transform is used; missing feature values are filled with zero.

Zero targets remain in MAE, RMSE, and bias calculations. WAPE is `sum(abs(error)) / sum(abs(actual))`; a zero-only evaluation window would be reported as undefined. Rows without a previous-week value are excluded only from that baseline. This dataset has enough nonzero absolute target mass for WAPE in every reported aggregate.

## Methodology

[evaluate_production_forecast.py](../experiments/evaluate_production_forecast.py) performs the reproducible comparison:

1. Validates required columns, nulls, duplicate ATM/date rows, and date ordering.
2. Builds the production feature list without using future values.
3. Splits on unique forecast dates: 60% train, 20% validation, 20% test.
4. Compares the persisted ensemble, an equivalent ensemble retrained on the training prefix, an expanding historical-mean baseline, and the previous-week same-weekday baseline.
5. Runs five rolling-origin folds with 14-day test windows.
6. Reports MAE, RMSE, WAPE, mean signed bias, bias as a percentage of absolute actual flow, and under-forecast rate.

The test period is 2018-06-27 through 2018-09-30 with 1,920 ATM-day predictions. Model selection was not performed using test results; the retrained model is the existing production architecture, used as a leakage-resistant comparison to the persisted artifact.

## Calendar-aligned re-evaluation (2026-10-16)

The earlier results below used the previous next-available-row methodology and
are retained as historical evidence only. The current evaluator uses exact
next-calendar-day targets. Of 8,461 source rows, 109 flagged placeholders are
not observations; among the remaining 8,352 observed rows, 20 candidates had
no next-calendar-day record and 69 had a next-day placeholder. The corrected
feature frame therefore contains **8,263** valid targets.

The corrected unique-date 60/20/20 holdout is 2018-06-28 through 2018-09-30
with **1,840** predictions. The persisted artifact is evaluated only as an
existing artifact: its original training procedure used the former alignment
and cannot be reproduced safely from this repository, so it has not been
replaced. The retrained equivalent uses the corrected labels solely for a
time-safe comparison.

| Method | Samples | MAE | RMSE | WAPE | Mean bias | Underforecast |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| Expanding historical mean | 1,840 | 286.53 | 406.10 | 72.24% | -166.14 | 63.37% |
| Previous-week same weekday | 1,840 | 332.72 | 451.96 | 83.89% | -18.16 | 52.55% |
| Persisted production ensemble | 1,840 | **252.53** | **350.72** | **63.67%** | -41.01 | 48.42% |
| Retrained equivalent ensemble | 1,840 | 254.87 | 359.59 | 64.26% | -54.77 | 50.65% |

Across five corrected 14-day rolling-origin folds, the unweighted mean results
were: historical mean 286.15 MAE / 407.49 RMSE / 72.59% WAPE; previous-week
baseline 339.76 / 465.39 / 86.61%; persisted ensemble **253.19 / 355.67 /
64.31%**; and retrained equivalent 253.52 / **349.08** / 64.48%. These figures
show a valid comparison on the revised signed-flow target, not a demand-model
improvement or an operational claim.

## Holdout results

| Method | Samples | MAE | RMSE | WAPE | Mean bias | Bias / abs actual | Underforecast |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| Expanding historical mean | 1,920 | 288.62 | 412.46 | 73.72% | -162.35 | -41.47% | 62.45% |
| Previous-week same weekday | 1,920 | 339.60 | 472.31 | 86.74% | -8.26 | -2.11% | 51.82% |
| Persisted production ensemble | 1,920 | **256.90** | **360.05** | **65.61%** | -39.42 | -10.07% | 47.71% |
| Retrained equivalent ensemble | 1,920 | 260.24 | 367.61 | 66.47% | -40.75 | -10.41% | 48.70% |

The persisted artifact beats both baselines on MAE, RMSE, and WAPE on this holdout. The retrained equivalent also beats both baselines, but is slightly worse than the persisted artifact on this holdout. Because the repository does not contain the original training script, training cutoff, or training timestamp for `phase4-production-50-50`, the persisted result may be optimistic.

## Rolling-origin results

Values below are unweighted means across five 14-day folds; each fold trains only on dates before its test window.

| Method | Mean MAE | Mean RMSE | Mean WAPE | Mean bias | Mean underforecast |
| --- | ---: | ---: | ---: | ---: | ---: |
| Expanding historical mean | 289.38 | 415.51 | 74.17% | -155.51 | 61.29% |
| Previous-week same weekday | 345.70 | 482.21 | 89.06% | -6.28 | 51.57% |
| Persisted production ensemble | **257.98** | 366.42 | 66.21% | -36.11 | 46.50% |
| Retrained equivalent ensemble | 258.88 | **361.23** | **66.54%** | -2.26 | 43.93% |

The retrained ensemble has the best rolling-origin RMSE, bias, and under-forecast rate among the model variants, while the persisted artifact has marginally better mean MAE and WAPE. Both model variants outperform both baselines on the aggregate rolling metrics.

## Holdout results by ATM

Each ATM contributes 96 holdout predictions. The persisted ensemble has lower MAE and WAPE than the previous-week baseline for all 20 ATM identifiers in this holdout.

| ATM | Persisted MAE | Weekday MAE | Persisted WAPE | Weekday WAPE |
| ---: | ---: | ---: | ---: | ---: |
| 74 | 629.68 | 695.60 | 56.84% | 62.79% |
| 85 | 274.79 | 336.14 | 51.10% | 62.51% |
| 86 | 200.03 | 230.43 | 84.96% | 97.87% |
| 87 | 287.52 | 358.60 | 81.00% | 101.02% |
| 88 | 258.97 | 320.08 | 64.55% | 79.78% |
| 90 | 234.18 | 310.98 | 56.42% | 74.92% |
| 91 | 224.48 | 314.52 | 92.74% | 129.93% |
| 93 | 277.95 | 392.11 | 42.90% | 60.53% |
| 94 | 174.26 | 251.23 | 55.46% | 79.96% |
| 96 | 185.58 | 234.71 | 81.70% | 103.33% |
| 97 | 249.96 | 331.66 | 76.53% | 101.54% |
| 98 | 160.92 | 227.20 | 62.69% | 88.51% |
| 99 | 286.16 | 388.19 | 84.03% | 113.99% |
| 100 | 271.41 | 409.20 | 78.67% | 118.61% |
| 101 | 277.73 | 383.04 | 80.45% | 110.96% |
| 102 | 243.52 | 348.48 | 94.50% | 135.23% |
| 103 | 277.34 | 335.27 | 54.48% | 65.86% |
| 104 | 275.73 | 417.21 | 57.61% | 87.17% |
| 105 | 268.97 | 390.55 | 70.31% | 102.09% |
| 106 | 78.78 | 116.83 | 75.11% | 111.39% |

## Leakage and methodology audit

Positive findings:

- The production feature builder computes lags and rolling values within each ATM group and shifts them before the target.
- The target/horizon alignment now uses an ATM-specific calendar grid and excludes non-consecutive pairs and missing placeholders. Calendar lag features likewise remain null when the required earlier calendar date is absent; no later/earlier observation is borrowed.
- The evaluator uses unique-date cutoffs, so train and test do not share a calendar date.
- The processed history has no duplicate ATM/date rows.
- Per-ATM coverage is incomplete: the full 20-ATM date span contains 9,580 expected ATM-days, 8,461 rows, 1,119 unobserved ATM-days, and 109 explicit internally imputed rows. The evaluator does not silently insert or impute the absent dates.
- Missing flags are retained as a feature and are not rewritten as genuine zero demand. Missing-flagged rows remain in the target evaluation when they are the observed next-day row, so the results are for the supplied signed-flow series rather than a cleaned demand series.
- Artifact feature order, model checksums, and scikit-learn compatibility were verified when the persisted bundle loaded.

Limitations found:

- The existing generic `chronological_split` splits rows rather than unique dates. With multiple ATMs, that can place different ATMs from the same date in different partitions. The new evaluator does not use that split.
- The synthetic `create_time_series_features` path applies global forward-fill after grouping, which can carry values across ATM boundaries. It is not used by the new production-history evaluator, but it should not be used as evidence of production accuracy without correction.
- The original artifact training code, cutoff, validation result, and training timestamp are not present. `model_config.json` records a dataset hash and model version but not a reproducible training procedure.
- The processed history includes explicit missing-observation rows and negative signed flow values. Their business meaning must be confirmed before treating the target as cash demand.
- The older generic `chronological_split` is row-based and can split one calendar date across partitions; the new evaluator uses unique-date boundaries. The persisted artifact's original training dates and procedure remain unknown, so its holdout result is potentially optimistic even though the retrained comparison is time-safe.

## Operational consequences

Shortage events, excess-cash exposure, and replenishment frequency cannot be assessed from this dataset. It has no aligned cash-on-hand history, ATM capacity history, replenishment events, service outages, or actual cash-out labels. The application’s seeded inventory/replenishment records are not a historical operational evaluation set. No business savings or cash-out reduction is inferred from the forecast metrics.

## Reproduction

From the repository root:

```powershell
$env:PYTHONPATH = "backend"
.\.venv\Scripts\python.exe experiments\evaluate_production_forecast.py --history <path-to-authorized-local-history.csv> --output tmp\model-evaluation.json
Remove-Item Env:PYTHONPATH
```

The output JSON is a generated local artifact and should not be committed unless a documented reporting workflow requires it.

## Conclusion and next acceptance gate

The current architecture is **better than the measured baselines** on this processed holdout and across five rolling-origin folds. It is nevertheless **PROMISING BUT NOT YET VALIDATED** for a controlled pilot because the target semantics, original artifact provenance, and operational outcome data are insufficient.

The next gate is to obtain an approved nonnegative withdrawal-demand target with aligned cash inventory and replenishment outcomes, reproduce training from a declared cutoff, and repeat the rolling-origin evaluation. Only then should shortage/excess/replenishment consequences and pilot readiness be assessed. Until then this is suitable for research demonstration, not controlled-pilot or operational claims.

## Reproducibility verdict

**SIGNED FLOW REPRODUCED IN PRIOR AUTHORIZED LOCAL EVIDENCE; WITHDRAWAL DEMAND UNAVAILABLE.** The monetary unit, operation-type/sign semantics, missing-observation construction, and withdrawal-demand target are not established in this publishing snapshot.
