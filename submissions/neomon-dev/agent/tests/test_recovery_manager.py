import importlib.util
import unittest
from pathlib import Path

MODULE_PATH = Path(__file__).resolve().parents[1] / "recovery_manager.py"
spec = importlib.util.spec_from_file_location("recovery_manager", MODULE_PATH)
recovery_manager = importlib.util.module_from_spec(spec)
assert spec and spec.loader
spec.loader.exec_module(recovery_manager)


class RecoveryManagerTests(unittest.TestCase):
    def test_refund_with_return_contradicts_charge(self):
        line = {"charge_type": "refund_issued_item_not_returned", "unit_id": "U1", "order_id": "O1"}
        decision = recovery_manager.evaluate_line(
            line,
            receiving_by_unit={},
            prep_by_unit={},
            pack_by_order={},
            returns_by_order={"O1": [{"record_id": "RTN-1"}]},
        )
        self.assertEqual(decision.status, "CONTRADICTS_CHARGE")
        self.assertTrue(decision.can_claim)

    def test_refund_without_return_supports_charge(self):
        line = {"charge_type": "refund_issued_item_not_returned", "unit_id": "U1", "order_id": "O2"}
        decision = recovery_manager.evaluate_line(
            line,
            receiving_by_unit={},
            prep_by_unit={},
            pack_by_order={"O2": [{"record_id": "PCK-2"}]},
            returns_by_order={},
        )
        self.assertEqual(decision.status, "SUPPORTS_CHARGE")
        self.assertFalse(decision.can_claim)

    def test_inbound_defect_fee_pass_contradicts_charge(self):
        line = {"charge_type": "inbound_defect_fee", "unit_id": "U3", "order_id": "O3"}
        prep = {
            "record_id": "PRP-3",
            "polybag_present_sealed": "yes",
            "suffocation_warning": "not_required",
            "fnsku_label_placement": "flat",
            "original_barcode_covered": "yes",
            "expiry_date": "not_required",
            "handling_marks": "all_present",
        }
        decision = recovery_manager.evaluate_line(
            line,
            receiving_by_unit={},
            prep_by_unit={"U3": [prep]},
            pack_by_order={},
            returns_by_order={},
        )
        self.assertEqual(decision.status, "CONTRADICTS_CHARGE")
        self.assertTrue(decision.can_claim)


if __name__ == "__main__":
    unittest.main()
