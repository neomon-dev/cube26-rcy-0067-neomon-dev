# neomon-dev · Recovery Manager

## What this build includes

- A headless Recovery Manager at `/home/runner/work/cube26-rcy-0067-neomon-dev/cube26-rcy-0067-neomon-dev/submissions/neomon-dev/agent/recovery_manager.py`
- CSV ingestion for fee report + upstream evidence files
- Per-charge decisioning: `SUPPORTS_CHARGE`, `CONTRADICTS_CHARGE`, `INSUFFICIENT`
- Claim recommendation output with explicit reason and evidence record IDs

## Run

```bash
python /home/runner/work/cube26-rcy-0067-neomon-dev/cube26-rcy-0067-neomon-dev/submissions/neomon-dev/agent/recovery_manager.py
```

Optional:

```bash
python /home/runner/work/cube26-rcy-0067-neomon-dev/cube26-rcy-0067-neomon-dev/submissions/neomon-dev/agent/recovery_manager.py \
  --data-dir /home/runner/work/cube26-rcy-0067-neomon-dev/cube26-rcy-0067-neomon-dev/data \
  --output /home/runner/work/cube26-rcy-0067-neomon-dev/cube26-rcy-0067-neomon-dev/submissions/neomon-dev/agent/outputs/claims.json
```

## Output

The run writes a JSON payload with:

- `summary`: total evaluated charges, claims recommended, total amount, decision breakdown
- `claims`: one entry per report line with reason and evidence references

## Assumptions

- Sample upstream files are used as stand-ins for round integration contract data.
- `fulfilment_fee_weight_tier` is marked `INSUFFICIENT` when no authoritative weight-tier source is present.
- Claim recommendations are only made when evidence contradicts a positive dollar charge.

## Limitations

- Uses rules-based logic, not a learned model.
- Uses fixture schema from this repository and does not yet ingest alternate contract variants.
- Precision/recall metrics against a labelled eval set are not included yet.
