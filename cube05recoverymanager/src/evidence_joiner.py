from typing import Any, Dict, List

import pandas as pd

from .loader import DataLoader
from .models import EvidenceRecord, UnitEvidence


class EvidenceJoiner:
    """
    Joins Recovery Manager charges to upstream evidence.

    The DataLoader returns all upstream records for a unit/org
    as a dictionary keyed by filename.

    The joiner converts those records into the UnitEvidence
    structure expected by the rest of the Recovery Manager.

    Important:
        Missing evidence is NOT treated as failure.
        Uncertain evidence is NOT treated as success.
        The joiner does not make final recovery decisions.
    """

    SOURCE_MAP = {
        "receiving": "receiving_sample.csv",
        "prep": "prep_sample.csv",
        "pack": "pack_sample.csv",
        "returns": "returns_sample.csv",
    }

    def __init__(self, loader: DataLoader):
        self.loader = loader

    # ========================================================
    # BUILD UNIT EVIDENCE
    # ========================================================

    def build_unit_evidence(
        self,
        unit_id: str,
        org_id: str,
    ) -> UnitEvidence:

        unit_id = str(unit_id).strip()
        org_id = str(org_id).strip()

        evidence = UnitEvidence(
            unit_id=unit_id,
            org_id=org_id,
        )

        # DataLoader returns:
        #
        # {
        #     "receiving_sample.csv": [...],
        #     "prep_sample.csv": [...],
        #     "pack_sample.csv": [...],
        #     "returns_sample.csv": [...]
        # }
        #
        upstream = self.loader.get_upstream_record(
            unit_id,
            org_id,
        )

        if not upstream:
            evidence.missing_sources = [
                "receiving",
                "prep",
                "pack",
                "returns",
            ]

            return evidence

        for source, filename in self.SOURCE_MAP.items():

            rows = upstream.get(
                filename,
                [],
            )

            if not rows:
                evidence.missing_sources.append(
                    source
                )
                continue

            records = self._rows_to_records(
                rows=rows,
                source=source,
                unit_id=unit_id,
                org_id=org_id,
            )

            if source == "receiving":
                evidence.receiving.extend(records)

            elif source == "prep":
                evidence.prep.extend(records)

            elif source == "pack":
                evidence.pack.extend(records)

            elif source == "returns":
                evidence.returns.extend(records)

        evidence.contradictions = (
            self._find_contradictions(
                evidence
            )
        )

        return evidence

    # ========================================================
    # CONVERT ROWS TO EvidenceRecord
    # ========================================================

    def _rows_to_records(
        self,
        rows: List[Dict[str, Any]],
        source: str,
        unit_id: str,
        org_id: str,
    ) -> List[EvidenceRecord]:

        records = []

        for index, row in enumerate(rows):

            cleaned_data = {}

            for key, value in row.items():

                if key.startswith("_"):
                    continue

                cleaned_data[key] = (
                    self._clean_value(value)
                )

            record_id = self._record_id(
                row,
                source,
                index,
            )

            event_date = self._event_date(
                row
            )

            records.append(
                EvidenceRecord(
                    source=source,
                    record_id=record_id,
                    unit_id=unit_id,
                    org_id=org_id,
                    data=cleaned_data,
                    event_date=event_date,
                )
            )

        return records

    # ========================================================
    # VALUE CLEANING
    # ========================================================

    @staticmethod
    def _clean_value(
        value: Any,
    ) -> Any:

        if value is None:
            return None

        try:
            if pd.isna(value):
                return None
        except (TypeError, ValueError):
            pass

        if hasattr(value, "item"):

            try:
                return value.item()
            except (TypeError, ValueError):
                pass

        return value

    # ========================================================
    # RECORD ID
    # ========================================================

    @staticmethod
    def _record_id(
        row: Dict[str, Any],
        source: str,
        index: int,
    ) -> str:

        possible_columns = (
            "record_id",
            "evidence_id",
            "event_id",
            "id",
            "line_id",
        )

        for column in possible_columns:

            value = row.get(column)

            if value is None:
                continue

            value = str(value).strip()

            if value:
                return value

        return f"{source}-{index + 1}"

    # ========================================================
    # EVENT DATE
    # ========================================================

    @staticmethod
    def _event_date(
        row: Dict[str, Any],
    ) -> str | None:

        possible_columns = (
            "captured_at",
            "event_date",
            "recorded_at",
            "timestamp",
            "created_at",
            "received_date",
            "prep_date",
            "packed_date",
            "return_date",
            "date",
        )

        for column in possible_columns:

            value = row.get(column)

            if value is None:
                continue

            value = str(value).strip()

            if value:
                return value

        return None

    # ========================================================
    # CONTRADICTION DETECTION
    # ========================================================

    def _find_contradictions(
        self,
        evidence: UnitEvidence,
    ) -> List[str]:

        contradictions = []

        # ----------------------------------------------------
        # RECEIVING
        # ----------------------------------------------------

        for record in evidence.receiving:

            data = record.data

            identity = self._normalise(
                data.get("identity_match")
            )

            if identity in {
                "no",
                "false",
                "fail",
                "failed",
                "mismatch",
                "incorrect",
            }:

                contradictions.append(
                    f"{record.record_id}: "
                    "Receiving identity_match indicates "
                    "a mismatch."
                )

            unit_damage = self._normalise(
                data.get("unit_damage")
            )

            if unit_damage in {
                "yes",
                "damaged",
                "true",
                "fail",
                "failed",
            }:

                contradictions.append(
                    f"{record.record_id}: "
                    "Receiving unit_damage indicates "
                    "damage."
                )

            qty_ordered = self._number(
                data.get("qty_ordered")
            )

            qty_received = self._number(
                data.get("qty_received")
            )

            if (
                qty_ordered is not None
                and qty_received is not None
                and qty_ordered != qty_received
            ):

                contradictions.append(
                    f"{record.record_id}: "
                    "Receiving quantity differs "
                    "from quantity ordered."
                )

        # ----------------------------------------------------
        # PREP
        # ----------------------------------------------------

        for record in evidence.prep:

            data = record.data

            polybag = self._normalise(
                data.get(
                    "polybag_present_sealed"
                )
            )

            if polybag in {
                "missing",
                "no",
                "false",
                "fail",
                "failed",
            }:

                contradictions.append(
                    f"{record.record_id}: "
                    "Prep evidence indicates the "
                    "polybag requirement was not satisfied."
                )

            warning = self._normalise(
                data.get(
                    "suffocation_warning"
                )
            )

            if warning in {
                "missing",
                "no",
                "false",
                "fail",
                "failed",
            }:

                contradictions.append(
                    f"{record.record_id}: "
                    "Prep evidence indicates the "
                    "suffocation warning is missing."
                )

            barcode = self._normalise(
                data.get(
                    "original_barcode_covered"
                )
            )

            if barcode in {
                "no",
                "false",
                "fail",
                "failed",
            }:

                contradictions.append(
                    f"{record.record_id}: "
                    "Prep evidence indicates the "
                    "original barcode is not covered."
                )

            label_placement = self._normalise(
                data.get(
                    "fnsku_label_placement"
                )
            )

            if label_placement in {
                "invalid",
                "incorrect",
                "failed",
                "fail",
            }:

                contradictions.append(
                    f"{record.record_id}: "
                    "Prep evidence indicates invalid "
                    "FNSKU label placement."
                )

        # ----------------------------------------------------
        # PACK
        # ----------------------------------------------------

        for record in evidence.pack:

            data = record.data

            verdict = self._normalise(
                data.get("operator_verdict")
            )

            if verdict in {
                "stop_and_fix",
                "failed",
                "fail",
            }:

                contradictions.append(
                    f"{record.record_id}: "
                    "Pack evidence contains a failure verdict."
                )

            order_lines = data.get(
                "order_lines"
            )

            observed = data.get(
                "observed_in_box"
            )

            if (
                order_lines is not None
                and observed is not None
                and str(order_lines).strip()
                and str(observed).strip()
                and str(order_lines).strip()
                != str(observed).strip()
            ):

                contradictions.append(
                    f"{record.record_id}: "
                    "Pack order contents differ "
                    "from observed contents."
                )

        # ----------------------------------------------------
        # RETURNS
        # ----------------------------------------------------

        for record in evidence.returns:

            data = record.data

            identity = self._normalise(
                data.get("identity_match")
            )

            if identity in {
                "no",
                "false",
                "fail",
                "failed",
                "mismatch",
                "incorrect",
            }:

                contradictions.append(
                    f"{record.record_id}: "
                    "Return evidence reports an "
                    "identity mismatch."
                )

            parts_missing = data.get(
                "parts_missing"
            )

            if (
                parts_missing is not None
                and str(parts_missing).strip()
                and str(parts_missing)
                .strip()
                .lower()
                not in {
                    "none",
                    "null",
                    "nan",
                    "[]",
                    "0",
                }
            ):

                contradictions.append(
                    f"{record.record_id}: "
                    "Return evidence reports "
                    "missing parts."
                )

        return sorted(
            set(contradictions)
        )

    # ========================================================
    # RELATIONSHIP VALIDATION
    # ========================================================

    @staticmethod
    def validate_relationship(
        evidence: UnitEvidence,
        sku: str | None = None,
        shipment_id: str | None = None,
        order_id: str | None = None,
    ) -> List[str]:

        mismatches = []

        expected_sku = (
            str(sku).strip()
            if sku is not None
            and str(sku).strip()
            else None
        )

        expected_shipment = (
            str(shipment_id).strip()
            if shipment_id is not None
            and str(shipment_id).strip()
            else None
        )

        expected_order = (
            str(order_id).strip()
            if order_id is not None
            and str(order_id).strip()
            else None
        )

        all_records = (
            evidence.receiving
            + evidence.prep
            + evidence.pack
            + evidence.returns
        )

        for record in all_records:

            data = record.data

            actual_sku = data.get("sku")

            if (
                expected_sku
                and actual_sku is not None
                and str(actual_sku).strip()
                and str(actual_sku).strip()
                != expected_sku
            ):

                mismatches.append(
                    f"{record.source}:"
                    f"{record.record_id} "
                    "SKU mismatch."
                )

            actual_shipment = data.get(
                "fba_shipment_id"
            )

            if (
                expected_shipment
                and actual_shipment is not None
                and str(actual_shipment).strip()
                and str(actual_shipment).strip()
                != expected_shipment
            ):

                mismatches.append(
                    f"{record.source}:"
                    f"{record.record_id} "
                    "shipment mismatch."
                )

            actual_order = data.get(
                "order_id"
            )

            if (
                expected_order
                and actual_order is not None
                and str(actual_order).strip()
                and str(actual_order).strip()
                != expected_order
            ):

                mismatches.append(
                    f"{record.source}:"
                    f"{record.record_id} "
                    "order mismatch."
                )

        return sorted(
            set(mismatches)
        )

    # ========================================================
    # UTILITIES
    # ========================================================

    @staticmethod
    def all_records(
        evidence: UnitEvidence,
    ) -> List[EvidenceRecord]:

        return (
            list(evidence.receiving)
            + list(evidence.prep)
            + list(evidence.pack)
            + list(evidence.returns)
        )

    @staticmethod
    def source_counts(
        evidence: UnitEvidence,
    ) -> Dict[str, int]:

        return {
            "receiving": len(
                evidence.receiving
            ),
            "prep": len(
                evidence.prep
            ),
            "pack": len(
                evidence.pack
            ),
            "returns": len(
                evidence.returns
            ),
        }

    @staticmethod
    def summary(
        evidence: UnitEvidence,
    ) -> Dict[str, Any]:

        return {
            "unit_id": evidence.unit_id,
            "org_id": evidence.org_id,
            "receiving_records": len(
                evidence.receiving
            ),
            "prep_records": len(
                evidence.prep
            ),
            "pack_records": len(
                evidence.pack
            ),
            "returns_records": len(
                evidence.returns
            ),
            "missing_sources": list(
                evidence.missing_sources
            ),
            "contradictions": list(
                evidence.contradictions
            ),
        }

    # ========================================================
    # NORMALISATION HELPERS
    # ========================================================

    @staticmethod
    def _normalise(
        value: Any,
    ) -> str:

        if value is None:
            return ""

        try:
            if pd.isna(value):
                return ""
        except (TypeError, ValueError):
            pass

        return (
            str(value)
            .strip()
            .lower()
            .replace("-", "_")
            .replace(" ", "_")
        )

    @staticmethod
    def _number(
        value: Any,
    ) -> float | None:

        if value is None:
            return None

        try:
            if pd.isna(value):
                return None
        except (TypeError, ValueError):
            pass

        try:
            return float(value)
        except (TypeError, ValueError):
            return None