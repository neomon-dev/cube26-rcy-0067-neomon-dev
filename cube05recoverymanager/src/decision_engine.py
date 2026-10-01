from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

from .models import (
    Charge,
    EvidenceCheck,
    EvidenceStatus,
    RecoveryDecision,
    Verdict,
)


# ---------------------------------------------------------------------
# Recovery policy
# ---------------------------------------------------------------------

CLAIM_WINDOW_DAYS = 120


# ---------------------------------------------------------------------
# Evidence mappings
# ---------------------------------------------------------------------

CHARGE_CHECKS: Dict[str, List[str]] = {
    "lost_inbound": ["quantity_matches_po"],
    "damaged_in_warehouse": ["unit_undamaged"],
    "refund_issued_item_not_returned": ["condition_grade"],
    "customer_return_item_not_as_described": ["condition_grade"],
    "mis_ship": ["all_items_present", "quantities_correct"],
    "fulfilment_fee_weight_tier": [],
}


INBOUND_DEFECT_MAPPINGS: Dict[str, List[str]] = {
    "inbound_defect_unbagged": [
        "polybag_present",
    ],
    "missing_suffocation_warning": [
        "suffocation_warning_present",
        "suffocation_warning_legible",
    ],
    "unscannable_barcode": [
        "fnsku_label_flat",
        "fnsku_label_placement_valid",
    ],
    "manufacturer_barcode_visible": [
        "manufacturer_barcode_covered",
    ],
    "unplanned_prep_labelling": [
        "fnsku_label_placement_valid",
    ],
    "unplanned_prep_bagging": [
        "polybag_present",
        "polybag_sealed",
    ],
    "warehouse_damaged": [
        "unit_undamaged",
    ],
    "warehouse_lost": [
        "quantity_matches_po",
    ],
}


INBOUND_ALIASES = {
    "unbagged": "inbound_defect_unbagged",
    "polybag": "inbound_defect_unbagged",
    "missing_suffocation_warning": "missing_suffocation_warning",
    "suffocation_warning": "missing_suffocation_warning",
    "unscannable_barcode": "unscannable_barcode",
    "barcode_unscannable": "unscannable_barcode",
    "manufacturer_barcode_visible": "manufacturer_barcode_visible",
    "manufacturer_barcode": "manufacturer_barcode_visible",
    "unplanned_prep_labelling": "unplanned_prep_labelling",
    "unplanned_prep_labeling": "unplanned_prep_labelling",
    "unplanned_prep_bagging": "unplanned_prep_bagging",
    "warehouse_damaged": "warehouse_damaged",
    "warehouse_lost": "warehouse_lost",
}


# ---------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------

