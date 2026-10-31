import os
import unittest
from uuid import UUID

from fastapi import HTTPException

os.environ["DATABASE_URL"] = "sqlite://"

from app.shipments import CompleteSampleRecoveryIn, complete_sample_recovery


ORDER_ID = UUID("0fe82451-0761-4f54-88a9-f94e7feb9147")


class FakeResult:
    def __init__(self, value):
        self.value = value

    def mappings(self):
        return self

    def first(self):
        return self.value

    def scalar_one(self):
        return self.value


class FakeSession:
    def __init__(self, row, existing_event=None):
        self.row = row
        self.existing_event = existing_event
        self.statements = []
        self.committed = False
        self.rolled_back = False

    def execute(self, statement, params):
        sql = str(statement)
        self.statements.append(sql)
        if "SELECT o.customer_session" in sql:
            return FakeResult(self.row)
        if "SELECT event_id FROM events" in sql:
            return FakeResult(self.existing_event)
        return FakeResult(None)

    def commit(self):
        self.committed = True

    def rollback(self):
        self.rolled_back = True


class SampleRecoveryTests(unittest.TestCase):
    def setUp(self):
        self.row = {
            "customer_session": "session-123",
            "incident_id": UUID("35c3ad3d-9012-4f6d-9217-ae507cc3937c"),
            "payment_status": "captured",
            "shipment_status": "failed",
            "last_error": "Seeded demo failure: carrier allocation timeout",
        }
        self.payload = CompleteSampleRecoveryIn(
            order_id=ORDER_ID, customer_session="session-123"
        )

    def test_only_sample_event_is_recorded(self):
        db = FakeSession(self.row)
        result = complete_sample_recovery(self.payload, db)
        self.assertEqual(result["demo_recovery_status"], "completed")
        self.assertTrue(db.committed)
        self.assertTrue(any("INSERT INTO events" in sql for sql in db.statements))
        self.assertFalse(any("UPDATE shipments" in sql or "UPDATE incidents" in sql for sql in db.statements))

    def test_other_customer_cannot_complete_sample(self):
        db = FakeSession(self.row)
        payload = CompleteSampleRecoveryIn(order_id=ORDER_ID, customer_session="other")
        with self.assertRaises(HTTPException) as error:
            complete_sample_recovery(payload, db)
        self.assertEqual(error.exception.status_code, 404)
        self.assertFalse(db.committed)

    def test_real_failure_is_not_eligible(self):
        db = FakeSession({**self.row, "last_error": "Carrier allocation timeout"})
        with self.assertRaises(HTTPException) as error:
            complete_sample_recovery(self.payload, db)
        self.assertEqual(error.exception.status_code, 409)
        self.assertFalse(db.committed)

    def test_unverified_payment_is_not_eligible(self):
        db = FakeSession({**self.row, "payment_status": "pending"})
        with self.assertRaises(HTTPException) as error:
            complete_sample_recovery(self.payload, db)
        self.assertEqual(error.exception.status_code, 409)
        self.assertFalse(db.committed)

    def test_repeated_recovery_does_not_add_another_event(self):
        db = FakeSession(self.row, existing_event=(UUID("35c3ad3d-9012-4f6d-9217-ae507cc3937c"),))
        result = complete_sample_recovery(self.payload, db)
        self.assertEqual(result["demo_recovery_status"], "completed")
        self.assertTrue(db.committed)
        self.assertFalse(any("INSERT INTO events" in sql for sql in db.statements))


if __name__ == "__main__":
    unittest.main()
