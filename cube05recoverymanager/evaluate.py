import json
import os
import time
from collections import Counter
from pathlib import Path

from src.loader import DataLoader
from src.evidence_joiner import EvidenceJoiner
from src.agent import RecoveryAgent, agent_checks_to_models
from src.decision_engine import decide_charge


# ============================================================
# CONFIG
# ============================================================

MODEL_NAME = os.getenv(
    "GEMINI_MODEL",
    "gemini-3.8-flash",
)

CLAIM_WINDOW_DAYS = os.getenv(
    "CLAIM_WINDOW_DAYS"
)

if CLAIM_WINDOW_DAYS in (
    None,
    "",
):
    CLAIM_WINDOW_DAYS = 120
else:
    CLAIM_WINDOW_DAYS = int(
        CLAIM_WINDOW_DAYS
    )


# Gemini free/rate-limited configuration
RPM = 5


# ============================================================
# HELPERS
# ============================================================

def get_all_evidence(
    unit_evidence,
):
    """
    Convert UnitEvidence into the flat EvidenceRecord list
    expected by RecoveryAgent.
    """

    if unit_evidence is None:
        return []

    return (
        list(
            getattr(
                unit_evidence,
                "receiving",
                [],
            )
            or []
        )
        + list(
            getattr(
                unit_evidence,
                "prep",
                [],
            )
            or []
        )
        + list(
            getattr(
                unit_evidence,
                "pack",
                [],
            )
            or []
        )
        + list(
            getattr(
                unit_evidence,
                "returns",
                [],
            )
            or []
        )
    )


def get_key():

    try:

        import tomllib

        secret_file = Path(
            ".streamlit/secrets.toml"
        )

        if secret_file.exists():

            with open(
                secret_file,
                "rb",
            ) as f:

                secrets = tomllib.load(
                    f
                )

            key = secrets.get(
                "GEMINI_API_KEY"
            )

            if key:
                return key

    except Exception as exc:

        print(
            f"Could not load Streamlit secret: {exc}",
            flush=True,
        )

    return os.getenv(
        "GEMINI_API_KEY"
    )


def safe_amount(value):

    try:
        return float(
            value or 0
        )
    except Exception:
        return 0.0


# ============================================================
# EVALUATION
# ============================================================