def _clean(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip().lower()


def _parse_date(value: Any) -> Optional[datetime]:
    if value is None:
        return None

    text = str(value).strip()

    if not text:
        return None

    try:
        if text.endswith("Z"):
            text = text[:-1] + "+00:00"

        dt = datetime.fromisoformat(text)

        return dt

    except Exception:
        pass

    # Common CSV date format.
    for fmt in (
        "%Y-%m-%d",
        "%Y/%m/%d",
        "%Y-%m-%d %H:%M:%S",
        "%Y/%m/%d %H:%M:%S",
    ):
        try:
            return datetime.strptime(text, fmt)
        except Exception:
            continue

    return None


def _same_timezone(
    first: datetime,
    second: datetime,
) -> Tuple[datetime, datetime]:

    if first.tzinfo is None and second.tzinfo is None:
        return first, second

    if first.tzinfo is None:
        first = first.replace(tzinfo=second.tzinfo)

    if second.tzinfo is None:
        second = second.replace(tzinfo=first.tzinfo)

    return first, second


def _evidence_before_or_on_charge(
    evidence_date: Any,
    charge_date: Any,
) -> bool:
    """
    Historical evidence is valid when it was captured on or before
    the charge posting date.

    Missing dates do NOT invalidate otherwise usable evidence.
    """

    evidence_dt = _parse_date(evidence_date)
    charge_dt = _parse_date(charge_date)

    if evidence_dt is None or charge_dt is None:
        return True

    evidence_dt, charge_dt = _same_timezone(
        evidence_dt,
        charge_dt,
    )

    return evidence_dt <= charge_dt


def _normalise_subtype(charge: Charge) -> Optional[str]:
    subtype = _clean(getattr(charge, "charge_subtype", None))

    if subtype:
        if subtype in INBOUND_DEFECT_MAPPINGS:
            return subtype

        if subtype in INBOUND_ALIASES:
            return INBOUND_ALIASES[subtype]

    description = _clean(
        getattr(charge, "description", None)
    )

    for alias, canonical in INBOUND_ALIASES.items():
        if alias in description:
            return canonical

    return None


def _required_keys(
    charge: Charge,
) -> Tuple[List[str], Optional[str]]:

    charge_type = _clean(
        getattr(charge, "charge_type", None)
    )

    if charge_type == "inbound_defect_fee":
        subtype = _normalise_subtype(charge)

        if subtype is None:
            return [], None

        return (
            INBOUND_DEFECT_MAPPINGS.get(subtype, []),
            subtype,
        )

    return CHARGE_CHECKS.get(charge_type, []), None


def _normalise_value(value: Any) -> str:
    return _clean(value).replace("-", "_").replace(" ", "_")


# ---------------------------------------------------------------------
# Claim-aware evidence interpretation
# ---------------------------------------------------------------------

def _claim_relation(
    subtype: Optional[str],
    check: EvidenceCheck,
) -> EvidenceStatus:

    value = _normalise_value(check.value)

    if not value:
        return EvidenceStatus.INSUFFICIENT

    # ---------------------------------------------------------------
    # Inbound unbagged
    # ---------------------------------------------------------------
    if subtype == "inbound_defect_unbagged":
        if value in {
            "no",
            "missing",
            "absent",
            "false",
            "not_present",
            "unbagged",
        }:
            return EvidenceStatus.SUPPORTS

        if value in {
            "yes",
            "present",
            "sealed",
            "true",
        }:
            return EvidenceStatus.CONTRADICTS

        return EvidenceStatus.INSUFFICIENT

    # ---------------------------------------------------------------
    # Missing suffocation warning
    # ---------------------------------------------------------------
    if subtype == "missing_suffocation_warning":

        if check.check_key == "suffocation_warning_present":
            if value in {
                "no",
                "missing",
                "absent",
                "false",
            }:
                return EvidenceStatus.SUPPORTS

            if value in {
                "yes",
                "present",
                "true",
            }:
                return EvidenceStatus.CONTRADICTS

        if check.check_key == "suffocation_warning_legible":
            if value in {
                "no",
                "missing",
                "absent",
                "illegible",
                "false",
            }:
                return EvidenceStatus.SUPPORTS

            if value in {
                "yes",
                "present",
                "legible",
                "true",
            }:
                return EvidenceStatus.CONTRADICTS

        if value == "not_required":
            return EvidenceStatus.INSUFFICIENT

        return EvidenceStatus.INSUFFICIENT

    # ---------------------------------------------------------------
    # Unscannable barcode / labelling
    # ---------------------------------------------------------------
    if subtype in {
        "unscannable_barcode",
        "unplanned_prep_labelling",
    }:

        if value in {
            "no",
            "missing",
            "absent",
            "invalid",
            "misplaced",
            "not_flat",
            "false",
        }:
            return EvidenceStatus.SUPPORTS

        if value in {
            "yes",
            "flat",
            "valid",
            "correct",
            "true",
        }:
            return EvidenceStatus.CONTRADICTS

        if value == "not_required":
            return EvidenceStatus.INSUFFICIENT

        return EvidenceStatus.INSUFFICIENT

    # ---------------------------------------------------------------
    # Manufacturer barcode visible
    # ---------------------------------------------------------------
    if subtype == "manufacturer_barcode_visible":

        if value in {
            "no",
            "uncovered",
            "visible",
            "false",
        }:
            return EvidenceStatus.SUPPORTS

        if value in {
            "yes",
            "covered",
            "true",
        }:
            return EvidenceStatus.CONTRADICTS

        return EvidenceStatus.INSUFFICIENT

    # ---------------------------------------------------------------
    # Unplanned prep bagging
    # ---------------------------------------------------------------
    if subtype == "unplanned_prep_bagging":

        if value in {
            "no",
            "missing",
            "absent",
            "unsealed",
            "false",
        }:
            return EvidenceStatus.SUPPORTS

        if value in {
            "yes",
            "present",
            "sealed",
            "true",
        }:
            return EvidenceStatus.CONTRADICTS

        if value == "not_required":
            return EvidenceStatus.INSUFFICIENT

        return EvidenceStatus.INSUFFICIENT

    # ---------------------------------------------------------------
    # Warehouse damaged
    # ---------------------------------------------------------------
    if subtype == "warehouse_damaged":

        if value in {
            "no",
            "damaged",
            "broken",
            "false",
        }:
            return EvidenceStatus.SUPPORTS

        if value in {
            "yes",
            "undamaged",
            "none",
            "true",
        }:
            return EvidenceStatus.CONTRADICTS

        return EvidenceStatus.INSUFFICIENT

    # ---------------------------------------------------------------
    # Generic checks
    # ---------------------------------------------------------------

    if check.status == EvidenceStatus.SUPPORTS:
        return EvidenceStatus.SUPPORTS

    if check.status == EvidenceStatus.CONTRADICTS:
        return EvidenceStatus.CONTRADICTS

    return EvidenceStatus.INSUFFICIENT


# ---------------------------------------------------------------------
# Reimbursement helpers
# ---------------------------------------------------------------------

def _reimbursement_matches(
    reimbursement: Any,
    charge: Charge,
) -> bool:

    if not isinstance(reimbursement, dict):
        try:
            reimbursement = vars(reimbursement)
        except Exception:
            return False

    charge_id = _clean(
        getattr(charge, "charge_id", None)
    )

    possible_ids = {
        _clean(reimbursement.get("charge_id")),
        _clean(reimbursement.get("line_id")),
        _clean(reimbursement.get("fee_id")),
    }

    if charge_id and charge_id in possible_ids:
        return True

    return False


def _reimbursement_amount(
    reimbursement: Any,
) -> float:

    if not isinstance(reimbursement, dict):
        try:
            reimbursement = vars(reimbursement)
        except Exception:
            return 0.0

    for key in (
        "amount",
        "amount_total",
        "amount_usd",
        "reimbursement_amount",
        "credited_amount",
    ):
        value = reimbursement.get(key)

        if value is None:
            continue

        try:
            return float(value)
        except Exception:
            continue

    return 0.0


def _net_reimbursement_amount(
    charge: Charge,
    reimbursements: Optional[List[Any]],
) -> float:

    if not reimbursements:
        return 0.0

    total = 0.0

    for reimbursement in reimbursements:
        if _reimbursement_matches(
            reimbursement,
            charge,
        ):
            total += _reimbursement_amount(
                reimbursement
            )

    return max(0.0, total)


# ---------------------------------------------------------------------
# Main decision function
# ---------------------------------------------------------------------

def decide_charge(
    charge: Charge,
    checks: Optional[List[EvidenceCheck]] = None,
    reimbursements: Optional[List[Any]] = None,
    evidence: Optional[Any] = None,
    claim_window_days: Optional[int] = CLAIM_WINDOW_DAYS,
) -> RecoveryDecision:

    checks = checks or []

    amount = float(
        getattr(charge, "amount_total", 0.0) or 0.0
    )

    charge_type = _clean(
        getattr(charge, "charge_type", None)
    )

    # ---------------------------------------------------------------
    # Zero / negative amount
    # ---------------------------------------------------------------

    if amount <= 0:
        return RecoveryDecision(
            charge_id=charge.charge_id,
            unit_id=getattr(charge, "unit_id", None),
            charge_type=charge_type,
            amount_total=amount,
            verdict=Verdict.INSUFFICIENT_EVIDENCE,
            recommended_claim_amount=0.0,
            checks=checks,
            reasons=[
                "Charge amount is zero; no monetary recovery claim is recommended."
            ],
            uncertainty_reasons=[
                "No recoverable monetary amount exists."
            ],
            evidence_complete=False,
            window_status="not_applicable",
            model_status="complete",
        )

    # ---------------------------------------------------------------
    # Reimbursements
    # ---------------------------------------------------------------

    reimbursed = _net_reimbursement_amount(
        charge,
        reimbursements,
    )

    if reimbursed >= amount:
        return RecoveryDecision(
            charge_id=charge.charge_id,
            unit_id=getattr(charge, "unit_id", None),
            charge_type=charge_type,
            amount_total=amount,
            verdict=Verdict.ALREADY_REIMBURSED,
            recommended_claim_amount=0.0,
            checks=checks,
            reasons=[
                "Charge has already been fully reimbursed."
            ],
            evidence_complete=True,
            already_reimbursed_amount=reimbursed,
            window_status="in_window",
            model_status="complete",
        )

    recoverable_amount = max(
        0.0,
        amount - reimbursed,
    )

    if recoverable_amount <= 0:
        return RecoveryDecision(
            charge_id=charge.charge_id,
            unit_id=getattr(charge, "unit_id", None),
            charge_type=charge_type,
            amount_total=amount,
            verdict=Verdict.INSUFFICIENT_EVIDENCE,
            recommended_claim_amount=0.0,
            checks=checks,
            reasons=[
                "No recoverable monetary amount exists."
            ],
            evidence_complete=False,
            already_reimbursed_amount=reimbursed,
            window_status="in_window",
            model_status="complete",
        )

    # ---------------------------------------------------------------
    # Mapping
    # ---------------------------------------------------------------

    required_keys, subtype = _required_keys(charge)

    if charge_type == "fulfilment_fee_weight_tier":
        return RecoveryDecision(
            charge_id=charge.charge_id,
            unit_id=getattr(charge, "unit_id", None),
            charge_type=charge_type,
            amount_total=amount,
            verdict=Verdict.INSUFFICIENT_EVIDENCE,
            recommended_claim_amount=0.0,
            checks=checks,
            reasons=[
                "Fulfilment fee weight tier has no documented Recovery evidence mapping."
            ],
            uncertainty_reasons=[
                "The Evidence Contract does not define a charge-to-evidence mapping for this charge type."
            ],
            evidence_complete=False,
            already_reimbursed_amount=reimbursed,
            window_status="unknown",
            model_status="complete",
        )

    if charge_type == "inbound_defect_fee" and subtype is None:
        return RecoveryDecision(
            charge_id=charge.charge_id,
            unit_id=getattr(charge, "unit_id", None),
            charge_type=charge_type,
            amount_total=amount,
            verdict=Verdict.INSUFFICIENT_EVIDENCE,
            recommended_claim_amount=0.0,
            checks=checks,
            reasons=[
                "Inbound defect subtype is missing or unmapped."
            ],
            uncertainty_reasons=[
                "The charge cannot be linked to a documented evidence check."
            ],
            evidence_complete=False,
            already_reimbursed_amount=reimbursed,
            window_status="unknown",
            model_status="complete",
        )

    if not required_keys:
        return RecoveryDecision(
            charge_id=charge.charge_id,
            unit_id=getattr(charge, "unit_id", None),
            charge_type=charge_type,
            amount_total=amount,
            verdict=Verdict.INSUFFICIENT_EVIDENCE,
            recommended_claim_amount=0.0,
            checks=checks,
            reasons=[
                "The charge cannot be linked to a documented evidence check."
            ],
            evidence_complete=False,
            already_reimbursed_amount=reimbursed,
            window_status="unknown",
            model_status="complete",
        )

    # ---------------------------------------------------------------
    # Find relevant checks
    # ---------------------------------------------------------------

    relevant: Dict[str, List[EvidenceCheck]] = {}

    for key in required_keys:
        relevant[key] = [
            c
            for c in checks
            if c.check_key == key
        ]

    # ---------------------------------------------------------------
    # Evaluate each required check
    # ---------------------------------------------------------------

    supporting: List[EvidenceCheck] = []
    contradictions: List[EvidenceCheck] = []
    uncertain: List[EvidenceCheck] = []
    missing: List[str] = []

    for key in required_keys:

        candidates = relevant.get(key, [])

        if not candidates:
            missing.append(key)
            continue

        key_support = False
        key_contradiction = False
        key_uncertain = False

        for check in candidates:

            relation = _claim_relation(
                subtype,
                check,
            )

            # A Gemini/fallback check must also be historically valid.
            if relation == EvidenceStatus.SUPPORTS:

                if _evidence_before_or_on_charge(
                    check.event_date,
                    charge.posted_date,
                ):
                    key_support = True

                else:
                    key_uncertain = True

            elif relation == EvidenceStatus.CONTRADICTS:
                key_contradiction = True

            else:
                key_uncertain = True

        if key_support:
            for check in candidates:
                relation = _claim_relation(
                    subtype,
                    check,
                )

                if relation == EvidenceStatus.SUPPORTS and _evidence_before_or_on_charge(
                    check.event_date,
                    charge.posted_date,
                ):
                    supporting.append(check)
                    break

        elif key_contradiction:
            for check in candidates:
                if (
                    _claim_relation(
                        subtype,
                        check,
                    )
                    == EvidenceStatus.CONTRADICTS
                ):
                    contradictions.append(check)
                    break

        elif key_uncertain:
            uncertain.extend(candidates)

        else:
            missing.append(key)

    # Remove duplicate check objects by key/source/reason.
    unique_supporting = []
    seen = set()

    for c in supporting:
        marker = (
            c.source,
            c.check_key,
            c.value,
            c.reason,
        )

        if marker not in seen:
            seen.add(marker)
            unique_supporting.append(c)

    supporting = unique_supporting

    # ---------------------------------------------------------------
    # Contradicting evidence
    # ---------------------------------------------------------------

    if contradictions:
        names = sorted(
            {
                c.check_key
                for c in contradictions
            }
        )

        return RecoveryDecision(
            charge_id=charge.charge_id,
            unit_id=getattr(charge, "unit_id", None),
            charge_type=charge_type,
            amount_total=amount,
            verdict=Verdict.CONTESTED,
            recommended_claim_amount=recoverable_amount,
            checks=checks,
            supporting_evidence=[
                c.reason for c in supporting
            ],
            reasons=[
                "Evidence contradicts the recovery claim for: "
                + ", ".join(names)
            ],
            uncertainty_reasons=[],
            evidence_complete=False,
            already_reimbursed_amount=reimbursed,
            window_status="in_window",
            model_status="complete",
        )

    # ---------------------------------------------------------------
    # Missing / uncertain evidence
    # ---------------------------------------------------------------

    if missing or uncertain or len(supporting) < len(required_keys):

        reasons = []

        if missing:
            reasons.append(
                "Required evidence checks are missing: "
                + ", ".join(sorted(set(missing)))
            )

        if uncertain:
            uncertain_names = sorted(
                {
                    c.check_key
                    for c in uncertain
                }
            )

            reasons.append(
                "Evidence is uncertain or insufficient for: "
                + ", ".join(uncertain_names)
            )

        return RecoveryDecision(
            charge_id=charge.charge_id,
            unit_id=getattr(charge, "unit_id", None),
            charge_type=charge_type,
            amount_total=amount,
            verdict=Verdict.INSUFFICIENT_EVIDENCE,
            recommended_claim_amount=0.0,
            checks=checks,
            supporting_evidence=[
                c.reason for c in supporting
            ],
            reasons=reasons,
            uncertainty_reasons=[
                "Not all required evidence checks support contesting the charge."
            ],
            evidence_complete=False,
            already_reimbursed_amount=reimbursed,
            window_status="in_window",
            model_status="complete",
        )

    # ---------------------------------------------------------------
    # Claim window
    # ---------------------------------------------------------------

    window_status = "in_window"

    charge_date = _parse_date(
        charge.posted_date
    )

    if (
        claim_window_days is not None
        and charge_date is not None
    ):
        now = datetime.now(
            timezone.utc
        )

        if charge_date.tzinfo is None:
            charge_date = charge_date.replace(
                tzinfo=timezone.utc
            )

        age_days = (
            now - charge_date
        ).total_seconds() / 86400.0

        if age_days > claim_window_days:
            window_status = "out_of_window"

            return RecoveryDecision(
                charge_id=charge.charge_id,
                unit_id=getattr(charge, "unit_id", None),
                charge_type=charge_type,
                amount_total=amount,
                verdict=Verdict.OUT_OF_WINDOW,
                recommended_claim_amount=0.0,
                checks=checks,
                supporting_evidence=[
                    c.reason for c in supporting
                ],
                reasons=[
                    f"Charge is outside the configured "
                    f"{claim_window_days}-day claim window."
                ],
                evidence_complete=True,
                already_reimbursed_amount=reimbursed,
                window_status=window_status,
                model_status="complete",
            )

    # ---------------------------------------------------------------
    # Fully supported claim
    # ---------------------------------------------------------------

    return RecoveryDecision(
        charge_id=charge.charge_id,
        unit_id=getattr(charge, "unit_id", None),
        charge_type=charge_type,
        amount_total=amount,
        verdict=Verdict.CONTESTED,
        recommended_claim_amount=recoverable_amount,
        checks=checks,
        supporting_evidence=[
            c.reason for c in supporting
        ],
        reasons=[
            "All required evidence checks support contesting the charge."
        ],
        uncertainty_reasons=[],
        evidence_complete=True,
        already_reimbursed_amount=reimbursed,
        window_status=window_status,
        model_status="complete",
    )