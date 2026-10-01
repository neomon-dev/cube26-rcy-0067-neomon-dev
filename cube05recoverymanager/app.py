import streamlit as st

from src.loader import DataLoader
from src.evidence_joiner import EvidenceJoiner
from src.agent import RecoveryAgent, agent_checks_to_models
from src.check_normalizer import normalize_checks
from src.decision_engine import decide_charge


# ============================================================
# PAGE CONFIG
# ============================================================

st.set_page_config(
    page_title="Recovery Manager",
    page_icon="🛡️",
    layout="wide",
)


# ============================================================
# HEADER
# ============================================================

st.title("🛡️ Recovery Manager")
st.caption(
    "AI-assisted evidence-to-recovery analysis for charge disputes"
)


# ============================================================
# LOAD DATA
# ============================================================

@st.cache_resource
def load_data():
    loader = DataLoader()
    joiner = EvidenceJoiner(loader)
    return loader, joiner


loader, joiner = load_data()


# ============================================================
# SIDEBAR
# ============================================================

st.sidebar.header("Configuration")

orgs = loader.get_orgs()

if not orgs:
    st.error("No organisations were found in the dataset.")
    st.stop()


org_id = st.sidebar.selectbox(
    "Organisation",
    orgs,
)


# ============================================================
# LOAD CHARGES
# ============================================================

charges = loader.get_charges(
    org_id=org_id
)

if not charges:
    st.warning(
        "No charges found for this organisation."
    )
    st.stop()


# ============================================================
# LOAD REIMBURSEMENTS
# IMPORTANT: DEFINE THIS BEFORE DECISION ENGINE
# ============================================================

reimbursements = loader.get_reimbursements(
    org_id=org_id
)

if reimbursements is None:
    reimbursements = []


# ============================================================
# UNIT SELECTION
# ============================================================

unit_ids = sorted(
    {
        charge.unit_id
        for charge in charges
        if charge.unit_id
    }
)

if not unit_ids:
    st.warning(
        "No unit-level charges were found."
    )
    st.stop()


unit_id = st.sidebar.selectbox(
    "Unit",
    unit_ids,
)


# ============================================================
# SELECTED UNIT CHARGES
# ============================================================

unit_charges = [
    charge
    for charge in charges
    if charge.unit_id == unit_id
]


# ============================================================
# LOAD UNIT EVIDENCE
# ============================================================

unit_evidence = joiner.build_unit_evidence(
    unit_id=unit_id,
    org_id=org_id,
)


# ============================================================
# COMBINE EVIDENCE
# ============================================================

all_evidence = (
    list(unit_evidence.receiving or [])
    + list(unit_evidence.prep or [])
    + list(unit_evidence.pack or [])
    + list(unit_evidence.returns or [])
)


# ============================================================
# HEADER METRICS
# ============================================================

total_amount = sum(
    float(charge.amount_total or 0)
    for charge in unit_charges
)


evidence_count = len(all_evidence)


col1, col2, col3, col4 = st.columns(4)


with col1:
    st.metric(
        "Charges",
        len(unit_charges),
    )


with col2:
    st.metric(
        "Charge amount",
        f"${total_amount:.2f}",
    )


with col3:
    st.metric(
        "Evidence records",
        evidence_count,
    )


with col4:
    st.metric(
        "Unit",
        unit_id,
    )


# ============================================================
# REIMBURSEMENT METRIC
# ============================================================

total_reimbursed = 0.0

for reimbursement in reimbursements:

    amount = getattr(
        reimbursement,
        "amount_total",
        None,
    )

    if amount is None:
        amount = getattr(
            reimbursement,
            "amount",
            0,
        )

    try:
        total_reimbursed += float(
            amount or 0
        )
    except Exception:
        pass


st.info(
    f"Reimbursement records available: "
    f"{len(reimbursements)} | "
    f"Total recorded reimbursement amount: "
    f"${total_reimbursed:.2f}"
)


# ============================================================
# EVIDENCE SECTION
# ============================================================

st.subheader("Evidence")


evidence_tabs = st.tabs(
    [
        "Receiving",
        "Prep",
        "Pack",
        "Returns",
    ]
)