def evaluate():

    loader = DataLoader()

    joiner = EvidenceJoiner(
        loader
    )

    orgs = loader.get_orgs()

    api_key = get_key()

    agent = None

    if api_key:
        agent = RecoveryAgent(
            api_key=api_key,
            model_name=MODEL_NAME,
        )

    totals = Counter()
    verdict_counts = Counter()
    failure_modes = Counter()

    results = []

    model_runs = 0
    model_successes = 0
    model_failures = 0

    last_model_call = 0.0

    # ========================================================
    # ORGANIZATIONS
    # ========================================================

    for org_id in orgs:

        charges = loader.get_charges(
            org_id=org_id
        )

        reimbursements = (
            loader.get_reimbursements(
                org_id=org_id
            )
        )

        # ----------------------------------------------------
        # Group charges by unit.
        # ----------------------------------------------------

        units = {}

        for charge in charges:

            if charge.unit_id:

                units.setdefault(
                    charge.unit_id,
                    [],
                ).append(
                    charge
                )

        # ----------------------------------------------------
        # Evaluate each unit
        # ----------------------------------------------------

        for unit_id, unit_charges in units.items():

            # Only invoke Gemini where there is a positive
            # monetary charge with a potentially supported
            # evidence mapping.
            needs_model = any(
                safe_amount(
                    charge.amount_total
                ) > 0
                and str(
                    charge.charge_type or ""
                ).strip().lower()
                != "fulfilment_fee_weight_tier"
                for charge in unit_charges
            )

            normalized_checks = []

            model_status = "not_run"

            # ------------------------------------------------
            # Gemini evidence extraction
            # ------------------------------------------------

            if agent and needs_model:

                wait = (
                    60.0 / RPM
                    - (
                        time.monotonic()
                        - last_model_call
                    )
                )

                if (
                    last_model_call
                    and wait > 0
                ):
                    time.sleep(
                        wait
                    )

                last_model_call = (
                    time.monotonic()
                )

                model_runs += 1

                try:

                    unit_evidence = (
                        joiner.build_unit_evidence(
                            unit_id=unit_id,
                            org_id=org_id,
                        )
                    )

                    evidence_records = (
                        get_all_evidence(
                            unit_evidence
                        )
                    )

                    agent_result = (
                        agent.analyze_unit(
                            evidence_records
                        )
                    )

                    model_status = "completed"

                    normalized_checks = (
                        agent_checks_to_models(
                            agent_result
                        )
                    )

                    if not normalized_checks:
                        failure_modes[
                            "gemini_no_checks"
                        ] += 1

                    model_successes += 1

                except Exception as exc:

                    model_failures += 1

                    model_status = "failed"

                    failure_modes[
                        "gemini_error"
                    ] += 1

                    print(
                        f"Gemini error for "
                        f"{org_id}/{unit_id}: "
                        f"{exc}",
                        flush=True,
                    )

            # ------------------------------------------------
            # Decision for every charge
            # ------------------------------------------------

            for charge in unit_charges:

                decision = decide_charge(
                    charge=charge,
                    checks=normalized_checks,
                    reimbursements=reimbursements,
                    claim_window_days=(
                        CLAIM_WINDOW_DAYS
                    ),
                )

                verdict = decision.verdict.value

                verdict_counts[
                    verdict
                ] += 1

                amount = safe_amount(
                    charge.amount_total
                )

                recommended = safe_amount(
                    decision.recommended_claim_amount
                )

                totals[
                    "charges"
                ] += 1

                totals[
                    "amount"
                ] += amount

                totals[
                    "recommended"
                ] += recommended

                if recommended > 0:
                    totals[
                        "claims"
                    ] += 1

                else:
                    totals[
                        "review"
                    ] += 1

                results.append(
                    {
                        "organization_id": org_id,
                        "unit_id": unit_id,
                        "charge_id": charge.charge_id,
                        "charge_type": charge.charge_type,
                        "charge_subtype": charge.charge_subtype,
                        "amount": amount,
                        "verdict": verdict,
                        "recommended_claim_amount": recommended,
                        "model_status": model_status,
                        "checks": [
                            {
                                "check_key": c.check_key,
                                "status": c.status.value,
                                "value": c.value,
                                "reason": c.reason,
                            }
                            for c in (
                                decision.checks
                                or []
                            )
                        ],
                        "reasons": (
                            decision.reasons
                            or []
                        ),
                        "uncertainty_reasons": (
                            decision.uncertainty_reasons
                            or []
                        ),
                    }
                )

    # ========================================================
    # FAILURE-MODE SUMMARY
    # ========================================================

    # Count the major decision reasons so evaluation output
    # explains why claims were not recommended.

    for result in results:

        if (
            result[
                "recommended_claim_amount"
            ] > 0
        ):
            continue

        for reason in (
            result["reasons"]
            or []
        ):

            failure_modes[
                reason
            ] += 1

        for reason in (
            result[
                "uncertainty_reasons"
            ]
            or []
        ):

            failure_modes[
                reason
            ] += 1

    # ========================================================
    # OUTPUT
    # ========================================================

    print()
    print(
        "RECOVERY MANAGER EVALUATION"
    )

    print(
        f"Model: {MODEL_NAME}"
    )

    print(
        f"Charges: {totals['charges']} | "
        f"Amount: ${totals['amount']:.2f}"
    )

    print(
        f"Claims: {totals['claims']} | "
        f"Recommended: "
        f"${totals['recommended']:.2f}"
    )

    review_count = totals[
        "review"
    ]

    total_count = totals[
        "charges"
    ]

    review_rate = (
        review_count / total_count * 100
        if total_count
        else 0
    )

    print(
        f"Review: {review_count} "
        f"({review_rate:.2f}%)"
    )

    print(
        f"Verdicts: "
        f"{dict(verdict_counts)}"
    )

    print(
        "Gemini: "
        f"{{'model': '{MODEL_NAME}', "
        f"'runs': {model_runs}, "
        f"'successes': {model_successes}, "
        f"'failures': {model_failures}}}"
    )

    # Don't print an empty failure section.
    if failure_modes:

        print(
            "Failure modes: "
            f"{dict(failure_modes)}"
        )

    else:

        print(
            "Failure modes: {}"
        )

    # ========================================================
    # OPTIONAL JSON OUTPUT
    # ========================================================

    output_path = os.getenv(
        "EVALUATION_OUTPUT"
    )

    if output_path:

        payload = {
            "model": MODEL_NAME,
            "claim_window_days": (
                CLAIM_WINDOW_DAYS
            ),
            "charges": totals[
                "charges"
            ],
            "amount": round(
                totals["amount"],
                2,
            ),
            "claims": totals[
                "claims"
            ],
            "recommended": round(
                totals["recommended"],
                2,
            ),
            "review": review_count,
            "review_rate": review_rate,
            "verdicts": dict(
                verdict_counts
            ),
            "gemini": {
                "model": MODEL_NAME,
                "runs": model_runs,
                "successes": (
                    model_successes
                ),
                "failures": (
                    model_failures
                ),
            },
            "failure_modes": dict(
                failure_modes
            ),
            "results": results,
        }

        with open(
            output_path,
            "w",
            encoding="utf-8",
        ) as f:

            json.dump(
                payload,
                f,
                indent=2,
                default=str,
            )

        print(
            f"Saved evaluation to "
            f"{output_path}"
        )

    return results


if __name__ == "__main__":
    evaluate()