# Authorized Raw-Source Acquisition and Verification

## Current status

**Audited:** 2026-10-16
**Result:** An authorized local snapshot was previously used to reproduce the
signed ATM-day target. The raw/private files are not included here, and a
withdrawal-demand target remains unavailable.

The local files used for that verification were `train_kaggle.csv` and
`test_file.csv`; they are excluded from this repository. Their authorization
reference, download timestamp, and terms-acceptance record must remain in the
applicable private registry.

`train_kaggle.csv` has 1,048,575 valid operation rows, five fields
(`datetime`, `atm_id`, `operation_type`, `client_id`, and `operation_value`),
20 ATMs, and date-only values from 2017-06-09 through 2018-09-30.
`test_file.csv` has 116,308 rows and only `datetime` and `atm_id`; it cannot
independently derive a target. The training file contains 11,289 exact duplicate
raw rows. They are intentionally retained in the verified aggregation because
the processed operation counts include them.

The official competition page defines its target as the sum of values of all
operations for each ATM-day. Applying that literal formula to the supplied
date-only `datetime` field and `operation_value`, without deduplication or sign
conversion, yields 8,352 ATM-days. Every one matches the corresponding
`daily_cash_flow` and `operation_count` in
`data/processed/atm_daily_history.csv` (maximum absolute floating-point delta
`4.55e-13`). The 109 processed ATM-days absent from raw aggregation are exactly
the existing rows with `is_missing_observation=1`, `daily_cash_flow=0`, and
`operation_count=0`; no raw ATM-day is absent from the processed file.

This validates the signed-flow aggregation, not the currency/unit, operation
type semantics, or missing-observation construction. The supplied numeric codes
are `0`, `1`, `2`, `4`, `5`, and `6`; no official code dictionary was supplied.
Several codes contain both positive and negative values. Therefore the dataset
does not support classifying a code as a withdrawal or deriving a nonnegative
withdrawal-demand series.

## Approved source to request/download

Use the official Tinkoff ATM Competition data page:

<https://www.kaggle.com/competitions/tinkoffatm/data>

Access must be through an account authorized to accept the competition's terms.
Do not use an unofficial mirror, scraped copy, or a dataset whose provenance,
version, and authorization cannot be recorded. The official page identifies
these expected upstream files:

- `train_kaggle.csv`
- `test_kaggle.csv`
- `kaggle_partners_2015_2016.csv`

These names are a source-family check, not proof that any particular download
reproduces the local processed data.

## What to retain with the download

Before any transformation, retain the original files unchanged in a private,
access-controlled location. Record the following in a source manifest stored
alongside the private data or in an approved internal registry:

- official source URL and competition/dataset title;
- account or organizational authorization reference (not credentials);
- terms/license accepted, access date/time, and dataset/version or download
  timestamp;
- original filename, byte size, SHA-256 checksum, encoding, delimiter, and
  header list for every file;
- any accompanying data dictionary, competition rules, or operation-type code
  table; and
- the authorized storage location and retention/access restrictions.

Do not add credentials, tokens, personal data, or unapproved raw transaction
files to Git. Raw files may be placed in `data/raw/tinkoff/` only after the
applicable data-governance decision permits local storage; keep them ignored or
otherwise outside version control unless their license and review explicitly
allow publication.

## Minimum fields required for signed-flow reconstruction

For every operation-level record used, preserve the raw values for:

- ATM identifier (`atm_id`) and a documented map to the processed identifiers;
- operation timestamp (`datetime` or equivalent), including source timezone;
- operation type/code and its official semantics;
- monetary value (`operation_value` and/or `trxn_amt_rub`) and its unit; and
- transaction count/record identity sufficient to detect duplicates.

`train_kaggle.csv` and the related metadata must be inspected rather than
assumed to establish which of these fields applies. `test_kaggle.csv` alone
cannot establish historical labels if it omits the relevant operation values.

## Additional evidence required for a withdrawal-demand target

Signed net cash flow is not withdrawal demand. To derive and validate a
nonnegative withdrawal target, obtain or formally document:

- the operation-type code(s) that represent customer cash withdrawals;
- whether amount signs encode direction, reversal, correction, or another
  meaning, plus the authoritative sign convention;
- withdrawal amount and, where available, withdrawal count separately from
  deposits and non-cash operations;
- timezone and ATM-local calendar-day boundary;
- cash-on-hand history, ATM capacity, replenishment events/amounts, service
  availability, and cash-out/shortage outcomes for operational evaluation;
- stable ATM identity mapping across operations, balances, replenishments, and
  the current processed history; and
- a documented duplicate, reversal, cancellation, and late-arrival policy.

Without these inputs, do not clip negative net flow, infer withdrawals from its
absolute value, or label predictions as demand.

## Required reproduction procedure after authorization

1. Inventory every received file and create the source manifest above.
2. Profile schemas, row counts, date ranges, ATM identifiers, nulls, duplicate
   keys, operation codes, and amount distributions without modifying the raw
   files.
3. Obtain written or official documentation for the aggregation formula,
   operation-type/sign mapping, timezone, units, missing-date policy, and ATM
   mapping. If any is unavailable, report reconstruction as inconclusive.
4. Implement the derivation as a separately reviewed, deterministic script that
   reads immutable raw input and writes a new comparison artifact; it must not
   overwrite the current processed CSV.
5. Compare all ATM/date keys and values against
   `data/processed/atm_daily_history.csv`, reporting matches, missing/extra
   keys, numeric discrepancies, operation-count discrepancies, and the 109
   currently flagged missing observations.
6. Derive a withdrawal-only series only when the source semantics above are
   verified. Reindex or exclude non-consecutive calendar-day pairs before any
   next-day evaluation; do not use an unrestricted `shift(-1)` across date
   gaps.
7. Re-run chronological and rolling-origin evaluation only after the target
   definition and lineage review pass. Operational claims also require the
   aligned inventory/replenishment/cash-out outcomes listed above.

### Reproducible local verification

From the repository root, run the focused aggregation tests:

```powershell
.\.venv\Scripts\python.exe -m pytest backend/tests/test_data_provenance.py -q
```

To repeat the reconciliation without changing either input file:

```powershell
$env:PYTHONPATH = "backend"
.\.venv\Scripts\python.exe -c "from pathlib import Path; from app.data.tinkoff_history import reconstruct_tinkoff_signed_daily_flow; print(reconstruct_tinkoff_signed_daily_flow(Path('data/raw/tinkoff/train_kaggle.csv')).head())"
Remove-Item Env:PYTHONPATH
```

For the full comparison, aggregate with
`reconstruct_tinkoff_signed_daily_flow`, outer-join it to
`data/processed/atm_daily_history.csv` on normalized `atm_id` and date, and
report both key coverage and the two numeric deltas. Do not overwrite the
processed history.

## Acceptance evidence

The signed-flow provenance gate passed in prior authorized local evidence for
`train_kaggle.csv`: a reviewer can reproduce the ATM-day sum and inspect the
record-level key/value comparison when the private source is available. The
withdrawal-demand gate remains blocked until a code dictionary,
direction/sign semantics, monetary unit, and the operational outcome inputs
listed above are supplied. The project remains a signed-net-cash-flow prototype
and model tuning is out of scope.