def display_evidence(records):

    if not records:

        st.info(
            "No evidence records available."
        )

        return


    for record in records:

        if hasattr(
            record,
            "model_dump",
        ):

            data = record.model_dump()

        elif isinstance(
            record,
            dict,
        ):

            data = record

        else:

            try:
                data = vars(record)
            except Exception:
                data = {
                    "value": str(record)
                }


        record_id = data.get(
            "record_id",
            "Evidence record",
        )


        with st.expander(
            str(record_id)
        ):

            st.json(data)


with evidence_tabs[0]:

    display_evidence(
        unit_evidence.receiving
    )


with evidence_tabs[1]:

    display_evidence(
        unit_evidence.prep
    )


with evidence_tabs[2]:

    display_evidence(
        unit_evidence.pack
    )


with evidence_tabs[3]:

    display_evidence(
        unit_evidence.returns
    )


# ============================================================
# AI ANALYSIS
# ============================================================

st.subheader(
    "AI Evidence Interpretation"
)


# ============================================================
# SESSION STATE
# ============================================================

session_key = (
    f"agent_result_{org_id}_{unit_id}"
)


agent_result = st.session_state.get(
    session_key,
    None,
)


# ============================================================
# ALWAYS INITIALIZE CHECKS
# ============================================================

normalized_checks = []


# ============================================================
# GEMINI API
# ============================================================

if "GEMINI_API_KEY" not in st.secrets:

    st.warning(
        "GEMINI_API_KEY is not configured. "
        "The deterministic recovery workflow can still run, "
        "but AI evidence interpretation will remain pending."
    )

else:

    try:

        api_key = st.secrets[
            "GEMINI_API_KEY"
        ]


        model = st.secrets.get(
            "GEMINI_MODEL",
            "gemini-3.5-flash-lite",
        )


        agent = RecoveryAgent(
            api_key=api_key,
            model=model,
        )


        if st.button(
            "Analyze evidence with agent",
            type="primary",
        ):

            with st.spinner(
                "Analyzing unit evidence..."
            ):

                agent_result = agent.analyze_unit(
                    unit_id=unit_id,
                    evidence=all_evidence,
                )


            st.session_state[
                session_key
            ] = agent_result


    except Exception as exc:

        st.error(
            "Unable to initialize Gemini model: "
            f"{type(exc).__name__}: {exc}"
        )

        agent_result = None


# ============================================================
# PROCESS AI RESULT
# ============================================================

if agent_result is not None:

    if agent_result.checks:

        st.success(
            f"Gemini returned "
            f"{len(agent_result.checks)} "
            f"evidence checks."
        )


        # ----------------------------------------------------
        # CONVERT GEMINI CHECKS
        # ----------------------------------------------------

        try:

            ai_checks = agent_checks_to_models(
                agent_result
            )

        except Exception as exc:

            ai_checks = []

            st.error(
                "Could not convert Gemini checks: "
                f"{type(exc).__name__}: {exc}"
            )


        # ----------------------------------------------------
        # NORMALIZE CHECKS
        # ----------------------------------------------------

        if ai_checks:

            try:

                normalized_checks = normalize_checks(
                    ai_checks
                )

            except Exception as exc:

                normalized_checks = []

                st.error(
                    "Could not normalize evidence checks: "
                    f"{type(exc).__name__}: {exc}"
                )


        # ----------------------------------------------------
        # DISPLAY CHECKS
        # ----------------------------------------------------

        if normalized_checks:

            st.write(
                f"Contract-compatible checks: "
                f"{len(normalized_checks)}"
            )


            check_rows = []


            for check in normalized_checks:

                check_rows.append(
                    {
                        "Source": check.source,
                        "Check": check.check_key,
                        "Status": str(check.status),
                        "Value": check.value,
                        "Event date": check.event_date,
                        "Reason": check.reason,
                    }
                )


            st.dataframe(
                check_rows,
                use_container_width=True,
                hide_index=True,
            )

        else:

            st.warning(
                "Gemini returned checks, but none "
                "mapped to the Recovery Manager contract."
            )


    else:

        st.warning(
            "No AI evidence checks were returned. "
            "The case remains conservative/pending."
        )


        if agent_result.summary:

            st.caption(
                agent_result.summary
            )


# ============================================================
# DECISION ENGINE
# ============================================================

st.subheader(
    "Recovery Decisions"
)


decision_rows = []


decisions = []


