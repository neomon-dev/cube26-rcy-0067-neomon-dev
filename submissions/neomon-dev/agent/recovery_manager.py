import argparse
import csv
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Iterable, List, Optional


PASS_TOKENS = {"yes", "all_present", "legible", "on_seam", "flat", "none", "not_required", "seal", "restock", "refurbish"}
FAIL_TOKENS = {"no", "not_sealed", "missing", "missing_components", "damaged", "liquidate", "dispose", "fail"}
UNCERTAIN_TOKENS = {"uncertain", "pending_review", "unknown"}


@dataclass
class Decision:
    status: str
    reason: str
    evidence_record_ids: List[str]
    can_claim: bool


def _read_csv(path: Path) -> List[dict]:
    with path.open(newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def _to_lookup(rows: Iterable[dict], key: str) -> Dict[str, List[dict]]:
    out: Dict[str, List[dict]] = {}
    for row in rows:
        out.setdefault((row.get(key) or "").strip(), []).append(row)
    return out


def _normalize(value: Optional[str]) -> str:
    return (value or "").strip().lower()


def _evidence_state(values: Iterable[str]) -> str:
    normalized = [_normalize(v) for v in values if _normalize(v)]
    if any(v in UNCERTAIN_TOKENS for v in normalized):
        return "uncertain"
    if any(v in FAIL_TOKENS for v in normalized):
        return "fail"
    if normalized and all(v in PASS_TOKENS for v in normalized):
        return "pass"
    return "insufficient"


def _get_record_ids(records: List[dict]) -> List[str]:
    ids = []
    for record in records:
        rid = (record.get("record_id") or "").strip()
        if rid:
            ids.append(rid)
    return ids


def evaluate_line(
    line: dict,
    receiving_by_unit: Dict[str, List[dict]],
    prep_by_unit: Dict[str, List[dict]],
    pack_by_order: Dict[str, List[dict]],
    returns_by_order: Dict[str, List[dict]],
) -> Decision:
    charge_type = _normalize(line.get("charge_type"))
    unit_id = (line.get("unit_id") or "").strip()
    order_id = (line.get("order_id") or "").strip()

    receiving = receiving_by_unit.get(unit_id, [])
    prep = prep_by_unit.get(unit_id, [])
    pack = pack_by_order.get(order_id, [])
    returns = returns_by_order.get(order_id, [])

    if charge_type == "inbound_defect_fee":
        if not prep:
            return Decision("INSUFFICIENT", "missing_prep_evidence", [], False)
        values = []
        for rec in prep:
            values.extend(
                [
                    rec.get("polybag_present_sealed"),
                    rec.get("suffocation_warning"),
                    rec.get("fnsku_label_placement"),
                    rec.get("original_barcode_covered"),
                    rec.get("expiry_date"),
                    rec.get("handling_marks"),
                ]
            )
        state = _evidence_state(values)
        ids = _get_record_ids(prep)
        if state == "pass":
            return Decision("CONTRADICTS_CHARGE", "prep_evidence_passed", ids, True)
        if state == "fail":
            return Decision("SUPPORTS_CHARGE", "prep_evidence_shows_defect", ids, False)
        return Decision("INSUFFICIENT", "prep_evidence_uncertain", ids, False)

    if charge_type == "lost_inbound":
        if not receiving:
            return Decision("INSUFFICIENT", "missing_receiving_evidence", [], False)
        rec = receiving[0]
        ids = _get_record_ids(receiving)
        ordered = int(rec.get("qty_ordered") or 0)
        received = int(rec.get("qty_received") or 0)
        state = _evidence_state([rec.get("identity_match"), rec.get("carton_damage"), rec.get("unit_damage")])
        if state == "uncertain":
            return Decision("INSUFFICIENT", "receiving_uncertain", ids, False)
        if received >= ordered and state == "pass":
            return Decision("CONTRADICTS_CHARGE", "receiving_confirms_full_inbound", ids, True)
        return Decision("SUPPORTS_CHARGE", "receiving_shows_inbound_gap_or_damage", ids, False)

    if charge_type == "damaged_in_warehouse":
        if not returns:
            return Decision("INSUFFICIENT", "missing_returns_evidence", [], False)
        values = []
        for rec in returns:
            values.extend([rec.get("observed_state"), rec.get("operator_disposition"), rec.get("identity_match")])
        state = _evidence_state(values)
        ids = _get_record_ids(returns)
        if state == "fail":
            return Decision("SUPPORTS_CHARGE", "returns_evidence_shows_damage", ids, False)
        if state == "pass":
            return Decision("CONTRADICTS_CHARGE", "returns_evidence_not_damaged", ids, True)
        return Decision("INSUFFICIENT", "returns_evidence_uncertain", ids, False)

    if charge_type == "refund_issued_item_not_returned":
        if returns:
            return Decision("CONTRADICTS_CHARGE", "return_record_exists", _get_record_ids(returns), True)
        if pack:
            return Decision("SUPPORTS_CHARGE", "order_shipped_but_no_return_record", _get_record_ids(pack), False)
        return Decision("INSUFFICIENT", "missing_pack_and_returns_evidence", [], False)

    if charge_type == "fulfilment_fee_weight_tier":
        return Decision("INSUFFICIENT", "weight_tier_source_not_available_in_upstream_records", _get_record_ids(prep), False)

    return Decision("INSUFFICIENT", "unknown_charge_type", [], False)


def build_claims(
    fee_rows: List[dict],
    receiving_rows: List[dict],
    prep_rows: List[dict],
    pack_rows: List[dict],
    returns_rows: List[dict],
) -> List[dict]:
    receiving_by_unit = _to_lookup(receiving_rows, "unit_id")
    prep_by_unit = _to_lookup(prep_rows, "unit_id")
    pack_by_order = _to_lookup(pack_rows, "order_id")
    returns_by_order = _to_lookup(returns_rows, "order_id")

    decisions = []
    for line in fee_rows:
        decision = evaluate_line(line, receiving_by_unit, prep_by_unit, pack_by_order, returns_by_order)
        amount = float(line.get("amount_usd") or 0)
        claim_amount = amount if decision.can_claim and amount > 0 else 0.0
        decisions.append(
            {
                "line_id": line.get("line_id"),
                "org_id": line.get("org_id"),
                "unit_id": line.get("unit_id"),
                "order_id": line.get("order_id"),
                "charge_type": line.get("charge_type"),
                "amount_usd": amount,
                "decision": decision.status,
                "reason": decision.reason,
                "recommend_claim": decision.can_claim and claim_amount > 0,
                "claim_amount_usd": round(claim_amount, 2),
                "evidence_record_ids": decision.evidence_record_ids,
            }
        )
    return decisions


def summarize(decisions: List[dict]) -> dict:
    total = len(decisions)
    claims = [d for d in decisions if d["recommend_claim"]]
    by_decision: Dict[str, int] = {}
    for d in decisions:
        by_decision[d["decision"]] = by_decision.get(d["decision"], 0) + 1
    return {
        "total_charges_evaluated": total,
        "claims_recommended": len(claims),
        "total_claim_amount_usd": round(sum(c["claim_amount_usd"] for c in claims), 2),
        "decision_breakdown": by_decision,
    }


def run(data_dir: Path, output_path: Path) -> None:
    fee_rows = _read_csv(data_dir / "fee_report_sample.csv")
    upstream = data_dir / "upstream"
    receiving_rows = _read_csv(upstream / "receiving_sample.csv")
    prep_rows = _read_csv(upstream / "prep_sample.csv")
    pack_rows = _read_csv(upstream / "pack_sample.csv")
    returns_rows = _read_csv(upstream / "returns_sample.csv")

    decisions = build_claims(fee_rows, receiving_rows, prep_rows, pack_rows, returns_rows)
    payload = {"summary": summarize(decisions), "claims": decisions}

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description="Run Recovery Manager over CSV fixtures")
    parser.add_argument(
        "--data-dir",
        type=Path,
        default=Path(__file__).resolve().parents[3] / "data",
        help="Path to data directory containing fee_report_sample.csv and upstream/",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path(__file__).resolve().parent / "outputs" / "claims.json",
        help="Output JSON file for claim decisions",
    )
    args = parser.parse_args()
    run(args.data_dir, args.output)


if __name__ == "__main__":
    main()
