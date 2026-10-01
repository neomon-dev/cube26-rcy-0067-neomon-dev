from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional


# ============================================================
# VERDICTS
# ============================================================

class Verdict(str, Enum):
    CONTESTED = "contested"
    ACCEPTED = "accepted"
    INSUFFICIENT_EVIDENCE = "insufficient_evidence"
    ALREADY_REIMBURSED = "already_reimbursed"
    OUT_OF_WINDOW = "out_of_window"


# ============================================================
# EVIDENCE STATUS
# ============================================================

class EvidenceStatus(str, Enum):
    SUPPORTS = "supports"
    CONTRADICTS = "contradicts"
    INSUFFICIENT = "insufficient"
    NOT_APPLICABLE = "not_applicable"


# ============================================================
# CHARGE
# ============================================================

@dataclass
class Charge:
    charge_id: str
    line_id: str
    report_type: str

    charge_type: str
    charge_subtype: Optional[str]

    description: str
    granularity: str

    unit_id: Optional[str]
    org_id: str

    sku: Optional[str]
    fnsku: Optional[str]
    asin: Optional[str]

    shipment_id: Optional[str]
    order_id: Optional[str]

    quantity: float

    currency: str

    amount_per_unit: float
    amount_total: float

    posted_date: Optional[str] = None


# ============================================================
# REIMBURSEMENT
# ============================================================

@dataclass
class Reimbursement:
    reimbursement_id: str

    case_id: Optional[str]
    approval_date: Optional[str]

    amazon_order_id: Optional[str]

    sku: Optional[str]
    fnsku: Optional[str]
    asin: Optional[str]

    reason: str
    condition: Optional[str]

    currency: str

    amount_per_unit: float
    amount_total: float

    quantity_reimbursed_cash: float
    quantity_reimbursed_inventory: float

    original_reimbursement_id: Optional[str]

    org_id: Optional[str] = None


# ============================================================
# EVIDENCE RECORD
# ============================================================

@dataclass
class EvidenceRecord:
    source: str
    record_id: str

    unit_id: str
    org_id: str

    data: Dict[str, Any] = field(
        default_factory=dict
    )

    event_date: Optional[str] = None


# ============================================================
# UNIT EVIDENCE
# ============================================================

@dataclass
class UnitEvidence:
    """
    All upstream evidence associated with one unit.
    """

    unit_id: str
    org_id: str

    receiving: List[EvidenceRecord] = field(
        default_factory=list
    )

    prep: List[EvidenceRecord] = field(
        default_factory=list
    )

    pack: List[EvidenceRecord] = field(
        default_factory=list
    )

    returns: List[EvidenceRecord] = field(
        default_factory=list
    )

    contradictions: List[str] = field(
        default_factory=list
    )

    missing_sources: List[str] = field(
        default_factory=list
    )


# ============================================================
# EVIDENCE CHECK
# ============================================================

@dataclass
class EvidenceCheck:
    """
    Contract-defined evidence interpretation.

    Example:

        check_key = "polybag_present"
        status = EvidenceStatus.SUPPORTS
        value = "pass"
    """

    source: str
    check_key: str

    status: EvidenceStatus

    value: Optional[str]

    reason: str

    fields: List[str] = field(
        default_factory=list
    )

    event_date: Optional[str] = None


# ============================================================
# AGENT EVIDENCE
# ============================================================

@dataclass
class AgentEvidence:
    """
    Legacy compatibility structure.

    The current Gemini agent uses its own Pydantic
    AgentCheck / AgentResult structures, then converts
    them into EvidenceCheck objects.
    """

    unit_id: str

    charge_assessment: str

    evidence_interpretation: str

    checks: List[EvidenceCheck] = field(
        default_factory=list
    )

    supporting_evidence: List[str] = field(
        default_factory=list
    )

    uncertainty_reasons: List[str] = field(
        default_factory=list
    )


# ============================================================
# RECOVERY DECISION
# ============================================================

@dataclass
class RecoveryDecision:
    """
    Final deterministic Recovery Manager decision.
    """

    charge_id: str
    unit_id: Optional[str]

    charge_type: str
    amount_total: float

    verdict: Verdict

    recommended_claim_amount: float

    checks: List[EvidenceCheck] = field(
        default_factory=list
    )

    supporting_evidence: List[str] = field(
        default_factory=list
    )

    reasons: List[str] = field(
        default_factory=list
    )

    uncertainty_reasons: List[str] = field(
        default_factory=list
    )

    evidence_complete: bool = False

    already_reimbursed_amount: float = 0.0

    window_status: str = "unknown"

    model_status: str = "not_run"