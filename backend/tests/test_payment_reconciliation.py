import unittest
from pathlib import Path


class PaymentReconciliationSourceTests(unittest.TestCase):
    """Regression guards for captured payments when inventory is insufficient."""

    @classmethod
    def setUpClass(cls):
        cls.source = Path(__file__).resolve().parents[1].joinpath(
            "app", "payments.py"
        ).read_text()

    def test_shortfall_commits_captured_payment_and_manual_incident(self):
        start = self.source.index("inventory_shortfall = [")
        end = self.source.index("                reconciliation_required = True", start)
        branch = self.source[start:end]
        self.assertIn("SET status='captured'", branch)
        self.assertIn("SET status='needs_human'", branch)
        self.assertIn("INSERT INTO incidents", branch)
        self.assertIn("INSERT INTO events", branch)
        self.assertIn("INSERT INTO audit_log", branch)

    def test_normal_fulfilment_is_guarded_from_shortfall(self):
        start = self.source.index("            if not reconciliation_required:")
        end = self.source.index("    except HTTPException:", start)
        normal_path = self.source[start:end]
        self.assertIn("INSERT INTO inventory_reservations", normal_path)
        self.assertIn("INSERT INTO shipments", normal_path)
        self.assertIn('"fulfillment_status": "blocked"', self.source)

    def test_reconciliation_response_is_explicit(self):
        self.assertIn('"reconciliation_required": True', self.source)
        self.assertIn('Payment was captured, but inventory was unavailable.', self.source)


if __name__ == "__main__":
    unittest.main()
