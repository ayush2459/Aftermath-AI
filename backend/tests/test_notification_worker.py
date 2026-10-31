from pathlib import Path
import unittest


class NotificationWorkerTests(unittest.TestCase):
    def test_worker_uses_bounded_retries_and_stale_claim_recovery(self):
        source = Path(__file__).resolve().parents[1].joinpath(
            "app", "notification_worker.py"
        ).read_text()
        self.assertIn("attempts < 5", source)
        self.assertIn("make_interval(", source)
        self.assertIn("secs => LEAST(900", source)
        self.assertIn("INTERVAL '5 minutes'", source)
        self.assertIn("LIMIT :batch_size", source)

    def test_shipment_sample_recovery_dispatches_a_distinct_event(self):
        source = Path(__file__).resolve().parents[1].joinpath(
            "app", "shipments.py"
        ).read_text()
        self.assertIn("notification_key=f\"shipment.sample_recovery:{payload.order_id}\"", source)


if __name__ == "__main__":
    unittest.main()
