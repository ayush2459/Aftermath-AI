import unittest

from app.recovery import build_recovery_plan


class RecoveryPlanTests(unittest.TestCase):
    def test_failed_shipment_requires_human_review(self):
        plan = build_recovery_plan(
            {"payment": {"status": "captured"}, "shipment": {"status": "failed"}},
            [{"code": "payment_captured_shipment_failed", "severity": "high", "message": "Mismatch"}],
        )
        self.assertEqual(plan["strategy"], "operator_review")
        self.assertTrue(plan["actions"][0]["approval_required"])
        self.assertFalse(plan["execution_enabled"])

    def test_clean_snapshot_proposes_read_only_monitoring(self):
        plan = build_recovery_plan(
            {"payment": {"status": "captured"}, "shipment": {"status": "shipped"}},
            [],
        )
        self.assertEqual(plan["strategy"], "read_only")
        self.assertFalse(plan["actions"][0]["approval_required"])
        self.assertFalse(plan["execution_enabled"])


class RecoveryExecutionUnitTests(unittest.TestCase):
    def test_recovery_plan_is_not_executable_before_approval(self):
        plan = build_recovery_plan(
            {"payment": {"status": "captured"}, "shipment": {"status": "failed"}},
            [{"code": "payment_captured_shipment_failed", "severity": "high", "message": "Mismatch"}],
        )
        self.assertFalse(plan["execution_enabled"])
        self.assertTrue(plan["actions"][0]["approval_required"])


if __name__ == "__main__":
    unittest.main()