for charge in unit_charges:

    try:

        decision = decide_charge(
            charge=charge,
            checks=normalized_checks,
            reimbursements=reimbursements,
            
        )

        decisions.append(
            decision
        )


        decision_rows.append(
            {
                "Charge ID": decision.charge_id,
                "Charge type": decision.charge_type,
                "Amount": (
                    f"${decision.amount_total:.2f}"
                ),
                "Verdict": decision.verdict.value,
                "Recommended claim": (
                    f"${decision.recommended_claim_amount:.2f}"
                ),
                "Evidence complete": (
                    decision.evidence_complete
                ),
                "Reimbursed": (
                    f"${decision.already_reimbursed_amount:.2f}"
                ),
                "Window": decision.window_status,
                "Model": decision.model_status,
            }
        )


    except Exception as exc:

        st.error(
            f"Decision engine failed for "
            f"{charge.charge_id}: "
            f"{type(exc).__name__}: {exc}"
        )


# ============================================================
# DECISION TABLE
# ============================================================

if decision_rows:

    st.dataframe(
        decision_rows,
        use_container_width=True,
        hide_index=True,
    )


# ============================================================
# DECISION DETAILS
# ============================================================

st.subheader(
    "Decision Details"
)


for decision in decisions:

    with st.expander(
        f"{decision.charge_id} — "
        f"{decision.charge_type} — "
        f"{decision.verdict.value}"
    ):

        col1, col2 = st.columns(2)


        # ----------------------------------------------------
        # LEFT
        # ----------------------------------------------------

        with col1:

            st.write(
                "**Charge amount:** "
                f"${decision.amount_total:.2f}"
            )


            st.write(
                "**Recommended claim:** "
                f"${decision.recommended_claim_amount:.2f}"
            )


            st.write(
                "**Already reimbursed:** "
                f"${decision.already_reimbursed_amount:.2f}"
            )


            st.write(
                "**Evidence complete:** "
                f"{decision.evidence_complete}"
            )


        # ----------------------------------------------------
        # RIGHT
        # ----------------------------------------------------

        with col2:

            st.write(
                "**Verdict:** "
                f"`{decision.verdict.value}`"
            )


            st.write(
                "**Window status:** "
                f"`{decision.window_status}`"
            )


            st.write(
                "**Model status:** "
                f"`{decision.model_status}`"
            )


        # ----------------------------------------------------
        # REASONS
        # ----------------------------------------------------

        if decision.reasons:

            st.markdown(
                "### Reasons"
            )


            for reason in decision.reasons:

                st.write(
                    f"- {reason}"
                )


        # ----------------------------------------------------
        # UNCERTAINTY
        # ----------------------------------------------------

        if decision.uncertainty_reasons:

            st.markdown(
                "### Uncertainty"
            )


            for reason in decision.uncertainty_reasons:

                st.write(
                    f"- {reason}"
                )


        # ----------------------------------------------------
        # SUPPORTING EVIDENCE
        # ----------------------------------------------------

        if decision.supporting_evidence:

            st.markdown(
                "### Supporting evidence"
            )


            for evidence_id in decision.supporting_evidence:

                st.write(
                    f"- `{evidence_id}`"
                )


        # ----------------------------------------------------
        # RELEVANT CHECKS
        # ----------------------------------------------------

        if decision.checks:

            st.markdown(
                "### Relevant checks"
            )


            check_rows = []


            for check in decision.checks:

                check_rows.append(
                    {
                        "Source": check.source,
                        "Check": check.check_key,
                        "Status": str(check.status),
                        "Value": check.value,
                        "Event date": check.event_date,
                        "Reason": check.reason,
                    }
                )


            st.dataframe(
                check_rows,
                use_container_width=True,
                hide_index=True,
            )


# ============================================================
# DATASET SUMMARY
# ============================================================

with st.expander(
    "Dataset summary"
):

    try:

        summary = loader.summary()

        st.json(summary)

    except Exception as exc:

        st.warning(
            "Could not load dataset summary: "
            f"{type(exc).__name__}: {exc}"
        )


# ============================================================
# FOOTER
# ============================================================

st.divider()


st.caption(
    "Recovery Manager uses deterministic contract rules "
    "for final recovery decisions. AI interpretation is "
    "treated as evidence input and does not override "
    "the decision contract."
)
