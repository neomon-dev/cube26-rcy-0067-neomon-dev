import json
from typing import Any

from google import genai
from pydantic import BaseModel, Field

from .models import EvidenceCheck, EvidenceStatus


# ============================================================
# OFFICIAL CHECK KEYS
# ============================================================

OFFICIAL_CHECK_KEYS = {
    "identity_matches_po",
    "quantity_matches_po",
    "carton_undamaged",
    "unit_undamaged",
    "variant_correct",
    "polybag_present",
    "polybag_sealed",
    "suffocation_warning_present",
    "suffocation_warning_legible",
    "fnsku_label_flat",
    "fnsku_label_placement_valid",
    "manufacturer_barcode_covered",
    "expiry_date_legible",
    "handling_marks_present",
    "all_items_present",
    "quantities_correct",
    "no_extra_items",
    "order_matches_manifest",
    "identity_matches_order",
    "completeness_verified",
    "condition_grade",
    "disposition_assigned",
}


# ============================================================
# GEMINI MODELS
# ============================================================

class AgentEvidence(BaseModel):
    source: str
    check: str
    status: str
    value: str | None = None
    reason: str
    event_date: str | None = None


class AgentResult(BaseModel):
    unit_id: str
    checks: list[AgentEvidence] = Field(
        default_factory=list
    )
    summary: str = ""


# ============================================================
# RECOVERY AGENT
# ============================================================

