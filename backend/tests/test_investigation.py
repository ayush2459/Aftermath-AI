import unittest

from app.investigation import reconcile_snapshot


class GhostTrailReconciliationTests(unittest.TestCase):
    def test_detects_captured_payment_with_failed_shipment(self):
        findings = reconcile_snapshot({
            "order": {"status": "recovery_required"},
            "payment": {"status": "captured"},
            "shipment": {"status": "failed"},
            "order_items": [{"product_id": "p1"}],
            "inventory_reservations": [{"product_id": "p1", "status": "reserved"}],
        })
        codes = {finding["code"] for finding in findings}
        self.assertIn("payment_captured_shipment_failed", codes)
        self.assertIn("shipment_not_confirmed", codes)
        self.assertIn("order_requires_recovery", codes)
        self.assertNotIn("inventory_reservation_missing", codes)

    def test_missing_records_are_reported_as_unknown_evidence(self):
        findings = reconcile_snapshot({
            "order": {"status": "created"},
            "payment": None,
            "shipment": None,
            "order_items": [{"product_id": "p1"}],
            "inventory_reservations": [],
        })
        by_code = {finding["code"]: finding for finding in findings}
        self.assertIn("payment_record_missing", by_code)
        self.assertIn("shipment_record_missing", by_code)
        self.assertIn("inventory_reservation_missing", by_code)
        self.assertIn("does not prove", by_code["shipment_record_missing"]["message"])

    def test_released_reservation_is_a_conflict(self):
        findings = reconcile_snapshot({
            "order": {"status": "recovery_required"},
            "payment": {"status": "captured"},
            "shipment": {"status": "pending"},
            "order_items": [{"product_id": "p1"}],
            "inventory_reservations": [{"product_id": "p1", "status": "released"}],
        })
        self.assertIn(
            "inventory_reservation_not_active",
            {finding["code"] for finding in findings},
        )

    def test_healthy_restored_snapshot_has_no_findings(self):
        findings = reconcile_snapshot({
            "order": {"status": "restored"},
            "payment": {"status": "captured"},
            "shipment": {"status": "shipped"},
            "order_items": [{"product_id": "p1"}],
            "inventory_reservations": [{"product_id": "p1", "status": "consumed"}],
        })
        self.assertEqual(findings, [])


if __name__ == "__main__":
    unittest.main()
