from pathlib import Path
from typing import Optional

import pandas as pd

from .models import Charge, Reimbursement


class DataLoader:

    def __init__(
        self,
        data_dir: str = "data",
    ):
        self.data_dir = Path(data_dir)

        self.fee_report_path = (
            self.data_dir / "fee_report_sample.csv"
        )

        self.upstream_dir = (
            self.data_dir / "upstream"
        )

        self._fee_df = None
        self._upstream = {}

        self._load_all()

    # ========================================================
    # LOAD
    # ========================================================

    def _load_all(self):

        if self.fee_report_path.exists():

            self._fee_df = pd.read_csv(
                self.fee_report_path,
                dtype=str,
            )

            self._fee_df.columns = [
                str(column).strip()
                for column in self._fee_df.columns
            ]

        else:

            self._fee_df = pd.DataFrame()

        if self.upstream_dir.exists():

            for path in self.upstream_dir.glob(
                "*.csv"
            ):

                try:

                    df = pd.read_csv(
                        path,
                        dtype=str,
                    )

                    df.columns = [
                        str(column).strip()
                        for column in df.columns
                    ]

                    self._upstream[
                        path.name
                    ] = df

                except Exception as exc:

                    print(
                        f"Could not read {path}: {exc}"
                    )

    # ========================================================
    # HELPERS
    # ========================================================

    @staticmethod
    def _clean_string(value):

        if value is None:
            return None

        try:

            if pd.isna(value):
                return None

        except (TypeError, ValueError):
            pass

        value = str(value).strip()

        if not value:
            return None

        return value

    @staticmethod
    def _float(value) -> float:

        if value is None:
            return 0.0

        try:

            if pd.isna(value):
                return 0.0

        except (TypeError, ValueError):
            return 0.0

        try:

            return float(
                str(value)
                .replace(",", "")
                .strip()
            )

        except Exception:

            return 0.0

    # ========================================================
    # FILE DISCOVERY
    # ========================================================

    def get_upstream_files(self):

        return sorted(
            self._upstream.keys()
        )

    # ========================================================
    # ORGANISATIONS
    # ========================================================

    def get_orgs(self):

        orgs = set()

        if self._fee_df is not None:

            if "org_id" in self._fee_df.columns:

                for value in self._fee_df[
                    "org_id"
                ].dropna():

                    cleaned = self._clean_string(
                        value
                    )

                    if cleaned:
                        orgs.add(cleaned)

        for df in self._upstream.values():

            if "org_id" not in df.columns:
                continue

            for value in df[
                "org_id"
            ].dropna():

                cleaned = self._clean_string(
                    value
                )

                if cleaned:
                    orgs.add(cleaned)

        return sorted(orgs)

    # ========================================================
    # GRANULARITY
    # ========================================================

    def infer_granularity(
        self,
        row,
    ) -> str:

        charge_type = (
            self._clean_string(
                row.get("charge_type")
            )
            or ""
        ).lower()

        shipment_id = self._clean_string(
            row.get("fba_shipment_id")
        )

        order_id = self._clean_string(
            row.get("order_id")
        )

        unit_id = self._clean_string(
            row.get("unit_id")
        )

        # ----------------------------------------------------
        # Contract warning:
        #
        # Inbound defect charges can be shipment-level even
        # when a unit_id is present.
        # ----------------------------------------------------

        if charge_type == "inbound_defect_fee":

            if shipment_id:
                return "shipment"

        if unit_id:
            return "unit"

        if shipment_id:
            return "shipment"

        if order_id:
            return "order"

        return "unknown"

    # ========================================================
    # CHARGES
    # ========================================================

    def get_charges(
        self,
        org_id: Optional[str] = None,
    ):

        if self._fee_df is None:
            return []

        if self._fee_df.empty:
            return []

        rows = self._fee_df.copy()

        # ----------------------------------------------------
        # Reimbursement report is not a charge.
        # ----------------------------------------------------

        if "report_type" in rows.columns:

            rows = rows[
                rows[
                    "report_type"
                ]
                .fillna("")
                .str.lower()
                != "reimbursement_report"
            ]

        # ----------------------------------------------------
        # Tenant isolation.
        # ----------------------------------------------------

        if org_id is not None:

            if "org_id" not in rows.columns:
                return []

            rows = rows[
                rows["org_id"].fillna("")
                == str(org_id)
            ]

        charges = []

        for index, row in rows.iterrows():

            line_id = (
                self._clean_string(
                    row.get("line_id")
                )
                or f"ROW-{index + 1}"
            )

            charge_id = (
                self._clean_string(
                    row.get("charge_id")
                )
                or line_id
            )

            report_type = (
                self._clean_string(
                    row.get("report_type")
                )
                or "fee_report"
            )

            charge_type = (
                self._clean_string(
                    row.get("charge_type")
                )
                or "unknown"
            )

            # ------------------------------------------------
            # IMPORTANT:
            #
            # Preserve subtype if the fee report contains it.
            # ------------------------------------------------

            charge_subtype = (
                self._clean_string(
                    row.get("charge_subtype")
                )
            )

            # ------------------------------------------------
            # Preserve description if supplied.
            # ------------------------------------------------

            description = (
                self._clean_string(
                    row.get("description")
                )
            )

            # If there is no explicit description, use the
            # charge subtype before falling back to charge type.
            if not description:

                description = (
                    charge_subtype
                    or charge_type
                )

            unit_id = self._clean_string(
                row.get("unit_id")
            )

            shipment_id = self._clean_string(
                row.get("fba_shipment_id")
            )

            order_id = self._clean_string(
                row.get("order_id")
            )

            amount_total = self._float(
                row.get("amount_usd")
            )

            quantity = self._float(
                row.get("quantity")
            )

            if quantity:

                amount_per_unit = (
                    amount_total / quantity
                )

            else:

                amount_per_unit = (
                    amount_total
                )

            charge = Charge(

                charge_id=charge_id,

                line_id=line_id,

                report_type=report_type,

                charge_type=charge_type,

                charge_subtype=charge_subtype,

                description=description,

                granularity=(
                    self.infer_granularity(
                        row
                    )
                ),

                unit_id=unit_id,

                org_id=(
                    self._clean_string(
                        row.get("org_id")
                    )
                    or ""
                ),

                sku=self._clean_string(
                    row.get("sku")
                ),

                fnsku=self._clean_string(
                    row.get("fnsku")
                ),

                asin=self._clean_string(
                    row.get("asin")
                ),

                shipment_id=shipment_id,

                order_id=order_id,

                quantity=quantity,

                currency=(
                    self._clean_string(
                        row.get("currency")
                    )
                    or "USD"
                ),

                amount_per_unit=(
                    amount_per_unit
                ),

                amount_total=amount_total,

                posted_date=(
                    self._clean_string(
                        row.get("posted_date")
                    )
                ),
            )

            charges.append(
                charge
            )

        return charges

    # ========================================================
    # REIMBURSEMENTS
    # ========================================================

    def get_reimbursements(
        self,
        org_id: Optional[str] = None,
    ):

        if self._fee_df is None:
            return []

        if self._fee_df.empty:
            return []

        if "report_type" not in self._fee_df.columns:
            return []

        rows = self._fee_df[
            self._fee_df[
                "report_type"
            ]
            .fillna("")
            .str.lower()
            == "reimbursement_report"
        ]

        if org_id is not None:

            if "org_id" not in rows.columns:
                return []

            rows = rows[
                rows["org_id"].fillna("")
                == str(org_id)
            ]

        reimbursements = []

        for index, row in rows.iterrows():

            reimbursement_id = (
                self._clean_string(
                    row.get(
                        "reimbursement_id"
                    )
                )
                or self._clean_string(
                    row.get("line_id")
                )
                or f"REIMB-{index + 1}"
            )

            quantity_cash = self._float(
                row.get(
                    "quantity_reimbursed_cash"
                )
            )

            quantity_inventory = self._float(
                row.get(
                    "quantity_reimbursed_inventory"
                )
            )

            reimbursement = Reimbursement(

                reimbursement_id=(
                    reimbursement_id
                ),

                case_id=self._clean_string(
                    row.get("case_id")
                ),

                approval_date=(
                    self._clean_string(
                        row.get("approval_date")
                    )
                ),

                amazon_order_id=(
                    self._clean_string(
                        row.get(
                            "amazon_order_id"
                        )
                        or row.get("order_id")
                    )
                ),

                sku=self._clean_string(
                    row.get("sku")
                ),

                fnsku=self._clean_string(
                    row.get("fnsku")
                ),

                asin=self._clean_string(
                    row.get("asin")
                ),

                reason=(
                    self._clean_string(
                        row.get("reason")
                    )
                    or ""
                ),

                condition=self._clean_string(
                    row.get("condition")
                ),

                currency=(
                    self._clean_string(
                        row.get("currency")
                    )
                    or "USD"
                ),

                amount_per_unit=self._float(
                    row.get("amount_per_unit")
                ),

                amount_total=self._float(
                    row.get("amount_total")
                ),

                quantity_reimbursed_cash=(
                    quantity_cash
                ),

                quantity_reimbursed_inventory=(
                    quantity_inventory
                ),

                original_reimbursement_id=(
                    self._clean_string(
                        row.get(
                            "original_reimbursement_id"
                        )
                    )
                ),

                org_id=(
                    self._clean_string(
                        row.get("org_id")
                    )
                ),
            )

            reimbursements.append(
                reimbursement
            )

        return reimbursements

    # ========================================================
    # UPSTREAM RECORD
    # ========================================================

    def get_upstream_record(
        self,
        unit_id: str,
        org_id: str,
    ):

        results = {}

        for filename, df in self._upstream.items():

            if "unit_id" not in df.columns:
                continue

            filtered = df[
                df["unit_id"].fillna("")
                == str(unit_id)
            ]

            if "org_id" in df.columns:

                filtered = filtered[
                    filtered["org_id"].fillna("")
                    == str(org_id)
                ]

            results[
                filename
            ] = filtered.to_dict(
                orient="records"
            )

        return results

    # ========================================================
    # SUMMARY
    # ========================================================

    def summary(self):

        return {
            "fee_report": str(
                self.fee_report_path
            ),

            "organisations": (
                self.get_orgs()
            ),

            "upstream_files": (
                self.get_upstream_files()
            ),

            "charge_count": len(
                self.get_charges()
            ),

            "reimbursement_count": len(
                self.get_reimbursements()
            ),
        }