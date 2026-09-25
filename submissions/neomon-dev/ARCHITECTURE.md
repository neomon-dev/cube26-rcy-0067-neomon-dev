# Recovery Manager Architecture

## Flow

1. Read fee report lines.
2. Read upstream evidence tables (receiving, prep, pack, returns).
3. Join evidence to each fee line using `unit_id` and `order_id`.
4. Apply charge-type specific decision rules.
5. Emit structured per-line decisions and claim recommendations.

## Components

- **Ingestion layer**
  - CSV parser for fee and upstream datasets.
- **Evidence index**
  - Lookup maps keyed by `unit_id` and `order_id`.
- **Decision engine**
  - Rule set per `charge_type`.
  - Uses `PASS`/`FAIL`/`UNCERTAIN` token normalization.
- **Claim assembler**
  - Adds `recommend_claim`, `claim_amount_usd`, and evidence IDs.
- **Output writer**
  - Produces JSON report with summary + claims.

## Traceability

Each claim entry includes:

- fee report identifiers (`line_id`, `unit_id`, `order_id`)
- decision and reason
- evidence record IDs used for the decision

## Fail-open behavior

Missing evidence does not drop lines. The engine emits `INSUFFICIENT` with explicit reasons.