class RecoveryAgent:

    def __init__(
        self,
        api_key: str,
        model_name: str = "gemini-3.8-flash",
        model: str | None = None,
    ):
        self.api_key = api_key
        self.model = model or model_name

        self.client = genai.Client(
            api_key=api_key
        )

    # ========================================================
    # ANALYZE UNIT
    # ========================================================

    def analyze_unit(
        self,
        evidence: list[Any],
        unit_id: str | None = None,
    ) -> AgentResult:

        # ----------------------------------------------------
        # Determine unit ID
        # ----------------------------------------------------

        if unit_id is None:

            for record in evidence:

                try:

                    if isinstance(
                        record,
                        BaseModel,
                    ):
                        data = record.model_dump()

                    elif isinstance(
                        record,
                        dict,
                    ):
                        data = dict(record)

                    else:
                        data = getattr(
                            record,
                            "data",
                            {},
                        )

                    if not isinstance(
                        data,
                        dict,
                    ):
                        continue

                    candidate = data.get(
                        "unit_id"
                    )

                    if candidate:
                        unit_id = str(
                            candidate
                        )
                        break

                    subject = data.get(
                        "subject"
                    )

                    if isinstance(
                        subject,
                        dict,
                    ):
                        candidate = subject.get(
                            "unit_id"
                        )

                        if candidate:
                            unit_id = str(
                                candidate
                            )
                            break

                    candidate = getattr(
                        record,
                        "unit_id",
                        None,
                    )

                    if candidate:
                        unit_id = str(
                            candidate
                        )
                        break

                except Exception:
                    continue

        if not unit_id:
            unit_id = "unknown"

        # ----------------------------------------------------
        # Serialize evidence
        # ----------------------------------------------------

        payload = [
            self._serialize_record(record)
            for record in evidence
        ]

        prompt = self._build_prompt(
            unit_id,
            payload,
        )

        # ----------------------------------------------------
        # Gemini
        # ----------------------------------------------------

        try:

            response = self.client.models.generate_content(
                model=self.model,
                contents=prompt,
            )

            content = getattr(
                response,
                "text",
                None,
            ) or ""

            if content:

                data = self._extract_json(
                    content
                )

                if isinstance(
                    data,
                    dict,
                ):

                    data["unit_id"] = unit_id

                    raw_checks = data.get(
                        "checks",
                        [],
                    )

                    if not isinstance(
                        raw_checks,
                        list,
                    ):
                        raw_checks = []

                    clean_checks = []

                    for check in raw_checks:

                        if not isinstance(
                            check,
                            dict,
                        ):
                            continue

                        check_name = str(
                            check.get(
                                "check",
                                "",
                            )
                        ).strip().lower()

                        if check_name not in OFFICIAL_CHECK_KEYS:
                            continue

                        status = str(
                            check.get(
                                "status",
                                "",
                            )
                        ).strip().lower()

                        if status not in {
                            "supports",
                            "contradicts",
                            "insufficient",
                            "not_applicable",
                        }:
                            continue

                        clean_checks.append(
                            check
                        )

                    # ------------------------------------------------
                    # Gemini produced usable checks
                    # ------------------------------------------------

                    if clean_checks:

                        data["checks"] = clean_checks

                        return AgentResult.model_validate(
                            data
                        )

            # ------------------------------------------------
            # Gemini returned no usable checks.
            # Use deterministic evidence extraction.
            # ------------------------------------------------

            fallback_checks = self._fallback_checks(
                evidence
            )

            return AgentResult(
                unit_id=unit_id,
                checks=fallback_checks,
                summary=(
                    "Evidence interpreted using deterministic "
                    "fallback extraction."
                ),
            )

        except Exception as exc:

            # ------------------------------------------------
            # Gemini failure -> deterministic fallback
            # ------------------------------------------------

            fallback_checks = self._fallback_checks(
                evidence
            )

            if fallback_checks:

                return AgentResult(
                    unit_id=unit_id,
                    checks=fallback_checks,
                    summary=(
                        "Gemini unavailable; evidence interpreted "
                        "using deterministic fallback. "
                        f"Original error: {type(exc).__name__}: {exc}"
                    ),
                )

            return self._fail_open(
                unit_id,
                (
                    "Gemini evidence interpretation failed: "
                    f"{type(exc).__name__}: {exc}"
                ),
            )

    # ========================================================
    # FALLBACK EVIDENCE EXTRACTION
    # ========================================================

    def _fallback_checks(
        self,
        evidence: list[Any],
    ) -> list[AgentEvidence]:

        output = []

        def add(
            source,
            check,
            status,
            value,
            reason,
            event_date=None,
        ):

            if check not in OFFICIAL_CHECK_KEYS:
                return

            output.append(
                AgentEvidence(
                    source=str(source),
                    check=check,
                    status=status,
                    value=(
                        None
                        if value is None
                        else str(value)
                    ),
                    reason=str(reason),
                    event_date=(
                        None
                        if event_date is None
                        else str(event_date)
                    ),
                )
            )

        def positive_status(value):

            if value is None:
                return "insufficient"

            v = str(
                value
            ).strip().lower()

            if v in {
                "",
                "uncertain",
                "unknown",
            }:
                return "insufficient"

            if v in {
                "yes",
                "true",
                "pass",
                "passed",
                "present",
                "valid",
                "flat",
                "legible",
                "covered",
                "sealed",
                "none",
                "undamaged",
            }:
                return "supports"

            if v in {
                "no",
                "false",
                "fail",
                "failed",
                "missing",
                "invalid",
                "damaged",
                "crushed",
                "water",
            }:
                return "contradicts"

            return "insufficient"

        def get(
            data,
            *keys,
        ):

            for key in keys:

                if key in data:
                    return data.get(key)

            return None

        # ----------------------------------------------------
        # Process records
        # ----------------------------------------------------

        for record in evidence:

            try:

                # --------------------------------------------
                # Convert record
                # --------------------------------------------

                if isinstance(
                    record,
                    BaseModel,
                ):
                    record_data = record.model_dump()

                elif isinstance(
                    record,
                    dict,
                ):
                    record_data = dict(
                        record
                    )

                else:

                    record_data = getattr(
                        record,
                        "data",
                        {},
                    )

                    if not isinstance(
                        record_data,
                        dict,
                    ):
                        record_data = {}

                    record_meta = {}

                    for key in (
                        "record_id",
                        "event_date",
                        "unit_id",
                        "org_id",
                        "source",
                    ):

                        value = getattr(
                            record,
                            key,
                            None,
                        )

                        if value is not None:
                            record_meta[key] = value

                    merged = dict(
                        record_data
                    )

                    merged.update(
                        {
                            k: v
                            for k, v in record_meta.items()
                            if k not in merged
                        }
                    )

                    record_data = merged

                if not isinstance(
                    record_data,
                    dict,
                ):
                    continue

                # --------------------------------------------
                # EvidenceRecord may contain nested data
                # --------------------------------------------

                if isinstance(
                    record_data.get("data"),
                    dict,
                ):

                    nested = record_data[
                        "data"
                    ]

                    merged = dict(
                        nested
                    )

                    for key in (
                        "record_id",
                        "event_date",
                        "unit_id",
                        "org_id",
                        "source",
                    ):

                        if key in record_data:
                            merged.setdefault(
                                key,
                                record_data[key],
                            )

                    record_data = merged

                source = record_data.get(
                    "record_id",
                    record_data.get(
                        "source",
                        "evidence",
                    ),
                )

                event_date = (
                    record_data.get(
                        "event_date"
                    )
                    or record_data.get(
                        "captured_at"
                    )
                )

                source_type = str(
                    record_data.get(
                        "source",
                        "",
                    )
                ).strip().lower()

                # =================================================
                # PREP
                # =================================================

                if source_type == "prep":

                    # ---------------------------------------------
                    # Polybag
                    # ---------------------------------------------

                    polybag = get(
                        record_data,
                        "polybag_present_sealed",
                        "polybag_present",
                    )

                    if polybag is not None:

                        v = str(
                            polybag
                        ).strip().lower()

                        if v in {
                            "not_required",
                            "not required",
                        }:

                            status = "not_applicable"

                        else:

                            status = positive_status(
                                polybag
                            )

                        add(
                            source,
                            "polybag_present",
                            status,
                            polybag,
                            (
                                "Prep evidence records "
                                f"polybag status as '{polybag}'."
                            ),
                            event_date,
                        )

                        if (
                            "polybag_present_sealed"
                            in record_data
                        ):

                            add(
                                source,
                                "polybag_sealed",
                                status,
                                polybag,
                                (
                                    "Prep evidence records "
                                    f"polybag sealing status as '{polybag}'."
                                ),
                                event_date,
                            )

                    # ---------------------------------------------
                    # Suffocation warning
                    # ---------------------------------------------

                    warning = get(
                        record_data,
                        "suffocation_warning",
                        "suffocation_warning_present",
                    )

                    if warning is not None:

                        v = str(
                            warning
                        ).strip().lower()

                        if v in {
                            "not_required",
                            "not required",
                        }:

                            status = "not_applicable"

                        else:

                            status = positive_status(
                                warning
                            )

                        add(
                            source,
                            "suffocation_warning_present",
                            status,
                            warning,
                            (
                                "Prep evidence records "
                                f"suffocation warning as '{warning}'."
                            ),
                            event_date,
                        )

                        add(
                            source,
                            "suffocation_warning_legible",
                            status,
                            warning,
                            (
                                "Prep evidence records "
                                f"suffocation warning condition as '{warning}'."
                            ),
                            event_date,
                        )

                    # ---------------------------------------------
                    # FNSKU placement
                    # ---------------------------------------------

                    fnsku = get(
                        record_data,
                        "fnsku_label_placement",
                        "fnsku_label_placement_valid",
                    )

                    if fnsku is not None:

                        v = str(
                            fnsku
                        ).strip().lower()

                        if v in {
                            "not_required",
                            "not required",
                        }:

                            status = "not_applicable"

                        elif v in {
                            "flat",
                            "valid",
                            "pass",
                            "passed",
                        }:

                            status = "supports"

                        elif v in {
                            "uncertain",
                            "unknown",
                        }:

                            status = "insufficient"

                        else:

                            status = "contradicts"

                        add(
                            source,
                            "fnsku_label_flat",
                            status,
                            fnsku,
                            (
                                "Prep evidence records "
                                f"FNSKU placement as '{fnsku}'."
                            ),
                            event_date,
                        )

                        add(
                            source,
                            "fnsku_label_placement_valid",
                            status,
                            fnsku,
                            (
                                "Prep evidence records "
                                f"FNSKU placement as '{fnsku}'."
                            ),
                            event_date,
                        )

                    # ---------------------------------------------
                    # Manufacturer barcode
                    # ---------------------------------------------

                    barcode = get(
                        record_data,
                        "original_barcode_covered",
                        "manufacturer_barcode_covered",
                    )

                    if barcode is not None:

                        status = positive_status(
                            barcode
                        )

                        add(
                            source,
                            "manufacturer_barcode_covered",
                            status,
                            barcode,
                            (
                                "Prep evidence records "
                                f"original barcode coverage as '{barcode}'."
                            ),
                            event_date,
                        )

                # =================================================
                # RECEIVING
                # =================================================

                elif source_type == "receiving":

                    damage = get(
                        record_data,
                        "unit_damage",
                        "unit_undamaged",
                    )

                    if damage is not None:

                        v = str(
                            damage
                        ).strip().lower()

                        if v in {
                            "none",
                            "no",
                            "undamaged",
                            "pass",
                        }:

                            status = "supports"

                        elif v in {
                            "uncertain",
                            "unknown",
                        }:

                            status = "insufficient"

                        else:

                            status = "contradicts"

                        add(
                            source,
                            "unit_undamaged",
                            status,
                            damage,
                            (
                                "Receiving evidence records "
                                f"unit damage as '{damage}'."
                            ),
                            event_date,
                        )

                    qty_ordered = get(
                        record_data,
                        "qty_ordered",
                    )

                    qty_received = get(
                        record_data,
                        "qty_received",
                    )

                    if (
                        qty_ordered is not None
                        and qty_received is not None
                    ):

                        if str(
                            qty_ordered
                        ).strip() == str(
                            qty_received
                        ).strip():

                            status = "supports"

                        else:

                            status = "contradicts"

                        add(
                            source,
                            "quantity_matches_po",
                            status,
                            (
                                f"{qty_received}/{qty_ordered}"
                            ),
                            (
                                "Receiving evidence records "
                                f"{qty_received} units received "
                                f"against {qty_ordered} ordered."
                            ),
                            event_date,
                        )

                # =================================================
                # PACK
                # =================================================

                elif source_type == "pack":

                    for key in (
                        "all_items_present",
                        "quantities_correct",
                    ):

                        value = get(
                            record_data,
                            key,
                        )

                        if value is not None:

                            add(
                                source,
                                key,
                                positive_status(value),
                                value,
                                (
                                    f"Pack evidence records "
                                    f"{key} as '{value}'."
                                ),
                                event_date,
                            )

                # =================================================
                # RETURNS
                # =================================================

                elif source_type == "returns":

                    condition = get(
                        record_data,
                        "condition_grade",
                    )

                    if condition is not None:

                        add(
                            source,
                            "condition_grade",
                            "supports",
                            condition,
                            (
                                "Returns evidence records "
                                f"condition grade '{condition}'."
                            ),
                            event_date,
                        )

            except Exception:
                continue

        return output

    # ========================================================
    # PROMPT
    # ========================================================

    def _build_prompt(
        self,
        unit_id: str,
        evidence: list[dict[str, Any]],
    ) -> str:

        keys = ", ".join(
            sorted(
                OFFICIAL_CHECK_KEYS
            )
        )

        return f"""
You are the evidence interpretation component
of a Recovery Manager.

Your job is ONLY to interpret evidence explicitly
present in the supplied records.

You MUST NOT make the final recovery,
reimbursement, or claim decision.

UNIT_ID:

{unit_id}

OFFICIAL CHECK KEYS:

{keys}

STATUS VALUES:

- supports
- contradicts
- insufficient
- not_applicable

RULES:

1. Never invent evidence.
2. Never invent dates, IDs, quantities, SKUs,
   orders, shipments, policies, or outcomes.
3. Missing evidence is NOT a failed check.
4. Uncertain evidence must be "insufficient".
5. Contradictory evidence must be "contradicts".
6. Explicitly irrelevant checks may be "not_applicable".
7. Preserve the source record_id whenever available.
8. Preserve the actual event/captured date whenever available.
9. Only return checks directly grounded in supplied evidence.
10. Do not decide whether a charge should be claimed.
11. Do not infer policies from general knowledge.
12. Do not convert uncertainty into support.
13. Return all clearly observable relevant checks.
14. For condition_grade, preserve the observed grade/detail.

EVIDENCE:

{json.dumps(
    evidence,
    indent=2,
    ensure_ascii=False,
    default=str,
)}

RETURN ONLY VALID JSON.

Required structure:

{{
    "unit_id": "{unit_id}",
    "summary": "brief evidence summary",
    "checks": [
        {{
            "source": "record_id",
            "check": "official_check_key",
            "status": "supports",
            "value": "observed value or null",
            "reason": "evidence-grounded explanation",
            "event_date": "date or null"
        }}
    ]
}}
""".strip()

    # ========================================================
    # SERIALIZATION
    # ========================================================

    def _serialize_record(
        self,
        record: Any,
    ) -> dict[str, Any]:

        if isinstance(
            record,
            BaseModel,
        ):

            data = record.model_dump()

        elif isinstance(
            record,
            dict,
        ):

            data = dict(
                record
            )

        else:

            data = {}

            try:

                record_data = getattr(
                    record,
                    "data",
                    None,
                )

                if isinstance(
                    record_data,
                    dict,
                ):

                    data.update(
                        record_data
                    )

                for key in dir(record):

                    if key.startswith("_"):
                        continue

                    try:
                        value = getattr(
                            record,
                            key,
                        )
                    except Exception:
                        continue

                    if callable(value):
                        continue

                    if key not in data:
                        data[key] = value

            except Exception:
                pass

        return self._clean_value(
            data
        )

    def _clean_value(
        self,
        value: Any,
    ) -> Any:

        if isinstance(
            value,
            dict,
        ):

            return {
                str(k): self._clean_value(v)
                for k, v in value.items()
            }

        if isinstance(
            value,
            (list, tuple),
        ):

            return [
                self._clean_value(v)
                for v in value
            ]

        if isinstance(
            value,
            BaseModel,
        ):

            return self._clean_value(
                value.model_dump()
            )

        try:

            json.dumps(
                value
            )

            return value

        except (
            TypeError,
            ValueError,
        ):

            return str(value)

    # ========================================================
    # JSON EXTRACTION
    # ========================================================

    def _extract_json(
        self,
        content: str,
    ) -> dict[str, Any] | None:

        content = content.strip()

        if not content:
            return None

        # Remove markdown fences.
        if content.startswith("```"):

            lines = content.splitlines()

            if lines:
                lines = lines[1:]

            if (
                lines
                and lines[-1].strip() == "```"
            ):
                lines = lines[:-1]

            content = "\n".join(
                lines
            ).strip()

        try:

            data = json.loads(
                content
            )

            if isinstance(
                data,
                dict,
            ):
                return data

        except json.JSONDecodeError:
            pass

        # Extract JSON object from surrounding text.
        start = content.find("{")
        end = content.rfind("}")

        if start >= 0 and end > start:

            try:

                data = json.loads(
                    content[
                        start:end + 1
                    ]
                )

                if isinstance(
                    data,
                    dict,
                ):
                    return data

            except json.JSONDecodeError:
                pass

        return None

    # ========================================================
    # FAIL SAFE
    # ========================================================

    def _fail_open(
        self,
        unit_id: str,
        message: str,
    ) -> AgentResult:

        return AgentResult(
            unit_id=unit_id,
            checks=[],
            summary=message,
        )


# ============================================================
# CONVERT GEMINI CHECKS TO PROJECT MODELS
# ============================================================

def agent_checks_to_models(
    result: AgentResult,
) -> list[EvidenceCheck]:

    output = []

    for item in result.checks:

        try:

            status = EvidenceStatus(
                item.status
            )

        except ValueError:

            continue

        try:

            output.append(
                EvidenceCheck(
                    source=item.source,
                    check_key=item.check,
                    status=status,
                    value=item.value,
                    reason=item.reason,
                    event_date=item.event_date,
                )
            )

        except Exception:

            continue

    return output